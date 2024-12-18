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

import contextlib
import subprocess
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QSettings, QItemSelectionModel
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QMessageBox

from unittest import mock

import pytest

from qubesadmin import exc
from .. import qube_manager
from qubesadmin.tests.mock_app import (MockDispatcher, MockAsyncDispatcher,
                                       MockEvent, MockQube)

import asyncio

FEDORA_OLD = 'fedora-35'
FEDORA_LATEST = 'fedora-36'

@pytest.fixture
def qubes_manager(qapp, test_qubes_app):
    dispatcher = MockAsyncDispatcher(test_qubes_app)
    qm = qube_manager.VmManagerWindow(qapp, test_qubes_app, dispatcher)
    return qm


def _select_vm(dialog: qube_manager.VmManagerWindow, vm_name, *additonal_vms):
    """
    Select any number of vms provided, raise error if unsucessful.
    """
    dialog.table.selectionModel().clear()
    mode = (QItemSelectionModel.SelectionFlag.Select |
            QItemSelectionModel.SelectionFlag.Rows)

    vms_to_select = {vm_name}
    for vm in additonal_vms:
        vms_to_select.add(vm)

    for row in range(dialog.table.model().rowCount()):
        idx = dialog.table.model().index(
            row, dialog.qubes_model.columns_indices.index("Name"))
        current_name = dialog.table.model().data(
            idx, Qt.ItemDataRole.DisplayRole)

        if current_name in vms_to_select:
            dialog.table.selectionModel().select(idx, mode)
            vms_to_select.remove(current_name)

    if vms_to_select:
        raise ValueError


def _count_visible_rows(table):
    """Count how many rows are visible (not filtered out)"""
    result = 0
    for i in range(table.model().rowCount()):
        if not table.isRowHidden(i):
            result += 1
    return result


def _get_current_vms(qm):
    """Get a set of names of currently visible vms"""
    model = qm.table.model()
    col_indices = qm.qubes_model.columns_indices
    result = []
    for row in range(model.rowCount()):
        # name
        index_name = model.index(row, col_indices.index("Name"))
        vm_name = model.data(index_name, Qt.ItemDataRole.DisplayRole)
        result.append(vm_name)
    return sorted(result)


def _get_column_value(qm, column_name, vm_name,
                      role = Qt.ItemDataRole.DisplayRole):
    model = qm.table.model()
    col_indices = qm.qubes_model.columns_indices
    for row in range(model.rowCount()):
        # name
        index_name = model.index(row, col_indices.index("Name"))
        name = model.data(index_name, Qt.ItemDataRole.DisplayRole)
        if name == vm_name:
            idx = model.index(row, col_indices.index(column_name))
            val = model.data(idx, role)
            return val
    else:
        raise KeyError(vm_name)


def _check_sorting(qm, column_name):
    """
    Check if model is sorted in ascending order on the provided column
    """
    last_text = None
    last_vm = None

    model = qm.table.model()
    column = qm.qubes_model.columns_indices.index(column_name)
    name_column = qm.qubes_model.columns_indices.index("Name")

    for row in range(model.rowCount()):
        vm_name = model.index(row,
                              name_column).data(Qt.ItemDataRole.DisplayRole)
        column_data = model.index(row, column).data(Qt.ItemDataRole.DisplayRole)

        if row == 0:
            assert vm_name == 'dom0'
        elif last_text is None:
            last_text = column_data
            last_vm = vm_name
        else:
            if last_text == column_data:
                assert vm_name.lower() > last_vm.lower()
            else:
                assert column_data.lower() > last_text.lower()
            last_text = column_data
            last_vm = vm_name


def _is_icon(icon, icon_name: str = 'on'):
    """This is a helper method, returning True if provided icon is the same
    as QIcon for the on.png file, False if it is empty icon, and ValueError
    if some other item was found"""
    ref_icon = QIcon(f":/{icon_name}.png").pixmap(64).toImage()
    off_icon = QIcon().pixmap(64).toImage()
    my_icon = icon.pixmap(64).toImage()

    if my_icon == ref_icon:
        return True
    if my_icon == off_icon:
        return False
    raise ValueError


def test_000_window_loads(qapp, test_qubes_app):
    dispatcher = MockDispatcher(test_qubes_app)

    with mock.patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warning:
        qm = qube_manager.VmManagerWindow(qapp, test_qubes_app, dispatcher)
        assert mock_warning.call_count == 0
        assert qm.table is not None
        assert qm.table.model().rowCount() > 0


def test_001_model_correctness(qapp, test_qubes_app):
    dispatcher = MockDispatcher(test_qubes_app)
    qm = qube_manager.VmManagerWindow(qapp, test_qubes_app, dispatcher)

    model = qm.qubes_model

    domains = list(test_qubes_app.domains)

    # number of domains
    assert model.rowCount(None) == len(domains)

    # domain data
    for row in range(model.rowCount(None)):
        # name
        index_name = model.index(row, model.columns_indices.index("Name"))
        vm_name = model.data(index_name, Qt.ItemDataRole.DisplayRole)
        assert vm_name in domains

        vm_object = test_qubes_app.domains[vm_name]

        # label
        index_label = model.index(row, model.columns_indices.index("Label"))
        text = model.data(index_label, Qt.ItemDataRole.DisplayRole)
        assert text is None
        vm_label_pixmap = model.data(index_label,
                                     Qt.ItemDataRole.DecorationRole)
        assert isinstance(vm_label_pixmap, QPixmap)
        assert vm_label_pixmap == model.label_pixmap[vm_object.icon]

        # template
        index_template = model.index(row, model.columns_indices.index(
            "Template"))
        template_data = model.data(index_template, Qt.ItemDataRole.DisplayRole)
        if hasattr(vm_object, 'template'):
            assert vm_object.template == template_data
        else:
            assert vm_object.klass == template_data

        # netvm
        index_netvm = model.index(row, model.columns_indices.index(
            "NetVM"))
        netvm_data = model.data(index_netvm, Qt.ItemDataRole.DisplayRole)
        if getattr(vm_object, 'netvm', None):
            assert str(vm_object.netvm) in netvm_data
            if vm_object.property_is_default('netvm'):
                assert 'default' in netvm_data.lower()
        else:
            assert 'n/a' in netvm_data

        # internal
        index_internal = model.index(row, model.columns_indices.index(
            "Internal"))
        internal_data = model.data(index_internal, Qt.ItemDataRole.DisplayRole)
        if getattr(vm_object, 'internal', False):
            assert internal_data == "Yes"

        # disk usage
        du_index = model.index(row, model.columns_indices.index(
            "Disk Usage"))
        du_data = model.data(du_index, Qt.ItemDataRole.DisplayRole)

        if vm_object.klass == 'AdminVM':
            assert du_data == 'n/a'
        else:
            expected_size = round(
                vm_object.get_disk_utilization() / (1024 * 1024), 2)
            assert str(expected_size) in du_data

        # ip
        ip_index = model.index(row, model.columns_indices.index(
            "IP Address"))
        ip_data = model.data(ip_index, Qt.ItemDataRole.DisplayRole)

        if not hasattr(vm_object, 'ip') or not getattr(vm_object, 'netvm'):
            assert ip_data == 'n/a'
        else:
            assert ip_data == vm_object.ip

        # include in backups
        bkp_index = model.index(row, model.columns_indices.index(
            "Backup"))
        # convert the checkstate to bool
        bkp_data = (model.data(bkp_index, Qt.ItemDataRole.CheckStateRole)
                    == Qt.CheckState.Checked)

        assert bkp_data == getattr(vm_object, 'include_in_backups', False)

        # default dispvm
        index_dispvm = model.index(row, model.columns_indices.index(
            "Default DispVM"))
        dispvm_data = model.data(index_dispvm, Qt.ItemDataRole.DisplayRole)
        if getattr(vm_object, 'default_dispvm', None):
            assert str(vm_object.default_dispvm) in dispvm_data
            if vm_object.property_is_default('default_dispvm'):
                assert 'default' in dispvm_data.lower()
        else:
            assert 'n/a' in dispvm_data

        # is dvm template
        index_dvm_template = model.index(row, model.columns_indices.index(
            "Is DVM Template"))
        dvm_template_data = model.data(index_dvm_template,
                                 Qt.ItemDataRole.DisplayRole)

        assert dvm_template_data == ("Yes"
                                     if getattr(
            vm_object, 'template_for_dispvms', False) else "")


