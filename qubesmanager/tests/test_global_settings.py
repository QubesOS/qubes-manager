#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2016 Marek Marczykowski-Górecki
#                                       <marmarek@invisiblethingslab.com>
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
import sys
import unittest
import unittest.mock

from PyQt4 import QtGui, QtTest, QtCore
from qubesadmin import Qubes
from qubes.tests import SystemTestCase
import qubesmanager.global_settings as global_settings
import concurrent.futures

# sudo systemctl stop qubesd; sudo -E python3 test_backup.py -v ; sudo systemctl start qubesd

def wrap_in_loop(func):
    def wrapped(self):
        self.loop.run_until_complete(
            self.loop.run_in_executor(self.executor,
                                      func, self))
    return wrapped


class GlobalSettingsTest(SystemTestCase):
    def setUp(self):
        super(GlobalSettingsTest, self).setUp()

        self.qtapp = QtGui.QApplication(sys.argv)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.setUpInExecutor()

    @wrap_in_loop
    def setUpInExecutor(self):
        self.qapp = Qubes()
        self.dialog = global_settings.GlobalSettingsWindow(
                self.qtapp, self.qapp)

    def tearDown(self):
        self.tearDownInExecutor()
        super(GlobalSettingsTest, self).tearDown()

    @wrap_in_loop
    def tearDownInExecutor(self):
        del self.dialog
        del self.qtapp

    @wrap_in_loop
    def test_00_settings_started(self):
        # non-empty drop-downs
        self.assertNotEqual(
            self.dialog.default_kernel_combo.currentText(), "")
        self.assertNotEqual(
            self.dialog.default_netvm_combo.currentText(), "")
        self.assertNotEqual(
            self.dialog.default_template_combo.currentText(),
            "")
        self.assertNotEqual(
            self.dialog.clock_vm_combo.currentText(), "")
        self.assertNotEqual(
            self.dialog.update_vm_combo.currentText(), "")

    @wrap_in_loop
    def test_01_load_correct_defs(self):
        # correctly selected default template
        selected_default_template = \
            self.dialog.default_template_combo.currentText()
        self.assertTrue(
            selected_default_template.startswith(
                self.app.default_template.name))

        # correctly selected default NetVM
        selected_default_netvm = \
            self.dialog.default_netvm_combo.currentText()
        self.assertTrue(selected_default_netvm.startswith(
            self.app.default_netvm.name))

        # correctly selected default kernel
        selected_default_kernel = \
            self.dialog.default_kernel_combo.currentText()
        self.assertTrue(selected_default_kernel.startswith(
            self.app.default_kernel))

        # correct ClockVM
        selected_clockvm = \
            self.dialog.clock_vm_combo.currentText()
        correct_clockvm = self.app.clockvm.name if self.app.clockvm \
            else "(none)"
        self.assertTrue(selected_clockvm.startswith(correct_clockvm))

        # correct updateVM
        selected_updatevm = \
            self.dialog.update_vm_combo.currentText()
        correct_updatevm = \
            self.app.updatevm.name if self.app.updatevm else "(none)"
        self.assertTrue(selected_updatevm.startswith(correct_updatevm))

        # update vm status
        self.assertEqual(self.app.check_updates_vm,
                         self.dialog.updates_vm.isChecked())

    @wrap_in_loop
    def test_02_dom0_updates_load(self):
        # check dom0 updates
        try:
            dom0_updates = self.app.check_updates_dom0
        except AttributeError:
            self.skipTest("check_updates_dom0 property not implemented")
            return

        self.assertEqual(dom0_updates, self.dialog.updates_dom0.isChecked())

    def __set_noncurrent(self, widget):
        if widget.count() < 2:
            self.skipTest("not enough choices for " + widget.objectName())

        widget.setCurrentIndex(0)
        while widget.currentText().endswith("(current)") \
                or widget.currentText().startswith("(none)"):
            widget.setCurrentIndex(widget.currentIndex() + 1)

        return widget.currentText()

    def __set_none(self, widget):
        widget.setCurrentIndex(0)
        while not widget.currentText().startswith("(none)"):
            if widget.currentIndex() == widget.count():
                self.skipTest("none not available for " + widget.objectName())
            widget.setCurrentIndex(widget.currentIndex() + 1)

    def __click_ok(self):
        okwidget = self.dialog.buttonBox.button(
                    self.dialog.buttonBox.Ok)

        QtTest.QTest.mouseClick(okwidget,
                                QtCore.Qt.LeftButton)

    @wrap_in_loop
    def test_10_set_update_vm(self):
        new_updatevm_name = self.__set_noncurrent(self.dialog.update_vm_combo)
        self.__click_ok()

        self.assertEqual(self.app.updatevm.name, new_updatevm_name)

    @wrap_in_loop
    def test_11_set_update_vm_to_none(self):
        self.__set_none(self.dialog.update_vm_combo)
        self.__click_ok()

        self.assertIsNone(self.app.updatevm)

    @wrap_in_loop
    def test_12_set_update_vm_to_none2(self):
        self.app.updatevm = None
        self.dialog = global_settings.GlobalSettingsWindow(
            self.qtapp, self.qapp)

        self.assertEqual(self.dialog.update_vm_combo.currentText(),
                         "(none) (current)")

    @wrap_in_loop
    def test_20_set_clock_vm(self):
        new_clockvm_name = self.__set_noncurrent(self.dialog.clock_vm_combo)
        self.__click_ok()

        self.assertEqual(self.app.clockvm.name, new_clockvm_name)

    @wrap_in_loop
    def test_21_set_clock_vm_to_none(self):
        self.__set_none(self.dialog.clock_vm_combo)
        self.__click_ok()

        self.assertIsNone(self.app.clockvm)

    @wrap_in_loop
    def test_22_set_clock_vm_to_none2(self):
        self.app.clockvm = None
        self.dialog = global_settings.GlobalSettingsWindow(
                self.qtapp, self.qapp)

        self.assertEqual(self.dialog.clock_vm_combo.currentText(),
                         "(none) (current)")

    @wrap_in_loop
    def test_30_set_default_netvm(self):
        new_netvm_name = self.__set_noncurrent(self.dialog.default_netvm_combo)
        self.__click_ok()

        self.assertEqual(self.app.default_netvm.name, new_netvm_name)

    @wrap_in_loop
    def test_31_set_default_netvm_to_none(self):
        self.__set_none(self.dialog.default_netvm_combo)
        self.__click_ok()

        self.assertIsNone(self.app.default_netvm)

    @wrap_in_loop
    def test_32_set_default_netvm_to_none2(self):
        self.app.default_netvm = None
        self.dialog = global_settings.GlobalSettingsWindow(
                self.qtapp, self.qapp)

        self.assertEqual(self.dialog.default_netvm_combo.currentText(),
                         "(none) (current)")

    @wrap_in_loop
    def test_40_set_default_template(self):
        new_def_template_name = self.__set_noncurrent(
            self.dialog.default_template_combo)
        self.__click_ok()

        self.assertEqual(self.app.default_template.name, new_def_template_name)

    @wrap_in_loop
    def test__50_set_default_kernel(self):
        new_def_kernel_name = self.__set_noncurrent(
            self.dialog.default_kernel_combo)
        self.__click_ok()

        self.assertEqual(self.app.default_kernel, new_def_kernel_name)

    @wrap_in_loop
    def test_51_set_default_kernel_to_none(self):
        self.__set_none(self.dialog.default_kernel_combo)
        self.__click_ok()

        self.assertEqual(self.app.default_kernel, '')

    @wrap_in_loop
    def test_52_set_default_kernel_to_none2(self):
        self.app.default_kernel = None
        self.dialog = global_settings.GlobalSettingsWindow(
                self.qtapp, self.qapp)

        self.assertEqual(self.dialog.default_kernel_combo.currentText(),
                         "(none) (current)")

    @wrap_in_loop
    def test_60_set_dom0_updates_true(self):
        self.dialog.updates_dom0.setChecked(True)
        self.__click_ok()

        if not hasattr(self.app, 'check_updates_dom0'):
            self.skipTest("check_updates_dom0 property not implemented")

        self.assertTrue(self.app.check_updates_dom0)

    @wrap_in_loop
    def test_61_set_dom0_updates_false(self):
        self.dialog.updates_dom0.setChecked(False)
        self.__click_ok()

        if not hasattr(self.app, 'check_updates_dom0'):
            self.skipTest("check_updates_dom0 property not implemented")

        self.assertFalse(self.app.check_updates_dom0)

    @wrap_in_loop
    def test_70_set_vm_updates_true(self):
        self.dialog.updates_vm.setChecked(True)
        self.__click_ok()

        self.assertTrue(self.app.check_updates_vm)

    @wrap_in_loop
    def test_71_set_vm_updates_false(self):
        self.dialog.updates_vm.setChecked(False)
        self.__click_ok()

        self.assertFalse(self.app.check_updates_vm)

    @wrap_in_loop
    def test_72_set_all_vms_true(self):

        with unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                                 return_value=QtGui.QMessageBox.Yes) as msgbox:

            QtTest.QTest.mouseClick(self.dialog.enable_updates_all,
                                    QtCore.Qt.LeftButton)

            msgbox.assert_called_once_with(
                self.dialog,
                "Change state of all qubes",
                "Are you sure you want to set all qubes to check for updates?",
                unittest.mock.ANY)

        for vm in self.app.domains:
            self.assertTrue(vm.features['check-updates'])

    @wrap_in_loop
    def test_73_set_all_vms_false(self):
        with unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                                 return_value=QtGui.QMessageBox.Yes) as msgbox:
            QtTest.QTest.mouseClick(self.dialog.disable_updates_all,
                                    QtCore.Qt.LeftButton)

            msgbox.assert_called_once_with(
                self.dialog,
                "Change state of all qubes",
                "Are you sure you want to set all qubes to not check "
                "for updates?",
                unittest.mock.ANY)

        for vm in self.app.domains:
            self.assertFalse(vm.features['check-updates'])


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
