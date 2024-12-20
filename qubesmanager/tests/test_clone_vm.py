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

from unittest import mock
import pytest

from qubesmanager import clone_vm

# empty entry means the cloneVM dialog was called without specifying source VM
TEST_VMS = ["test-blue", "test-red", ""]


@pytest.fixture
def clone_window(request, qapp, test_qubes_app):
    if request.param:
        vm = test_qubes_app.domains[request.param]
    else:
        vm = None
    qm = clone_vm.CloneVMDlg(qapp, test_qubes_app, src_vm=vm)
    return vm, qm


@pytest.mark.parametrize("clone_window", TEST_VMS, indirect=True)
def test_00_clone_loads(clone_window):
    vm, clone_dlg = clone_window
    assert clone_dlg.src_vm.count() > 0, "No source vms shown"
    assert clone_dlg.label.count() > 0, "No labels shown"
    assert clone_dlg.storage_pool.count() > 0, "No storage pools listed"
    if not vm:
        assert clone_dlg.src_vm.isEnabled(), "Source VM dialog active"
    else:
        assert not clone_dlg.src_vm.isEnabled(), "Source VM dialog not active"


@pytest.mark.parametrize("clone_window", TEST_VMS, indirect=True)
def test_01_cancel(clone_window):
    vm, clone_dlg = clone_window

    with (mock.patch('qubesmanager.common_threads.CloneVMThread') as
          mock_clone_thread):
        clone_dlg.buttonBox.button(
            clone_dlg.buttonBox.StandardButton.Cancel).click()

        assert mock_clone_thread.call_count == 0, ("Cancel caused a clone to "
                                                   "happen")


@pytest.mark.parametrize("clone_window", TEST_VMS, indirect=True)
def test_02_name_correctly_updates(clone_window):
    vm, clone_dlg = clone_window

    src_name = clone_dlg.src_vm.currentText()
    target_name = clone_dlg.name.text()

    if vm:
        assert src_name == vm.name, "Wrong VM preselected"
    assert src_name in target_name
    assert "clone" in target_name

    if vm:
        assert not clone_dlg.src_vm.isEnabled()
        return

    # select a different VM
    clone_dlg.src_vm.setCurrentIndex(clone_dlg.src_vm.currentIndex() + 1)

    src_name_2 = clone_dlg.src_vm.currentText()
    target_name_2 = clone_dlg.name.text()

    assert src_name != src_name_2
    assert src_name_2 in target_name_2
    assert "clone" in target_name_2


@pytest.mark.parametrize("clone_window", TEST_VMS, indirect=True)
def test_03_label_correctly_updates(clone_window):
    vm, clone_dlg = clone_window

    if vm:
        assert str(vm.label) in clone_dlg.label.currentText()
        return

    src_vm_1 = clone_dlg.app.domains[clone_dlg.src_vm.currentText()]
    assert str(src_vm_1.label) in clone_dlg.label.currentText()

    for i in range(clone_dlg.src_vm.count()):
        clone_dlg.src_vm.setCurrentIndex(i)
        selected_vm = clone_dlg.app.domains[clone_dlg.src_vm.currentText()]
        assert str(selected_vm.label) in clone_dlg.label.currentText()


@mock.patch('qubesmanager.common_threads.CloneVMThread')
@mock.patch('PyQt6.QtWidgets.QProgressDialog')
@mock.patch('PyQt6.QtWidgets.QMessageBox.information')
@pytest.mark.parametrize("clone_window", TEST_VMS, indirect=True)
def test_04_simple_clone(_mock_info, _mock_progress, mock_clone, clone_window):
    # info and progress are mocked to make sure no random windows slow down
    # the test / success does not hang the test
    vm, clone_dlg = clone_window
    clone_dlg.name.setText('clone-test')
    src_vm = clone_dlg.app.domains[clone_dlg.src_vm.currentText()]

    if vm:
        assert vm.name == src_vm.name

    clone_dlg.buttonBox.button(
        clone_dlg.buttonBox.StandardButton.Ok).click()

    assert mock_clone.call_count == 1
    mock_clone.assert_called_once_with(
        src_vm, "clone-test", pool=None, label=src_vm.label)
    mock_clone().start.assert_called_once_with()


