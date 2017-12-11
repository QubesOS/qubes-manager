#!/usr/bin/python3
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
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
#
#

import traceback

import signal
import shutil

from qubesadmin import Qubes, exc
from qubesadmin import utils as admin_utils
from qubes.storage.file import get_disk_usage

from PyQt4 import QtCore  # pylint: disable=import-error
from PyQt4 import QtGui  # pylint: disable=import-error
from . import ui_backupdlg  # pylint: disable=no-name-in-module
from . import multiselectwidget

from . import backup_utils
from . import utils
import grp
import pwd
import sys
import os
from . import thread_monitor
import threading
import time


class BackupVMsWindow(ui_backupdlg.Ui_Backup, multiselectwidget.QtGui.QWizard):

    def __init__(self, app, qvm_collection, parent=None):
        super(BackupVMsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection
        self.backup_settings = QtCore.QSettings()

        self.selected_vms = []
        self.tmpdir_to_remove = None
        self.canceled = False
        self.thread_monitor = None

        self.setupUi(self)

        self.progress_status.text = self.tr("Backup in progress...")
        self.dir_line_edit.setReadOnly(False)

        self.select_vms_widget = multiselectwidget.MultiSelectWidget(self)
        self.verticalLayout.insertWidget(1, self.select_vms_widget)

        self.connect(self, QtCore.SIGNAL("currentIdChanged(int)"),
                     self.current_page_changed)
        self.connect(self.select_vms_widget,
                     QtCore.SIGNAL("items_removed(PyQt_PyObject)"),
                     self.vms_removed)
        self.connect(self.select_vms_widget,
                     QtCore.SIGNAL("items_added(PyQt_PyObject)"),
                     self.vms_added)
        self.dir_line_edit.connect(self.dir_line_edit,
                                   QtCore.SIGNAL("textChanged(QString)"),
                                   self.backup_location_changed)

        self.select_vms_page.isComplete = self.has_selected_vms
        self.select_dir_page.isComplete = self.has_selected_dir_and_pass
        # FIXME
        # this causes to run isComplete() twice, I don't know why
        self.select_vms_page.connect(
                self.select_vms_widget,
                QtCore.SIGNAL("selected_changed()"),
                QtCore.SIGNAL("completeChanged()"))
        self.passphrase_line_edit.connect(
                self.passphrase_line_edit,
                QtCore.SIGNAL("textChanged(QString)"),
                self.backup_location_changed)
        self.passphrase_line_edit_verify.connect(
                self.passphrase_line_edit_verify,
                QtCore.SIGNAL("textChanged(QString)"),
                self.backup_location_changed)

        self.total_size = 0

        self.target_vm_list, self.target_vm_idx = utils.prepare_vm_choice(
            self.appvm_combobox,
            self.qvm_collection,
            None,
            self.qvm_collection.domains['dom0'],
            (lambda vm: vm.klass != 'TemplateVM' and vm.is_running()),
            allow_internal=False,
            allow_default=False,
            allow_none=False
        )

        selected = self.load_settings()
        self.__fill_vms_list__(selected)

    def load_settings(self):
        try:
            profile_data = backup_utils.load_backup_profile()
        except FileNotFoundError:
            return
        except exc.QubesException:
            QtGui.QMessageBox.information(
                None, self.tr("Error loading backup profile"),
                self.tr("Unable to load saved backup profile."))
            return
        if not profile_data:
            return

        if 'destination_vm' in profile_data:
            dest_vm_name = profile_data['destination_vm']
            dest_vm_idx = self.appvm_combobox.findText(dest_vm_name)
            if dest_vm_idx > -1:
                self.appvm_combobox.setCurrentIndex(dest_vm_idx)

        if 'destination_path' in profile_data:
            dest_path = profile_data['destination_path']
            self.dir_line_edit.setText(dest_path)

        if 'passphrase_text' in profile_data:
            self.passphrase_line_edit.setText(profile_data['passphrase_text'])
            self.passphrase_line_edit_verify.setText(
                profile_data['passphrase_text'])

        if 'include' in profile_data:
            return profile_data['include']

        return None

    def save_settings(self, use_temp):
        settings = {'destination_vm': self.appvm_combobox.currentText(),
                    'destination_path': self.dir_line_edit.text(),
                    'include': [vm.name for vm in self.selected_vms],
                    'passphrase_text': self.passphrase_line_edit.text()}
        # TODO: add compression when it is added

        backup_utils.write_backup_profile(settings, use_temp)

    class VmListItem(QtGui.QListWidgetItem):
        # pylint: disable=too-few-public-methods
        def __init__(self, vm):
            self.vm = vm
            if vm.qid == 0:
                local_user = grp.getgrnam('qubes').gr_mem[0]
                home_dir = pwd.getpwnam(local_user).pw_dir
                self.size = get_disk_usage(home_dir)
            else:
                self.size = vm.get_disk_utilization()
            super(BackupVMsWindow.VmListItem, self).__init__(
                vm.name + " (" + admin_utils.size_to_human(self.size) + ")")

    def __fill_vms_list__(self, selected=None):
        for vm in self.qvm_collection.domains:
            if vm.features.get('internal', False):
                continue

            item = BackupVMsWindow.VmListItem(vm)
            if (selected is None and
                    getattr(vm, 'include_in_backups', True)) \
                    or (selected and vm.name in selected):
                self.select_vms_widget.selected_list.addItem(item)
                self.total_size += item.size
            else:
                self.select_vms_widget.available_list.addItem(item)
        self.select_vms_widget.available_list.sortItems()
        self.select_vms_widget.selected_list.sortItems()

        self.unrecognized_config_label.setVisible(
            selected is not None and
            len(selected) != len(self.select_vms_widget.selected_list))
        self.total_size_label.setText(
            admin_utils.size_to_human(self.total_size))

    def vms_added(self, items):
        for i in items:
            self.total_size += i.size
        self.total_size_label.setText(
            admin_utils.size_to_human(self.total_size))

    def vms_removed(self, items):
        for i in items:
            self.total_size -= i.size
        self.total_size_label.setText(
            admin_utils.size_to_human(self.total_size))

    @QtCore.pyqtSlot(name='on_select_path_button_clicked')
    def select_path_button_clicked(self):
        backup_utils.select_path_button_clicked(self)

    def validateCurrentPage(self):
        # pylint: disable=invalid-name
        if self.currentPage() is self.select_vms_page:

            self.selected_vms = []
            for i in range(self.select_vms_widget.selected_list.count()):
                self.selected_vms.append(
                    self.select_vms_widget.selected_list.item(i).vm)

        elif self.currentPage() is self.select_dir_page:
            backup_location = str(self.dir_line_edit.text())
            if not backup_location:
                QtGui.QMessageBox.information(
                    None, self.tr("Wait!"),
                    self.tr("Enter backup target location first."))
                return False
            if self.appvm_combobox.currentIndex() == 0 \
                    and not os.path.isdir(backup_location):
                QtGui.QMessageBox.information(
                    None, self.tr("Wait!"),
                    self.tr("Selected directory do not exists or "
                            "not a directory (%s).") % backup_location)
                return False
            if not self.passphrase_line_edit.text():
                QtGui.QMessageBox.information(
                    None, self.tr("Wait!"),
                    self.tr("Enter passphrase for backup "
                            "encryption/verification first."))
                return False
            if self.passphrase_line_edit.text() !=\
                    self.passphrase_line_edit_verify.text():
                QtGui.QMessageBox.information(
                    None, self.tr("Wait!"),
                    self.tr("Enter the same passphrase in both fields."))
                return False

        return True

    def __do_backup__(self, t_monitor):
        msg = []

        try:
            vm = self.qvm_collection.domains[
                self.appvm_combobox.currentText()]
            if not vm.is_running():
                vm.start()
            self.qvm_collection.qubesd_call(
                'dom0', 'admin.backup.Execute',
                backup_utils.get_profile_name(True))
        except Exception as ex:  # pylint: disable=broad-except
            msg.append(str(ex))

        if msg:
            t_monitor.set_error_msg('\n'.join(msg))

        t_monitor.set_finished()


    def current_page_changed(self, page_id): # pylint: disable=unused-argument
        old_sigchld_handler = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        if self.currentPage() is self.confirm_page:

            self.save_settings(True)
            backup_summary = self.qvm_collection.qubesd_call(
                'dom0', 'admin.backup.Info',
                backup_utils.get_profile_name(True))

            self.textEdit.setReadOnly(True)
            self.textEdit.setFontFamily("Monospace")
            self.textEdit.setText(backup_summary.decode())

        elif self.currentPage() is self.commit_page:

            if self.save_profile_checkbox.isChecked():
                self.save_settings(False)

            self.button(self.FinishButton).setDisabled(True)
            self.showFileDialog.setEnabled(
                self.appvm_combobox.currentIndex() != 0)
            self.showFileDialog.setChecked(self.showFileDialog.isEnabled()
                                           and str(self.dir_line_edit.text())
                                           .count("media/") > 0)
            self.thread_monitor = thread_monitor.ThreadMonitor()
            thread = threading.Thread(
                target=self.__do_backup__,
                args=(self.thread_monitor,))
            thread.daemon = True
            thread.start()

            while not self.thread_monitor.is_finished():
                self.app.processEvents()
                time.sleep(0.1)

            if not self.thread_monitor.success:
                if self.canceled:
                    self.progress_status.setText(self.tr("Backup aborted."))
                    if self.tmpdir_to_remove:
                        if QtGui.QMessageBox.warning(
                                None, self.tr("Backup aborted"),
                                self.tr(
                                    "Do you want to remove temporary files "
                                    "from %s?") % self.tmpdir_to_remove,
                                QtGui.QMessageBox.Yes,
                                QtGui.QMessageBox.No) == QtGui.QMessageBox.Yes:
                            shutil.rmtree(self.tmpdir_to_remove)
                else:
                    self.progress_status.setText(self.tr("Backup error."))
                    QtGui.QMessageBox.warning(
                        self, self.tr("Backup error!"),
                        self.tr("ERROR: {}").format(
                            self.thread_monitor.error_msg))
            else:
                self.progress_bar.setMaximum(100)
                self.progress_bar.setValue(100)
                self.progress_status.setText(self.tr("Backup finished."))
            if self.showFileDialog.isChecked():
                orig_text = self.progress_status.text
                self.progress_status.setText(
                    orig_text + self.tr(
                        " Please unmount your backup volume and cancel "
                        "the file selection dialog."))
                backup_utils.select_path_button_clicked(self, False, True)
            self.button(self.CancelButton).setEnabled(False)
            self.button(self.FinishButton).setEnabled(True)
            self.showFileDialog.setEnabled(False)
        signal.signal(signal.SIGCHLD, old_sigchld_handler)

    def reject(self):
        # cancel clicked while the backup is in progress.
        # calling kill on tar.
        if self.currentPage() is self.commit_page:
            pass  # TODO: this does nothing
            # if backup.backup_cancel():
            #     self.button(self.CancelButton).setDisabled(True)
        else:
            self.done(0)

    def has_selected_vms(self):
        return self.select_vms_widget.selected_list.count() > 0

    def has_selected_dir_and_pass(self):
        if not self.passphrase_line_edit.text():
            return False
        if self.passphrase_line_edit.text() != \
                self.passphrase_line_edit_verify.text():
            return False
        return len(self.dir_line_edit.text()) > 0

    def backup_location_changed(self, new_dir=None):
        # pylint: disable=unused-argument
        self.select_dir_page.emit(QtCore.SIGNAL("completeChanged()"))


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception(exc_type, exc_value, exc_traceback):
    filename, line, dummy, dummy = traceback.extract_tb(exc_traceback).pop()
    filename = os.path.basename(filename)
    error = "%s: %s" % (exc_type.__name__, exc_value)

    QtGui.QMessageBox.critical(
        None,
        "Houston, we have a problem...",
        "Whoops. A critical error has occured. This is most likely a bug "
        "in Qubes Global Settings application.<br><br><b><i>%s</i></b>" %
        error + "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
        % (line, filename))


def main():

    qtapp = QtGui.QApplication(sys.argv)
    qtapp.setOrganizationName("The Qubes Project")
    qtapp.setOrganizationDomain("http://qubes-os.org")
    qtapp.setApplicationName("Qubes Backup VMs")

    sys.excepthook = handle_exception

    app = Qubes()

    backup_window = BackupVMsWindow(qtapp, app)

    backup_window.show()

    qtapp.exec_()
    qtapp.exit()


if __name__ == "__main__":
    main()
