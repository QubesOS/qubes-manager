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

from PyQt4 import QtGui, QtTest, QtCore
from qubesadmin import Qubes
import qubesmanager.backup as backup_gui


class BackupTest(unittest.TestCase):
    def setUp(self):
        super(QubeManagerTest, self).setUp()

        self.mock_qprogress = unittest.mock.patch('PyQt4.QtGui.QProgressDialog')
        self.mock_qprogress.start()

        self.addCleanup(self.mock_qprogress.stop)

        self.qapp = Qubes()
        self.qtapp = QtGui.QApplication(sys.argv)
        self.dispatcher = events.EventsDispatcher(self.qapp)

        self.loop = quamash.QEventLoop(self.qtapp)

        self.dialog = qube_manager.VmManagerWindow(
            self.qtapp, self.qapp, self.dispatcher)

    def tearDown(self):
        self.qtapp.deleteLater()
        self.dialog.deleteLater()
        self.qtapp.processEvents()
        self.qtapp.processEvents()
        self.qtapp.processEvents()
        self.loop.run_until_complete(asyncio.sleep(0))
        self.loop.close()
        del self.loop
        del self.qtapp
        del self.dialog
        gc.collect()
        super(QubeManagerTest, self).tearDown()

class BackupTest(unittest.TestCase):
    def setUp(self):
        super(BackupTest, self).setUp()

        # mock up nonexistence of saved backup settings
        self.patcher = unittest.mock.patch('builtins.open')
        self.mock_open = self.patcher.start()
        self.mock_open.side_effect = FileNotFoundError()
        self.addCleanup(self.patcher.stop)

        self.qapp = Qubes()
        self.qtapp = QtGui.QApplication(sys.argv)
        self.dialog = backup_gui.BackupVMsWindow(self.qtapp, self.qapp)

    def tearDown(self):
        del self.dialog
        del self.qtapp
        del self.qapp
        super(BackupTest, self).tearDown()

    def test_00_window_loads(self):
        self.assertTrue(self.dialog.select_vms_widget is not None)

    def test_01_vms_load_correctly(self):
        all_vms = len([vm for vm in self.qapp.domains
                       if not vm.features.get('internal', False)])

        selected_vms = self.dialog.select_vms_widget.selected_list.count()
        available_vms = self.dialog.select_vms_widget.available_list.count()

        self.assertEqual(all_vms, available_vms + selected_vms)

    def test_02_correct_defaults(self):
        # backup is compressed
        self.assertTrue(self.dialog.compress_checkbox.isChecked(),
                        "Compress backup should be checked by default")

        # correct VMs are selected
        include_in_backups_no = len([vm for vm in self.qapp.domains
                                     if not vm.features.get('internal', False)
                                     and getattr(vm, 'include_in_backups', True)])
        selected_no = self.dialog.select_vms_widget.selected_list.count()
        self.assertEqual(include_in_backups_no, selected_no,
                         "Incorrect VMs selected by default")

        # passphrase is empty
        self.assertEqual(self.dialog.passphrase_line_edit.text(), "",
                          "Passphrase should be empty")

        # save defaults
        self.assertTrue(self.dialog.save_profile_checkbox.isChecked(),
                        "By default, profile should be saved")

    # Check if target vms are selected
    # Check if no default file loads correctly - another file??
    # TODO: make a separate backup testing file to test various backup defaults


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
