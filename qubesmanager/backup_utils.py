#!/usr/bin/python2.6
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#

import sys
import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time

from thread_monitor import *

from datetime import datetime
from string import replace

mount_for_backup_path = '/usr/libexec/qubes-manager/mount_for_backup.sh'

def check_if_mounted(dev_path):
    mounts_file = open("/proc/mounts")
    for m in list(mounts_file):
        if m.startswith(dev_path):
            return m.split(" ")[1]
    return None


def mount_device(dev_path):
    try:
        mount_dir_name = "backup" + replace(str(datetime.now()),' ', '-').split(".")[0]
        pmount_cmd = [mount_for_backup_path, dev_path, mount_dir_name]
        res = subprocess.check_call(pmount_cmd)
    except Exception as ex:
        QMessageBox.warning (None, "Error mounting selected device!", "ERROR: {0}".format(ex))
        return None
    if res == 0:
        dev_mount_path = "/media/"+mount_dir_name
        return dev_mount_path
    return None

def umount_device(dev_mount_path):
    try:
        pumount_cmd = ["pumount", dev_mount_path]
        res = subprocess.check_call(pumount_cmd)
        if res == 0:
            dev_mount_path = None
    except Exception as ex:
        QMessageBox.warning (None, "Could not unmount backup device!", "ERROR: {0}".format(ex))
    return dev_mount_path


def fill_devs_list(dialog):
    dialog.dev_combobox.clear()
    dialog.dev_combobox.addItem("None")
    
    dialog.blk_manager.blk_lock.acquire()
    for a in dialog.blk_manager.attached_devs:
        if dialog.blk_manager.attached_devs[a]['attached_to']['vm'] == dialog.vm.name :
            att = a + " " + unicode(dialog.blk_manager.attached_devs[a]['size']) + " " + dialog.blk_manager.attached_devs[a]['desc']
            dialog.dev_combobox.addItem(att, QVariant(a))
    for a in dialog.blk_manager.free_devs:
        att = a + " " + unicode(dialog.blk_manager.free_devs[a]['size']) + " " + dialog.blk_manager.free_devs[a]['desc']
        dialog.dev_combobox.addItem(att, QVariant(a))
    dialog.blk_manager.blk_lock.release()

    dialog.dev_combobox.setCurrentIndex(0) #current selected is null ""
    dialog.prev_dev_idx = 0
    dialog.dir_line_edit.clear()
    enable_dir_line_edit(dialog, True)


def enable_dir_line_edit(dialog, boolean):
    dialog.dir_line_edit.setEnabled(boolean)
    dialog.select_path_button.setEnabled(boolean)      


def dev_combobox_activated(dialog, idx):
    if idx == dialog.prev_dev_idx:    #nothing has changed
        return
    #there was a change

    dialog.dir_line_edit.setText("")
    dialog.backup_dir = None

    if dialog.dev_mount_path != None:
        dialog.dev_mount_path = umount_device(dialog.dev_mount_path)
        if dialog.dev_mount_path != None:
            dialog.dev_combobox.setCurrentIndex(dialog.prev_dev_idx)
            return

    if dialog.dev_combobox.currentText() != "None":   #An existing device chosen 
        dev_name = str(dialog.dev_combobox.itemData(idx).toString())

        dialog.blk_manager.blk_lock.acquire()
        if dev_name in dialog.blk_manager.free_devs:
            if dev_name.startswith(dialog.vm.name):       # originally attached to dom0
                dev_path = "/dev/"+dev_name.split(":")[1]

            else:       # originally attached to another domain, eg. usbvm
                #attach it to dom0, then treat it as an attached device
                dialog.blk_manager.attach_device(dialog.vm, dev_name)

        if dev_name in dialog.blk_manager.attached_devs:       #is attached to dom0
            assert dialog.blk_manager.attached_devs[dev_name]['attached_to']['vm'] == dialog.vm.name
            dev_path = "/dev/" + dialog.blk_manager.attached_devs[dev_name]['attached_to']['frontend']
        dialog.blk_manager.blk_lock.release()

        #check if device mounted
        dialog.dev_mount_path = check_if_mounted(dev_path)
        if dialog.dev_mount_path == None:
            dialog.dev_mount_path = mount_device(dev_path)
            if dialog.dev_mount_path == None:
                dialog.dev_combobox.setCurrentIndex(0) #if couldn't mount - set current device to "None"
                dialog.prev_dev_idx = 0
                return
                
    dialog.prev_dev_idx = idx
    dialog.select_dir_page.emit(SIGNAL("completeChanged()"))

                   
def select_path_button_clicked(dialog):
    dialog.backup_dir = dialog.dir_line_edit.text()
    file_dialog = QFileDialog()
    file_dialog.setReadOnly(True)

    if dialog.dev_mount_path != None:
        new_path = file_dialog.getExistingDirectory(dialog, "Select backup directory.", dialog.dev_mount_path)
    else:
        new_path = file_dialog.getExistingDirectory(dialog, "Select backup directory.", "~")
        
    if new_path:
        dialog.dir_line_edit.setText(new_path)
        dialog.backup_dir = new_path
        dialog.select_dir_page.emit(SIGNAL("completeChanged()"))



def simulate_long_lasting_proces(period, progress_callback):
    for i in range(period):
        progress_callback((i*100)/period)
        time.sleep(1)

    progress_callback(100)
    return 0

