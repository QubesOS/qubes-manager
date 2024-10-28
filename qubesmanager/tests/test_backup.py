#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2016 Marta Marczykowska-Górecka
#                                       <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
import logging.handlers
import unittest
import unittest.mock

from PyQt6 import QtTest, QtCore, QtWidgets
from qubesadmin import Qubes, events, utils, exc
from qubesmanager import backup
from qubesmanager.tests import init_qtapp


class BackupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qapp = Qubes()

        cls.dom0_name = "dom0"

        cls.vms = []
        cls.running_vm = None

        for vm in qapp.domains:
            if vm.klass != "AdminVM" and vm.is_running():
                cls.running_vm = vm.name
            if vm.klass != "AdminVM" and vm.get_disk_utilization() > 0:
                cls.vms.append(vm.name)
            if cls.running_vm and len(cls.vms) >= 3:
                break

    def setUp(self):
        super(BackupTest, self).setUp()
        self.qtapp, self.loop = init_qtapp()

        # mock up nonexistence of saved backup settings
        self.patcher_open = unittest.mock.patch('builtins.open')
        self.mock_open = self.patcher_open.start()
        self.mock_open.side_effect = FileNotFoundError()
        self.addCleanup(self.patcher_open.stop)

        # mock up the Backup Thread to avoid accidentally changing system state
        self.patcher_thread = unittest.mock.patch(
            'qubesmanager.backup.BackupThread')
        self.mock_thread = self.patcher_thread.start()
        self.addCleanup(self.patcher_thread.stop)

        self.qapp = Qubes()
        self.dispatcher = events.EventsDispatcher(self.qapp)

        self.dialog = backup.BackupVMsWindow(
            self.qtapp, self.qapp, self.dispatcher)
        self.dialog.show()

    def tearDown(self):
        self.dialog.done(0)
        super(BackupTest, self).tearDown()

    def test_00_window_loads(self):
        self.assertTrue(self.dialog.select_vms_widget is not None)

    def test_01_vms_load_correctly(self):
        all_vms = len([vm for vm in self.qapp.domains
                       if not vm.features.get('internal', False)])

        selected_vms = self.dialog.select_vms_widget.selected_list.count()
        available_vms = self.dialog.select_vms_widget.available_list.count()

        self.assertEqual(all_vms, available_vms + selected_vms)

    def test_02_correct_defaults(self):
        # backup is compressed
        self.assertTrue(self.dialog.compress_checkbox.isChecked(),
                        "Compress backup should be checked by default")

        # correct VMs are selected
        include_in_backups_no = len(
            [vm for vm in self.qapp.domains
             if not vm.features.get('internal', False)
             and getattr(vm, 'include_in_backups', True)])
        selected_no = self.dialog.select_vms_widget.selected_list.count()
        self.assertEqual(include_in_backups_no, selected_no,
                         "Incorrect VMs selected by default")

        # passphrase is empty
        self.assertEqual(self.dialog.passphrase_line_edit.text(), "",
                         "Passphrase should be empty")

        # save defaults
        self.assertTrue(self.dialog.save_profile_checkbox.isChecked(),
                        "By default, profile should be saved")

    def test_03_select_vms_widget(self):
        number_of_all_vms = len([vm for vm in self.qapp.domains
                                 if not vm.features.get('internal', False)])

        # select all
        self.dialog.select_vms_widget.add_all_button.click()
        self.assertEqual(number_of_all_vms,
                         self.dialog.select_vms_widget.selected_list.count(),
                         "Add All VMs does not work")

        # remove all
        self.dialog.select_vms_widget.remove_all_button.click()
        self.assertEqual(number_of_all_vms,
                         self.dialog.select_vms_widget.available_list.count(),
                         "Remove All VMs does not work")

        self._select_vm(self.vms[0])

        self.assertEqual(self.dialog.select_vms_widget.selected_list.count(),
                         1, "Select a single VM does not work")

    def test_04_open_directory(self):
        self.dialog.next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        with unittest.mock.patch('qubesmanager.backup_utils.'
                                 'select_path_button_clicked') as mock_func:
            self.dialog.select_path_button.click()
            mock_func.assert_called_once_with(unittest.mock.ANY)

    def test_05_running_vms_listed(self):
        self.dialog.next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        running_vms = [vm.name for vm in self.qapp.domains if vm.is_running()]

        listed_vms = []

        for i in range(self.dialog.appvm_combobox.count()):
            listed_vms.append(self.dialog.appvm_combobox.itemText(i))

        self.assertListEqual(sorted(running_vms), sorted(listed_vms),
                             "Incorrect list of running vms")

    def test_06_passphrase_verification(self):
        self.dialog.next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)
        # required to check if next button is correctly enabled
        self.dialog.dir_line_edit.setText("/home")

        next_button = self.dialog.button(self.dialog.WizardButton.NextButton)

        # check if next remains inactive for various incorrect
        # passphrase/incorrect combinations
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("fail")
        self.assertFalse(next_button.isEnabled(),
                         "Mismatched passphrase/verification accepted")

        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("")
        self.assertFalse(next_button.isEnabled(), "Empty verification accepted")

        self.dialog.passphrase_line_edit.setText("")
        self.dialog.passphrase_line_edit_verify.setText("fail")
        self.assertFalse(next_button.isEnabled(), "Empty passphrase accepted")

        self.dialog.passphrase_line_edit.setText("")
        self.dialog.passphrase_line_edit_verify.setText("")
        self.assertFalse(next_button.isEnabled(),
                         "Empty passphrase and verification accepted")

        # check if next is active for a correct passphrase/verify
        # combination
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")
        self.assertTrue(next_button.isEnabled(),
                        "Matching passphrase/verification not accepted")

    def test_07_disk_space_correct(self):
        for i in range(self.dialog.select_vms_widget.available_list.count()):
            item = self.dialog.select_vms_widget.available_list.item(i)
            if item.vm.name == self.dom0_name or \
                    item.vm.get_disk_utilization() > 0:
                self.assertGreater(
                    item.size, 0,
                    "{} size incorrectly reported as 0".format(item.vm.name))

    def test_08_total_size_correct(self):
        if len(self.vms) < 3:
            self.skipTest("Insufficient number of VMs with positive "
                          "disk utilization")
        # select nothing
        self.dialog.select_vms_widget.remove_all_button.click()
        self.assertEqual(self.dialog.total_size_label.text(), "0",
                         "Total size of 0 vms incorrectly reported as 0")

        current_size = 0
        # select a single VM
        self._select_vm(self.vms[0])

        current_size += self.qapp.domains[self.vms[0]].get_disk_utilization()
        self.assertEqual(self.dialog.total_size_label.text(),
                         utils.size_to_human(current_size),
                         "Size incorrectly listed for a single VM")

        # add two more
        self._select_vm(self.vms[1])
        self._select_vm(self.vms[2])

        current_size += self.qapp.domains[self.vms[1]].get_disk_utilization()
        current_size += self.qapp.domains[self.vms[2]].get_disk_utilization()

        self.assertEqual(self.dialog.total_size_label.text(),
                         utils.size_to_human(current_size),
                         "Size incorrectly listed for several VMs")

        # remove one
        self._deselect_vm(self.vms[0])
        current_size -= self.qapp.domains[self.vms[0]].get_disk_utilization()
        self.assertEqual(self.dialog.total_size_label.text(),
                         utils.size_to_human(current_size),
                         "Size incorrectly listed for several VMs")

    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_10_first_backup(self, mock_qubesd, mock_write_profile):
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_vms_page)

        self.dialog.select_vms_widget.remove_all_button.click()
        self._select_vm(self.vms[0])

        self._click_next()

        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        # setup backup
        self._select_location(self.dom0_name)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")
        self.dialog.save_profile_checkbox.setChecked(True)
        self.dialog.turn_off_checkbox.setChecked(False)
        self.dialog.compress_checkbox.setChecked(False)
        expected_settings = {'destination_vm': self.dom0_name,
                             'destination_path': "/home",
                             'include': [self.vms[0]],
                             'passphrase_text': "pass",
                             'compression': False}
        with unittest.mock.patch.object(self.dialog.textEdit, 'setText')\
                as mock_set_text:
            self._click_next()

            # make sure the confirmation is not empty
            self.assertTrue(self.dialog.currentPage()
                            is self.dialog.confirm_page)

            mock_write_profile.assert_called_with(expected_settings, True)
            mock_qubesd.assert_called_with('dom0', 'admin.backup.Info',
                                           unittest.mock.ANY)
            mock_set_text.assert_called_once_with("backup output")

        # make sure the backup is executed
        self._click_next()
        self.mock_thread.assert_called_once_with(
            self.qapp.domains[self.dom0_name])
        self.mock_thread().start.assert_called_once_with()

    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_11_second_backup(self, mock_qubesd, mock_write_profile):
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_vms_page)

        self.dialog.select_vms_widget.remove_all_button.click()
        self._select_vm(self.dom0_name)
        self._select_vm(self.vms[0])
        self._select_vm(self.vms[1])

        self._click_next()

        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        # setup backup
        self._select_location(self.running_vm)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("longerPassPhrase")
        self.dialog.passphrase_line_edit_verify.setText("longerPassPhrase")
        self.dialog.save_profile_checkbox.setChecked(False)
        self.dialog.turn_off_checkbox.setChecked(False)
        self.dialog.compress_checkbox.setChecked(True)
        expected_settings = {'destination_vm': self.running_vm,
                             'destination_path': "/home",
                             'include': sorted([self.dom0_name, self.vms[0],
                                         self.vms[1]]),
                             'passphrase_text': "longerPassPhrase",
                             'compression': True}
        with unittest.mock.patch.object(self.dialog.textEdit, 'setText')\
                as mock_set_text:
            self._click_next()

            # make sure the confirmation is not empty
            self.assertTrue(self.dialog.currentPage()
                            is self.dialog.confirm_page)

            mock_write_profile.assert_called_with(expected_settings, True)
            mock_qubesd.assert_called_with('dom0', 'admin.backup.Info',
                                           unittest.mock.ANY)
            mock_set_text.assert_called_once_with("backup output")

        # make sure the backup is executed
        self._click_next()
        self.mock_thread.assert_called_once_with(
            self.qapp.domains[self.running_vm])
        self.mock_thread().start.assert_called_once_with()

    @unittest.mock.patch('qubesmanager.backup_utils.load_backup_profile')
    def test_20_loading_settings(self, mock_load):

        mock_load.return_value = {
            'destination_vm': self.running_vm,
            'destination_path': "/home",
            'include': [self.dom0_name, self.vms[0], self.vms[1]],
            'passphrase_text': "longerPassPhrase",
            'compression': True
        }

        self.dialog.hide()
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = backup.BackupVMsWindow(
            self.qtapp, self.qapp, self.dispatcher)
        self.dialog.show()

        # check if settings were loaded
        self.assertEqual(self.dialog.appvm_combobox.currentText(),
                         self.running_vm,
                         "Destination VM not loaded")
        self.assertEqual(self.dialog.dir_line_edit.text(), "/home",
                         "Destination path not loaded")
        self.assertEqual(self.dialog.passphrase_line_edit.text(),
                         "longerPassPhrase", "Passphrase not loaded")
        self.assertEqual(self.dialog.passphrase_line_edit_verify.text(),
                         "longerPassPhrase", "Passphrase verify not loaded")
        self.assertTrue(self.dialog.compress_checkbox.isChecked())

        # check that 'include' vms were not pre-selected
        include_in_backups_no = len(
            [vm for vm in self.qapp.domains
             if not vm.features.get('internal', False)
             and getattr(vm, 'include_in_backups', True)])
        selected_no = self.dialog.select_vms_widget.selected_list.count()
        self.assertEqual(include_in_backups_no, selected_no,
                         "Incorrect VM list selected")

        # check no errors were detected
        self.assertFalse(self.dialog.unrecognized_config_label.isVisible())

    @unittest.mock.patch('qubesmanager.backup_utils.load_backup_profile')
    def test_21_loading_settings_error(self, mock_load):

        mock_load.return_value = {
            'destination_vm': "incorrect_vm",
        }

        self.dialog.hide()
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = backup.BackupVMsWindow(
            self.qtapp, self.qapp, self.dispatcher)
        self.dialog.show()

        # check errors were detected
        self.assertIn('incorrect_vm', self.dialog.warning_running_label.text())

    @unittest.mock.patch('qubesmanager.backup_utils.load_backup_profile')
    @unittest.mock.patch('PyQt6.QtWidgets.QMessageBox.information')
    def test_22_loading_settings_exc(self, mock_info, mock_load):

        mock_load.side_effect = exc.QubesException('Error')

        self.dialog.hide()
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = backup.BackupVMsWindow(
            self.qtapp, self.qapp, self.dispatcher)
        self.dialog.show()

        # check error was reported
        self.assertEqual(mock_info.call_count, 1, "Warning not shown")

    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_23_cancel_confirm(self, *_args):
        self._click_next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        self._select_location(self.dom0_name)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")

        self._click_next()

        # attempt to cancel
        with unittest.mock.patch('os.remove') as mock_remove:
            self._click_cancel()
            mock_remove.assert_called_once_with(
                '/etc/qubes/backup/qubes-manager-backup-tmp.conf')

    @unittest.mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_24_cancel_in_progress(self, mock_call, *_args):
        self._click_next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        self._select_location(self.dom0_name)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")

        self._click_next()
        self._click_next()

        # attempt to cancel
        with unittest.mock.patch('os.remove') as mock_remove:
            self._click_cancel()
            mock_call.assert_called_with('dom0', 'admin.backup.Cancel',
                                         'qubes-manager-backup-tmp')
            mock_remove.assert_called_once_with(
                '/etc/qubes/backup/qubes-manager-backup-tmp.conf')

    @unittest.mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
    @unittest.mock.patch('os.system')
    @unittest.mock.patch('os.remove')
    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_25_successful_backup(self, _a, _b, mock_remove,
                                  mock_system, mock_warning):
        self._click_next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        self._select_location(self.dom0_name)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")
        self.dialog.turn_off_checkbox.setChecked(False)

        self._click_next()
        self._click_next()

        # assume backup went correctly
        self.mock_thread().msg = None

        self.mock_thread().finished.connect.assert_called_once_with(
            self.dialog.backup_finished)

        self.dialog.backup_finished()

        self.assertFalse(self.dialog.button(
            QtWidgets.QWizard.WizardButton.CancelButton).isEnabled())
        self.assertTrue(self.dialog.button(
            QtWidgets.QWizard.WizardButton.FinishButton).isEnabled())
        mock_remove.assert_called_once_with(
            '/etc/qubes/backup/qubes-manager-backup-tmp.conf')
        self.assertEqual(mock_system.call_count, 0,
                         "System turned off unnecessarily")
        self.assertEqual(mock_warning.call_count, 0,
                         "Backup succeeded but received warning")

    @unittest.mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
    @unittest.mock.patch('os.system')
    @unittest.mock.patch('os.remove')
    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_26_success_backup_poweroff(
            self, _a, _b, mock_remove, mock_system, mock_warning):
        self._click_next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        self._select_location(self.dom0_name)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")
        self.dialog.turn_off_checkbox.setChecked(True)

        self._click_next()

        self._click_next()

        # assume backup went correctly
        self.mock_thread().msg = None
        self.mock_thread().finished.connect.assert_called_once_with(
            self.dialog.backup_finished)

        self.dialog.backup_finished()

        self.assertFalse(self.dialog.button(
            QtWidgets.QWizard.WizardButton.CancelButton).isEnabled())
        self.assertTrue(self.dialog.button(
            QtWidgets.QWizard.WizardButton.FinishButton).isEnabled())
        mock_remove.assert_called_once_with(
            '/etc/qubes/backup/qubes-manager-backup-tmp.conf')
        mock_system.assert_called_once_with('systemctl poweroff')
        self.assertEqual(mock_warning.call_count, 0,
                         "Backup succeeded but received warning")

    @unittest.mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
    @unittest.mock.patch('os.system')
    @unittest.mock.patch('os.remove')
    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_27_failed_backup(
            self, _a, _b, mock_remove, mock_system, mock_warn):
        self._click_next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        self._select_location(self.dom0_name)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")
        self.dialog.turn_off_checkbox.setChecked(True)

        self._click_next()
        self._click_next()

        # assume backup went wrong
        self.mock_thread().msg = "Error"
        self.mock_thread().finished.connect.assert_called_once_with(
            self.dialog.backup_finished)

        self.dialog.backup_finished()

        self.assertFalse(self.dialog.button(
            QtWidgets.QWizard.WizardButton.CancelButton).isEnabled())
        self.assertTrue(self.dialog.button(
            QtWidgets.QWizard.WizardButton.FinishButton).isEnabled())
        mock_remove.assert_called_once_with(
            '/etc/qubes/backup/qubes-manager-backup-tmp.conf')
        self.assertEqual(mock_system.call_count, 0,
                         "Attempted shutdown at failed backup")
        self.assertEqual(mock_warn.call_count, 1)

    @unittest.mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
    @unittest.mock.patch('os.system')
    @unittest.mock.patch('os.remove')
    @unittest.mock.patch('qubesmanager.backup_utils.write_backup_profile')
    @unittest.mock.patch('qubesadmin.Qubes.qubesd_call',
                         return_value=b'backup output')
    def test_28_progress(
            self, _a, _b, _mock_remove, _mock_system, _mock_warn):
        self._click_next()
        self.assertTrue(self.dialog.currentPage()
                        is self.dialog.select_dir_page)

        self._select_location(self.dom0_name)
        self.dialog.dir_line_edit.setText("/home")
        self.dialog.passphrase_line_edit.setText("pass")
        self.dialog.passphrase_line_edit_verify.setText("pass")
        self.dialog.turn_off_checkbox.setChecked(True)

        self._click_next()
        self._click_next()

        # see if backup is correctly in progress
        self.assertTrue(self.dialog.button(
            QtWidgets.QWizard.WizardButton.CancelButton).isEnabled())
        self.assertFalse(self.dialog.button(
            QtWidgets.QWizard.WizardButton.FinishButton).isEnabled())
        self.assertEqual(self.dialog.progress_bar.value(), 0,
                         "Progress bar does not start at 0")

        # this is not a perfect method, but it is something

        self.dialog.on_backup_progress(None, None, progress='23.3123')
        self.assertEqual(self.dialog.progress_bar.value(), 23,
                         "Progress bar does not update correctly")

        self.dialog.on_backup_progress(None, None, progress='87.89')
        self.assertEqual(self.dialog.progress_bar.value(), 87,
                         "Progress bar does not update correctly")

    def _select_location(self, vm_name):
        widget = self.dialog.appvm_combobox
        widget.setCurrentIndex(0)
        while not widget.currentText() == vm_name:
            if widget.currentIndex() == widget.count():
                self.skipTest("target VM not found")
            widget.setCurrentIndex(widget.currentIndex() + 1)

    def _click_next(self):
        next_widget = self.dialog.button(
            QtWidgets.QWizard.WizardButton.NextButton)
        QtTest.QTest.mouseClick(next_widget, QtCore.Qt.MouseButton.LeftButton)

    def _click_cancel(self):
        cancel_widget = self.dialog.button(
            QtWidgets.QWizard.WizardButton.CancelButton)
        QtTest.QTest.mouseClick(cancel_widget, QtCore.Qt.MouseButton.LeftButton)

    def _select_vm(self, name_starts_with):
        for i in range(self.dialog.select_vms_widget.available_list.count()):
            item = self.dialog.select_vms_widget.available_list.item(i)
            if item.text().startswith(name_starts_with):
                item.setSelected(True)
                self.dialog.select_vms_widget.add_selected_button.click()
                return

    def _deselect_vm(self, name_starts_with):
        for i in range(self.dialog.select_vms_widget.selected_list.count()):
            item = self.dialog.select_vms_widget.selected_list.item(i)
            if item.text().startswith(name_starts_with):
                item.setSelected(True)
                self.dialog.select_vms_widget.remove_selected_button.click()
                return


