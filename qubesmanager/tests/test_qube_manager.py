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
import sys
import unittest
import unittest.mock
import gc

from PyQt4 import QtGui, QtTest, QtCore
from qubesadmin import Qubes
import qubesmanager.qube_manager as qube_manager


class QubeManagerTest(unittest.TestCase):
    def setUp(self):
        super(QubeManagerTest, self).setUp()

        # # todo: mockup no settings file
        # self.patcher = unittest.mock.patch('builtins.open')
        # self.mock_open = self.patcher.start()
        # self.mock_open.side_effect = FileNotFoundError()
        # self.addCleanup(self.patcher.stop)

        self.qapp = Qubes()
        self.qtapp = QtGui.QApplication(sys.argv)
        self.dialog = qube_manager.VmManagerWindow(self.qtapp, self.qapp)

    def tearDown(self):
        del self.dialog
        del self.qtapp
        del self.qapp
        super(QubeManagerTest, self).tearDown()
        gc.collect()

    # 0 - Check if the window was displayed and populated correctly

    def test_00_window_loads(self):
        self.assertTrue(self.dialog.table is not None)

    @unittest.expectedFailure
    def test_01_table_populates_correctly(self):
        vms_in_table = []
        for row in range(self.dialog.table.rowCount()):
            item = self.dialog.table.item(row,
                                          self.dialog.columns_indices["Name"])
            self.assertIsNotNone(item)
            vms_in_table.append(item.text())

        actual_vms = [vm.name for vm in self.qapp.domains]

        self.assertEqual(len(vms_in_table), len(actual_vms),
                         "Incorrect number of VMs loaded")
        self.assertListEqual(sorted(vms_in_table), sorted(actual_vms),
                             "Incorrect VMs loaded")
# todos:
    # did settings load correctly
    # did settings save corectly

    @unittest.mock.patch('qubesmanager.settings.VMSettingsWindow')
    def test_20_vm_open_settings(self, mock_window):
        selected_vm = self._select_non_admin_vm()
        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")
        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_settings)
        QtTest.QTest.mouseClick(widget,
                                QtCore.Qt.LeftButton)
        mock_window.assert_called_once_with(selected_vm, self.qtapp, "basic")

    @unittest.mock.patch('qubesmanager.settings.VMSettingsWindow')
    def test_21_vm_firewall_settings(self, mock_window):
        selected_vm = self._select_non_admin_vm()
        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")
        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_editfwrules)
        QtTest.QTest.mouseClick(widget,
                                QtCore.Qt.LeftButton)
        mock_window.assert_called_once_with(selected_vm, self.qtapp, "firewall")


# test whether pause/start/resume works
    @unittest.mock.patch('qubesmanager.qubesadmin.vm.QubesVM.pause')
    @unittest.mock.patch('qubesmanager.qubesadmin.vm.QubesVM.is_running')
    @unittest.mock.patch('qubesmanager.qubesadmin.vm.QubesVM.get_power_state')
    def _select_non_admin_vm(self):
        for row in range(self.dialog.table.rowCount()):
            template = self.dialog.table.item(
                row, self.dialog.columns_indices["Template"])
            if template.text() != 'AdminVM':
                self.dialog.table.setCurrentItem(template)
                return template.vm
        return None

if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
