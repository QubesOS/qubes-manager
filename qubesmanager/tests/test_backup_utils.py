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
import unittest.mock
from PyQt6 import QtWidgets
from qubesadmin import Qubes

from qubesmanager import backup_utils
from qubesmanager.tests import init_qtapp


class BackupUtilsTest(unittest.TestCase):
    def setUp(self):
        super(BackupUtilsTest, self).setUp()
        self.qtapp, self.loop = init_qtapp()
        self.qapp = Qubes()

    def test_01_fill_apvms(self):
        dialog = QtWidgets.QDialog()
        combobox = QtWidgets.QComboBox()
        dialog.appvm_combobox = combobox
        dialog.qubes_app = self.qapp

        backup_utils.fill_appvms_list(dialog)

        # see if the dialog has nothing selected
        self.assertEqual(combobox.currentIndex(), 0,
                         "Incorrect item selected")

        # the combobox should contain running VMs that are not internal and
        #  not template
        expected_vm_list = [vm.name for vm in self.qapp.domains
                            if vm.is_running() and vm.klass != 'TemplateVM'
                            and not getattr(vm, 'internal', False)]
        received_vm_list = []
        for i in range(combobox.count()):
            received_vm_list.append(combobox.itemText(i))

        self.assertListEqual(sorted(expected_vm_list), sorted(received_vm_list),
                             "VM list not filled correctly")


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