class BackupThreadTest(unittest.TestCase):
    def test_01_backup_thread_vm_on(self):
        vm = unittest.mock.Mock(spec=['is_running', 'app'],
                                **{'is_running.return_value': True})

        vm.app = unittest.mock.Mock()

        thread = backup.BackupThread(vm)
        thread.run()

        vm.app.qubesd_call.assert_called_with(
            'dom0', 'admin.backup.Execute', 'qubes-manager-backup-tmp')

    def test_02_backup_thread_vm_off(self):
        vm = unittest.mock.Mock(spec=['is_running', 'app', 'start'],
                                **{'is_running.return_value': False})

        vm.app = unittest.mock.Mock()

        thread = backup.BackupThread(vm)
        thread.run()

        vm.app.qubesd_call.assert_called_with(
            'dom0', 'admin.backup.Execute', 'qubes-manager-backup-tmp')
        vm.start.assert_called_once_with()

    def test_03_backup_thread_error(self):
        vm = unittest.mock.Mock(spec=['is_running', 'app'],
                                **{'is_running.return_value': True})

        vm.app = unittest.mock.Mock()
        vm.app.qubesd_call.side_effect = exc.QubesException('Error')

        thread = backup.BackupThread(vm)
        thread.run()

        self.assertIsNotNone(thread.msg)


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
