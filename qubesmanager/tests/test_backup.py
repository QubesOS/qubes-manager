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
import unittest
import unittest.mock
from unittest import mock

import pytest
from PyQt6 import QtWidgets
from qubesadmin import exc
from qubesadmin.tests.mock_app import MockAsyncDispatcher, MockQube
from qubesmanager import backup


@pytest.fixture
def backup_dlg(qapp, test_qubes_app):
    test_qubes_app._qubes['test-backup'] = MockQube(
        name="test-backup", qapp=test_qubes_app, label="green",
        include_in_backups=False
    )
    test_qubes_app.update_vm_calls()

    dispatcher = MockAsyncDispatcher(test_qubes_app)
    dlg = backup.BackupVMsWindow(qapp, test_qubes_app, dispatcher)
    # needed because otherwise the wizard will not test correctly
    dlg.show()
    yield dlg


def _get_vms_from_widget(widget: QtWidgets.QListWidget):
    """Get a list of VMs in the for of vm (klass) strings"""
    vms = []
    for i in range(widget.count()):
        item = widget.item(i)
        # the text is in the form of vmname (klass) (size)
        vm, klass, _ = item.text().split(" ", maxsplit=2)
        vms.append(vm + " " + klass)
    return vms


def test_00_load_backup(backup_dlg):
    expected_selected_vms = [
        f"{vm.name} ({vm.klass})" for vm in
        backup_dlg.qubes_app.domains if vm.include_in_backups]
    expected_avail_vms = [
        f"{vm.name} ({vm.klass})" for vm in
        backup_dlg.qubes_app.domains if not vm.include_in_backups]
    avail_vms = _get_vms_from_widget(
        backup_dlg.select_vms_widget.available_list)
    selected_vms = _get_vms_from_widget(
        backup_dlg.select_vms_widget.selected_list)

    assert sorted(expected_selected_vms) == sorted(selected_vms)
    assert sorted(expected_avail_vms) == sorted(avail_vms)


def test_01_correct_default(backup_dlg):
    # backup is compressed
    assert backup_dlg.compress_checkbox.isChecked()

    # passphrase is empty
    assert backup_dlg.passphrase_line_edit.text() == "", "Password non-empty"

    # save default
    assert backup_dlg.save_profile_checkbox.isChecked()


def test_02_select_vms_widget(backup_dlg):
    init_selected = _get_vms_from_widget(
        backup_dlg.select_vms_widget.selected_list)
    init_avail = _get_vms_from_widget(
        backup_dlg.select_vms_widget.available_list)

    backup_dlg.select_vms_widget.add_all_button.click()
    select_all_selected = _get_vms_from_widget(
        backup_dlg.select_vms_widget.selected_list)
    select_all_available = _get_vms_from_widget(
        backup_dlg.select_vms_widget.available_list)

    assert not select_all_available
    assert sorted(select_all_selected) == sorted(init_selected + init_avail)

    backup_dlg.select_vms_widget.remove_all_button.click()
    unselect_all_selected = _get_vms_from_widget(
        backup_dlg.select_vms_widget.selected_list)
    unselect_all_available = _get_vms_from_widget(
        backup_dlg.select_vms_widget.available_list)

    assert not unselect_all_selected
    assert sorted(unselect_all_available) == sorted(init_selected + init_avail)


def test_03_passphrase_verification(backup_dlg):
    next_button = backup_dlg.button(backup_dlg.WizardButton.NextButton)
    assert next_button.isEnabled()
    next_button.click()

    assert backup_dlg.currentPage() is backup_dlg.select_dir_page

    backup_dlg.dir_line_edit.setText("/home")

    next_button = backup_dlg.button(backup_dlg.WizardButton.NextButton)

    # check if next remains inactive for various incorrect
    # passphrase/incorrect combinations
    backup_dlg.passphrase_line_edit.setText("pass")
    backup_dlg.passphrase_line_edit_verify.setText("fail")
    assert not next_button.isEnabled(), \
        "Mismatched passphrase/verification accepted"

    backup_dlg.passphrase_line_edit.setText("pass")
    backup_dlg.passphrase_line_edit_verify.setText("")
    assert not next_button.isEnabled(), \
        "Empty verification accepted"

    backup_dlg.passphrase_line_edit.setText("")
    backup_dlg.passphrase_line_edit_verify.setText("fail")
    assert not next_button.isEnabled(), \
        "Empty passphrase accepted"

    backup_dlg.passphrase_line_edit.setText("")
    backup_dlg.passphrase_line_edit_verify.setText("")
    assert not next_button.isEnabled(), \
        "Empty passphrase and verification accepted"

    # check if next is active for a correct passphrase/verify
    # combination
    backup_dlg.passphrase_line_edit.setText("pass")
    backup_dlg.passphrase_line_edit_verify.setText("pass")
    assert next_button.isEnabled(), \
        "Matching passphrase/verification not accepted"