def test_002_incorrect_settings_file(qapp, test_qubes_app):
    mock_settings = mock.MagicMock(spec=QSettings)
    settings_result_dict = {"view/sort_column": "Cthulhu",
                            "view/sort_order": "Fhtagn",
                            "view/menubar_visible": "R'lyeh"}
    mock_settings.side_effect = (
        lambda x, *args, **kwargs: settings_result_dict.get(x))

    with mock.patch('PyQt6.QtCore.QSettings.value', mock_settings), \
            mock.patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warning:
        dispatcher = MockDispatcher(test_qubes_app)
        qube_manager.VmManagerWindow(qapp, test_qubes_app, dispatcher)
        assert mock_warning.call_count == 1


def test_003_sorting(qubes_manager):
    name_column = qubes_manager.qubes_model.columns_indices.index("Name")
    template_column = qubes_manager.qubes_model.columns_indices.index("Template")

    qubes_manager.table.sortByColumn(template_column, Qt.SortOrder.AscendingOrder)
    _check_sorting(qubes_manager, "Template")

    qubes_manager.table.sortByColumn(name_column, Qt.SortOrder.AscendingOrder)
    _check_sorting(qubes_manager, "Name")


@mock.patch('qubesmanager.qube_manager.QSettings.setValue')
def test_004_hide_column(mock_settings, qubes_manager):
    action_no = qubes_manager.qubes_model.columns_indices.index(
        'Is DVM Template')
    qubes_manager.menu_view.actions()[action_no].trigger()

    mock_settings.assert_called_with('columns/Is DVM Template', True)

    qubes_manager.menu_view.actions()[action_no].trigger()
    mock_settings.assert_called_with('columns/Is DVM Template', False)


@mock.patch('qubesmanager.settings.VMSettingsWindow')
def test_200_vm_open_settings(mock_window, qubes_manager):
    _select_vm(qubes_manager, 'test-blue')

    qubes_manager.action_settings.trigger()

    mock_window.assert_called_once_with(
        "test-blue", "basic", mock.ANY, mock.ANY, qubes_manager)


@mock.patch('qubesmanager.settings.VMSettingsWindow')
def test_201_vm_open_firewall(mock_window, qubes_manager):
    _select_vm(qubes_manager, 'test-blue')

    qubes_manager.action_editfwrules.trigger()

    mock_window.assert_called_once_with(
        "test-blue", "firewall", mock.ANY, mock.ANY, qubes_manager)


@mock.patch('qubesmanager.settings.VMSettingsWindow')
def test_202_vm_open_apps(mock_window, qubes_manager):
    _select_vm(qubes_manager, 'test-blue')

    qubes_manager.action_appmenus.trigger()

    mock_window.assert_called_once_with(
        "test-blue", "applications", mock.ANY, mock.ANY, qubes_manager)


@mock.patch('qubesmanager.settings.VMSettingsWindow')
def test_203_vm_settings_dom0(mock_window, qubes_manager):
    _select_vm(qubes_manager, 'dom0')

    assert not qubes_manager.action_settings.isEnabled()
    qubes_manager.action_settings.trigger()
    # this should fail, the action should be inactive and not happen
    mock_window.assert_not_called()

    # some other actions should also be disabled
    assert not qubes_manager.action_editfwrules.isEnabled()
    assert not qubes_manager.action_appmenus.isEnabled()
    assert not qubes_manager.action_run_command_in_vm.isEnabled()


@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
def test_204_vm_keyboard(mock_message, qubes_manager):
    # should not be enabled on dom0
    _select_vm(qubes_manager, 'dom0')

    assert not qubes_manager.action_set_keyboard_layout.isEnabled()

    # get a running VM that supports keyboard layout
    _select_vm(qubes_manager, 'sys-usb')

    assert qubes_manager.action_set_keyboard_layout.isEnabled()

    vm = qubes_manager.qubes_app.domains['sys-usb']

    with mock.patch.object(vm, 'run') as mock_run:
        qubes_manager.action_set_keyboard_layout.trigger()
        mock_run.assert_called_once_with("qubes-change-keyboard-layout")

    mock_message.assert_not_called()


def test_205_update_vm_admin(qubes_manager):
    _select_vm(qubes_manager, 'dom0')

    with mock.patch('qubesmanager.qube_manager.UpdateVMsThread') as mock_update:
        qubes_manager.action_updatevm.trigger()
        mock_update.assert_called_once_with(['dom0'])
        mock_update().start.assert_called_once_with()


@mock.patch("PyQt6.QtWidgets.QInputDialog.getText",
            return_value=("command to run", True))
