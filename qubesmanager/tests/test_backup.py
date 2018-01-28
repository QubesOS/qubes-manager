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
# import unittest.mock

from PyQt4 import QtGui, QtTest, QtCore
from qubesadmin import Qubes
import qubesmanager.backup as backup_gui


class BackupTest(unittest.TestCase):
    def setUp(self):
        super(BackupTest, self).setUp()

        self.qapp = Qubes()
        self.qtapp = QtGui.QApplication(sys.argv)
        self.dialog = backup_gui.BackupVMsWindow(self.qtapp, self.qapp)

    def tearDown(self):
        del self.dialog
        del self.qtapp
        del self.qapp
        super(BackupTest, self).tearDown()

    def test_window_loads(self):
        self.assertTrue(self.dialog.select_vms_widget is not None)

    def test_vms_load_correctly(self):
        all_vms = len([vm for vm in self.qapp.domains
                       if not vm.features.get('internal', False)])

        selected_vms = self.dialog.select_vms_widget.selected_list.count()
        available_vms = self.dialog.select_vms_widget.available_list.count()

        self.assertEqual(all_vms, available_vms + selected_vms)


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
