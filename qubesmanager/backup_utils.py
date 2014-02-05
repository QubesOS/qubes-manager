#!/usr/bin/python2
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
import re
import sys
import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import subprocess
import time
from qubes.qubes import QubesException

from thread_monitor import *

from datetime import datetime
from string import replace

path_re = re.compile(r"[a-zA-Z0-9/:.,_+=() -]*")
path_max_len = 512
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
        QMessageBox.warning (None, "Error mounting selected device!", "<b>Could not mount {0}.</b><br><br>ERROR: {1}".format(dev_path, ex))
        return None
    if res == 0:
        dev_mount_path = "/media/"+mount_dir_name
        return dev_mount_path
    return None

def umount_device(dev_mount_path):
    while True:
        try:
            pumount_cmd = ["sudo", "pumount", "--luks-force", dev_mount_path]
            res = subprocess.check_call(pumount_cmd)
            if res == 0:
                dev_mount_path = None
                return dev_mount_path
        except Exception as ex:
            title = "Error unmounting backup device!"
            text =  "<b>Could not unmount {0}.</b><br>\
                    <b>Please retry or unmount it manually using</b><br> pumount {0}.<br><br>\
                    ERROR: {1}".format(dev_mount_path, ex)
            button = QMessageBox.warning (None, title, text, QMessageBox.Ok | QMessageBox.Retry, QMessageBox.Retry)
            if button == QMessageBox.Ok:
                return dev_mount_path

def detach_device(dialog, dev_name):
    """ Detach device from dom0, if device was attached from some VM"""
    if not dev_name.startswith(dialog.vm.name+":"):
        with dialog.blk_manager.blk_lock:
            dialog.blk_manager.detach_device(dialog.vm, dev_name)
            dialog.blk_manager.update()
    else:
        # umount/LUKS remove do not trigger udev event on underlying device,
        # so trigger it manually - to publish back as available device
        subprocess.call(["sudo", "udevadm", "trigger", "--action=change",
                                 "--subsystem-match=block",
                                 "--sysname-match=%s" % dev_name.split(":")[1]])
        with dialog.blk_manager.blk_lock:
            dialog.blk_manager.update()


def fill_appvms_list(dialog):
    dialog.appvm_combobox.clear()
    dialog.appvm_combobox.addItem("dom0")

    dialog.appvm_combobox.setCurrentIndex(0) #current selected is null ""

    for vm in dialog.qvm_collection.values():
        if vm.is_appvm() and vm.internal:
            continue
        if vm.is_template() and vm.installed_by_rpm:
            continue

        if vm.is_running() and vm.qid != 0:
            dialog.appvm_combobox.addItem(vm.name)

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

def update_device_appvm_enabled(dialog, idx):
    # Only one of those can be used
    dialog.dev_combobox.setEnabled(dialog.appvm_combobox.currentIndex() == 0)
    dialog.appvm_combobox.setEnabled(dialog.dev_combobox.currentIndex() == 0)

def dev_combobox_activated(dialog, idx):
    if idx == dialog.prev_dev_idx:    #nothing has changed
        return
    #there was a change

    dialog.dir_line_edit.setText("")

    # umount old device if any
    if dialog.dev_mount_path != None:
        dialog.dev_mount_path = umount_device(dialog.dev_mount_path)
        if dialog.dev_mount_path != None:
            dialog.dev_combobox.setCurrentIndex(dialog.prev_dev_idx)
            return
        else:
            detach_device(dialog,
                str(dialog.dev_combobox.itemData(dialog.prev_dev_idx).toString()))

    # then attach new one
    if dialog.dev_combobox.currentIndex() != 0:   #An existing device chosen
        dev_name = str(dialog.dev_combobox.itemData(idx).toString())

        if dev_name.startswith(dialog.vm.name+":"):
            # originally attached to dom0
            dev_path = "/dev/"+dev_name.split(":")[1]
        else:
            try:
                with dialog.blk_manager.blk_lock:
                    if dev_name in dialog.blk_manager.free_devs:
                        #attach it to dom0, then treat it as an attached device
                        dialog.blk_manager.attach_device(dialog.vm, dev_name)
                        dialog.blk_manager.update()

                    if dev_name in dialog.blk_manager.attached_devs:       #is attached to dom0
                        assert dialog.blk_manager.attached_devs[dev_name]['attached_to']['vm'] == dialog.vm.name
                        dev_path = "/dev/" + dialog.blk_manager.attached_devs[dev_name]['attached_to']['frontend']
                    else:
                        raise QubesException("device not attached?!")
            except QubesException as ex:
                QMessageBox.warning (None, "Error attaching selected device!",
                        "<b>Could not attach {0}.</b><br><br>ERROR: {1}".format(dev_name, ex))
                dialog.dev_combobox.setCurrentIndex(0) #if couldn't mount - set current device to "None"
                dialog.prev_dev_idx = 0
                return

        #check if device mounted
        dialog.dev_mount_path = check_if_mounted(dev_path)
        if dialog.dev_mount_path == None:
            dialog.dev_mount_path = mount_device(dev_path)
            if dialog.dev_mount_path == None:
                dialog.dev_combobox.setCurrentIndex(0) #if couldn't mount - set current device to "None"
                dialog.prev_dev_idx = 0
                detach_device(dialog,
                        str(dialog.dev_combobox.itemData(idx).toString()))
                return

    dialog.prev_dev_idx = idx

    if hasattr(dialog, 'selected_vms'):
        # backup window
        if dialog.dev_mount_path != None:
            # Initialize path with root of mounted device
            dialog.dir_line_edit.setText(dialog.dev_mount_path)
            dialog.select_dir_page.emit(SIGNAL("completeChanged()"))


def get_path_for_vm(vm, service_name):
    if not vm:
        return None
    proc = vm.run("QUBESRPC %s dom0" % service_name, passio_popen=True)
    proc.stdin.close()
    untrusted_path = proc.stdout.readline(path_max_len)
    if len(untrusted_path) == 0:
        return None
    if path_re.match(untrusted_path):
        return untrusted_path
    else:
        return None

def select_path_button_clicked(dialog, select_file = False):
    backup_location = str(dialog.dir_line_edit.text())
    file_dialog = QFileDialog()
    file_dialog.setReadOnly(True)

    if select_file:
        file_dialog_function = file_dialog.getOpenFileName
    else:
        file_dialog_function = file_dialog.getExistingDirectory

    new_appvm = None
    new_path = None
    if dialog.appvm_combobox.currentIndex() != 0:   #An existing appvm chosen
        new_appvm = str(dialog.appvm_combobox.currentText())
        vm = dialog.qvm_collection.get_vm_by_name(new_appvm)
        if vm:
            new_path = get_path_for_vm(vm, "qubes.SelectFile" if select_file
                    else "qubes.SelectDirectory")
    elif dialog.dev_mount_path != None:
        new_path = file_dialog_function(dialog, "Select backup location.", dialog.dev_mount_path)
    else:
        new_path = file_dialog_function(dialog, "Select backup location.",
                                        backup_location if backup_location
                                        else '/')

    if new_path != None:
        new_path = str(new_path)
        if os.path.basename(new_path) == 'qubes.xml':
            backup_location = os.path.dirname(new_path)
        else:
            backup_location = new_path
        dialog.dir_line_edit.setText(backup_location)

    if (new_path or new_appvm) and len(backup_location) > 0:
        dialog.select_dir_page.emit(SIGNAL("completeChanged()"))

def simulate_long_lasting_proces(period, progress_callback):
    for i in range(period):
        progress_callback((i*100)/period)
        time.sleep(1)

    progress_callback(100)
    return 0