def test_206_run_command_in_vm(_mock_command, qubes_manager):
    _select_vm(qubes_manager, 'test-blue')

    with (mock.patch('qubesmanager.qube_manager.RunCommandThread') as
            mock_thread):
        qubes_manager.action_run_command_in_vm.trigger()
        mock_thread.assert_called_once_with('test-blue', "command to run")
        mock_thread().finished.connect.assert_called_once_with(
            qubes_manager.clear_threads)
        mock_thread().start.assert_called_once_with()


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
def test_207_pausevm(mock_warn, qubes_manager):
    # get a running vm
    _select_vm(qubes_manager, 'test-blue')

    assert qubes_manager.action_pausevm.isEnabled()

    vm = qubes_manager.qubes_app.domains['test-blue']

    with mock.patch.object(vm, 'pause') as mock_pause:
        qubes_manager.action_pausevm.trigger()
        mock_pause.assert_called_once_with()
        assert mock_warn.call_count == 0

        mock_pause.side_effect = exc.QubesException('Error')
        qubes_manager.action_pausevm.trigger()
        assert mock_warn.call_count == 1


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
def test_208_resumevm(mock_warn, qubes_manager):
    # get a normal running vm
    _select_vm(qubes_manager, 'test-blue')

    assert not qubes_manager.action_resumevm.isEnabled()

    # get a non-running vm
    _select_vm(qubes_manager, 'test-red')

    vm = qubes_manager.qubes_app.domains['test-red']

    with mock.patch.object(vm, 'get_power_state') as mock_state, \
            mock.patch.object(vm, 'unpause') as mock_unpause:
        mock_state.return_value = 'Paused'
        qubes_manager.action_resumevm.trigger()
        mock_unpause.assert_called_once_with()

    with mock.patch('qubesmanager.qube_manager.StartVMThread') as mock_thread:
        qubes_manager.action_resumevm.trigger()
        mock_thread.assert_called_once_with(vm)
        mock_thread().finished.connect.assert_called_once_with(
            qubes_manager.clear_threads)
        mock_thread().start.assert_called_once_with()

    assert mock_warn.call_count == 0

