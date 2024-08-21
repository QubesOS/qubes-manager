#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2020 Marta Marczykowska-Górecka
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
from qubesmanager.tests import init_qtapp
from qubesmanager import clone_vm

# TODO: test when you do give a src vm


class CloneVMTest(unittest.TestCase):
    def setUp(self):
        super(CloneVMTest, self).setUp()
        self.qtapp, self.loop = init_qtapp()

        self.qapp = Qubes()

        # mock up the Create VM Thread to avoid changing system state
        self.patcher_thread = unittest.mock.patch(
            'qubesmanager.common_threads.CloneVMThread')
        self.mock_thread = self.patcher_thread.start()
        self.addCleanup(self.patcher_thread.stop)

        # mock the progress dialog to speed testing up
        self.patcher_progress = unittest.mock.patch(
            'PyQt5.QtWidgets.QProgressDialog')
        self.mock_progress = self.patcher_progress.start()
        self.addCleanup(self.patcher_progress.stop)

        # mock the message dialog to not hang on success
        self.patcher_warning = unittest.mock.patch(
            'PyQt5.QtWidgets.QMessageBox.warning')
        self.mock_warning = self.patcher_warning.start()
        self.addCleanup(self.patcher_warning.stop)
        self.patcher_information = unittest.mock.patch(
            'PyQt5.QtWidgets.QMessageBox.information')
        self.mock_information = self.patcher_information.start()
        self.addCleanup(self.patcher_information.stop)

        self.dialog = clone_vm.CloneVMDlg(self.qtapp, self.qapp)

    def test_00_window_loads(self):
        self.assertGreater(self.dialog.src_vm.count(), 0,
                           "No source vms shown")

        self.assertGreater(self.dialog.label.count(), 0, "No labels listed")

        self.assertGreater(self.dialog.storage_pool.count(), 0,
                           "No pools listed")

        self.assertTrue(self.dialog.src_vm.isEnabled(),
                        "source vm dialog not active")

    def test_01_cancel_works(self):
        self.__click_cancel()
        self.assertEqual(self.mock_thread.call_count, 0,
                         "Attempted to create VM on cancel")

    def test_02_name_correctly_updates(self):
        src_name = self.dialog.src_vm.currentText()
        target_name = self.dialog.name.text()

        self.assertTrue(target_name.startswith(src_name),
                        "target name does not contain source name")
        self.assertTrue('clone' in target_name,
                        "target name does not contain >clone<")

        self.dialog.src_vm.setCurrentIndex(self.dialog.src_vm.currentIndex()+1)

        src_name = self.dialog.src_vm.currentText()
        target_name = self.dialog.name.text()

        self.assertTrue(target_name.startswith(src_name),
                        "target name does not contain source name")
        self.assertTrue('clone' in target_name,
                        "target name does not contain >clone<")

    def test_03_label_correctly_updates(self):
        src_label = self.dialog.src_vm.currentData().label.name
        target_label = self.dialog.label.currentText()

        self.assertEqual(src_label, target_label, "incorrect start label")

        while self.dialog.src_vm.currentData().label.name == src_label:
            self.dialog.src_vm.setCurrentIndex(
                self.dialog.src_vm.currentIndex() + 1)

        src_label = self.dialog.src_vm.currentData().label.name
        target_label = self.dialog.label.currentText()

        self.assertEqual(src_label, target_label,
                         "label did not change correctly")

    def test_04_clone_first_vm(self):
        self.dialog.name.setText("clone-test")
        src_vm = self.qapp.domains[self.dialog.src_vm.currentText()]
        self.__click_ok()

        self.mock_thread.assert_called_once_with(
            src_vm, "clone-test", pool=None, label=src_vm.label)
        self.mock_thread().start.assert_called_once_with()

    def test_05_clone_other_vm(self):
        self.dialog.src_vm.setCurrentIndex(self.dialog.src_vm.currentIndex()+1)
        src_vm = self.qapp.domains[self.dialog.src_vm.currentText()]

        dst_name = self.dialog.name.text()

        self.__click_ok()

        self.mock_thread.assert_called_once_with(
            src_vm, dst_name, pool=None, label=src_vm.label)
        self.mock_thread().start.assert_called_once_with()

    def test_06_clone_label(self):
        src_vm = self.qapp.domains[self.dialog.src_vm.currentText()]

        dst_name = self.dialog.name.text()

        while self.dialog.label.currentText() != 'blue':
            self.dialog.label.setCurrentIndex(
                self.dialog.label.currentIndex()+1)

        self.__click_ok()

        self.mock_thread.assert_called_once_with(
            src_vm, dst_name, pool=None, label=self.qapp.labels['blue'])
        self.mock_thread().start.assert_called_once_with()

    @unittest.mock.patch('subprocess.check_call')
    def test_07_launch_settings(self, mock_call):
        self.dialog.launch_settings.setChecked(True)

        self.dialog.name.setText("clone-test")

        self.__click_ok()

        self.mock_thread.assert_called_once_with(
            unittest.mock.ANY, "clone-test", pool=None,
            label=unittest.mock.ANY)

        self.mock_thread().msg = ("Success", "Success")
        self.dialog.clone_finished()

        mock_call.assert_called_once_with(['qubes-vm-settings', "clone-test"])

    def test_08_progress_hides(self):
        self.dialog.name.setText("clone-test")

        self.__click_ok()

        self.mock_thread.assert_called_once_with(
            unittest.mock.ANY, "clone-test", pool=None,
            label=unittest.mock.ANY)

        # make sure the thread is not reporting an error
        self.mock_thread().start.assert_called_once_with()
        self.mock_thread().msg = ("Success", "Success")

        self.mock_progress().show.assert_called_once_with()

        self.dialog.clone_finished()

        self.mock_progress().hide.assert_called_once_with()

    def test_09_pool_nondefault(self):
        while 'default' in self.dialog.storage_pool.currentText():
            self.dialog.storage_pool.setCurrentIndex(
                self.dialog.storage_pool.currentIndex()+1)

        selected_pool = self.dialog.storage_pool.currentText()

        self.__click_ok()

        self.mock_thread.assert_called_once_with(
            unittest.mock.ANY, unittest.mock.ANY,
            pool=selected_pool,
            label=unittest.mock.ANY)
        self.mock_thread().start.assert_called_once_with()

    def __click_ok(self):
        okwidget = self.dialog.buttonBox.button(
                    self.dialog.buttonBox.Ok)

        QtTest.QTest.mouseClick(okwidget, QtCore.Qt.LeftButton)

    def __click_cancel(self):
        cancelwidget = self.dialog.buttonBox.button(
            self.dialog.buttonBox.Cancel)

        QtTest.QTest.mouseClick(cancelwidget, QtCore.Qt.LeftButton)