@mock.patch('qubesmanager.common_threads.CloneVMThread')
@mock.patch('PyQt6.QtWidgets.QProgressDialog')
@mock.patch('PyQt6.QtWidgets.QMessageBox.information')
@pytest.mark.parametrize("clone_window", [""], indirect=True)
def test_05_simple_clone_2(_mock_info, _mock_progress, mock_clone,
                           clone_window):
    # info and progress are mocked to make sure no random windows slow down
    # the test / success does not hang the test
    vm, clone_dlg = clone_window

    for i in range(clone_dlg.src_vm.count()):
        if clone_dlg.src_vm.itemText(i) == 'test-standalone':
            clone_dlg.src_vm.setCurrentIndex(i)
            break
    clone_dlg.name.setText('clone-test')
    src_vm = clone_dlg.app.domains['test-standalone']
    clone_dlg.buttonBox.button(
        clone_dlg.buttonBox.StandardButton.Ok).click()

    assert mock_clone.call_count == 1
    mock_clone.assert_called_once_with(
        src_vm, "clone-test", pool=None, label=src_vm.label)
    mock_clone().start.assert_called_once_with()


@mock.patch('qubesmanager.common_threads.CloneVMThread')
@mock.patch('PyQt6.QtWidgets.QProgressDialog')
@mock.patch('PyQt6.QtWidgets.QMessageBox.information')
@pytest.mark.parametrize("clone_window", [""], indirect=True)
def test_06_complex_clone(_mock_info, _mock_progress, mock_clone,
                           clone_window):
    # info and progress are mocked to make sure no random windows slow down
    # the test / success does not hang the test
    _, clone_dlg = clone_window

    for i in range(clone_dlg.src_vm.count()):
        if clone_dlg.src_vm.itemText(i) == 'test-standalone':
            clone_dlg.src_vm.setCurrentIndex(i)
            break
    clone_dlg.name.setText('clone-test')
    src_vm = clone_dlg.app.domains['test-standalone']

    for i in range(clone_dlg.label.count()):
        if clone_dlg.label.itemText(i) == 'orange':
            clone_dlg.label.setCurrentIndex(i)
            break

    for i in range(clone_dlg.storage_pool.count()):
        if clone_dlg.storage_pool.itemText(i) == 'vm-pool':
            clone_dlg.storage_pool.setCurrentIndex(i)
            break

    clone_dlg.buttonBox.button(
        clone_dlg.buttonBox.StandardButton.Ok).click()

    assert mock_clone.call_count == 1
    mock_clone.assert_called_once_with(
        src_vm, "clone-test", label=clone_dlg.app.labels[
            "orange"], pool='vm-pool')
    mock_clone().start.assert_called_once_with()


@mock.patch('qubesmanager.common_threads.CloneVMThread')
@mock.patch('PyQt6.QtWidgets.QProgressDialog')
@mock.patch('PyQt6.QtWidgets.QMessageBox.information')
@mock.patch('subprocess.check_call')
@pytest.mark.parametrize("clone_window", TEST_VMS, indirect=True)
def test_07_launch_settings(mock_subprocess, _mock_info, _mock_progress,
                         _mock_clone, clone_window):
    # info and progress are mocked to make sure no random windows slow down
    # the test / success does not hang the test
    vm, clone_dlg = clone_window
    clone_dlg.name.setText('clone-test')
    clone_dlg.launch_settings.setChecked(True)

    clone_dlg.buttonBox.button(
        clone_dlg.buttonBox.StandardButton.Ok).click()

    mock_subprocess(['qubes-vm-settings', "clone-test"])
