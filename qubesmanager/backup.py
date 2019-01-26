#!/usr/bin/python2
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
import signal
import shutil
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesException
from qubes.qubes import QubesDaemonPidfile
from qubes.qubes import QubesHost
from qubes import backup
from qubes import qubesutils

import qubesmanager.resources_rc

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import time
from thread_monitor import *
from operator import itemgetter

from datetime import datetime
from string import replace

from ui_backupdlg import *
from multiselectwidget import *

from backup_utils import *
import main
import grp,pwd


class BackupVMsWindow(Ui_Backup, QWizard):

    __pyqtSignals__ = ("backup_progress(int)",)

    def __init__(self, app, qvm_collection, blk_manager, shutdown_vm_func, parent=None):
        super(BackupVMsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection
        self.blk_manager = blk_manager
        self.shutdown_vm_func = shutdown_vm_func

        self.func_output = []
        self.selected_vms = []
        self.tmpdir_to_remove = None
        self.canceled = False

        self.vm = self.qvm_collection[0]
        self.files_to_backup = None

        assert self.vm != None

        self.setupUi(self)

        self.progress_status.text = self.tr("Backup in progress...")
        self.show_running_vms_warning(False)
        self.dir_line_edit.setReadOnly(False)

        self.select_vms_widget = MultiSelectWidget(self)
        self.verticalLayout.insertWidget(1, self.select_vms_widget)

        self.connect(self, SIGNAL("currentIdChanged(int)"), self.current_page_changed)
        self.connect(self.select_vms_widget, SIGNAL("selected_changed()"), self.check_running)
        self.connect(self.select_vms_widget, SIGNAL("items_removed(PyQt_PyObject)"), self.vms_removed)
        self.connect(self.select_vms_widget, SIGNAL("items_added(PyQt_PyObject)"), self.vms_added)
        self.refresh_button.clicked.connect(self.check_running)
        self.shutdown_running_vms_button.clicked.connect(self.shutdown_all_running_selected)
        self.connect(self, SIGNAL("backup_progress(int)"), self.progress_bar.setValue)
        self.dir_line_edit.connect(self.dir_line_edit, SIGNAL("textChanged(QString)"), self.backup_location_changed)

        self.select_vms_page.isComplete = self.has_selected_vms
        self.select_dir_page.isComplete = self.has_selected_dir_and_pass
        #FIXME
        #this causes to run isComplete() twice, I don't know why
        self.select_vms_page.connect(
                self.select_vms_widget,
                SIGNAL("selected_changed()"),
                SIGNAL("completeChanged()"))
        self.passphrase_line_edit.connect(
                self.passphrase_line_edit,
                SIGNAL("textChanged(QString)"),
                self.backup_location_changed)
        self.passphrase_line_edit_verify.connect(
                self.passphrase_line_edit_verify,
                SIGNAL("textChanged(QString)"),
                self.backup_location_changed)

        self.total_size = 0
        self.__fill_vms_list__()

        fill_appvms_list(self)
        self.load_settings()

    def load_settings(self):
        dest_vm_name = main.manager_window.manager_settings.value(
            'backup/vmname', defaultValue="")
        dest_vm_idx = self.appvm_combobox.findText(dest_vm_name.toString())
        if dest_vm_idx > -1:
            self.appvm_combobox.setCurrentIndex(dest_vm_idx)

        if main.manager_window.manager_settings.contains('backup/path'):
            dest_path = main.manager_window.manager_settings.value(
                'backup/path', defaultValue=None)
            self.dir_line_edit.setText(dest_path.toString())

        if main.manager_window.manager_settings.contains('backup/encrypt'):
            encrypt = main.manager_window.manager_settings.value(
                'backup/encrypt', defaultValue=None)
            self.encryption_checkbox.setChecked(encrypt.toBool())

    def save_settings(self):
        main.manager_window.manager_settings.setValue(
            'backup/vmname', self.appvm_combobox.currentText())
        main.manager_window.manager_settings.setValue(
            'backup/path', self.dir_line_edit.text())
        main.manager_window.manager_settings.setValue(
            'backup/encrypt', self.encryption_checkbox.isChecked())

    def show_running_vms_warning(self, show):
        self.running_vms_warning.setVisible(show)
        self.shutdown_running_vms_button.setVisible(show)
        self.refresh_button.setVisible(show)

    class VmListItem(QListWidgetItem):
        def __init__(self, vm):
            self.vm = vm
            if vm.qid == 0:
                local_user = grp.getgrnam('qubes').gr_mem[0]
                home_dir = pwd.getpwnam(local_user).pw_dir
                self.size = qubesutils.get_disk_usage(home_dir)
            else:
                self.size = self.get_vm_size(vm)
            super(BackupVMsWindow.VmListItem, self).__init__(vm.name+ " (" + qubesutils.size_to_human(self.size) + ")")

        def get_vm_size(self, vm):
            size = 0
            if vm.private_img is not None:
                size += qubesutils.get_disk_usage (vm.private_img)

            if vm.updateable:
                size += qubesutils.get_disk_usage(vm.root_img)

            return size


    def __fill_vms_list__(self):
        for vm in self.qvm_collection.values():
            if vm.internal:
                continue

            item = BackupVMsWindow.VmListItem(vm)
            if vm.include_in_backups == True:
                self.select_vms_widget.selected_list.addItem(item)
                self.total_size += item.size
            else:
                self.select_vms_widget.available_list.addItem(item)
        self.select_vms_widget.available_list.sortItems()
        self.select_vms_widget.selected_list.sortItems()
        self.check_running()
        self.total_size_label.setText(qubesutils.size_to_human(self.total_size))

    def vms_added(self, items):
        for i in items:
            self.total_size += i.size
        self.total_size_label.setText(qubesutils.size_to_human(self.total_size))

    def vms_removed(self, items):
        for i in items:
            self.total_size -= i.size
        self.total_size_label.setText(qubesutils.size_to_human(self.total_size))

    def check_running(self):
        some_selected_vms_running = False
        for i in range(self.select_vms_widget.selected_list.count()):
            item = self.select_vms_widget.selected_list.item(i)
            if item.vm.is_running() and item.vm.qid != 0:
                item.setForeground(QBrush(QColor(255, 0, 0)))
                some_selected_vms_running = True
            else:
                item.setForeground(QBrush(QColor(0, 0, 0)))

        self.show_running_vms_warning(some_selected_vms_running)

        for i in range(self.select_vms_widget.available_list.count()):
            item =  self.select_vms_widget.available_list.item(i)
            if item.vm.is_running() and item.vm.qid != 0:
                item.setForeground(QBrush(QColor(255, 0, 0)))
            else:
                item.setForeground(QBrush(QColor(0, 0, 0)))

        return some_selected_vms_running

    def shutdown_all_running_selected(self):
        (names, vms) = self.get_running_vms()
        if len(vms) == 0:
            return

        for vm in vms:
            self.blk_manager.check_if_serves_as_backend(vm)

        reply = QMessageBox.question(None, self.tr("VM Shutdown Confirmation"),
             unicode(self.tr(
                 "Are you sure you want to power down the following VMs: "
                 "<b>{0}</b>?<br/>"
                 "<small>This will shutdown all the running applications "
                 "within them.</small>")).format(', '.join(names)),
             QMessageBox.Yes | QMessageBox.Cancel)

        self.app.processEvents()

        if reply == QMessageBox.Yes:

            wait_time = 60.0
            for vm in vms:
                self.shutdown_vm_func(vm, wait_time*1000)

            progress = QProgressDialog ("Shutting down VMs <b>{0}</b>...".format(', '.join(names)), "", 0, 0)
            progress.setModal(True)
            progress.show()

            wait_for = wait_time
            while self.check_running() and wait_for > 0:
                self.app.processEvents()
                time.sleep (0.5)
                wait_for -= 0.5

            progress.hide()

    def get_running_vms(self):
        names = []
        vms = []
        for i in range(self.select_vms_widget.selected_list.count()):
            item = self.select_vms_widget.selected_list.item(i)
            if item.vm.is_running() and item.vm.qid != 0:
                names.append(item.vm.name)
                vms.append(item.vm)
        return (names, vms)

    @pyqtSlot(name='on_select_path_button_clicked')
    def select_path_button_clicked(self):
        select_path_button_clicked(self)

    def validateCurrentPage(self):
        if self.currentPage() is self.select_vms_page:
            if self.check_running():
                QMessageBox.information(None,
                    self.tr("Wait!"),
                    self.tr("Some selected VMs are running. "
                        "Running VMs can not be backuped. "
                        "Please shut them down or remove them from the list."))
                return False

            self.selected_vms = []
            for i in range(self.select_vms_widget.selected_list.count()):
                self.selected_vms.append(self.select_vms_widget.selected_list.item(i).vm)

        elif self.currentPage() is self.select_dir_page:
            backup_location = unicode(self.dir_line_edit.text())
            if not backup_location:
                QMessageBox.information(None, self.tr("Wait!"),
                    self.tr("Enter backup target location first."))
                return False
            if self.appvm_combobox.currentIndex() == 0 and \
                   not os.path.isdir(backup_location):
                QMessageBox.information(None, self.tr("Wait!"),
                    unicode(self.tr("Selected directory do not exists or "
                            "not a directory (%s).")) % backup_location)
                return False
            if not len(self.passphrase_line_edit.text()):
                QMessageBox.information(None, self.tr("Wait!"),
                    self.tr("Enter passphrase for backup encryption/verification first."))
                return False
            if self.passphrase_line_edit.text() != self.passphrase_line_edit_verify.text():
                QMessageBox.information(None,
                    self.tr("Wait!"),
                    self.tr("Enter the same passphrase in both fields."))
                return False

        return True

    def gather_output(self, s):
        self.func_output.append(s)

    def update_progress_bar(self, value):
        self.emit(SIGNAL("backup_progress(int)"), value)

    def __do_backup__(self, thread_monitor):
        msg = []

        try:
            backup.backup_do(unicode(self.dir_line_edit.text()),
                    self.files_to_backup,
                    unicode(self.passphrase_line_edit.text()),
                    progress_callback=self.update_progress_bar,
                    encrypted=self.encryption_checkbox.isChecked(),
                    appvm=self.target_appvm)
            #simulate_long_lasting_proces(10, self.update_progress_bar)
        except backup.BackupCanceledError as ex:
            msg.append(str(ex))
            self.canceled = True
            if ex.tmpdir:
                self.tmpdir_to_remove = ex.tmpdir
        except Exception as ex:
            print "Exception:", ex
            msg.append(str(ex))

        if len(msg) > 0 :
            thread_monitor.set_error_msg('\n'.join(msg))

        thread_monitor.set_finished()


    def current_page_changed(self, id):
        old_sigchld_handler = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        if self.currentPage() is self.confirm_page:

            self.target_appvm = None
            if self.appvm_combobox.currentIndex() != 0:   #An existing appvm chosen
                self.target_appvm = self.qvm_collection.get_vm_by_name(
                        self.appvm_combobox.currentText())

            del self.func_output[:]
            try:
                self.files_to_backup = backup.backup_prepare(
                        self.selected_vms,
                        print_callback = self.gather_output,
                        hide_vm_names=self.encryption_checkbox.isChecked())
            except Exception as ex:
                print "Exception:", ex
                QMessageBox.critical(None,
                    self.tr("Error while preparing backup."),
                    unicode(self.tr("ERROR: {0}")).format(ex))

            self.textEdit.setReadOnly(True)
            self.textEdit.setFontFamily("Monospace")
            self.textEdit.setText("\n".join(self.func_output))
            self.save_settings()

        elif self.currentPage() is self.commit_page:
            self.button(self.FinishButton).setDisabled(True)
            self.showFileDialog.setEnabled(
                self.appvm_combobox.currentIndex() != 0)
            self.showFileDialog.setChecked(self.showFileDialog.isEnabled()
                                           and unicode(self.dir_line_edit.text())
                                           .count("media/") > 0)
            self.thread_monitor = ThreadMonitor()
            thread = threading.Thread (target= self.__do_backup__ , args=(self.thread_monitor,))
            thread.daemon = True
            thread.start()

            counter = 0
            while not self.thread_monitor.is_finished():
                self.app.processEvents()
                time.sleep (0.1)

            if not self.thread_monitor.success:
                if self.canceled:
                    self.progress_status.setText(self.tr("Backup aborted."))
                    if self.tmpdir_to_remove:
                        if QMessageBox.warning(None, self.tr("Backup aborted"),
                                unicode(self.tr("Do you want to remove temporary files from "
                                        "%s?")) % self.tmpdir_to_remove,
                                QMessageBox.Yes, QMessageBox.No) == QMessageBox.Yes:
                            shutil.rmtree(self.tmpdir_to_remove)
                else:
                    self.progress_status.setText(self.tr("Backup error."))
                    QMessageBox.warning(self, self.tr("Backup error!"),
                        unicode(self.tr("ERROR: {}")).format(
                        self.thread_monitor.error_msg))
            else:
                self.progress_bar.setValue(100)
                self.progress_status.setText(self.tr("Backup finished."))
            if self.showFileDialog.isChecked():
                orig_text = self.progress_status.text
                self.progress_status.setText(
                    orig_text + self.tr(
                        " Please unmount your backup volume and cancel "
                        "the file selection dialog."))
                if self.target_appvm:
                    self.target_appvm.run("QUBESRPC %s dom0" % "qubes"
                                                               ".SelectDirectory")
            self.button(self.CancelButton).setEnabled(False)
            self.button(self.FinishButton).setEnabled(True)
            self.showFileDialog.setEnabled(False)
        signal.signal(signal.SIGCHLD, old_sigchld_handler)

    def reject(self):
        #cancell clicked while the backup is in progress.
        #calling kill on tar.
        if self.currentPage() is self.commit_page:
            if backup.backup_cancel():
                self.button(self.CancelButton).setDisabled(True)
        else:
            self.done(0)

    def has_selected_vms(self):
        return self.select_vms_widget.selected_list.count() > 0

    def has_selected_dir_and_pass(self):
        if not len(self.passphrase_line_edit.text()):
            return False
        if self.passphrase_line_edit.text() != self.passphrase_line_edit_verify.text():
            return False
        return len(self.dir_line_edit.text()) > 0

    def backup_location_changed(self, new_dir = None):
        self.select_dir_page.emit(SIGNAL("completeChanged()"))


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception(exc_type, exc_value, exc_traceback ):
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


def app_main():

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
    app_main()