@mock.patch('builtins.open', new_callable=mock.mock_open)
def test_10_do_backup(mock_open, backup_dlg):

    next_button = backup_dlg.button(backup_dlg.WizardButton.NextButton)
    backup_dlg.select_vms_widget.remove_all_button.click()

    for i in range(backup_dlg.select_vms_widget.available_list.count()):
        item = backup_dlg.select_vms_widget.available_list.item(i)
        if "test-blue" in item.text():
            item.setSelected(True)

    backup_dlg.select_vms_widget.add_selected_button.click()
    next_button.click()

    assert backup_dlg.currentPage() is backup_dlg.select_dir_page

    for i in range(backup_dlg.appvm_combobox.count()):
        if backup_dlg.appvm_combobox.itemText(i) == 'dom0':
            backup_dlg.appvm_combobox.setCurrentIndex(i)
            break

    assert backup_dlg.appvm_combobox.currentText() == 'dom0'

    backup_dlg.dir_line_edit.setText("/home")
    backup_dlg.passphrase_line_edit.setText("pass")
    backup_dlg.passphrase_line_edit_verify.setText("pass")
    backup_dlg.save_profile_checkbox.setChecked(False)
    backup_dlg.turn_off_checkbox.setChecked(False)
    backup_dlg.compress_checkbox.setChecked(False)

    expected_call = ('dom0', 'admin.backup.Info', 'qubes-manager-backup-tmp',
                     None)
    assert expected_call not in backup_dlg.qubes_app.expected_calls
    backup_dlg.qubes_app.expected_calls[expected_call] = b'0\0backup summary'

    next_button.click()

    assert expected_call in backup_dlg.qubes_app.expected_calls

    expected_call = ('dom0', 'admin.backup.Execute', 'qubes-manager-backup-tmp',
                     None)
    assert expected_call not in backup_dlg.qubes_app.expected_calls
    backup_dlg.qubes_app.expected_calls[expected_call] = b'0\0'

    next_button.click()

    assert expected_call in backup_dlg.qubes_app.expected_calls

    written_conf = ""
    for c in mock_open.return_value.write.mock_calls:
        written_conf += c[1][0]

    assert written_conf == """compression: false
destination_path: /home
destination_vm: dom0
include:
- test-blue
passphrase_text: pass
"""


@mock.patch('qubesmanager.backup_utils.load_backup_profile')
def test_20_loading_settings(mock_load, test_qubes_app, qapp):

    mock_load.return_value = {
        'destination_vm': 'test-blue',
        'destination_path': "/home",
        'include': ['dom0', 'test-red', 'sys-net'],
        'passphrase_text': "longerPassPhrase",
        'compression': True
    }

    dispatcher = MockAsyncDispatcher(test_qubes_app)
    backup_dlg = backup.BackupVMsWindow(qapp, test_qubes_app, dispatcher)
    # needed because otherwise the wizard will not test correctly
    backup_dlg.show()

    # check if settings were loaded
    assert backup_dlg.appvm_combobox.currentText() == 'test-blue', \
        "Destination VMot loaded"
    assert backup_dlg.dir_line_edit.text() == "/home", \
        "Destination path not loaded"
    assert backup_dlg.passphrase_line_edit.text() == "longerPassPhrase", \
        "Passphrase not loaded"
    assert backup_dlg.passphrase_line_edit_verify.text() == "longerPassPhrase" \
        , "Passphrase verify not loaded"
    assert backup_dlg.compress_checkbox.isChecked()

    # check that 'include' vms were not pre-selected
    include_in_backups_no = len(
        [vm for vm in test_qubes_app.domains
         if not vm.features.get('internal', False)
         and getattr(vm, 'include_in_backups', True)])
    selected_no = backup_dlg.select_vms_widget.selected_list.count()
    assert include_in_backups_no == selected_no, "Incorrect VM list selected"

    # check no errors were detected
    assert not backup_dlg.unrecognized_config_label.isVisible()


@mock.patch('qubesmanager.backup_utils.load_backup_profile')
def test_21_loading_settings_error(mock_load, test_qubes_app, qapp):
    mock_load.return_value = {
        'destination_vm': "incorrect_vm",
    }

    dispatcher = MockAsyncDispatcher(test_qubes_app)
    backup_dlg = backup.BackupVMsWindow(qapp, test_qubes_app, dispatcher)
    # needed because otherwise the wizard will not test correctly
    backup_dlg.show()

    assert "incorrect_vm" in backup_dlg.warning_running_label.text()