class CloneVMTestSrcVM(unittest.TestCase):
    def setUp(self):
        super(CloneVMTestSrcVM, self).setUp()
        self.qtapp, self.loop = init_qtapp()

        self.qapp = Qubes()

        # mock up the Create VM Thread to avoid changing system state
        self.patcher_thread = unittest.mock.patch(
            'qubesmanager.common_threads.CloneVMThread')
        self.mock_thread = self.patcher_thread.start()
        self.addCleanup(self.patcher_thread.stop)

        # mock the progress dialog to speed testing up
        self.patcher_progress = unittest.mock.patch(
            'PyQt5.QtWidgets.QProgressDialog')
        self.mock_progress = self.patcher_progress.start()
        self.addCleanup(self.patcher_progress.stop)

        # mock the message dialog to not hang on success
        self.patcher_warning = unittest.mock.patch(
            'PyQt5.QtWidgets.QMessageBox.warning')
        self.mock_warning = self.patcher_warning.start()
        self.addCleanup(self.patcher_warning.stop)
        self.patcher_information = unittest.mock.patch(
            'PyQt5.QtWidgets.QMessageBox.information')
        self.mock_information = self.patcher_information.start()
        self.addCleanup(self.patcher_information.stop)

        self.src_vm = next(
            domain for domain in self.qapp.domains
             if domain.klass != 'AdminVM')

        self.dialog = clone_vm.CloneVMDlg(self.qtapp, self.qapp,
                                          src_vm=self.src_vm)

    def test_00_window_loads(self):
        self.assertEqual(self.dialog.src_vm.currentText(), self.src_vm.name)
        self.assertEqual(self.dialog.src_vm.currentData(), self.src_vm)

        self.assertFalse(self.dialog.src_vm.isEnabled(),
                         "source vm dialog active")

        self.assertEqual(self.dialog.label.currentText(),
                         self.src_vm.label.name)

    def test_01_simple_clone(self):
        self.dialog.name.setText("clone-test")

        self.__click_ok()

        self.mock_thread.assert_called_once_with(
            self.src_vm, "clone-test", pool=None, label=self.src_vm.label)
        self.mock_thread().start.assert_called_once_with()

    def __click_ok(self):
        okwidget = self.dialog.buttonBox.button(
                    self.dialog.buttonBox.Ok)

        QtTest.QTest.mouseClick(okwidget, QtCore.Qt.LeftButton)


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
