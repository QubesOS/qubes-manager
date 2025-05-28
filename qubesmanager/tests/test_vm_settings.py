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

import datetime
from functools import wraps
from typing import Tuple
from unittest import mock
import pytest

from PyQt6 import QtCore, QtWidgets
import qubesmanager.settings as vm_settings
from qubesadmin.tests.mock_app import MockQube, MockDevice

PAGES = ["basic", "advanced", "firewall", "devices", "applications", "services"]

# just vms
TEST_VMS = ["test-red", "test-blue", "sys-net",
            "test-standalone", "test-old", "test-vm-set"]

# with a template
ALL_TEST_VMS = TEST_VMS + ["fedora-35"]

FULL_TEST = []

for p in PAGES:
    for vmname in ALL_TEST_VMS:
        FULL_TEST.append({"page": p, "vm": vmname})


def mock_subprocess_complex(command):
    vm_name = command[-1]
    if command[1] == '--get-available':
        if vm_name == 'test-vm-set':
            return (b'test.desktop|Test App||\n'
                    b'test2.desktop|Test2 App| test2|\n'
                    b'test3.desktop|Test3 App||\n'
                    b'myvm.desktop|My VM app||\n')
        elif vm_name == 'fedora-36':
            return b'tpl.desktop|Template App||\n'
        else:
            return (b'test.desktop|Test App||\n'
                    b'test2.desktop|Test2 App| test2|\n'
                    b'test3.desktop|Test3 App||\n')
    elif command[1] == '--get-whitelist':
        if vm_name == 'test-vm-set':
            return b'test.desktop\nmissing.desktop'
        else:
            return b''
    return b''


@pytest.fixture
def settings_fixture(request, qapp, test_qubes_app) -> Tuple[
        vm_settings.VMSettingsWindow, str, str]:
    # add a frankenqube with worst possible settings
    fw_rules = [
        {"action": "accept", "dsthost": "qubes-os.org"},
        {"action": "accept", "specialtarget":"dns"},
        {"action": "accept", "proto": "icmp"},
        {"action": "drop"}
    ]

    test_qubes_app._qubes['test-vm-set'] = MockQube(
        name="test-vm-set", qapp=test_qubes_app, label="green",
        template='fedora-36', include_in_backups=False, autostart=True,
        kernel='1.1', virt_mode='hvm', provides_network=True,
        usage=0.5, template_for_dispvms=True, features={
            'gui-allow-fullscreen': '1', 'gui-allow-utf8-titles': '1',
            'supported-service.qubes-u2f-proxy': '1',
            'service.qubes-u2f-proxy': '1', 'supported-service.clocksync': '1'},
        firewall_rules=fw_rules
    )

    # and add a qube that has a connected pci device
    test_qubes_app._qubes['test-pci-dev'] = MockQube(
        name="test-pci-dev", qapp=test_qubes_app, label="green",
        virt_mode='hvm'
    )

    test_qubes_app._qubes['sys-whonix'] = MockQube(
        name="sys-whonix", qapp=test_qubes_app, tags=['anon-gateway'])

    test_qubes_app._qubes['anon-whonix'] = MockQube(
        name="anon-whonix", qapp=test_qubes_app, tags=['anon-vm'])

    test_qubes_app._devices.append(
        MockDevice(test_qubes_app, 'pci', 'USB Controller', '00:03.2',
                   'dom0', attached='test-pci-dev'))

    # add a TemplateVM with some boot modes
    test_qubes_app._qubes['fedora-36-bootmodes'] = MockQube(
        name="fedora-36-bootmodes", qapp=test_qubes_app, klass="TemplateVM",
        netvm="", features={'boot-mode.kernelopts.mode1': 'mode1kern',
            'boot-mode.name.mode1': 'Mode One',
            'boot-mode.kernelopts.mode2': 'mode2kern1 mode2kern2',
            'boot-mode.active': 'mode1', 'boot-mode.appvm-default': 'mode2'}
    )

    # add an AppVM on top of the bootmode-enabled template
    test_qubes_app._qubes['test-vm-bootmodes'] = MockQube(
        name="test-vm-bootmodes", qapp=test_qubes_app,
        template="fedora-36-bootmodes", features={
            'boot-mode.kernelopts.mode1': 'mode1kern',
            'boot-mode.name.mode1': 'Mode One',
            'boot-mode.kernelopts.mode2': 'mode2kern1 mode2kern2',
            'boot-mode.active': 'mode1', 'boot-mode.appvm-default': 'mode2'}
    )

    # add another AppVM with a non-default bootmode set
    test_qubes_app._qubes['test-vm-bootmodes-nondefault'] = MockQube(
        name="test-vm-bootmodes-nondefault", qapp=test_qubes_app,
        template="fedora-36-bootmodes", bootmode="mode2", features={
            'boot-mode.kernelopts.mode1': 'mode1kern',
            'boot-mode.name.mode1': 'Mode One',
            'boot-mode.kernelopts.mode2': 'mode2kern1 mode2kern2',
            'boot-mode.active': 'mode1', 'boot-mode.appvm-default': 'mode2'}
    )

    test_qubes_app.update_vm_calls()

    if isinstance(request.param, dict):
        vm = test_qubes_app.domains[request.param['vm']]
        page = request.param['page']
    else:
        vm = test_qubes_app.domains[request.param]
        page = 'basic'
    with mock.patch('subprocess.check_output') as mock_subprocess:
        mock_subprocess.side_effect = mock_subprocess_complex
        expected_call = (vm.name, 'admin.vm.notes.Get', None, None)
        test_qubes_app.expected_calls[expected_call] = b'0\x00Some Notes\x00'
        vms = vm_settings.VMSettingsWindow(vm, page, qapp,
                                           test_qubes_app)

        yield vms, page, vm.name
# TODO: found a bug: firewall warning does not update