@mock.patch('qubesmanager.backup_utils.load_backup_profile')
@mock.patch('PyQt6.QtWidgets.QMessageBox.information')
def test_22_loading_settings_exc(mock_info, mock_load, test_qubes_app, qapp):
    mock_load.side_effect = exc.QubesException('Error')

    dispatcher = MockAsyncDispatcher(test_qubes_app)
    backup_dlg = backup.BackupVMsWindow(qapp, test_qubes_app, dispatcher)
    # needed because otherwise the wizard will not test correctly
    backup_dlg.show()

    assert mock_info.call_count == 1, "Warning not shown"


@mock.patch('qubesmanager.backup_utils.write_backup_profile')
def test_23_cancel_confirm(mock_write, backup_dlg):
    backup_dlg.qubes_app.expected_calls[(
        'dom0', 'admin.backup.Info', 'qubes-manager-backup-tmp', None)] = \
        b'0\0backup output'

    backup_dlg.next()
    assert backup_dlg.currentPage() is backup_dlg.select_dir_page

    backup_dlg.appvm_combobox.setCurrentIndex(0)
    while not backup_dlg.appvm_combobox.currentText() == 'dom0':
        backup_dlg.appvm_combobox.setCurrentIndex(
            backup_dlg.appvm_combobox.currentIndex() + 1)

    backup_dlg.dir_line_edit.setText("/home")
    backup_dlg.passphrase_line_edit.setText("pass")
    backup_dlg.passphrase_line_edit_verify.setText("pass")

    backup_dlg.next()

    # attempt to cancel
    with unittest.mock.patch('os.remove') as mock_remove:
        backup_dlg.button(QtWidgets.QWizard.WizardButton.CancelButton).click()
        mock_remove.assert_called_once_with(
            '/etc/qubes/backup/qubes-manager-backup-tmp.conf')


@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
@mock.patch('qubesmanager.backup_utils.write_backup_profile')
def test_24_cancel_in_progress(mock_write, mock_warning,
                               backup_dlg):
    backup_dlg.qubes_app.expected_calls[(
        'dom0', 'admin.backup.Info', 'qubes-manager-backup-tmp', None)] = \
        b'0\0backup output'
    backup_dlg.qubes_app.expected_calls[(
        'dom0', 'admin.backup.Execute', 'qubes-manager-backup-tmp', None)] = \
        b'0\x00'

    backup_dlg.next()
    assert backup_dlg.currentPage() is backup_dlg.select_dir_page

    backup_dlg.appvm_combobox.setCurrentIndex(0)
    while not backup_dlg.appvm_combobox.currentText() == 'dom0':
        backup_dlg.appvm_combobox.setCurrentIndex(
            backup_dlg.appvm_combobox.currentIndex() + 1)

    backup_dlg.dir_line_edit.setText("/home")
    backup_dlg.passphrase_line_edit.setText("pass")
    backup_dlg.passphrase_line_edit_verify.setText("pass")

    backup_dlg.next()
    backup_dlg.next()

    # attempt to cancel
    with unittest.mock.patch('os.remove') as mock_remove:
        expected_call = ('dom0', 'admin.backup.Cancel',
                         'qubes-manager-backup-tmp', None)
        assert expected_call not in backup_dlg.qubes_app.actual_calls
        backup_dlg.qubes_app.expected_calls[expected_call] = b'0\x00'

        backup_dlg.button(QtWidgets.QWizard.WizardButton.CancelButton).click()

        mock_remove.assert_called_once_with(
            '/etc/qubes/backup/qubes-manager-backup-tmp.conf')
        assert expected_call in backup_dlg.qubes_app.actual_calls


def test_101_backup_thread_vm_on():
    vm = unittest.mock.Mock(spec=['is_running', 'app'],
                            **{'is_running.return_value': True})

    vm.app = unittest.mock.Mock()

    thread = backup.BackupThread(vm)
    thread.run()

    vm.app.qubesd_call.assert_called_with(
        'dom0', 'admin.backup.Execute', 'qubes-manager-backup-tmp')


def test_102_backup_thread_vm_off():
    vm = unittest.mock.Mock(spec=['is_running', 'app', 'start'],
                            **{'is_running.return_value': False})

    vm.app = unittest.mock.Mock()

    thread = backup.BackupThread(vm)
    thread.run()

    vm.app.qubesd_call.assert_called_with(
        'dom0', 'admin.backup.Execute', 'qubes-manager-backup-tmp')
    vm.start.assert_called_once_with()


def test_103_backup_thread_error():
    vm = unittest.mock.Mock(spec=['is_running', 'app'],
                            **{'is_running.return_value': True})

    vm.app = unittest.mock.Mock()
    vm.app.qubesd_call.side_effect = exc.QubesException('Error')

    thread = backup.BackupThread(vm)
    thread.run()

    assert thread.msg is not None
