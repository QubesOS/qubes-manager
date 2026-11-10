# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2026 Frédéric Pierret <frederic@invisiblethingslab.com>
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

import subprocess
from unittest import mock

import pytest
from PyQt6 import QtWidgets

from qubesadmin import exc
from qubesadmin.tests.mock_app import MockAsyncDispatcher

from .. import bootfromdevice
from .. import qube_manager
from .. import settings as vm_settings
from .. import utils


@pytest.fixture
def settings_for(qapp):
    def make(app, name="test-red", page="basic"):
        with mock.patch("subprocess.check_output", return_value=b""):
            for qube in (name, "dom0"):
                app.expected_calls[
                    (qube, "admin.vm.feature.Get", "preload-dispvm-max", None)
                ] = b"0\x00"
            app.expected_calls[(name, "admin.vm.notes.Get", None, None)] = b"0\x00"
            return vm_settings.VMSettingsWindow(name, page, qapp, app)

    return make


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
def test_refused_kernels(warning, settings_for, test_qubes_app):
    app = test_qubes_app
    app.expected_calls[("dom0", "admin.pool.volume.List", "linux-kernel", None)] = b""
    dialog = settings_for(app)
    assert not dialog.kernel.isEnabled()
    assert not dialog.bootmode.isEnabled()
    with mock.patch("subprocess.check_output", return_value=b""):
        dialog.apply()
    warning.assert_not_called()
    assert not [call for call in app.actual_calls if call[1] == "admin.vm.property.Set"]


def test_refused_notes(settings_for, test_qubes_app):
    app = test_qubes_app
    dialog = settings_for(app)
    dialog.notes.setPlainText("new")
    app.expected_calls[("test-red", "admin.vm.notes.Set", None, b"new")] = b""
    errors = dialog.__save_changes__()
    assert errors[0] == "Notes tab:"
    assert "TypeError" not in "".join(errors)


def test_refused_appmenus(settings_for, test_qubes_app):
    dialog = settings_for(test_qubes_app)
    refused = subprocess.CalledProcessError(1, "qvm-appmenus")
    with mock.patch("subprocess.check_output", side_effect=refused):
        dialog.app_list_manager.fill_apps_list(template=None)
    assert dialog.app_list.available_list.count() == 0


def manager(qapp, app):
    return qube_manager.VmManagerWindow(qapp, app, MockAsyncDispatcher(app))


def select(window, name):
    window.table.clearSelection()
    proxy = window.proxy
    for row in range(proxy.rowCount()):
        source = proxy.mapToSource(proxy.index(row, 0))
        if window.qubes_cache.get_vm(row=source.row()).name == name:
            window.table.selectRow(row)
            return
    raise KeyError(name)


def test_cdrom_failure(test_qubes_app):
    vm = test_qubes_app.domains["test-red"]

    fail = exc.QubesException("Error: no such device")
    with mock.patch("qubesadmin.utils.start_expert", side_effect=fail):
        assert utils.start_from_cdrom(vm, "sys-usb:sda") == "Error: no such device"
    with mock.patch("qubesadmin.utils.start_expert"):
        assert utils.start_from_cdrom(vm, "sys-usb:sda") is None


@mock.patch("qubesadmin.Qubes")
@mock.patch("qubesmanager.bootfromdevice.utils.run_synchronous")
def test_boot_from_device_failure(run, qubes, test_qubes_app, capsys):
    qubes.return_value = test_qubes_app
    run.return_value = mock.Mock(cdrom_location="sys-usb:sda")
    run.return_value.result.return_value = 1
    fail = exc.QubesException("Error: no such device")
    with mock.patch("qubesadmin.utils.start_expert", side_effect=fail):
        assert bootfromdevice.main(["test-red"]) == 1
    assert "no such device" in capsys.readouterr().err


@mock.patch("qubesadmin.utils.start_expert")
@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
def test_no_windows_tools(warning, start, qapp, test_qubes_app):
    window = manager(qapp, test_qubes_app)
    select(window, "test-red")
    with mock.patch("os.path.exists", return_value=False):
        window.action_startvm_tools_install_triggered()
    warning.assert_called_once()
    start.assert_not_called()


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
@mock.patch(
    "PyQt6.QtWidgets.QMessageBox.question",
    return_value=QtWidgets.QMessageBox.StandardButton.Yes,
)
def test_refused_network_change(_question, warning, qapp, test_qubes_app):
    app = test_qubes_app
    window = manager(qapp, app)
    select(window, "test-red")
    # An empty answer is qubesd's refusal
    app.expected_calls[("test-red", "admin.vm.property.Set", "netvm", b"sys-net")] = b""
    window.change_network("sys-net")
    warning.assert_called_once()
    assert "network change failed" in warning.call_args[0][1]


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
def test_refused_clone(warning, qapp, test_qubes_app):
    app = test_qubes_app
    window = manager(qapp, app)
    select(window, "test-red")
    app.expected_calls[("dom0", "admin.label.List", None, None)] = b""
    app.labels.clear_cache()
    window.action_clonevm_triggered()
    warning.assert_called_once()
    assert warning.call_args[0][1] == "Cannot clone 'test-red'"


def test_refused_command(test_qubes_app):
    vm = test_qubes_app.domains["test-red"]
    thread = qube_manager.RunCommandThread(vm, "true")
    with mock.patch.object(
        type(vm), "run", side_effect=subprocess.CalledProcessError(126, "true")
    ):
        thread.run()
    assert thread.msg[1] == "Cannot run command due to qrexec policy"
    with mock.patch.object(
        type(vm), "run", side_effect=subprocess.CalledProcessError(2, "true")
    ):
        thread.run()
    assert "exit status 2" in thread.msg[1]