def check_errors(test_function):
    @wraps(test_function)
    def wrapper(*args, **kwargs):
        with mock.patch('PyQt6.QtWidgets.QMessageBox.warning') as mock_warning:
            result = test_function(*args, **kwargs)
            if mock_warning.call_count > 0:
                err = mock_warning.mock_calls[0][1][2]
                assert False, err
            assert mock_warning.call_count == 0
        return result
    return wrapper


def _select_item(combobox: QtWidgets.QComboBox, text: str,
                 match_strict: bool = False):
    """
    select a given item in the combobox; if match_strict is True, will only
    match exact matches, otherwise, will match any item that contains
    provided string.
    """
    for i in range(combobox.count()):
        item_text = str(combobox.itemData(i,
                                         QtCore.Qt.ItemDataRole.DisplayRole))
        if (match_strict and item_text == text) or (not match_strict and text
                                                    in item_text):
            combobox.setCurrentIndex(i)
            return
    assert False, "Failed to find " + text


@check_errors
@pytest.mark.parametrize("settings_fixture", FULL_TEST, indirect=True)
def test_000_load_and_open_tab(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.vmname.text() == vm_name
    assert settings_window.tabWidget.currentIndex() == PAGES.index(page)


@check_errors
@pytest.mark.parametrize("settings_fixture", FULL_TEST, indirect=True)
def test_001_apply_changes_nothing(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    settings_window.accept()


@check_errors
@pytest.mark.parametrize("settings_fixture", ALL_TEST_VMS, indirect=True)
def test_002_data(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    vm = settings_window.qubesapp.domains[vm_name]

    # check if contents are reasonable

    # basic tab
    if hasattr(vm, 'template'):
        assert str(vm.template) in settings_window.template_name.currentText()
    else:
        assert settings_window.template_name.currentText() == ""

    if hasattr(vm, "netvm"):
        if vm.property_is_default("netvm"):
            assert "default" in settings_window.netVM.currentText()
        if vm.netvm:
            assert str(vm.netvm) in settings_window.netVM.currentText()
        else:
            assert "none" in settings_window.netVM.currentText().lower()
    else:
        assert not settings_window.netVM.isEnabled()

    assert str(vm.label) in settings_window.vmlabel.currentText()

    assert (settings_window.include_in_backups.isChecked() ==
            getattr(vm, "include_in_backups", False))

    assert (settings_window.autostart_vm.isChecked() ==
            getattr(vm, "autostart", False))

    # advanced tab

    assert settings_window.run_in_debug_mode.isChecked() == vm.debug
    assert (settings_window.provides_network_checkbox.isChecked() ==
            getattr(vm, "provides_network", False))
    assert settings_window.dvm_template_checkbox.isChecked() == \
        getattr(vm, 'template_for_dispvms', False)

    if hasattr(vm, 'default_dispvm'):
        if vm.property_is_default('default_dispvm'):
            assert 'default' in settings_window.default_dispvm.currentText()
        if vm.default_dispvm:
            assert (str(vm.default_dispvm) in
                    settings_window.default_dispvm.currentText())
        else:
            assert ("none" in
                    settings_window.default_dispvm.currentText().lower())

    else:
        assert not settings_window.default_dispvm.isEnabled()

    if hasattr(vm, 'kernel'):
        assert vm.kernel in settings_window.kernel.currentText()

    if hasattr(vm, 'virt_mode'):
        assert vm.virt_mode.upper() in settings_window.virt_mode.currentText()


# BASIC TAB
# changing label

@check_errors
@pytest.mark.parametrize("settings_fixture", ALL_TEST_VMS, indirect=True)
def test_100_change_label(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    change_needed = str(vm.label) != 'red'

    if vm.is_running():
        assert not settings_window.vmlabel.isEnabled()
        return

    assert settings_window.vmlabel.isEnabled()

    # always change to red, because one of the test vms (test-red)
    # is red, while others are green
    _select_item(settings_window.vmlabel, "red")

    expected_call = (vm_name, 'admin.vm.property.Set', 'label', b'red')
    assert expected_call not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    if change_needed:
        assert expected_call in settings_window.qubesapp.actual_calls, \
            "Label not changed"
    else:
        assert expected_call not in settings_window.qubesapp.actual_calls, \
            "Unnecessary label change"


@check_errors
@pytest.mark.parametrize("settings_fixture", ALL_TEST_VMS, indirect=True)
def test_101_change_template(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    if vm.is_running() or not hasattr(vm, "template"):
        assert not settings_window.template_name.isEnabled()
        return

    change_needed = str(vm.template) != 'fedora-35'

    assert settings_window.template_name.isEnabled()

    # one of the vms (test-old) already has this template
    _select_item(settings_window.template_name, "fedora-35")

    expected_call = (vm_name, 'admin.vm.property.Set', 'template', b'fedora-35')
    assert expected_call not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    if change_needed:
        assert expected_call in settings_window.qubesapp.actual_calls, \
            "Template not changed"
    else:
        assert expected_call not in settings_window.qubesapp.actual_calls, \
            "Unnecessary template change"


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_102_change_netvm(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    change_needed = str(vm.netvm) != 'sys-net'

    assert settings_window.netVM.isEnabled()

    _select_item(settings_window.netVM, "sys-net")

    expected_call = (vm_name, 'admin.vm.property.Set', 'netvm', b'sys-net')
    assert expected_call not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    if change_needed:
        assert expected_call in settings_window.qubesapp.actual_calls, \
            "NetVM not changed"
    else:
        assert expected_call not in settings_window.qubesapp.actual_calls, \
            "Unnecessary NetVM change"

@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
@pytest.mark.parametrize("settings_fixture", ["fedora-35"], indirect=True)
def test_103_change_netvm_tpl(mock_warning, settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.netVM.isEnabled()

    _select_item(settings_window.netVM, "sys-net")

    expected_call = (vm_name, 'admin.vm.property.Set', 'netvm', b'sys-net')
    assert expected_call not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert mock_warning.call_count == 1, ("Didn't warn for changing netvm "
                                          "on a template")

    assert expected_call in settings_window.qubesapp.actual_calls, \
        "NetVM not changed"


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_104_change_netvm_default(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    change_needed = not vm.property_is_default("netvm")

    assert settings_window.netVM.isEnabled()

    _select_item(settings_window.netVM, "default")

    expected_call = (vm_name, 'admin.vm.property.Reset', 'netvm', None)
    assert expected_call not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    # when asking to change netvm of a running vm to halted vm, complaints will
    # ensue
    with mock.patch('PyQt6.QtWidgets.QMessageBox.question') as mock_question:
        mock_question.return_value = QtWidgets.QMessageBox.StandardButton.No
        settings_window.accept()
        if change_needed:
            return

    if change_needed:
        assert expected_call in settings_window.qubesapp.actual_calls, \
            "NetVM not changed"
    else:
        assert expected_call not in settings_window.qubesapp.actual_calls, \
            "Unnecessary NetVM change"


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_105_incl_in_backups(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.include_in_backups.isEnabled()
    assert (settings_window.include_in_backups.isChecked() ==
            vm.include_in_backups)

    expected_call = (vm_name, 'admin.vm.property.Set', 'include_in_backups',
                     str(not vm.include_in_backups).encode())
    assert expected_call not in settings_window.qubesapp.expected_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.include_in_backups.setChecked(
        not settings_window.include_in_backups.isChecked())

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls, \
        "Include in backups not changed"


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_106_autostart(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.autostart_vm.isEnabled()
    assert (settings_window.autostart_vm.isChecked() ==
            vm.autostart)

    expected_call = (vm_name, 'admin.vm.property.Set', 'autostart',
                     str(not vm.autostart).encode())
    assert expected_call not in settings_window.qubesapp.expected_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.autostart_vm.setChecked(
        not settings_window.autostart_vm.isChecked())

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls, \
        "Autostart not changed"


@check_errors
@pytest.mark.parametrize("settings_fixture", ALL_TEST_VMS, indirect=True)
def test_107_misc_info(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    if vm.netvm:
        assert settings_window.ip_label.text() == vm.ip
        assert settings_window.netmask_label.text() == vm.visible_netmask
        assert settings_window.gateway_label.text() == vm.visible_gateway
        assert settings_window.dns_label.text() == vm.dns.replace(' ', ', ')
    else:
        assert not settings_window.networking_groupbox.isEnabled()

    assert settings_window.type_label.text() == vm.klass
    assert settings_window.rpm_label.text() == "Yes" if vm.installed_by_rpm \
        else "No"


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_108_disk_space(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    if vm.klass in ['TemplateVM', 'StandaloneVM']:
        assert settings_window.root_resize.isEnabled()
    else:
        assert not settings_window.root_resize.isEnabled()

    assert settings_window.max_priv_storage.isEnabled()

    # try to increase one of them
    if vm.klass in ['TemplateVM', 'StandaloneVM']:
        expected_value = settings_window.root_resize.value() + 10
        expected_volume = 'root'
        settings_window.root_resize.setValue(expected_value)
    else:
        expected_value = settings_window.max_priv_storage.value() + 10
        expected_volume = 'private'
        settings_window.max_priv_storage.setValue(expected_value)

    expected_call = (vm.name, 'admin.vm.volume.Resize', expected_volume,
                     str(expected_value * 1024**2).encode())

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    assert expected_call not in settings_window.qubesapp.actual_calls

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


# the following tests don't use check_errors fixture, because we want to
# check for errors
@mock.patch('PyQt6.QtWidgets.QInputDialog.getText')
@mock.patch('qubesmanager.settings.RenameVMThread')
@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
@pytest.mark.parametrize("settings_fixture", ['fedora-36', 'test-vm-set',
                                              'test-blue'],
                         indirect=True)
def test_109_renamevm(mock_warning, mock_thread, mock_input, settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    if vm.is_running():
        assert not settings_window.rename_vm_button.isEnabled()
        assert mock_warning.call_count == 0
        return
    else:
        assert settings_window.rename_vm_button.isEnabled()

    mock_input.return_value = ("renamed-vm", True)
    settings_window.rename_vm_button.click()

    if vm.name == 'fedora-36':
        assert mock_warning.call_count == 1
        assert mock_thread.call_count == 0
        return
    elif vm.name == 'test-vm-set':
        mock_thread.assert_called_with(vm, "renamed-vm", mock.ANY)
        mock_thread().start.assert_called_with()
        assert mock_warning.call_count == 0

    assert mock_warning.call_count == 0


@mock.patch('PyQt6.QtWidgets.QInputDialog.getText')
@mock.patch('qubesmanager.common_threads.RemoveVMThread')
@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
@pytest.mark.parametrize("settings_fixture", ['fedora-36', 'test-vm-set',
                                              'test-blue'],
                         indirect=True)
def test_110_deletevm(mock_warning, mock_thread, mock_input, settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    if vm.is_running():
        assert not settings_window.delete_vm_button.isEnabled()
        assert mock_warning.call_count == 0
        return
    else:
        assert settings_window.delete_vm_button.isEnabled()

    mock_input.return_value = (vm.name, True)
    settings_window.delete_vm_button.click()

    if vm.name == 'fedora-36':
        assert mock_warning.call_count == 1
        assert mock_thread.call_count == 0
        return
    elif vm.name == 'test-vm-set':
        mock_thread.assert_called_with(vm)
        mock_thread().start.assert_called_with()
        assert mock_warning.call_count == 0

    assert mock_warning.call_count == 0


@mock.patch('PyQt6.QtWidgets.QInputDialog.getText')
@mock.patch('qubesmanager.common_threads.RemoveVMThread')
@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'],
                         indirect=True)
def test_111_deletevm_wrong_name(mock_warning, mock_thread, mock_input,
                                 settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.delete_vm_button.isEnabled()

    mock_input.return_value = (vm.name + 'pomidorek', True)
    settings_window.delete_vm_button.click()

    assert mock_thread.call_count == 0
    assert mock_warning.call_count == 1

    mock_input.return_value = (vm.name, False)
    settings_window.delete_vm_button.click()

    assert mock_thread.call_count == 0
    assert mock_warning.call_count == 1  # no warning, the user cancelled out


@mock.patch('qubesmanager.clone_vm.CloneVMDlg')
@check_errors
@pytest.mark.parametrize("settings_fixture", ['fedora-36', 'test-vm-set',
                                              'test-blue'],
                         indirect=True)
def test_112_clonevm(mock_clone, settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.clone_vm_button.isEnabled()

    settings_window.clone_vm_button.click()

    mock_clone.assert_called_with(mock.ANY, mock.ANY, src_vm=vm)


@mock.patch('PyQt6.QtWidgets.QMessageBox.warning')
@pytest.mark.parametrize("settings_fixture", ["anon-whonix"], indirect=True)
def test_113_change_netvm_anon(mock_warning, settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    change_netvm_call = (vm_name, 'admin.vm.property.Set', 'netvm', b'sys-net')
    get_tag_call = (vm_name, 'admin.vm.tag.Get', 'anon-vm', None)

    assert settings_window.netVM.isEnabled()

    _select_item(settings_window.netVM, "sys-net")

    assert get_tag_call in settings_window.qubesapp.actual_calls

    assert change_netvm_call not in settings_window.qubesapp.expected_calls
    settings_window.qubesapp.expected_calls[change_netvm_call] = b'0\x00'

    settings_window.accept()

    settings_window.qubesapp.expected_calls[change_netvm_call] = b'0\x00'

    assert mock_warning.call_count == 1, ("Didn't warn for changing netvm "
                                          "on anon-vm")

    assert change_netvm_call in settings_window.qubesapp.actual_calls


# ADVANCED TAB

@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_200_init_memory(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.init_mem.value() == vm.memory
    assert settings_window.max_mem_size.value() == vm.maxmem

    expected_value = vm.memory + 100

    settings_window.init_mem.setValue(expected_value)

    expected_call = (vm.name, 'admin.vm.property.Set', 'memory',
                     str(expected_value).encode())
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_201_max_memory(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.init_mem.value() == vm.memory
    assert settings_window.max_mem_size.value() == vm.maxmem

    expected_max = vm.maxmem + 100
    expected_init = vm.memory + 100

    settings_window.init_mem.setValue(expected_init)
    settings_window.max_mem_size.setValue(expected_max)

    assert not settings_window.warn_too_much_mem_label.isVisible()

    expected_calls = [
        (vm.name, 'admin.vm.property.Set', 'memory',
         str(expected_init).encode()),
        (vm.name, 'admin.vm.property.Set', 'maxmem',
         str(expected_max).encode()),
        (vm.name, 'admin.vm.feature.Set', 'qubesmanager.maxmem_value',
         str(expected_max - 100).encode())
    ]
    for call in expected_calls:
        assert call not in settings_window.qubesapp.actual_calls
        settings_window.qubesapp.expected_calls[call] = b'0\x00'

    settings_window.accept()

    for call in expected_calls:
        assert call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_202_vcpus(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.vcpus.value() == vm.vcpus

    expected_value = settings_window.vcpus.value() + 1
    settings_window.vcpus.setValue(expected_value)

    expected_call = (vm.name, 'admin.vm.property.Set', 'vcpus',
                     str(expected_value).encode())
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_203_mem_balancing(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.include_in_balancing.isChecked()

    settings_window.include_in_balancing.setChecked(False)

    expected_call = (vm.name, 'admin.vm.feature.Set',
                     'qubesmanager.maxmem_value', str(vm.maxmem).encode())
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    expected_calls = [
        (vm.name, 'admin.vm.feature.Set', 'qubesmanager.maxmem_value',
         str(vm.maxmem).encode()),
        (vm.name, 'admin.vm.property.Set', 'maxmem', b'0')
    ]
    for call in expected_calls:
        assert call not in settings_window.qubesapp.actual_calls
        settings_window.qubesapp.expected_calls[call] = b'0\x00'

    settings_window.accept()

    for call in expected_calls:
        assert call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_204_debug_mode(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.run_in_debug_mode.isChecked() == vm.debug

    settings_window.run_in_debug_mode.setChecked(not vm.debug)

    expected_call = (vm.name, 'admin.vm.property.Set', 'debug',
                     str(not vm.debug).encode())
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_205_povides_network(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert (settings_window.provides_network_checkbox.isChecked() ==
            vm.provides_network)

    settings_window.provides_network_checkbox.setChecked(
        not vm.provides_network)

    expected_call = (vm.name, 'admin.vm.property.Set', 'provides_network',
                     str(not vm.provides_network).encode())
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_206_dispvmtempl(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.dvm_template_checkbox.isEnabled()

    assert (settings_window.dvm_template_checkbox.isChecked() ==
            vm.template_for_dispvms)

    settings_window.dvm_template_checkbox.setChecked(
        not vm.template_for_dispvms)

    expected_calls = [
        (vm.name, 'admin.vm.property.Set', 'template_for_dispvms',
         str(not vm.template_for_dispvms).encode())
    ]
    if vm.template_for_dispvms:
        # remove existis menus
        expected_calls.append((vm.name, 'admin.vm.feature.Remove',
                               'appmenus-dispvm', None))
    else:
        expected_calls.append((vm.name, 'admin.vm.feature.Set',
                               'appmenus-dispvm', b'1'))

    for call in expected_calls:
        assert call not in settings_window.qubesapp.actual_calls
        settings_window.qubesapp.expected_calls[call] = b'0\x00'

    settings_window.accept()

    for call in expected_calls:
        assert call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_207_def_dispvm(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    _select_item(settings_window.default_dispvm, 'test-vm-set')

    expected_call = (vm.name, 'admin.vm.property.Set', 'default_dispvm',
                     b'test-vm-set')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_208_fullscreen(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert "current" in settings_window.allow_fullscreen.currentText()

    if 'gui-allow-fullscreen' not in vm.features:
        assert "default" in settings_window.allow_fullscreen.currentText()
    if vm.features.get('gui-allow-fullscreen', None) == '1':
        assert 'allow' in settings_window.allow_fullscreen.currentText()

    _select_item(settings_window.allow_fullscreen, "disallow")

    expected_call = (vm.name, 'admin.vm.feature.Set', 'gui-allow-fullscreen',
                     b'')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_209_utf8_titles(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert "current" in settings_window.allow_utf8.currentText()

    if 'gui-allow-utf8-titles' not in vm.features:
        assert "default" in settings_window.allow_utf8.currentText()
    if vm.features.get('gui-allow-utf8-titles', None) == '1':
        assert 'allow' in settings_window.allow_utf8.currentText()

    _select_item(settings_window.allow_utf8, "disallow")

    expected_call = (vm.name, 'admin.vm.feature.Set', 'gui-allow-utf8-titles',
                     b'')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_210_kernel(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert vm.kernel in settings_window.kernel.currentText()

    _select_item(settings_window.kernel, "misc")

    if not vm.property_is_default('kernel'):
        _select_item(settings_window.kernel, "default")
        expected_call = (vm.name, 'admin.vm.property.Reset', 'kernel', None)
    else:
        _select_item(settings_window.kernel, "misc")
        expected_call = (vm.name, 'admin.vm.property.Set', 'kernel',
                         b'misc')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_211_virtmode(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert str(vm.virt_mode).upper() in settings_window.virt_mode.currentText()

    if vm.virt_mode == 'pvh':
        _select_item(settings_window.virt_mode, 'HVM')
        expected_call = (vm.name, 'admin.vm.property.Set', 'virt_mode', b'hvm')
    else:
        _select_item(settings_window.virt_mode, 'PV', match_strict=True)
        expected_call = (vm.name, 'admin.vm.property.Set', 'virt_mode', b'pv')

    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@mock.patch('qubesadmin.tools.qvm_start.main')
@mock.patch('qubesmanager.bootfromdevice.VMBootFromDeviceWindow')
@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_212_boot_from_device(mock_boot, mock_start, settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.boot_from_device_button.isEnabled()

    settings_window.boot_from_device_button.click()

    mock_boot.assert_called_with(
        vm=vm.name, qapp=settings_window.qapp,
        qubesapp=settings_window.qubesapp, parent=settings_window)

    mock_start.assert_called_with(['--cdrom', mock.ANY, vm.name])

@check_errors
@pytest.mark.parametrize("settings_fixture", ["fedora-36-bootmodes"], indirect=True)
def test_213_bootmode_template(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert "mode1" in settings_window.bootmode_ids
    assert "mode2" in settings_window.bootmode_ids
    assert "Mode One" in settings_window.bootmode_names
    assert "mode2" in settings_window.bootmode_names

    _select_item(settings_window.bootmode, "mode2")
    assert settings_window.bootmode_kernel_opts.text() == "mode2kern1 mode2kern2"
    _select_item(settings_window.bootmode, "default")
    assert settings_window.bootmode_kernel_opts.text() == ""
    _select_item(settings_window.bootmode, "Mode One")
    assert settings_window.bootmode_kernel_opts.text() == "mode1kern"
    with mock.patch('qubesadmin.base.PropertyHolder.property_get_default',
                    return_value='mode1'):
        _select_item(settings_window.bootmode, "default")
        assert settings_window.bootmode_kernel_opts.text() == "mode1kern"

    _select_item(settings_window.bootmode, "mode2")
    _select_item(settings_window.appvm_default_bootmode, "Mode One")

    expected_call_bm = (vm_name, 'admin.vm.property.Set', 'bootmode', b'mode2')
    assert expected_call_bm not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call_bm] = b'0\x00'

    expected_call_adbm = (vm_name, 'admin.vm.property.Set', \
        'appvm_default_bootmode', b'mode1')
    assert expected_call_adbm not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call_adbm] = b'0\x00'

    settings_window.accept()
    assert expected_call_bm in settings_window.qubesapp.actual_calls, \
        "Boot mode not changed"
    assert expected_call_adbm in settings_window.qubesapp.actual_calls, \
        "AppVM default boot mode not changed"

@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-bootmodes"], indirect=True)
def test_214_bootmode_appvm(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert "mode1" in settings_window.bootmode_ids
    assert "mode2" in settings_window.bootmode_ids
    assert "Mode One" in settings_window.bootmode_names
    assert "mode2" in settings_window.bootmode_names

    _select_item(settings_window.bootmode, "Mode One")
    assert settings_window.bootmode_kernel_opts.text() == "mode1kern"
    _select_item(settings_window.bootmode, "mode2")
    assert settings_window.bootmode_kernel_opts.text() == "mode2kern1 mode2kern2"
    _select_item(settings_window.bootmode, "Mode One")

    expected_call = (vm_name, 'admin.vm.property.Set', 'bootmode', b'mode1')
    assert expected_call not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()
    assert expected_call in settings_window.qubesapp.actual_calls, \
        "Boot mode not changed"

@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-bootmodes-nondefault"], indirect=True)
def test_215_bootmode_appvm_nondefault(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert "mode1" in settings_window.bootmode_ids
    assert "mode2" in settings_window.bootmode_ids
    assert "Mode One" in settings_window.bootmode_names
    assert "mode2" in settings_window.bootmode_names
    assert settings_window.bootmode_kernel_opts.text() == "mode2kern1 mode2kern2"

    _select_item(settings_window.bootmode, "Mode One")
    assert settings_window.bootmode_kernel_opts.text() == "mode1kern"
    _select_item(settings_window.bootmode, "mode2")
    assert settings_window.bootmode_kernel_opts.text() == "mode2kern1 mode2kern2"
    _select_item(settings_window.bootmode, "Mode One")

    expected_call = (vm_name, 'admin.vm.property.Set', 'bootmode', b'mode1')
    assert expected_call not in settings_window.qubesapp.expected_calls

    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()
    assert expected_call in settings_window.qubesapp.actual_calls, \
        "Boot mode not changed"


@check_errors
@pytest.mark.parametrize("settings_fixture", TEST_VMS, indirect=True)
def test_213_prohibit_start(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    r = vm.features.get("prohibit-start", "")
    assert settings_window.prohibit_start_checkbox.isChecked() == bool(r)
    if r:
        assert settings_window.prohibit_start_rationale.text() == r

    settings_window.prohibit_start_checkbox.setChecked(not bool(r))

    if bool(r):
        settings_window.prohibit_start_rationale.setText("")
        expected_call = (
            vm.name,
            "admin.vm.feature.Remove",
            "prohibit-start",
            None,
        )
    else:
        settings_window.prohibit_start_rationale.setText("RATIONALE")
        expected_call = (
            vm.name,
            "admin.vm.feature.Set",
            "prohibit-start",
            "RATIONALE".encode(),
        )

    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b"0\x00"
    settings_window.accept()


# FIREWALL TAB

@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-blue"], indirect=True)
def test_300_firewall_start_limiting(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.firewall_tab.isEnabled()

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isChecked()

    settings_window.policy_deny_radio_button.setChecked(True)

    expected_call = (
        'test-blue', 'admin.vm.firewall.Set', None,
        b'action=accept specialtarget=dns\naction=accept '
        b'proto=icmp\naction=drop\n')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-set"], indirect=True)
def test_301_firewall_unlimit(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    assert settings_window.firewall_tab.isEnabled()

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_deny_radio_button.isChecked()

    settings_window.policy_allow_radio_button.setChecked(True)

    expected_call = (
        'test-vm-set', 'admin.vm.firewall.Set', None,
        b'action=accept dsthost=qubes-os.org\naction=accept\n')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-set"], indirect=True)
def test_302_firewall_remove_rule(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.firewall_tab.isEnabled()

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_deny_radio_button.isChecked()

    settings_window.rulesTreeView.setCurrentIndex(
        settings_window.fw_model.index(0, 0))
    settings_window.delete_rule_button.click()

    expected_call = (
        'test-vm-set', 'admin.vm.firewall.Set', None,
        b'action=accept specialtarget=dns\naction=accept '
        b'proto=icmp\naction=drop\n')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-set"], indirect=True)
def test_303_firewall_add_rule(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.firewall_tab.isEnabled()

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_deny_radio_button.isChecked()

    settings_window.new_rule_button.click()
    settings_window.fw_model.current_dialog.addressComboBox.setCurrentText(
        "test_stuff")
    settings_window.fw_model.current_dialog.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).click()

    expected_call = (
        'test-vm-set', 'admin.vm.firewall.Set', None,
        b'action=accept dsthost=qubes-os.org\n'
        b'action=accept dsthost=test_stuff\n'
        b'action=accept specialtarget=dns\n'
        b'action=accept proto=icmp\n'
        b'action=drop\n')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-set"], indirect=True)
def test_304_firewall_add_rule_complex(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.firewall_tab.isEnabled()

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_deny_radio_button.isChecked()

    settings_window.new_rule_button.click()
    settings_window.fw_model.current_dialog.addressComboBox.setCurrentText(
        "test_stuff")
    settings_window.fw_model.current_dialog.udp_radio.setChecked(True)
    _select_item(settings_window.fw_model.current_dialog.serviceComboBox,
                 "http")
    settings_window.fw_model.current_dialog.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).click()

    expected_call = (
        'test-vm-set', 'admin.vm.firewall.Set', None,
        b'action=accept dsthost=qubes-os.org\n'
        b'action=accept proto=udp dsthost=test_stuff dstports=80-80\n'
        b'action=accept specialtarget=dns\n'
        b'action=accept proto=icmp\n'
        b'action=drop\n')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-set"], indirect=True)
def test_305_firewall_edit_rule(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.firewall_tab.isEnabled()

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_deny_radio_button.isChecked()

    settings_window.rulesTreeView.setCurrentIndex(
        settings_window.fw_model.index(0, 0))
    settings_window.edit_rule_button.click()

    settings_window.fw_model.current_dialog.tcp_radio.setChecked(True)
    _select_item(settings_window.fw_model.current_dialog.serviceComboBox,
                 "printer")
    settings_window.fw_model.current_dialog.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok).click()

    expected_call = (
        'test-vm-set', 'admin.vm.firewall.Set', None,
        b'action=accept proto=tcp dsthost=qubes-os.org dstports=515-515\n'
        b'action=accept specialtarget=dns\naction=accept '
        b'proto=icmp\naction=drop\n')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ["test-vm-set"], indirect=True)
def test_306_firewall_unlimit(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.firewall_tab.isEnabled()

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_deny_radio_button.isChecked()

    settings_window.temp_full_access.setChecked(True)

    # add 5 minutes to now
    expiration_date = str((int(datetime.datetime.now().strftime(
        "%s")) + 5 * 60)).encode()

    expected_call = (
        'test-vm-set', 'admin.vm.firewall.Set', None,
        b'action=accept dsthost=qubes-os.org\n'
        b'action=accept expire=' + expiration_date + b'\n'
        b'action=accept specialtarget=dns\naction=accept '
        b'proto=icmp\naction=drop\n')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@mock.patch('subprocess.check_output')
def test_307_open_with_limit(mock_subprocess, qapp, test_qubes_app):
    # this test is supposed to check if the settings open even when there is
    # an unlimited FW access set
    # It also checks if inaccessible qube note is disabled
    mock_subprocess.result = []

    # add 2 minutes to now
    expiration_date = str((int(datetime.datetime.now().strftime(
        "%s")) + 2 * 60))

    fw_rules = [
        {"action": "accept", "expire": expiration_date},
        {"action": "accept", "specialtarget": "dns"},
        {"action": "accept", "proto": "icmp"},
        {"action": "drop"}
    ]

    test_qubes_app._qubes['test-vm-fw'] = MockQube(
        name="test-vm-fw", qapp=test_qubes_app, label="green",
        firewall_rules=fw_rules
    )
    expected_call = ("test-vm-fw", 'admin.vm.notes.Get', None, None)
    test_qubes_app.expected_calls[expected_call] = \
        '2\0QubesNotesException\0\0Notes not available!\0'
    test_qubes_app.update_vm_calls()

    settings_window = vm_settings.VMSettingsWindow(
        'test-vm-fw', 'basic', qapp, test_qubes_app)

    assert settings_window.policy_deny_radio_button.isEnabled()
    assert settings_window.policy_allow_radio_button.isEnabled()
    assert settings_window.policy_deny_radio_button.isChecked()

    assert settings_window.temp_full_access.isChecked()
    assert settings_window.tempFullAccessWidget.isEnabled()
    assert not settings_window.notes.isEnabled()


@check_errors
@pytest.mark.parametrize("settings_fixture",
                         [{'vm': 'vault', 'page': 'firewall'}],
                         indirect=True)
def test_308_firewall_none(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert settings_window.no_netvm_label.isVisibleTo(settings_window)

    _select_item(settings_window.netVM, 'sys-net')

    assert not settings_window.no_netvm_label.isVisibleTo(settings_window)

    _select_item(settings_window.netVM, 'none')

    assert settings_window.no_netvm_label.isVisibleTo(settings_window)


@check_errors
@pytest.mark.parametrize("settings_fixture",
                         [{'vm': 'vault', 'page': 'firewall'}],
                         indirect=True)
def test_309_firewall_warn(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert not settings_window.sysnet_warning_label.isVisibleTo(settings_window)

    settings_window.tabWidget.setCurrentIndex(settings_window.tabs_indices[
                                                  'advanced'])

    settings_window.provides_network_checkbox.setChecked(True)

    settings_window.tabWidget.setCurrentIndex(settings_window.tabs_indices[
                                                  'firewall'])

    assert settings_window.sysnet_warning_label.isVisibleTo(settings_window)


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-blue'], indirect=True)
def test_310_stupid_netvm(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    assert not settings_window.netvm_no_firewall_label.isVisibleTo(
        settings_window)

    _select_item(settings_window.netVM, 'test-vm-set')

    settings_window.tabWidget.setCurrentIndex(settings_window.tabs_indices[
                                                  'firewall'])

    assert settings_window.netvm_no_firewall_label.isVisibleTo(settings_window)


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'],
                         indirect=True)
def test_400_services(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    enabled_services = [settings_window.services_list.item(i).text() for i in
                        range(settings_window.services_list.count())]
    available_services = []

    for i in range(settings_window.service_line_edit.count()):
        item_text = str(settings_window.service_line_edit.itemData(i,
                                         QtCore.Qt.ItemDataRole.DisplayRole))
        available_services.append(item_text)

    assert enabled_services == ['qubes-u2f-proxy']
    assert sorted(available_services) == sorted(
        ['', 'qubes-u2f-proxy', 'clocksync', '(custom...)'])


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'],
                         indirect=True)
def test_401_services_remove(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.services_list.count()):
        item_text = settings_window.services_list.item(i).text()
        if item_text == 'qubes-u2f-proxy':
            settings_window.services_list.setCurrentRow(i)
            break
    else:
        assert False, "Failed to find service"

    settings_window.remove_srv_button.click()

    expected_call = (vm.name, 'admin.vm.feature.Remove',
                     'service.qubes-u2f-proxy', None)
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'],
                         indirect=True)
def test_402_services_add(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.service_line_edit.count()):
        item_text = str(settings_window.service_line_edit.itemData(i,
                                         QtCore.Qt.ItemDataRole.DisplayRole))
        if item_text == 'clocksync':
            settings_window.service_line_edit.setCurrentIndex(i)

    settings_window.add_srv_button.click()

    expected_call = (vm.name, 'admin.vm.feature.Set',
                     'service.clocksync', b'1')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'],
                         indirect=True)
def test_403_services_add_custom(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.service_line_edit.count()):
        item_text = str(settings_window.service_line_edit.itemData(i,
                                         QtCore.Qt.ItemDataRole.DisplayRole))
        if 'custom' in item_text:
            settings_window.service_line_edit.setCurrentIndex(i)

    with mock.patch('PyQt6.QtWidgets.QInputDialog.getText',
                    return_value=('shutdown-idle', True)):
        settings_window.add_srv_button.click()

    expected_call = (vm.name, 'admin.vm.feature.Set',
                     'service.shutdown-idle', b'1')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'],
                         indirect=True)
def test_404_services_disable(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.services_list.count()):
        item = settings_window.services_list.item(i)
        if item.text() == 'qubes-u2f-proxy':
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            break
    else:
        assert False, "Failed to find service"

    expected_call = (vm.name, 'admin.vm.feature.Set',
                     'service.qubes-u2f-proxy', b'')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-red'], indirect=True)
def test_500_applications_list(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    available = []
    selected = []
    for i in range(settings_window.app_list.available_list.count()):
        available.append(
            settings_window.app_list.available_list.item(i).text())

    for i in range(settings_window.app_list.selected_list.count()):
        selected.append(
            settings_window.app_list.selected_list.item(i).text())

    assert not selected
    assert available == ['Test App', 'Test2 App', 'Test3 App']


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'], indirect=True)
def test_501_applications_list_existing(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    available = []
    selected = []
    for i in range(settings_window.app_list.available_list.count()):
        available.append(
            settings_window.app_list.available_list.item(i).text())

    for i in range(settings_window.app_list.selected_list.count()):
        selected.append(
            settings_window.app_list.selected_list.item(i).text())

    # some apps are present, some are missing
    assert available == ['My VM app', 'Test2 App', 'Test3 App']
    assert selected == ['Application missing in template! (missing.desktop)',
                        'Test App']


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-red',
                                              'test-vm-set'], indirect=True)
def test_502_application_add(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.app_list.available_list.count()):
        item = settings_window.app_list.available_list.item(i)
        if item.text() == 'Test3 App':
            item.setSelected(True)
            break
    else:
        assert False, "Failed to find application"

    settings_window.app_list.add_selected_button.click()

    if vm.name == 'test-vm-set':
        expected_call = (
            vm.name, 'admin.vm.feature.Set', 'menu-items',
            b'missing.desktop test.desktop test3.desktop')
    else:
        expected_call = (
            vm.name, 'admin.vm.feature.Set', 'menu-items',
            b'test3.desktop')

    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'], indirect=True)
def test_503_application_remove(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.app_list.selected_list.count()):
        item = settings_window.app_list.selected_list.item(i)
        if item.text() == 'Test App':
            item.setSelected(True)
            break
    else:
        assert False, "Failed to find application"

    settings_window.app_list.remove_selected_button.click()

    expected_call = (
        vm.name, 'admin.vm.feature.Set', 'menu-items',
        b'missing.desktop')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'], indirect=True)
def test_504_application_remove_missing(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.app_list.selected_list.count()):
        item = settings_window.app_list.selected_list.item(i)
        if "missing" in item.text():
            item.setSelected(True)
            break
    else:
        assert False, "Failed to find application"

    settings_window.app_list.remove_selected_button.click()

    expected_call = (
        vm.name, 'admin.vm.feature.Set', 'menu-items',
        b'test.desktop')
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-red',
                                              'test-vm-set'], indirect=True)
def test_505_application_add_all(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    settings_window.app_list.add_all_button.click()

    if vm.name == 'test-vm-set':
        expected_call = (
            vm.name, 'admin.vm.feature.Set', 'menu-items',
            b'missing.desktop myvm.desktop test.desktop '
            b'test2.desktop test3.desktop')
    else:
        expected_call = (
            vm.name, 'admin.vm.feature.Set', 'menu-items',
            b'test.desktop test2.desktop test3.desktop')

    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-red',
                                              'test-vm-set'], indirect=True)
def test_506_application_remove_all(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    settings_window.app_list.remove_all_button.click()

    expected_call = (
        vm.name, 'admin.vm.feature.Set', 'menu-items', b'')

    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    if vm.name == 'test-vm-set':
        assert expected_call in settings_window.qubesapp.actual_calls
    else:
        # that VM had no apps to begin with
        assert expected_call not in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'], indirect=True)
def test_600_devices(settings_fixture):
    settings_window, page, vm_name = settings_fixture

    available_items = []
    for i in range(settings_window.dev_list.available_list.count()):
        item = settings_window.dev_list.available_list.item(i)
        available_items.append(item.text())

    assert len(available_items) == 4


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-vm-set'], indirect=True)
def test_601_device_add(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    for i in range(settings_window.dev_list.available_list.count()):
        item = settings_window.dev_list.available_list.item(i)
        if 'USB' in item.text():
            item.setSelected(True)
            break
    else:
        assert False, "Failed to find item"

    settings_window.dev_list.add_selected_button.click()

    expected_call = (
        vm.name, 'admin.vm.device.pci.Assign', 'dom0+00_03.2:*',
        b"device_id='*' port_id='00_03.2' devclass='pci' "
        b"backend_domain='dom0' mode='required' "
        b"frontend_domain='test-vm-set'")
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    # assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-pci-dev'], indirect=True)
def test_602_device_remove(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    vm = settings_window.qubesapp.domains[vm_name]

    available_items = []
    for i in range(settings_window.dev_list.available_list.count()):
        item = settings_window.dev_list.available_list.item(i)
        available_items.append(item.text())

    assert len(available_items) == 4

    selected_items = []
    for i in range(settings_window.dev_list.selected_list.count()):
        item = settings_window.dev_list.selected_list.item(i)
        selected_items.append(item.text())
        item.setSelected(True)

    assert len(selected_items) == 1

    settings_window.dev_list.remove_selected_button.click()

    expected_call = (vm.name, 'admin.vm.device.pci.Unassign', 'dom0+00:03.2',
                     None)
    assert expected_call not in settings_window.qubesapp.actual_calls
    settings_window.qubesapp.expected_calls[expected_call] = b'0\x00'

    settings_window.accept()

    assert expected_call in settings_window.qubesapp.actual_calls


@check_errors
@pytest.mark.parametrize("settings_fixture", ['test-pci-dev'],
                         indirect=True)
def test_603_virtmode_limitation(settings_fixture):
    settings_window, page, vm_name = settings_fixture
    available_virtmodes = []

    for i in range(settings_window.virt_mode.count()):
        item_text = str(settings_window.virt_mode.itemData(
            i, QtCore.Qt.ItemDataRole.DisplayRole))
        available_virtmodes.append(item_text)

    assert len(available_virtmodes) == 3 # HVM, PV, default
    assert 'PVH' not in available_virtmodes
    assert 'HVM (current)' in available_virtmodes
    assert 'PV' in available_virtmodes