@mock.patch("PyQt6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes)
@mock.patch('PyQt6.QtCore.QTimer.singleShot')
@mock.patch('qubesmanager.qube_manager.VmShutdownMonitor')
def test_209_shutdownvm(mock_monitor, mock_timer, _mock_question,
                        qubes_manager):
    # get a non-running vm
    _select_vm(qubes_manager, 'test-red')
    assert not qubes_manager.action_shutdownvm.isEnabled()

    _select_vm(qubes_manager, 'test-blue')
    assert qubes_manager.action_shutdownvm.isEnabled()
    vm = qubes_manager.qubes_app.domains['test-blue']

    with mock.patch.object(vm, 'shutdown') as mock_shutdown:
        qubes_manager.action_shutdownvm.trigger()
        mock_shutdown.assert_called_once_with(force=False)
        mock_monitor.assert_called_once_with(vm, mock.ANY, mock.ANY, mock.ANY)
        mock_timer.assert_called_once_with(mock.ANY, mock.ANY)


@mock.patch('qubesmanager.create_new_vm.NewVmDlg')
def test_210_create_vm(mock_new_vm, qubes_manager):
    assert qubes_manager.action_createvm.isEnabled()
    qubes_manager.action_createvm.trigger()
    assert mock_new_vm.call_count == 1


def test_211_remove_adminvm(qubes_manager):
    _select_vm(qubes_manager, 'dom0')

    assert not qubes_manager.action_removevm.isEnabled()


@mock.patch("qubesmanager.qube_manager.QMessageBox")
def test_212_remove_vm_dependencies(mock_msgbox, qubes_manager):
    # select a vm in use
    _select_vm(qubes_manager, FEDORA_LATEST)

    qubes_manager.action_removevm.trigger()

    mock_msgbox().show.assert_called_with()


@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
@mock.patch("PyQt6.QtWidgets.QInputDialog.getText")
def test_213_remove_vm_no_dependencies(mock_input, mock_warning, qubes_manager):
    # get a non-running vm
    _select_vm(qubes_manager, 'test-red')

    with (mock.patch('qubesmanager.common_threads.RemoveVMThread') as
          mock_thread):
        # user cancels
        mock_input.return_value = ('test-red', False)
        qubes_manager.action_removevm.trigger()
        assert mock_thread.call_count == 0
        assert mock_warning.call_count == 0

        mock_input.return_value = ("wrong_name", True)
        qubes_manager.action_removevm.trigger()
        assert mock_warning.call_count == 1
        assert mock_thread.call_count == 0

        mock_input.return_value = ('test-red', True)
        qubes_manager.action_removevm.trigger()
        assert mock_warning.call_count == 1
        mock_thread.assert_called_once_with(
            qubes_manager.qubes_app.domains['test-red'])
        mock_thread().finished.connect.assert_called_once_with(
            qubes_manager.clear_threads)
        mock_thread().start.assert_called_once_with()


@mock.patch('PyQt6.QtCore.QTimer.singleShot')
@mock.patch('qubesmanager.qube_manager.VmShutdownMonitor')
@mock.patch("PyQt6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes)
def test_214_restartvm(_msgbox, mock_monitor, _qtimer, qubes_manager):
    # get a non-running vm
    _select_vm(qubes_manager, 'test-red')

    assert not qubes_manager.action_restartvm.isEnabled()

    # get a running vm
    _select_vm(qubes_manager, 'test-blue')
    assert qubes_manager.action_restartvm.isEnabled()
    vm = qubes_manager.qubes_app.domains['test-blue']

    with mock.patch.object(vm, 'shutdown') as mock_shutdown:
        qubes_manager.action_restartvm.trigger()
        mock_shutdown.assert_called_once_with(force=True)
        mock_monitor.assert_called_once_with(vm, 1000, True, mock.ANY)


@mock.patch('qubesmanager.qube_manager.UpdateVMsThread')
def test_215_updatevm_template(mock_thread, qapp, test_qubes_app):
    test_qubes_app._qubes[FEDORA_OLD].properties['updateable'].value\
        = True
    test_qubes_app.update_vm_calls()

    dispatcher = MockDispatcher(test_qubes_app)
    qubes_manager = qube_manager.VmManagerWindow(qapp, test_qubes_app,
                                                 dispatcher)

    _select_vm(qubes_manager, FEDORA_OLD)
    assert qubes_manager.action_updatevm.isEnabled()

    qubes_manager.action_updatevm.trigger()
    mock_thread.assert_called_once_with([FEDORA_OLD])
    mock_thread().finished.connect.assert_called_once_with(
        qubes_manager.clear_threads)
    mock_thread().start.assert_called_once_with()


@mock.patch("PyQt6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes)
def test_216_killvm(_mock_question, qubes_manager):
    # get a non-running vm
    _select_vm(qubes_manager, 'test-red')

    assert not qubes_manager.action_killvm.isEnabled()

    # get a running vm
    _select_vm(qubes_manager, 'test-blue')
    assert qubes_manager.action_killvm.isEnabled()

    vm = qubes_manager.qubes_app.domains['test-blue']

    with mock.patch.object(vm, 'kill') as mock_kill:
        qubes_manager.action_killvm.trigger()
        mock_kill.assert_called_once_with()


@mock.patch("PyQt6.QtWidgets.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Cancel)
def test_217_killvm_cancel(_mock_question, qubes_manager):
    # get a running vm
    _select_vm(qubes_manager, 'test-blue')
    assert qubes_manager.action_killvm.isEnabled()

    vm = qubes_manager.qubes_app.domains['test-blue']

    with mock.patch.object(vm, 'kill') as mock_kill:
        qubes_manager.action_killvm.trigger()
        mock_kill.assert_not_called()


@mock.patch('subprocess.Popen')
def test_220_global_config(mock_subprocess, qubes_manager):
    qubes_manager.action_global_settings.trigger()
    mock_subprocess.assert_called_once_with(['qubes-global-config'])

    _select_vm(qubes_manager, 'test-blue')

    qubes_manager.action_global_settings.trigger()
    assert mock_subprocess.call_count == 2


@mock.patch('qubesmanager.backup.BackupVMsWindow')
@mock.patch('qubesmanager.restore.RestoreVMsWindow')
def test_221_backup_restore(mock_restore, mock_backup, qubes_manager):
    assert qubes_manager.action_backup.isEnabled()
    qubes_manager.action_backup.trigger()
    assert mock_backup.call_count == 1
    assert mock_restore.call_count == 0

    assert qubes_manager.action_restore.isEnabled()
    qubes_manager.action_restore.trigger()
    assert mock_backup.call_count == 1
    assert mock_restore.call_count == 1


@mock.patch('qubesmanager.qube_manager.AboutDialog')
def test_222_about(mock_about, qubes_manager):
    assert qubes_manager.action_about_qubes.isEnabled()
    qubes_manager.action_about_qubes.trigger()
    assert mock_about.call_count == 1


def test_223_exit_action(qubes_manager):
    qubes_manager.action_exit.isEnabled()
    with mock.patch.object(qubes_manager, 'close') as mock_close:
        qubes_manager.action_exit.trigger()
        mock_close.assert_called_once_with()


@mock.patch('subprocess.Popen')
def test_224_template_manager(mock_subprocess, qubes_manager):
    assert qubes_manager.action_manage_templates.isEnabled()
    qubes_manager.action_manage_templates.trigger()
    mock_subprocess.assert_called_once_with(['qubes-template-manager'])


@mock.patch('qubesmanager.clone_vm.CloneVMDlg')
def test_225_clonevm(mock_clone, qubes_manager):
    _select_vm(qubes_manager, 'dom0')
    assert not qubes_manager.action_clonevm.isEnabled()

    _select_vm(qubes_manager, 'test-blue')
    assert qubes_manager.action_clonevm.isEnabled()

    qubes_manager.action_clonevm.trigger()

    mock_clone.assert_called_once_with(
        mock.ANY, mock.ANY, src_vm=qubes_manager.qubes_app.domains['test-blue'])


def test_230_search_action(qtbot, qubes_manager):
    qubes_manager.qt_app.setActiveWindow(qubes_manager.searchbox)
    qubes_manager.action_search.trigger()
    assert qubes_manager.searchbox.hasFocus()

    # input text
    qubes_manager.searchbox.setText("sys")
    # click outside the widget
    qtbot.mouseClick(qubes_manager.table, Qt.MouseButton.LeftButton)
    assert not qubes_manager.searchbox.hasFocus()
    # click the widget, check if it is correctly activated and the whole
    # text was selected
    qtbot.mouseClick(qubes_manager.searchbox, Qt.MouseButton.LeftButton)
    assert qubes_manager.searchbox.hasFocus()
    assert qubes_manager.searchbox.selectedText() == "sys"


def test_235_searchbox(qubes_manager):
    qubes_manager.searchbox.setText("sys")
    expected_number = \
        len([vm for vm in qubes_manager.qubes_app.domains if "sys" in vm.name])
    actual_number = _count_visible_rows(qubes_manager.table)
    assert expected_number == actual_number

    # clear search
    qubes_manager.searchbox.setText("")
    expected_number = len([vm for vm in qubes_manager.qubes_app.domains
                           if not vm.features.get('internal', False)])
    actual_number = _count_visible_rows(qubes_manager.table)
    assert expected_number == actual_number


def test_235_hide_show_toolbars(qubes_manager):
    with mock.patch('PyQt6.QtCore.QSettings.setValue')\
                    as mock_setvalue:
        qubes_manager.action_menubar.trigger()
        mock_setvalue.assert_called_with('view/menubar_visible', False)
        qubes_manager.action_toolbar.trigger()
        mock_setvalue.assert_called_with('view/toolbar_visible', False)
        assert not qubes_manager.menubar.isVisible()
        assert not qubes_manager.toolbar.isVisible()


def test_236_clear_searchbox(qubes_manager, qtbot):
    qubes_manager.searchbox.setText("text")
    assert qubes_manager.searchbox.text() == "text"

    qtbot.keyPress(qubes_manager, Qt.Key.Key_Escape)

    assert qubes_manager.searchbox.text() == ""

    expected_number = len([vm for vm in qubes_manager.qubes_app.domains
                           if not vm.features.get('internal', False)])
    actual_number = _count_visible_rows(qubes_manager.table)
    assert expected_number == actual_number


### Test right click menus - template and netvm


@pytest.mark.asyncio(loop_scope="module")
@mock.patch('PyQt6.QtWidgets.QMessageBox.question')
async def test_300_netvm_menu(mock_question, qubes_manager):
    mock_question.return_value = QMessageBox.StandardButton.Yes

    # select a template
    _select_vm(qubes_manager, FEDORA_OLD)
    assert not qubes_manager.network_menu.isEnabled()

    # select a normal qube
    _select_vm(qubes_manager, 'test-blue')
    vm_object = qubes_manager.qubes_app.domains['test-blue']

    assert qubes_manager.network_menu.isEnabled()

    # check if network menu has sensible contents
    if vm_object.property_is_default('netvm'):
        current_netvm = 'default ({})'
    elif vm_object.netvm:
        current_netvm = '{}'
    else:
        current_netvm = 'n/a'
    current_netvm = current_netvm.format(vm_object.netvm)

    expected_vms = {str(vm) for vm in qubes_manager.qubes_app.domains if
                    getattr(vm, 'provides_network', False)}

    expected_vms.add('None')
    expected_vms.add('default ({})'.format(
        vm_object.property_get_default('netvm')))

    current_vms = set()

    for action in qubes_manager.network_menu.actions():
        current_vms.add(action.text())
        if action.text() == current_netvm:
            assert _is_icon(action.icon(), 'on')
        else:
            assert not _is_icon(action.icon(), 'on')

    assert current_vms == expected_vms

    # attempt to change netvm to something
    change_netvm_call = ('test-blue', 'admin.vm.property.Set',
                         'netvm', b'sys-net')
    assert change_netvm_call not in qubes_manager.qubes_app.actual_calls
    qubes_manager.qubes_app.expected_calls[change_netvm_call] = \
        b'0\x00'

    assert vm_object.netvm == 'sys-firewall'

    for action in qubes_manager.network_menu.actions():
        if action.text() == 'sys-net':
            action.trigger()

    assert change_netvm_call in qubes_manager.qubes_app.actual_calls

    # simulate firing property-set and new value
    qubes_manager.qubes_app._qubes['test-blue'].netvm = 'sys-net'
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:netvm',
                  [('name', 'netvm'), ('newvalue', 'sys-net')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    # check current state

    # select a template
    _select_vm(qubes_manager, FEDORA_OLD)
    assert not qubes_manager.network_menu.isEnabled()

    # select a normal qube
    _select_vm(qubes_manager, 'test-blue')
    vm_object = qubes_manager.qubes_app.domains['test-blue']

    if vm_object.property_is_default('netvm'):
        current_netvm = 'default ({})'
    elif vm_object.netvm:
        current_netvm = '{}'
    else:
        current_netvm = 'n/a'
    current_netvm = current_netvm.format(vm_object.netvm)

    for action in qubes_manager.network_menu.actions():
        if action.text() == current_netvm:
            assert _is_icon(action.icon())
        else:
            assert not _is_icon(action.icon())


@mock.patch('PyQt6.QtWidgets.QMessageBox.question')
def test_301_netvm_menu_none(mock_question, qubes_manager):
    mock_question.return_value = QMessageBox.StandardButton.Yes

    # select a normal qube
    _select_vm(qubes_manager, 'test-blue')
    vm_object = qubes_manager.qubes_app.domains['test-blue']

    assert qubes_manager.network_menu.isEnabled()

    # attempt to change netvm to none
    change_netvm_none_call = ('test-blue', 'admin.vm.property.Set',
                         'netvm', b'')
    assert change_netvm_none_call not in qubes_manager.qubes_app.actual_calls
    qubes_manager.qubes_app.expected_calls[change_netvm_none_call] = \
        b'0\x00'

    assert vm_object.netvm == 'sys-firewall'

    for action in qubes_manager.network_menu.actions():
        if action.text() == 'None':
            assert not _is_icon(action.icon())
            action.trigger()
            break
    else:
        assert False

    assert change_netvm_none_call in qubes_manager.qubes_app.actual_calls


@mock.patch('PyQt6.QtWidgets.QMessageBox.question')
def test_302_netvm_menu_default(mock_question, qubes_manager):
    mock_question.return_value = QMessageBox.StandardButton.Yes

    # select a normal qube
    _select_vm(qubes_manager, 'test-red')
    vm_object = qubes_manager.qubes_app.domains['test-red']

    assert qubes_manager.network_menu.isEnabled()

    # attempt to change netvm to default
    change_netvm_default_call = ('test-red', 'admin.vm.property.Reset',
                         'netvm', None)
    assert change_netvm_default_call not in qubes_manager.qubes_app.actual_calls
    qubes_manager.qubes_app.expected_calls[change_netvm_default_call] = \
        b'0\x00'

    assert vm_object.netvm == 'sys-firewall'

    for action in qubes_manager.network_menu.actions():
        if 'default' in action.text().lower():
            assert not _is_icon(action.icon())
            action.trigger()
            break
    else:
        assert False

    assert change_netvm_default_call in qubes_manager.qubes_app.actual_calls


@mock.patch('PyQt6.QtWidgets.QMessageBox.question')
def test_303_netvm_menu_multiple(mock_question, qubes_manager):
    mock_question.return_value = QMessageBox.StandardButton.Yes

    target_vm_names = ['test-red', 'test-standalone', 'vault']

    _select_vm(qubes_manager, *target_vm_names)

    assert qubes_manager.network_menu.isEnabled()

    for action in qubes_manager.network_menu.actions():
        if action.text() == 'sys-firewall':
            assert _is_icon(action.icon(), 'transient')
        elif action.text() == 'None':
            assert _is_icon(action.icon(), 'transient')
        else:
            assert not _is_icon(action.icon())

    # attempt to change netvm to sys-net
    calls = []
    for vm in target_vm_names:
        call = (vm, 'admin.vm.property.Set', 'netvm', b'sys-net')
        assert call not in qubes_manager.qubes_app.actual_calls
        qubes_manager.qubes_app.expected_calls[call] = b'0\x00'
        calls.append(call)

    # change to specific value
    for action in qubes_manager.network_menu.actions():
        if action.text() == 'sys-net':
            action.trigger()
            break

    for call in calls:
        assert call in qubes_manager.qubes_app.actual_calls


@pytest.mark.asyncio(loop_scope="module")
@mock.patch('PyQt6.QtWidgets.QMessageBox.question')
async def test_310_template_menu(mock_question, qubes_manager):
    mock_question.return_value = QMessageBox.StandardButton.Yes

    # select a template
    _select_vm(qubes_manager, FEDORA_OLD)
    assert not qubes_manager.template_menu.isEnabled()

    # select a normal qube
    _select_vm(qubes_manager, 'test-red')
    vm_object = qubes_manager.qubes_app.domains['test-red']

    assert qubes_manager.template_menu.isEnabled()

    # check if template menu has sensible contents
    vm_template = str(vm_object.template.name)

    expected_templates = {str(vm) for vm in qubes_manager.qubes_app.domains
                          if vm.klass == 'TemplateVM'}

    current_templates = set()

    for action in qubes_manager.template_menu.actions():
        current_templates.add(action.text())
        if action.text() == vm_template:
            assert _is_icon(action.icon(), 'on')
        else:
            assert not _is_icon(action.icon(), 'on')

    assert current_templates == expected_templates

    # attempt to change template to something
    change_call = ('test-red', 'admin.vm.property.Set',
                         'template', FEDORA_OLD.encode())
    assert change_call not in qubes_manager.qubes_app.actual_calls
    qubes_manager.qubes_app.expected_calls[change_call] = b'0\x00'

    assert vm_object.template == FEDORA_LATEST

    for action in qubes_manager.template_menu.actions():
        if action.text() == FEDORA_OLD:
            action.trigger()

    assert change_call in qubes_manager.qubes_app.actual_calls

    # simulate firing property-set and new value
    qubes_manager.qubes_app._qubes['test-red'].template = FEDORA_OLD
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-red',
                  'property-set:template',
                  [('name', 'template'), ('newvalue', FEDORA_OLD)]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    # check current state

    # select a template
    _select_vm(qubes_manager, FEDORA_OLD)
    assert not qubes_manager.template_menu.isEnabled()

    # select a normal qube
    _select_vm(qubes_manager, 'test-red')
    vm_object = qubes_manager.qubes_app.domains['test-red']

    vm_template = vm_object.template.name

    for action in qubes_manager.template_menu.actions():
        if action.text() == vm_template:
            assert _is_icon(action.icon())
        else:
            assert not _is_icon(action.icon())


@mock.patch('PyQt6.QtWidgets.QMessageBox.question')
def test_313_template_menu_multiple(mock_question, qubes_manager):
    mock_question.return_value = QMessageBox.StandardButton.Yes

    target_vm_names = ['test-red', 'test-vm', 'vault']

    _select_vm(qubes_manager, *target_vm_names)

    assert qubes_manager.template_menu.isEnabled()

    # attempt to change netvm to fedora-35
    calls = []
    for vm in target_vm_names:
        call = (vm, 'admin.vm.property.Set', 'template', FEDORA_OLD.encode())
        assert call not in qubes_manager.qubes_app.actual_calls
        qubes_manager.qubes_app.expected_calls[call] = b'0\x00'
        calls.append(call)

    # change to specific value
    for action in qubes_manager.template_menu.actions():
        if action.text() == FEDORA_OLD:
            action.trigger()
            break

    for call in calls:
        assert call in qubes_manager.qubes_app.actual_calls


@mock.patch('PyQt6.QtWidgets.QMessageBox.information')
@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
def test_320_clear_threads(mock_warning, mock_info, qubes_manager):
    mock_thread_finished_ok = mock.Mock(
        spec=['isFinished', 'msg', 'msg_is_success'],
        msg=None, msg_is_success=False,
        **{'isFinished.return_value': True})
    mock_thread_not_finished = mock.Mock(
        spec=['isFinished', 'msg', 'msg_is_success'],
        msg=None, msg_is_success=False,
        **{'isFinished.return_value': False})
    mock_thread_finished_error = mock.Mock(
        spec=['isFinished', 'msg', 'msg_is_success'],
        msg=("Error", "Error"), msg_is_success=False,
        **{'isFinished.return_value': True})
    mock_thread_fin_error_success = mock.Mock(
        spec=['isFinished', 'msg', 'msg_is_success'],
        msg=("Done", "Done"), msg_is_success=True,
        **{'isFinished.return_value': True})

    # single finished thread
    qubes_manager.threads_list = [mock_thread_not_finished,
                                  mock_thread_finished_ok]
    qubes_manager.clear_threads()
    assert mock_warning.call_count == 0
    assert mock_info.call_count == 0
    assert len(qubes_manager.threads_list) == 1

    # an error thread and some in-progress ones
    qubes_manager.threads_list = [mock_thread_not_finished,
                                  mock_thread_not_finished,
                                  mock_thread_finished_error]
    qubes_manager.clear_threads()
    assert mock_warning.call_count == 1
    assert mock_info.call_count == 0
    assert len(qubes_manager.threads_list) == 2

    # an error-success thread and some in-progress ones
    qubes_manager.threads_list = [mock_thread_not_finished,
                                  mock_thread_not_finished,
                                  mock_thread_fin_error_success,
                                  mock_thread_finished_error]
    qubes_manager.clear_threads()
    assert mock_warning.call_count == 1
    assert mock_info.call_count == 1
    assert len(qubes_manager.threads_list) == 3


@pytest.mark.asyncio(loop_scope="module")
async def test_400_domain_added(qubes_manager):
    initial_vms = _get_current_vms(qubes_manager)
    assert 'test-new' not in initial_vms

    # simulate adding a new qube
    qubes_manager.qubes_app._qubes['test-new'] = MockQube(
        'test-new', qubes_manager.qubes_app, label='green',
        template=FEDORA_OLD)
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('',
                  'domain-add',
                  [('vm', 'test-new')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    current_vms = _get_current_vms(qubes_manager)
    assert 'test-new' in current_vms
    assert current_vms == sorted(initial_vms + ['test-new'])

    assert (_get_column_value(qubes_manager, "Template", "test-new") ==
            FEDORA_OLD)

    _check_sorting(qubes_manager, "Name")


@pytest.mark.asyncio(loop_scope="module")
async def test_401_domain_removed(qubes_manager):
    initial_vms = _get_current_vms(qubes_manager)
    assert 'test-blue' in initial_vms

    # simulate removing a qube
    del qubes_manager.qubes_app._qubes['test-blue']
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('',
                  'domain-delete',
                  [('vm', 'test-blue')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    current_vms = _get_current_vms(qubes_manager)
    assert 'test-blue' not in current_vms
    assert (sorted(current_vms + ['test-blue']) == initial_vms)

    _check_sorting(qubes_manager, "Name")


# orderly disp-vm event
@pytest.mark.asyncio(loop_scope="module")
async def test_403_dispdomain_added(qubes_manager):
    initial_vms = _get_current_vms(qubes_manager)

    # simulate adding a new qube
    qubes_manager.qubes_app._qubes['disp123'] = MockQube(
        'disp123', qubes_manager.qubes_app, label='red',
        template='default-dvm', auto_cleanup=True, klass='DispVM', running=True)
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('',
                  'domain-add',
                  [('vm', 'disp123')]))
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('disp123',
                  'domain-pre-start',
                  [('vm', 'disp123')]))
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('disp123',
                  'domain-start',
                  [('vm', 'disp123')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    current_vms = _get_current_vms(qubes_manager)

    assert current_vms == sorted(initial_vms + ['disp123'])

    assert (_get_column_value(qubes_manager, "Template", "disp123") ==
            'default-dvm')

    _check_sorting(qubes_manager, "Name")


# failed disp_vm event
@pytest.mark.asyncio(loop_scope="module")
async def test_404_dispdomain_fail(qubes_manager):
    initial_vms = _get_current_vms(qubes_manager)

    # simulate failure to start-up a dispvm
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('',
                  'domain-add',
                  [('vm', 'disp123')]))
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('disp123',
                  'domain-pre-start'))
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('disp123',
                  'domain-start'))
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('disp123',
                  'domain-start-failed'))
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('',
                  'domain-remove',
                  [('vm', 'disp123')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    current_vms = _get_current_vms(qubes_manager)

    assert current_vms == initial_vms


@pytest.mark.asyncio(loop_scope="module")
async def test_410_prop_change_label(qubes_manager):
    initial_icon = _get_column_value(qubes_manager, "Label", "test-blue",
                                     Qt.ItemDataRole.DecorationRole)

    qubes_manager.qubes_app._qubes['test-blue'].label = 'black'
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:label',
                  [('name', 'label'),
                   ('newvalue', 'black'), ('oldvalue', 'blue')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    changed_icon = _get_column_value(qubes_manager, "Label", "test-blue",
                                     Qt.ItemDataRole.DecorationRole)

    assert changed_icon != initial_icon


@pytest.mark.asyncio(loop_scope="module")
async def test_411_prop_change_tpl(qubes_manager):
    assert (_get_column_value(qubes_manager, "Template", "test-blue") ==
            FEDORA_LATEST)

    qubes_manager.qubes_app._qubes['test-blue'].template = FEDORA_OLD
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:template',
                  [('name', 'template'),
                   ('newvalue', FEDORA_OLD), ('oldvalue', FEDORA_LATEST)]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    assert (_get_column_value(qubes_manager, "Template", "test-blue") ==
            FEDORA_OLD)


@pytest.mark.asyncio(loop_scope="module")
async def test_412_prop_change_netvm(qubes_manager):
    assert (_get_column_value(qubes_manager, "NetVM", "test-blue") ==
            'sys-firewall')

    qubes_manager.qubes_app._qubes['test-blue'].set_property_default(
        'netvm', 'sys-firewall')
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-del:netvm',
                  [('name', 'netvm')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    assert (_get_column_value(qubes_manager, "NetVM", "test-blue") ==
            'default (sys-firewall)')


@pytest.mark.asyncio(loop_scope="module")
async def test_413_prop_change_internal(qubes_manager):
    assert (_get_column_value(qubes_manager, "Internal", "test-blue") ==
            '')

    qubes_manager.qubes_app._qubes['test-blue'].features['internal'] = '1'
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'domain-feature-set:internal',
                  [('name', 'internal'),
                   ('newvalue', '1'), ('oldvalue', '')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    # as manager by default hides internal qubes, it should be hidden here too
    assert 'test-blue' not in _get_current_vms(qubes_manager)

    # reset the feature
    qubes_manager.qubes_app._qubes['test-blue'].features['internal'] = ''
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'domain-feature-delete:internal',
                  [('name', 'internal')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    # now unhidden
    assert 'test-blue' in _get_current_vms(qubes_manager)


@pytest.mark.asyncio(loop_scope="module")
async def test_414_prop_change_ip(qubes_manager):
    current_ip = _get_column_value(qubes_manager, "IP Address", "test-blue")
    new_ip = '1.2.3.4'

    qubes_manager.qubes_app._qubes['test-blue'].ip = new_ip
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:ip',
                  [('name', 'ip'), ('newvalue', new_ip),
                   ('oldvalue', current_ip)]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    assert _get_column_value(qubes_manager, "IP Address", 'test-blue') == new_ip


@pytest.mark.asyncio(loop_scope="module")
async def test_415_prop_change_incl_backups(qubes_manager):
    current_value = _get_column_value(
        qubes_manager, "Backup", "test-blue",
        role=Qt.ItemDataRole.CheckStateRole)

    current_bool_value = current_value == Qt.CheckState.Checked

    qubes_manager.qubes_app._qubes['test-blue'].include_in_backups = \
        not current_bool_value
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:include_in_backups',
                  [('name', 'include_in_backups'),
                   ('newvalue', str(not current_bool_value)),
                   ('oldvalue', str(current_bool_value))]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    new_value = _get_column_value(qubes_manager, "Backup", 'test-blue')
    new_bool_value = new_value == Qt.CheckState.Checked
    assert new_bool_value != current_bool_value


@pytest.mark.asyncio(loop_scope="module")
async def test_416_prop_change_backup_timestamp(qubes_manager):
    current_value = _get_column_value(
        qubes_manager, "Last backup", "test-blue")

    assert current_value is None

    qubes_manager.qubes_app._qubes['test-blue'].backup_timestamp = 123
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:backup_timestamp',
                  [('name', 'backup_timestamp'),
                   ('newvalue', '123'),
                   ('oldvalue', '')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    new_value = _get_column_value(qubes_manager, "Last backup", 'test-blue')

    assert new_value == datetime.fromtimestamp(123).strftime(
        '%Y-%m-%d %H:%M:%S')


@pytest.mark.asyncio(loop_scope="module")
async def test_417_prop_change_def_dispvm(qubes_manager):
    current_value = _get_column_value(
        qubes_manager, "Default DispVM", "test-blue")
    assert current_value == 'default-dvm'

    qubes_manager.qubes_app._qubes['new-dvm'] = MockQube(
            name="new-dvm", qapp=qubes_manager.qubes_app, klass='DispVM',
            template_for_dispvms='True', template=FEDORA_LATEST,
            features={'appmenus-dispvm': '1'})
    qubes_manager.qubes_app._qubes['test-blue'].default_dispvm = 'new-dvm'
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:default_dispvm',
                  [('name', 'default_dispvm'),
                   ('newvalue', 'new-dvm'),
                   ('oldvalue', 'default-dvm')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    new_value = _get_column_value(qubes_manager, "Default DispVM", 'test-blue')

    assert new_value == 'new-dvm'


@pytest.mark.asyncio(loop_scope="module")
async def test_418_prop_change_templ_for_disp(qubes_manager):
    current_value = _get_column_value(
        qubes_manager, "Is DVM Template", "test-blue")
    assert current_value == ''

    qubes_manager.qubes_app._qubes['test-blue'].template_for_dispvms = True
    qubes_manager.qubes_app.update_vm_calls()
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-blue',
                  'property-set:template_for_dispvms',
                  [('name', 'template_for_dispvms'),
                   ('newvalue', 'True'), ('oldvalue', 'False')]))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    new_value = _get_column_value(qubes_manager, "Is DVM Template", 'test-blue')

    assert new_value == 'Yes'


@pytest.mark.asyncio(loop_scope="module")
async def test_420_vm_state_change(qubes_manager):
    current_value = _get_column_value(
        qubes_manager, "State", "test-red")
    assert current_value['power'] == 'Halted'

    # start a VM
    qubes_manager.qubes_app._qubes['test-red'].running = True
    qubes_manager.qubes_app.update_vm_calls()

    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-red',
                  'domain-pre-start'))
    qubes_manager.dispatcher.add_expected_event(
        MockEvent('test-red',
                  'domain-start'))

    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(qubes_manager.dispatcher.listen_for_events(), 1)

    new_value = _get_column_value(
        qubes_manager, "State", "test-red")
    assert new_value['power'] == ('Running')


@mock.patch('os.path.exists', return_value=True)
@mock.patch('qubesmanager.log_dialog.LogDialog')
def test_500_logs(mock_log_dialog, _mock_path, qubes_manager):
    _select_vm(qubes_manager, 'dom0')

    qubes_manager.action_show_logs.trigger()
    assert mock_log_dialog.call_count == 1

    dom0_logs = mock_log_dialog.mock_calls[0][1][1]
    for c in dom0_logs:
        assert "hypervisor" in c

    mock_log_dialog.reset_mock()

    _select_vm(qubes_manager, 'test-blue')

    qubes_manager.action_show_logs.trigger()
    assert mock_log_dialog.call_count == 1

    vm_logs = mock_log_dialog.mock_calls[0][1][1]
    for c in vm_logs:
        assert "test-blue" in c

    assert dom0_logs != vm_logs


# THREAD TESTS


def test_601_startvm_thread():
    vm = mock.Mock(spec=['start'])

    thread = qube_manager.StartVMThread(vm)
    thread.run()

    vm.start.assert_called_once_with()


def test_602_startvm_thread_error():
    vm = mock.Mock(
        spec=['start'],
        **{'start.side_effect': exc.QubesException('Error')})

    thread = qube_manager.StartVMThread(vm)
    thread.run()

    assert thread.msg is not None


def test_610_run_command_thread():
    vm = mock.Mock(spec=['run'])

    thread = qube_manager.RunCommandThread(vm, "test_command")
    thread.run()

    vm.run.assert_called_once_with("test_command")


def test_611_run_command_thread_error():
    vm = mock.Mock(spec=['run'],
                            **{'run.side_effect': ChildProcessError})

    thread = qube_manager.RunCommandThread(vm, "test_command")
    thread.run()

    assert thread.msg is not None


@mock.patch('subprocess.check_call')
def test_620_update_vm_thread_dom0(check_call):
    vm = mock.Mock(spec=['klass', 'name'])
    vm.klass = 'AdminVM'
    vm.name = 'dom0'
    thread = qube_manager.UpdateVMsThread([vm.name])
    thread.run()

    check_call.assert_called_once_with(
        ["/usr/bin/qubes-update-gui", "--targets", "dom0"])


@mock.patch('subprocess.check_call')
def test_621_update_vm_thread_running(mock_call):
    vm = mock.Mock(
        spec=['klass', 'is_running', 'run_service_for_stdio',
              'run_service', 'name'],
        **{'is_running.return_value': True})

    vm.klass = 'AppVM'
    vm.name = 'testvm'
    vm.run_service_for_stdio.return_value = (b'changed=no\n', None)

    thread = qube_manager.UpdateVMsThread([vm.name])

    thread.run()

    mock_call.assert_called_once_with(
        ["/usr/bin/qubes-update-gui", "--targets", "testvm"])


@mock.patch('subprocess.check_call')
def test_623_update_vm_thread_error(mock_call):
    mock_call.side_effect = subprocess.SubprocessError
    thread = qube_manager.UpdateVMsThread(['test'])
    thread.run()

    assert thread.msg is not None


# SHUTDOWN MONITOR TEST

@mock.patch('qubesmanager.qube_manager.QMessageBox')
@mock.patch('PyQt6.QtCore.QTimer')
def test_701_vm_shutdown_correct( mock_timer, mock_question):
    mock_vm = mock.Mock()
    mock_vm.is_running.return_value = False

    monitor = qube_manager.VmShutdownMonitor(mock_vm)
    monitor.restart_vm_if_needed = mock.Mock()

    monitor.check_if_vm_has_shutdown()

    assert mock_question.call_count == 0
    assert mock_timer.call_count == 0
    monitor.restart_vm_if_needed.assert_called_once_with()


@mock.patch('qubesmanager.qube_manager.QMessageBox')
@mock.patch('PyQt6.QtCore.QTimer.singleShot')
def test_702_vm_not_shutdown_wait(mock_timer, mock_question):
    mock_question().clickedButton.return_value = 1
    mock_question().addButton.return_value = 0

    mock_vm = mock.Mock()
    mock_vm.is_running.return_value = True
    mock_vm.start_time = datetime.now().timestamp() - 3000
    mock_vm.shutdown_timeout = 60

    monitor = qube_manager.VmShutdownMonitor(mock_vm)
    time.sleep(3)

    monitor.check_if_vm_has_shutdown()

    assert mock_timer.call_count == 1


@mock.patch('qubesmanager.qube_manager.QMessageBox')
@mock.patch('PyQt6.QtCore.QTimer.singleShot')
def test_703_vm_kill( mock_timer, mock_question):
    mock_question().clickedButton.return_value = 1
    mock_question().addButton.return_value = 1

    mock_vm = mock.Mock()
    mock_vm.is_running.return_value = True
    mock_vm.start_time = datetime.now().timestamp() - 3000
    mock_vm.shutdown_timeout = 1

    monitor = qube_manager.VmShutdownMonitor(mock_vm)
    time.sleep(3)
    monitor.restart_vm_if_needed = mock.Mock()

    monitor.check_if_vm_has_shutdown()

    assert mock_timer.call_count == 0
    mock_vm.kill.assert_called_once_with()
    monitor.restart_vm_if_needed.assert_called_once_with()


@mock.patch('qubesmanager.qube_manager.QMessageBox')
@mock.patch('PyQt6.QtCore.QTimer.singleShot')
def test_704_check_later(mock_timer, mock_question):
    mock_vm = mock.Mock()
    mock_vm.is_running.return_value = True
    mock_vm.start_time = datetime.now().timestamp() - 3000
    mock_vm.shutdown_timeout = 30

    monitor = qube_manager.VmShutdownMonitor(mock_vm)
    time.sleep(1)

    monitor.check_if_vm_has_shutdown()

    assert mock_question.call_count == 0
    assert mock_timer.call_count == 1
