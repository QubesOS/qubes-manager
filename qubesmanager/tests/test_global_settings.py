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
# pylint: disable=wrong-import-position
import os
os.environ['QUAMASH_QTIMPL'] = 'PyQt4'

import logging.handlers
import quamash
import asyncio
import unittest
import unittest.mock
import gc

from PyQt4 import QtGui, QtTest, QtCore
from qubesadmin import Qubes
import qubesmanager.global_settings as global_settings


class GlobalSettingsTest(unittest.TestCase):
    def setUp(self):
        super(GlobalSettingsTest, self).setUp()

        self.qapp = Qubes()
        self.qtapp = QtGui.QApplication(["test", "-style", "cleanlooks"])
        self.loop = quamash.QEventLoop(self.qtapp)
        self.dialog = global_settings.GlobalSettingsWindow(self.qtapp,
                                                           self.qapp)

        self.setattr_patcher = unittest.mock.patch.object(
            type(self.dialog.qvm_collection), "__setattr__")
        self.setattr_mock = self.setattr_patcher.start()
        self.addCleanup(self.setattr_patcher.stop)

    def tearDown(self):
        # process any pending events before destroying the object
        self.qtapp.processEvents()

        # queue destroying the QApplication object, do that for any other QT
        # related objects here too
        self.qtapp.deleteLater()
        self.dialog.deleteLater()

        # process any pending events (other than just queued destroy),
        # just in case
        self.qtapp.processEvents()

        # execute main loop, which will process all events, _
        # including just queued destroy_
        self.loop.run_until_complete(asyncio.sleep(0))

        # at this point it QT objects are destroyed, cleanup all remaining
        # references;
        # del other QT object here too
        self.loop.close()
        del self.dialog
        del self.qtapp
        del self.loop
        gc.collect()
        super(GlobalSettingsTest, self).tearDown()

    def test_00_settings_started(self):
        # non-empty drop-downs
        self.assertNotEqual(
            self.dialog.default_kernel_combo.currentText(), "",
            "Default kernel not listed")
        self.assertNotEqual(
            self.dialog.default_netvm_combo.currentText(), "",
            "Default netVM not listed")
        self.assertNotEqual(
            self.dialog.default_template_combo.currentText(),
            "", "Default template not listed")
        self.assertNotEqual(
            self.dialog.clock_vm_combo.currentText(), "",
            "ClockVM not listed")
        self.assertNotEqual(
            self.dialog.update_vm_combo.currentText(), "",
            "UpdateVM for dom0 not listed")
        self.assertNotEqual(
            self.dialog.default_dispvm_combo.currentText(), "",
            "Default DispVM not listed")

        # not empty memory settings
        self.assertTrue(len(self.dialog.min_vm_mem.text()) > 4,
                        "Too short min mem value")
        self.assertTrue(len(self.dialog.dom0_mem_boost.text()) > 4,
                        "Too short dom0 mem boost value")

    def test_01_load_correct_defs(self):
        # correctly selected default template
        selected_default_template = \
            self.dialog.default_template_combo.currentText()
        self.assertTrue(
            selected_default_template.startswith(
                str(getattr(self.qapp, 'default_template', '(none)'))),
            "Incorrect default template loaded")

        # correctly selected default NetVM
        selected_default_netvm = self.dialog.default_netvm_combo.currentText()
        self.assertTrue(selected_default_netvm.startswith(
            str(getattr(self.qapp, 'default_netvm', '(none)'))),
            "Incorrect default netVM loaded")

        # correctly selected default kernel
        selected_default_kernel = self.dialog.default_kernel_combo.currentText()
        self.assertTrue(selected_default_kernel.startswith(
            str(getattr(self.qapp, 'default_kernel', '(none)'))),
            "Incorrect default kernel loaded")

        # correct ClockVM
        selected_clockvm = self.dialog.clock_vm_combo.currentText()
        correct_clockvm = str(getattr(self.qapp, 'clockvm', "(none)"))
        self.assertTrue(selected_clockvm.startswith(correct_clockvm),
                        "Incorrect clockVM loaded")

        # correct updateVM
        selected_updatevm = self.dialog.update_vm_combo.currentText()
        correct_updatevm = str(getattr(self.qapp, 'updatevm', "(none)"))
        self.assertTrue(selected_updatevm.startswith(correct_updatevm),
                        "Incorrect updateVm loaded")

        # correct defaultDispVM
        selected_default_dispvm = self.dialog.default_dispvm_combo.currentText()
        correct_default_dispvm = \
            str(getattr(self.qapp, 'default_dispvm', "(none)"))
        self.assertTrue(
            selected_default_dispvm.startswith(correct_default_dispvm),
            "Incorrect defaultDispVM loaded")

        # update vm status
        self.assertEqual(self.qapp.check_updates_vm,
                         self.dialog.updates_vm.isChecked(),
                         "Incorrect check qube updates value loaded")

    def test_02_dom0_updates_load(self):
        # check dom0 updates
        try:
            dom0_updates = self.qapp.domains[
                'dom0'].features['service.qubes-update-check']
        except KeyError:
            self.skipTest("check_updates_dom0 property not implemented")
            return

        self.assertEqual(bool(dom0_updates),
                         self.dialog.updates_dom0.isChecked(),
                         "Incorrect dom0 updates value")

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

        QtTest.QTest.mouseClick(okwidget, QtCore.Qt.LeftButton)

    def __click_cancel(self):
        cancelwidget = self.dialog.buttonBox.button(
            self.dialog.buttonBox.Cancel)

        QtTest.QTest.mouseClick(cancelwidget, QtCore.Qt.LeftButton)

    def test_03_nothing_changed_ok(self):
        self.__click_ok()

        self.assertEqual(self.setattr_mock.call_count, 0,
                         "Changes occurred despite no changes being made")

    def test_04_nothing_changed_cancel(self):
        self.__click_cancel()

        self.assertEqual(self.setattr_mock.call_count, 0,
                         "Changes occurred despite no changes being made")

    def test_10_set_update_vm(self):
        new_updatevm_name = self.__set_noncurrent(self.dialog.update_vm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('updatevm', new_updatevm_name)

    def test_11_set_update_vm_to_none(self):
        self.__set_none(self.dialog.update_vm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('updatevm', None)

    def test_20_set_clock_vm(self):
        new_clockvm_name = self.__set_noncurrent(self.dialog.clock_vm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('clockvm', new_clockvm_name)

    def test_21_set_clock_vm_to_none(self):
        self.__set_none(self.dialog.clock_vm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('clockvm', None)

    def test_30_set_default_netvm(self):
        new_netvm_name = self.__set_noncurrent(self.dialog.default_netvm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('default_netvm',
                                                  new_netvm_name)

    def test_31_set_default_netvm_to_none(self):
        self.__set_none(self.dialog.default_netvm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('default_netvm', None)

    def test_40_set_default_template(self):
        new_def_template_name = self.__set_noncurrent(
            self.dialog.default_template_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('default_template',
                                                  new_def_template_name)

    def test_50_set_default_kernel(self):
        new_def_kernel_name = self.__set_noncurrent(
            self.dialog.default_kernel_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('default_kernel',
                                                  new_def_kernel_name)

    def test_51_set_default_kernel_to_none(self):
        self.__set_none(self.dialog.default_kernel_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('default_kernel',
                                                  None)

    def test_60_set_dom0_updates_true(self):
        current_state = self.dialog.updates_dom0.isChecked()
        self.dialog.updates_dom0.setChecked(not current_state)

        with unittest.mock.patch.object(
                type(self.dialog.qvm_collection.domains['dom0'].features),
                '__setitem__') as mock_features:
            self.__click_ok()
            mock_features.assert_called_once_with('service.qubes-update-check',
                                                  not current_state)

    def test_70_change_vm_updates(self):
        current_state = self.dialog.updates_vm.isChecked()
        self.dialog.updates_vm.setChecked(not current_state)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('check_updates_vm',
                                                  not current_state)

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    @unittest.mock.patch('qubesadmin.features.Features.__setitem__')
    def test_72_set_all_vms_true(self, mock_features, msgbox):

        QtTest.QTest.mouseClick(self.dialog.enable_updates_all,
                                QtCore.Qt.LeftButton)

        self.assertEqual(msgbox.call_count, 1,
                         "Wrong number of confirmation window calls")

        call_list_expected = \
            [unittest.mock.call('service.qubes-update-check', True) for vm
             in self.qapp.domains if vm.klass != 'AdminVM']

        self.assertListEqual(call_list_expected,
                             mock_features.call_args_list)

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    @unittest.mock.patch('qubesadmin.features.Features.__setitem__')
    def test_73_set_all_vms_false(self, mock_features, msgbox):

        QtTest.QTest.mouseClick(self.dialog.disable_updates_all,
                                QtCore.Qt.LeftButton)

        self.assertEqual(msgbox.call_count, 1,
                         "Wrong number of confirmation window calls")

        call_list_expected = \
            [unittest.mock.call('service.qubes-update-check', False) for vm
             in self.qapp.domains if vm.klass != 'AdminVM']

        self.assertListEqual(call_list_expected,
                             mock_features.call_args_list)

    def test_80_set_default_dispvm(self):
        new_dispvm_name = self.__set_noncurrent(
            self.dialog.default_dispvm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('default_dispvm',
                                                  new_dispvm_name)

    def test_81_set_default_dispvm_to_none(self):
        self.__set_none(self.dialog.default_dispvm_combo)

        self.__click_ok()

        self.setattr_mock.assert_called_once_with('default_dispvm', None)

    @unittest.mock.patch.object(
        type(Qubes()), '__getattr__',
        side_effect=(lambda x: False if x == 'check_updates_vm' else None))
    def test_90_test_all_set_none(self, mock_qubes):
        mock_qubes.configure_mock()
        self.dialog = global_settings.GlobalSettingsWindow(
            self.qtapp, self.qapp)

        self.assertEqual(self.dialog.update_vm_combo.currentText(),
                         "(none) (current)",
                         "UpdateVM displays as none incorrectly")
        self.assertEqual(self.dialog.clock_vm_combo.currentText(),
                         "(none) (current)",
                         "ClockVM displays as none incorrectly")
        self.assertEqual(self.dialog.default_netvm_combo.currentText(),
                         "(none) (current)",
                         "Default NetVM displays as none incorrectly")
        self.assertEqual(self.dialog.default_template_combo.currentText(),
                         "(none) (current)",
                         "Default template displays as none incorrectly")
        self.assertEqual(self.dialog.default_kernel_combo.currentText(),
                         "(none) (current)",
                         "Defautl kernel displays as none incorrectly")
        self.assertEqual(self.dialog.default_dispvm_combo.currentText(),
                         "(none) (current)",
                         "Default DispVM displays as none incorrectly")


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()

# TODO: add tests for memory settings once memory is handled better
