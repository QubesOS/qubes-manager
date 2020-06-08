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

from PyQt5 import QtTest, QtCore
from qubesadmin import Qubes
import qubesmanager.settings as vm_settings
from qubesmanager.tests import init_qtapp


class VMSettingsTest(unittest.TestCase):
    def setUp(self):
        super(VMSettingsTest, self).setUp()
        self.qtapp, self.loop = init_qtapp()

        self.mock_qprogress = unittest.mock.patch(
            'PyQt5.QtWidgets.QProgressDialog')
        self.mock_qprogress.start()

        self.addCleanup(self.mock_qprogress.stop)

        self.qapp = Qubes()

        if "test-vm" in self.qapp.domains:
            del self.qapp.domains["test-vm"]

    def tearDown(self):
        if "test-vm" in self.qapp.domains:
            del self.qapp.domains["test-vm"]
        super(VMSettingsTest, self).tearDown()

    def test_00_load_correct_tab(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "red")

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")
        self.assertTrue(
            self.dialog.tabWidget.currentWidget() is self.dialog.basic_tab)
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self.assertTrue(
            self.dialog.tabWidget.currentWidget() is self.dialog.advanced_tab)
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="firewall")
        self.assertTrue(
            self.dialog.tabWidget.currentWidget() is self.dialog.firewall_tab)
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="devices")
        self.assertTrue(
            self.dialog.tabWidget.currentWidget() is self.dialog.devices_tab)
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp,
            init_page="applications")
        self.assertTrue(
            self.dialog.tabWidget.currentWidget() is self.dialog.apps_tab)
        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="services")
        self.assertTrue(
            self.dialog.tabWidget.currentWidget() is self.dialog.services_tab)
        self.dialog.deleteLater()
        self.qtapp.processEvents()

    def test_01_basic_tab_default(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        # set the vm to have a default template and netvm

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        self.assertEqual(self.dialog.vmname.text(), "test-vm",
                         "Name displayed incorrectly")

        self.assertTrue("blue" in self.dialog.vmlabel.currentText(),
                        "Incorrect label displayed")

        displayed_template = self.dialog.template_name.currentText()
        correct_template = self.vm.template.name

        self.assertTrue("current" in displayed_template,
                        "Template incorrectly not shown as current")
        self.assertTrue(correct_template in displayed_template,
                        "Template not displayed correctly")

        displayed_netvm = self.dialog.netVM.currentText()
        correct_netvm = self.vm.netvm.name
        self.assertTrue("current" in displayed_netvm,
                        "NetVM incorrectly not shown as current")
        self.assertTrue(correct_netvm in displayed_netvm,
                        "NetVM not displayed correctly")

        self.assertEqual(self.dialog.include_in_backups.isChecked(),
                         self.vm.include_in_backups,
                         "Incorrect 'include in backups' state")

        self.assertEqual(self.dialog.autostart_vm.isChecked(),
                         self.vm.autostart,
                         "Incorrect 'autostart' state")

        self.assertEqual(self.dialog.type_label.text(),
                         self.vm.klass,
                         "Incorrect class displayed")

        self.assertEqual(self.dialog.ip_label.text(),
                         self.vm.ip,
                         "Incorrect IP displayed")
        self.assertEqual(self.dialog.netmask_label.text(),
                         self.vm.visible_netmask,
                         "Incorrect netmask displayed")
        self.assertEqual(self.dialog.gateway_label.text(),
                         self.vm.visible_gateway,
                         "Incorrect gateway displayed")

        self.assertEqual(self.dialog.max_priv_storage.value(),
                         self.vm.volumes['private'].size // 1024 ** 2,
                         "Incorrect max private storage size")
        self.assertEqual(self.dialog.root_resize.value(),
                         self.vm.volumes['root'].size // 1024 ** 2,
                         "Incorrect max private root size")

    def test_02_basic_tab_nones(self):
        self.vm = self.qapp.add_new_vm("StandaloneVM", "test-vm", "blue")
        # set the vm to have a default template and netvm
        self.vm.netvm = None

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        self.assertEqual("", self.dialog.template_name.currentText(),
                         "No template incorrectly displayed")

        displayed_netvm = self.dialog.netVM.currentText()
        self.assertTrue("current" in displayed_netvm,
                        "None NetVM incorrectly not shown as current")
        self.assertTrue("none" in displayed_netvm,
                        "None NetVM not displayed correctly")

        self.assertEqual(self.dialog.type_label.text(), "StandaloneVM",
                         "Type displayed incorrectly for standaloneVM")

        self.assertEqual(self.dialog.ip_label.text(),
                         "---",
                         "Incorrect IP displayed")
        self.assertEqual(self.dialog.netmask_label.text(),
                         "---",
                         "Incorrect netmask displayed")
        self.assertEqual(self.dialog.gateway_label.text(),
                         "---",
                         "Incorrect gateway displayed")

    def test_03_change_label(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")
        self.dialog.show()

        new_label = self._set_noncurrent(self.dialog.vmlabel)
        self._click_ok()

        self.assertEqual(str(self.vm.label), new_label,
                         "Label is not set correctly")

    def test_04_change_template(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        new_template = self._set_noncurrent(self.dialog.template_name)
        self._click_ok()

        self.assertEqual(self.vm.template.name, new_template,
                         "Template is not set correctly")

    def test_05_change_networking(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        new_netvm = self._set_noncurrent(self.dialog.netVM)
        self._click_ok()

        self.assertEqual(self.vm.netvm.name, new_netvm,
                         "NetVM is not set correctly")

    def test_06_change_networking_none(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        self._set_none(self.dialog.netVM)
        self._click_ok()

        self.assertIsNone(self.vm.netvm,
                          "None netVM is not set correctly")

    def test_07_change_networking_to_default(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")

        for vm in self.qapp.domains:
            if getattr(vm, 'provides_network', False)\
                    and vm != self.qapp.default_netvm:
                self.vm.netvm = vm
                break

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        new_netvm = self._set_default(self.dialog.netVM)
        self._click_ok()

        self.assertTrue(self.vm.netvm.name in new_netvm,
                        "NetVM is not set correctly")
        self.assertTrue(self.vm.property_is_default('netvm'))

    def test_08_basic_checkboxes_true(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")
        self.dialog.show()

        self.dialog.include_in_backups.setChecked(True)
        self.dialog.autostart_vm.setChecked(True)

        self._click_ok()

        self.assertTrue(self.vm.include_in_backups,
                        "Include in backups not set to true")
        self.assertTrue(self.vm.autostart,
                        "Autostart not set to true")

    def test_09_basic_checkboxes_false(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")
        self.dialog.show()

        self.dialog.include_in_backups.setChecked(False)
        self.dialog.autostart_vm.setChecked(False)

        self._click_ok()

        self.assertFalse(self.vm.include_in_backups,
                         "Include in backups not set to false")
        self.assertFalse(self.vm.autostart,
                         "Autostart not set to false")

    def test_10_increase_private_storage(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        current_storage = self.vm.volumes['private'].size // 1024**2
        new_storage = current_storage + 512

        self.dialog.max_priv_storage.setValue(new_storage)
        self._click_ok()

        self.assertEqual(self.vm.volumes['private'].size // 1024**2,
                         new_storage)

        # TODO are dependencies correctly processed

    @unittest.mock.patch('PyQt5.QtWidgets.QProgressDialog')
    @unittest.mock.patch('PyQt5.QtWidgets.QInputDialog.getText')
    @unittest.mock.patch('qubesmanager.settings.RenameVMThread')
    def test_11_rename_vm(self, mock_thread, mock_input, _):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        self.assertTrue(self.dialog.rename_vm_button.isEnabled())

        mock_input.return_value = ("test-vm2", True)
        self.dialog.rename_vm_button.click()

        mock_thread.assert_called_with(self.vm, "test-vm2", unittest.mock.ANY)
        mock_thread().start.assert_called_with()

# TODO: thread tests for rename

    @unittest.mock.patch('PyQt5.QtWidgets.QProgressDialog')
    @unittest.mock.patch('PyQt5.QtWidgets.QInputDialog.getText')
    @unittest.mock.patch('qubesmanager.common_threads.CloneVMThread')
    def test_12_clone_vm(self, mock_thread, mock_input, _):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        self.assertTrue(self.dialog.clone_vm_button.isEnabled())

        mock_input.return_value = ("test-vm2", True)
        self.dialog.clone_vm_button.click()

        mock_thread.assert_called_with(self.vm, "test-vm2")
        mock_thread().start.assert_called_with()

    @unittest.mock.patch('PyQt5.QtWidgets.QMessageBox.warning')
    @unittest.mock.patch('PyQt5.QtWidgets.QProgressDialog')
    @unittest.mock.patch('PyQt5.QtWidgets.QInputDialog.getText')
    @unittest.mock.patch('qubesmanager.common_threads.RemoveVMThread')
    def test_13_remove_vm(self, mock_thread, mock_input, _, mock_warning):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="basic")

        self.assertTrue(self.dialog.delete_vm_button.isEnabled())

        # try with a wrong name
        mock_input.return_value = ("test-vm2", True)
        self.dialog.delete_vm_button.click()
        self.assertEqual(mock_warning.call_count, 1)

        # and now correct one
        mock_input.return_value = ("test-vm", True)
        self.dialog.delete_vm_button.click()

        mock_thread.assert_called_with(self.vm)
        mock_thread().start.assert_called_with()

# Advanced Tab
    def test_20_advanced_loads(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")

        self.assertEqual(self.dialog.init_mem.value(), self.vm.memory,
                         "Incorrect initial memory")
        # default maxmem
        self.assertEqual(self.dialog.max_mem_size.value(),
                         self.vm.property_get_default('maxmem'),
                         "Maxmem incorrectly displayed for default value")
        self.assertEqual(self.dialog.vcpus.value(), self.vm.vcpus,
                         "Incorrect number of VCPUs")
        self.assertTrue(self.dialog.include_in_balancing.isChecked(),
                        "Include in memory balancing incorrectly not checked")

        # debug mode
        self.assertEqual(self.dialog.run_in_debug_mode.isChecked(),
                         self.vm.debug,
                         "Incorrect 'run in debug mode' state")

        # kernel
        self.assertTrue(self.vm.kernel in self.dialog.kernel.currentText(),
                        "Kernel displayed incorrectly")

        # default dispvm
        self.assertTrue(
            str(self.vm.default_dispvm) in
            self.dialog.default_dispvm.currentText(),
            "Default dispVM incorrectly displayed")
        self.assertEqual(self.vm.template_for_dispvms,
                         self.dialog.dvm_template_checkbox.isChecked(),
                         "Incorrectly shown to be template for dispvms")

        # virtmode
        self.assertTrue("default" in self.dialog.virt_mode.currentText())
        self.assertTrue("PVH" in self.dialog.virt_mode.currentText())

    def test_21_nondefaultmaxmem(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.vm.maxmem = 3500

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")

        self.assertEqual(self.dialog.max_mem_size.value(), 3500)

        self.dialog.include_in_balancing.setChecked(False)
        self._click_ok()

        self.assertEqual(self.vm.maxmem, 0)

        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self.assertFalse(self.dialog.include_in_balancing.isChecked())

        self.dialog.include_in_balancing.setChecked(True)
        self.assertEqual(self.dialog.max_mem_size.value(), 3500)
        self._click_ok()

        self.assertEqual(self.vm.maxmem, 3500)

    def test_22_initmem(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.vm.memory = 500

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")

        self.assertEqual(self.dialog.init_mem.value(), 500,
                         "Incorrect initial memory")
        self.dialog.init_mem.setValue(600)
        self._click_ok()

        self.assertEqual(self.vm.memory, 600, "Setting initial memory failed")

    def test_23_vcpus(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.vm.vcpus = 1

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self.assertEqual(self.dialog.vcpus.value(), 1,
                         "Incorrect number of VCPUs")

        self.dialog.vcpus.setValue(2)
        self._click_ok()

        self.assertEqual(self.vm.vcpus, 2,
                         "Incorrect number of VCPUs")

    def test_24_kernel(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self.dialog.show()

        new_kernel = self._set_noncurrent(self.dialog.kernel)
        self._click_ok()

        self.assertEqual(self.vm.kernel, new_kernel)

        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self.dialog.show()
        self._set_default(self.dialog.kernel)

        self._click_ok()
        self.assertTrue(self.vm.property_is_default('kernel'))

    def test_25_virtmode_change(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")

        modes = ["HVM", "PVH", "PV"]

        for mode in modes:
            self.dialog = vm_settings.VMSettingsWindow(
                self.vm, qapp=self.qtapp, qubesapp=self.qapp,
                init_page="advanced")

            self._set_value(self.dialog.virt_mode, mode)
            self._click_ok()

            self.assertEqual(self.vm.virt_mode.upper(), mode)

            self.dialog.deleteLater()
            self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self._set_default(self.dialog.virt_mode)
        self._click_ok()

        self.assertTrue(self.vm.property_is_default('virt_mode'))

    def test_26_default_dispvm(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")

        new_dvm = self._set_noncurrent(self.dialog.default_dispvm)
        self._click_ok()

        self.assertEqual(self.vm.default_dispvm.name, new_dvm)

        self.dialog.deleteLater()
        self.qtapp.processEvents()

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self._set_default(self.dialog.default_dispvm)
        self._click_ok()

        self.assertTrue(self.vm.property_is_default('default_dispvm'))

    @unittest.mock.patch('subprocess.check_call')
    def test_27_boot_cdrom(self, mock_call):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")

        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")

        self.dialog.boot_from_device_button.click()
        mock_call.assert_called_with(['qubes-vm-boot-from-device', "test-vm"])

    def test_28_advanced_debug_false(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self.dialog.show()

        self.dialog.run_in_debug_mode.setChecked(False)

        self._click_ok()

        self.assertFalse(self.vm.debug,
                         "Debug mode not set to false")

    def test_28_advanced_debug_true(self):
        self.vm = self.qapp.add_new_vm("AppVM", "test-vm", "blue")
        self.dialog = vm_settings.VMSettingsWindow(
            self.vm, qapp=self.qtapp, qubesapp=self.qapp, init_page="advanced")
        self.dialog.show()

        self.dialog.run_in_debug_mode.setChecked(True)

        self._click_ok()

        self.assertTrue(self.vm.debug,
                        "Debug mode not set to true")

    def _click_ok(self):
        okwidget = self.dialog.buttonBox.button(
                    self.dialog.buttonBox.Ok)

        QtTest.QTest.mouseClick(okwidget, QtCore.Qt.LeftButton)

    def _click_cancel(self):
        cancelwidget = self.dialog.buttonBox.button(
            self.dialog.buttonBox.Cancel)

        QtTest.QTest.mouseClick(cancelwidget, QtCore.Qt.LeftButton)

    def _set_noncurrent(self, widget):
        if widget.count() < 2:
            self.skipTest("not enough choices for " + widget.objectName())

        widget.setCurrentIndex(0)
        while widget.currentText().endswith("(current)") \
                or widget.currentText().startswith("(none)"):
            widget.setCurrentIndex(widget.currentIndex() + 1)

        return widget.currentText()

    def _set_default(self, widget):
        if widget.count() < 2:
            self.skipTest("not enough choices for " + widget.objectName())

        widget.setCurrentIndex(0)
        while "default" not in widget.currentText():
            widget.setCurrentIndex(widget.currentIndex() + 1)

        return widget.currentText()

    def _set_none(self, widget):
        if widget.count() < 2:
            self.skipTest("not enough choices for " + widget.objectName())

        widget.setCurrentIndex(0)
        while "none" not in widget.currentText():
            widget.setCurrentIndex(widget.currentIndex() + 1)

        return widget.currentText()

    def _set_value(self, widget, value):
        if widget.count() < 2:
            self.skipTest("not enough choices for " + widget.objectName())

        widget.setCurrentIndex(0)
        while value != widget.currentText():
            widget.setCurrentIndex(widget.currentIndex() + 1)

        return widget.currentText()


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
