#!/usr/bin/python2.6
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski <marmarek@mimuw.edu.pl>
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

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesException
from qubes.qubes import QubesDaemonPidfile
from qubes.qubes import QubesHost
from qubes import qubesutils

import qubesmanager.resources_rc

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time
from thread_monitor import *
from operator import itemgetter

from datetime import datetime
from string import replace

from ui_backupdlg import *
from multiselectwidget import *



class BackupVMsWindow(Ui_Backup, QWizard):

    __pyqtSignals__ = ("backup_progress(int)",)

    excluded = []
    to_backup = []

    def __init__(self, app, qvm_collection, blk_manager, parent=None):
        super(BackupVMsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection
        self.blk_manager = blk_manager

        self.backup_dir = None
        self.func_output = []

        for vm in self.qvm_collection.values():
            if vm.qid == 0:
                self.vm = vm
                break;
        
        assert self.vm != None

        self.setupUi(self)

        self.dir_line_edit.setReadOnly(True)

        self.select_vms_widget = MultiSelectWidget(self)
        self.verticalLayout.insertWidget(1, self.select_vms_widget)

        self.connect(self, SIGNAL("currentIdChanged(int)"), self.current_page_changed)
        self.connect(self.dev_combobox, SIGNAL("activated(int)"), self.dev_combobox_activated)
        self.connect(self, SIGNAL("backup_progress(int)"), self.progress_bar.setValue)

        self.select_vms_page.isComplete = self.has_selected_vms
        self.select_dir_page.isComplete = self.has_selected_dir
        #FIXME
        #this causes to run isComplete() twice, I don't know why
        self.select_vms_page.connect(self.select_vms_widget, SIGNAL("selected_changed()"), SIGNAL("completeChanged()")) 

        self.__fill_vms_list__()
        self.__fill_devs_list__()

    def __fill_vms_list__(self):
        for vm in self.qvm_collection.values():
            if vm.is_running() and vm.qid != 0:
                self.excluded.append(vm.name)
                continue
            
            if vm.is_appvm() and vm.internal:
                self.excluded.append(vm.name)
                continue

            if vm.is_template() and vm.installed_by_rpm:
                self.excluded.append(vm.name)
                continue

            self.to_backup.append(vm.name)
            self.select_vms_widget.available_list.addItem(vm.name)

    def __fill_devs_list__(self):
        self.dev_combobox.clear()
        self.dev_combobox.addItem("None")
        for a in self.blk_manager.attached_devs:
            if self.blk_manager.attached_devs[a]['attached_to']['vm'] == self.vm.name :
                att = a + " " + unicode(self.blk_manager.attached_devs[a]['size']) + " " + self.blk_manager.attached_devs[a]['desc']
                self.dev_combobox.addItem(att, QVariant(a))
        for a in self.blk_manager.free_devs:
            att = a + " " + unicode(self.blk_manager.free_devs[a]['size']) + " " + self.blk_manager.free_devs[a]['desc']
            self.dev_combobox.addItem(att, QVariant(a))
        self.dev_combobox.setCurrentIndex(0) #current selected is null ""
        self.prev_dev_idx = 0
        self.dir_line_edit.clear()
        self.dir_line_edit.setEnabled(False)
        self.select_path_button.setEnabled(False)

    def __check_if_mounted__(self, dev_path):
        mounts_file = open("/proc/mounts")
        for m in list(mounts_file):
            if m.startswith(dev_path):
                print m
                return m.split(" ")[1]
        return None

    def __mount_device__(self, dev_path):
        try:
            mount_dir_name = "backup" + replace(str(datetime.now()),' ', '-').split(".")[0]
            pmount_cmd = ["pmount", dev_path, mount_dir_name]
            res = subprocess.check_call(pmount_cmd)
            print "pmount device res: ", res
        except Exception as ex:
            QMessageBox.warning (None, "Error mounting selected device!", "ERROR: {0}".format(ex))
            return None
        if res == 0:
            self.dev_mount_path = "/media/"+mount_dir_name
            return self.dev_mount_path

    def __umount_device__(self, dev_mount_path):
        try:
            pumount_cmd = ["pumount", dev_mount_path]
            res = subprocess.check_call(pumount_cmd)
            print "pumount device res: ", res
        except Exception as ex:
            QMessageBox.warning (None, "Could not unmount backup device!", "ERROR: {0}".format(ex))



    def __enable_dir_line_edit__(self, boolean):
        self.dir_line_edit.setEnabled(boolean)
        self.select_path_button.setEnabled(boolean)      


    def dev_combobox_activated(self, idx):
        print self.dev_combobox.currentText()
        if idx == self.prev_dev_idx:    #nothing has changed
            return
        #there was a change
        self.prev_dev_idx = idx

        self.dir_line_edit.setText("")
        self.backup_dir = None
        self.dev_mount_path = None
        self.__enable_dir_line_edit__(False)

        if self.dev_combobox.currentText() != "None":   #An existing device chosen 
            dev_name = str(self.dev_combobox.itemData(idx).toString())

            if dev_name in self.blk_manager.free_devs:
                if dev_name.startswith(self.vm.name):       # originally attached to dom0
                    dev_path = "/dev/"+dev_name.split(":")[1]
                    print "device from dom0 - no need to attach"

                else:       # originally attached to another domain, eg. usbvm
                    print "device from " + dev_name.split(":")[0]
                    #attach it to dom0, then treat it as an attached device
                    self.blk_manager.attach_device(self.vm, dev_name)

            if dev_name in self.blk_manager.attached_devs:       #is attached to dom0
                print "device attached as " + self.blk_manager.attached_devs[dev_name]['attached_to']['frontend']
                assert self.blk_manager.attached_devs[dev_name]['attached_to']['vm'] == self.vm.name

                dev_path = "/dev/" + self.blk_manager.attached_devs[dev_name]['attached_to']['frontend']

            #check if device mounted
            self.dev_mount_path = self.__check_if_mounted__(dev_path)
            if self.dev_mount_path != None:
                self.__enable_dir_line_edit__(True)
            else:
                self.dev_mount_path = self.__mount_device__(dev_path)
                if self.dev_mount_path != None:
                    self.__enable_dir_line_edit__(True)

        self.select_dir_page.emit(SIGNAL("completeChanged()"))

                   

    @pyqtSlot(name='on_select_path_button_clicked')
    def select_path_button_clicked(self):
        self.backup_dir = self.dir_line_edit.text()
        file_dialog = QFileDialog()
        file_dialog.setReadOnly(True)
        new_path = file_dialog.getExistingDirectory(self, "Select backup directory.", self.dev_mount_path)
        if new_path:
            self.dir_line_edit.setText(new_path)
            self.backup_dir = new_path
            self.select_dir_page.emit(SIGNAL("completeChanged()"))

    def validateCurrentPage(self):
        if self.currentPage() is self.select_vms_page:
            for i in range(self.select_vms_widget.available_list.count()):
                vmname =  self.select_vms_widget.available_list.item(i).text()
                self.excluded.append(vmname)
        return True

    def gather_output(self, s):
        self.func_output.append(s)

    def update_progress_bar(self, value):
        print "progress bar value: ", value
        self.emit(SIGNAL("backup_progress(int)"), value)


    def __do_backup__(self, thread_monitor):
        print "doiing backup"
        msg = []
        try:
            qubesutils.backup_do(str(self.backup_dir), self.files_to_backup, self.update_progress_bar)
            #simulate_long_lasting_proces(10, self.update_progress_bar) 
        except Exception as ex:
            print "got exception from backup"
            msg.append(str(ex))

        if len(msg) > 0 :
            thread_monitor.set_error_msg('\n'.join(msg))

        thread_monitor.set_finished()

    
    def current_page_changed(self, id):
        if self.currentPage() is self.confirm_page:
            del self.func_output[:]
            self.files_to_backup = qubesutils.backup_prepare(str(self.backup_dir), exclude_list = self.excluded, print_callback = self.gather_output)
            for i in self.excluded:
                print i
            self.textEdit.setReadOnly(True)
            self.textEdit.setFontFamily("Monospace")
            self.textEdit.setText("\n".join(self.func_output))
            for i in self.func_output:
                print i

            for s in self.files_to_backup:
                print s

        elif self.currentPage() is self.commit_page:
            self.button(self.CancelButton).setDisabled(True)
            self.button(self.FinishButton).setDisabled(True)
            print "butons disabled"
            self.thread_monitor = ThreadMonitor()
            thread = threading.Thread (target= self.__do_backup__ , args=(self.thread_monitor,))
            thread.daemon = True
            print "will start thread"
            thread.start()

            while not self.thread_monitor.is_finished():
                self.app.processEvents()
                time.sleep (0.1)

            if not self.thread_monitor.success:
                QMessageBox.warning (None, "Backup error!", "ERROR: {1}".format(self.vm.name, self.thread_monitor.error_msg))

            self.__umount_device__(self.dev_mount_path)
            self.button(self.FinishButton).setEnabled(True)

 
    def has_selected_vms(self):
        print "isComplete called"
        return self.select_vms_widget.selected_list.count() > 0

    def has_selected_dir(self):
        return self.backup_dir != None
            

def simulate_long_lasting_proces(period, progress_callback):
    for i in range(period):
        progress_callback((i*100)/period)
        time.sleep(1)

    progress_callback(100)
    return 0


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception( exc_type, exc_value, exc_traceback ):
    import sys
    import os.path
    import traceback

    filename, line, dummy, dummy = traceback.extract_tb( exc_traceback ).pop()
    filename = os.path.basename( filename )
    error    = "%s: %s" % ( exc_type.__name__, exc_value )

    QMessageBox.critical(None, "Houston, we have a problem...",
                         "Whoops. A critical error has occured. This is most likely a bug "
                         "in Qubes Restore VMs application.<br><br>"
                         "<b><i>%s</i></b>" % error +
                         "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
                         % ( line, filename ))




def main():

    global qubes_host
    qubes_host = QubesHost()

    global app
    app = QApplication(sys.argv)
    app.setOrganizationName("The Qubes Project")
    app.setOrganizationDomain("http://qubes-os.org")
    app.setApplicationName("Qubes Backup VMs")

    sys.excepthook = handle_exception

    qvm_collection = QubesVmCollection()
    qvm_collection.lock_db_for_reading()
    qvm_collection.load()
    qvm_collection.unlock_db()

    global backup_window
    backup_window = BackupVMsWindow()

    backup_window.show()

    app.exec_()
    app.exit()



if __name__ == "__main__":
    main()
