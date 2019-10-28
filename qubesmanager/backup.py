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

import signal
from qubesadmin import exc
from qubesadmin import utils as admin_utils

from PyQt5 import QtCore, QtWidgets  # pylint: disable=import-error
from . import ui_backupdlg  # pylint: disable=no-name-in-module
from . import multiselectwidget

from . import backup_utils
from . import utils

import grp
import pwd
import os
import shutil


# pylint: disable=too-few-public-methods
class BackupThread(QtCore.QThread):
    def __init__(self, vm):
        QtCore.QThread.__init__(self)
        self.vm = vm
        self.msg = None

    def run(self):
        msg = []
        try:
            if not self.vm.is_running():
                self.vm.start()
            self.vm.app.qubesd_call(
                'dom0', 'admin.backup.Execute',
                backup_utils.get_profile_name(True))
        except Exception as ex:  # pylint: disable=broad-except
            msg.append(str(ex))

        if msg:
            self.msg = '\n'.join(msg)


class BackupVMsWindow(ui_backupdlg.Ui_Backup, QtWidgets.QWizard):
    def __init__(self, qt_app, qubes_app, dispatcher, parent=None):
        super(BackupVMsWindow, self).__init__(parent)

        self.qt_app = qt_app
        self.qubes_app = qubes_app

        self.selected_vms = []
        self.thread = None

        self.setupUi(self)

        self.progress_status.text = self.tr("Backup in progress...")
        self.dir_line_edit.setReadOnly(False)

        self.select_vms_widget = multiselectwidget.MultiSelectWidget(self)
        self.verticalLayout.insertWidget(1, self.select_vms_widget)

        self.currentIdChanged.connect(self.current_page_changed)
        self.select_vms_widget.itemsRemoved.connect(self.vms_removed)
        self.select_vms_widget.itemsAdded.connect(self.vms_added)
        self.dir_line_edit.textChanged.connect(self.backup_location_changed)

        self.select_vms_page.isComplete = self.has_selected_vms
        self.select_dir_page.isComplete = self.has_selected_dir_and_pass
        # FIXME
        # this causes to run isComplete() twice, I don't know why
        self.select_vms_widget.selectedChanged.connect(
            self.select_vms_page.completeChanged.emit)
        self.passphrase_line_edit.textChanged.connect(
            self.backup_location_changed)
        self.passphrase_line_edit_verify.textChanged.connect(
            self.backup_location_changed)

        self.total_size = 0

        self.target_vm_list, self.target_vm_idx = utils.prepare_vm_choice(
            self.appvm_combobox,
            self.qubes_app,
            None,
            self.qubes_app.domains['dom0'],
            filter_function=(lambda vm:
                             vm.klass != 'TemplateVM'
                             and vm.is_running()
                             and not vm.features.get('internal', False)),
            allow_default=False,
            allow_none=False
        )

        self.unrecognized_config_label.setVisible(False)
        self.load_settings()

        selected = self.vms_to_include()
        self.__fill_vms_list__(selected)

        # Connect backup events for progress_bar
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.dispatcher = dispatcher
        dispatcher.add_handler('backup-progress', self.on_backup_progress)

    def on_backup_progress(self, __submitter, _event, **kwargs):
        self.progress_bar.setValue(int(float(kwargs['progress'])))

    def vms_to_include(self):
        """
        Helper function that returns list of VMs with 'include_in_backups'
        attribute set to True.
        :return: list of VM names
        """

        result = []

        for domain in self.qubes_app.domains:
            if getattr(domain, 'include_in_backups', None):
                result.append(domain.name)

        return result

    def load_settings(self):
        """
        Helper function that tries to load existing backup profile
        (default path: /etc/qubes/backup/qubes-manager-backup.conf )
        and then apply its contents to the Backup window.
        Ignores listed VMs, to prioritize include_in_backups feature.
        :return: None
        """
        try:
            profile_data = backup_utils.load_backup_profile()
        except FileNotFoundError:
            return
        except exc.QubesException:
            QtWidgets.QMessageBox.information(
                self, self.tr("Error loading backup profile"),
                self.tr("Unable to load saved backup profile."))
            return
        if not profile_data:
            return

        if 'destination_vm' in profile_data:
            dest_vm_name = profile_data['destination_vm']
            dest_vm_idx = self.appvm_combobox.findText(dest_vm_name)
            if dest_vm_idx > -1:
                self.appvm_combobox.setCurrentIndex(dest_vm_idx)
            else:
                self.unrecognized_config_label.setVisible(True)

        if 'destination_path' in profile_data:
            dest_path = profile_data['destination_path']
            self.dir_line_edit.setText(dest_path)

        if 'passphrase_text' in profile_data:
            self.passphrase_line_edit.setText(profile_data['passphrase_text'])
            self.passphrase_line_edit_verify.setText(
                profile_data['passphrase_text'])

        if 'compression' in profile_data:
            self.compress_checkbox.setChecked(profile_data['compression'])

    def save_settings(self, use_temp):
        """
        Helper function that saves backup profile to either
        /etc/qubes/backup/qubes-manager-backup.conf or
        /etc/qubes/backup/qubes-manager-backup-tmp.conf
        :param use_temp: whether to use temporary profile (True) or the default
         backup profile (False)
        """
        settings = {'destination_vm': self.appvm_combobox.currentText(),
                    'destination_path': self.dir_line_edit.text(),
                    'include': [vm.name for vm in self.selected_vms],
                    'passphrase_text': self.passphrase_line_edit.text(),
                    'compression': self.compress_checkbox.isChecked()}

        backup_utils.write_backup_profile(settings, use_temp)

    class VmListItem(QtWidgets.QListWidgetItem):
        # pylint: disable=too-few-public-methods
        def __init__(self, vm):
            self.vm = vm
            if vm.qid == 0:
                local_user = grp.getgrnam('qubes').gr_mem[0]
                home_dir = pwd.getpwnam(local_user).pw_dir
                self.size = shutil.disk_usage(home_dir)[1]
            else:
                self.size = vm.get_disk_utilization()
            super(BackupVMsWindow.VmListItem, self).__init__(
                vm.name + " (" + admin_utils.size_to_human(self.size) + ")")

    def __fill_vms_list__(self, selected=None):
        for vm in self.qubes_app.domains:
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
                QtWidgets.QMessageBox.information(
                    self, self.tr("Wait!"),
                    self.tr("Enter backup target location first."))
                return False
            if self.appvm_combobox.currentText() == "dom0" \
                    and not os.path.isdir(backup_location):
                QtWidgets.QMessageBox.information(
                    self, self.tr("Wait!"),
                    self.tr("Selected directory do not exists or "
                            "not a directory (%s).") % backup_location)
                return False
            if not self.passphrase_line_edit.text():
                QtWidgets.QMessageBox.information(
                    self, self.tr("Wait!"),
                    self.tr("Enter passphrase for backup "
                            "encryption/verification first."))
                return False
            if self.passphrase_line_edit.text() !=\
                    self.passphrase_line_edit_verify.text():
                QtWidgets.QMessageBox.information(
                    self, self.tr("Wait!"),
                    self.tr("Enter the same passphrase in both fields."))
                return False

        return True

    @staticmethod
    def cleanup_temporary_files():
        try:
            os.remove(backup_utils.get_profile_path(use_temp=True))
        except FileNotFoundError:
            pass

    def current_page_changed(self, page_id):  # pylint: disable=unused-argument
        old_sigchld_handler = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        if self.currentPage() is self.confirm_page:

            self.save_settings(use_temp=True)
            backup_summary = self.qubes_app.qubesd_call(
                'dom0', 'admin.backup.Info',
                backup_utils.get_profile_name(True))

            self.textEdit.setReadOnly(True)
            self.textEdit.setFontFamily("Monospace")
            self.textEdit.setText(backup_summary.decode())

        elif self.currentPage() is self.commit_page:

            if self.save_profile_checkbox.isChecked():
                self.save_settings(use_temp=False)

            self.button(self.FinishButton).setDisabled(True)
            self.showFileDialog.setEnabled(
                self.appvm_combobox.currentIndex() != 0)
            self.showFileDialog.setChecked(self.showFileDialog.isEnabled()
                                           and str(self.dir_line_edit.text())
                                           .count("media/") > 0)

            vm = self.qubes_app.domains[
                self.appvm_combobox.currentText()]

            self.thread = BackupThread(vm)
            self.thread.finished.connect(self.backup_finished)
            self.thread.start()

        signal.signal(signal.SIGCHLD, old_sigchld_handler)

    def backup_finished(self):
        if self.thread.msg:
            self.progress_status.setText(self.tr("Backup error."))
            QtWidgets.QMessageBox.warning(
                self, self.tr("Backup error!"),
                self.tr("ERROR: {}").format(
                    self.thread.msg))
            self.button(self.CancelButton).setEnabled(False)
            self.button(self.FinishButton).setEnabled(True)
            self.cleanup_temporary_files()

        else:
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
            self.cleanup_temporary_files()

            # turn off only when backup was successful
            if self.turn_off_checkbox.isChecked():
                os.system('systemctl poweroff')

    def reject(self):
        if (self.currentPage() is self.commit_page) and \
                self.button(self.CancelButton).isEnabled():
            try:
                self.qubes_app.qubesd_call(
                    'dom0', 'admin.backup.Cancel',
                    backup_utils.get_profile_name(True))
            except exc.QubesException as ex:
                QtWidgets.QMessageBox.warning(
                    self, self.tr("Error cancelling backup!"),
                    self.tr("ERROR: {}").format(str(ex)))

            self.thread.wait()
            QtWidgets.QMessageBox.warning(
                self, self.tr("Backup aborted!"),
                self.tr("ERROR: {}").format("Aborted!"))

        self.cleanup_temporary_files()
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
        self.select_dir_page.completeChanged.emit()


def main():
    utils.run_asynchronous("Qubes Backup VMs",
                           "qubes-manager",
                           BackupVMsWindow)


if __name__ == "__main__":
    main()
