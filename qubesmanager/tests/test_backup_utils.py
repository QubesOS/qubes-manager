# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2024 Marta Marczykowska-Górecka
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
import subprocess
import threading
from unittest import mock

from PyQt6 import QtCore, QtWidgets

from qubesmanager import backup_utils


def test_01_fill_apvms(qapp, test_qubes_app):
    # this needs the qapp import to make sure QApplication doesn't go weird

    dialog = QtWidgets.QDialog()
    combobox = QtWidgets.QComboBox()
    dialog.appvm_combobox = combobox
    dialog.qubes_app = test_qubes_app

    backup_utils.fill_appvms_list(dialog)

    # see if the dialog has nothing selected
    assert combobox.currentIndex() == 0, "Incorrect item selected"

    # the combobox should contain running VMs that are not internal and
    #  not template
    expected_vm_list = [vm.name for vm in test_qubes_app.domains
                        if vm.is_running() and vm.klass != 'TemplateVM'
                        and not vm.features.get('internal', False)]
    received_vm_list = []
    for i in range(combobox.count()):
        received_vm_list.append(combobox.itemText(i))

    assert sorted(expected_vm_list) == sorted(received_vm_list), \
        "VM list not filled correctly"


def make_path_dialog(qubes_app, vm_name):
    dialog = QtWidgets.QDialog()
    dialog.qubes_app = qubes_app
    dialog.dir_line_edit = QtWidgets.QLineEdit(dialog)
    dialog.select_path_button = QtWidgets.QPushButton(dialog)
    dialog.appvm_combobox = QtWidgets.QComboBox(dialog)
    dialog.appvm_combobox.addItem(vm_name)
    return dialog


def test_02_select_path_keeps_event_loop(qapp, test_qubes_app):
    """Qt events still run while the qube's path dialog is open."""
    dialog = make_path_dialog(test_qubes_app, 'test-vm')
    timer_fired = threading.Event()
    enabled_while_waiting = []

    def on_timer():
        enabled_while_waiting.append(dialog.isEnabled())
        timer_fired.set()

    def fake_get_path(_vm, _service_name):
        return '/home/user/backups' if timer_fired.wait(5) else None

    QtCore.QTimer.singleShot(0, on_timer)
    with mock.patch('qubesmanager.utils.get_path_from_vm', fake_get_path):
        backup_utils.select_path_button_clicked(dialog)

    assert dialog.dir_line_edit.text() == '/home/user/backups'
    assert enabled_while_waiting == [False]
    assert dialog.isEnabled()


def test_03_select_path_error_from_qube(qapp, test_qubes_app):
    """An error in the qube's path dialog is shown to the user."""
    dialog = make_path_dialog(test_qubes_app, 'test-vm')
    error = subprocess.CalledProcessError(2, 'qubes.SelectDirectory')

    with mock.patch('qubesmanager.utils.get_path_from_vm',
                    side_effect=error), \
            mock.patch.object(QtWidgets.QMessageBox, 'warning') as warning:
        backup_utils.select_path_button_clicked(dialog)

    warning.assert_called_once()
    assert dialog.dir_line_edit.text() == ''
    assert dialog.isEnabled()


def test_04_select_path_cancel_read_only(qapp, test_qubes_app):
    """Cancelling the qube's dialog in read-only mode shows no warning."""
    dialog = make_path_dialog(test_qubes_app, 'test-vm')
    error = subprocess.CalledProcessError(1, 'qubes.SelectDirectory')

    with mock.patch('qubesmanager.utils.get_path_from_vm',
                    side_effect=error), \
            mock.patch.object(QtWidgets.QMessageBox, 'warning') as warning:
        backup_utils.select_path_button_clicked(dialog, read_only=True)

    warning.assert_not_called()
    assert dialog.isEnabled()
