#!/usr/bin/python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
#
#

from . import ui_devicelist  # pylint: disable=no-name-in-module
from PyQt4 import QtGui, QtCore  # pylint: disable=import-error


class PCIDeviceListWindow(ui_devicelist.Ui_Dialog, QtGui.QDialog):
    def __init__(self, vm, qapp, dev_list, parent=None):
        super(PCIDeviceListWindow, self).__init__(parent)

        self.vm = vm
        self.qapp = qapp
        self.dev_list = dev_list

        self.setupUi(self)

        self.connect(
            self.buttonBox, QtCore.SIGNAL("accepted()"), self.save_and_apply)
        self.connect(
            self.buttonBox, QtCore.SIGNAL("rejected()"), self.reject)

        self.fill_device_list()

    def fill_device_list(self):
        self.device_list.clear()

        pci_devices = [ass.ident.replace('_', ':')
                       for ass in self.vm.devices['pci'].assignments()]

        for i in range(self.dev_list.selected_list.count()):
            text = self.dev_list.selected_list.item(i).text()
            ident = self.dev_list.selected_list.item(i).ident
            if ident in pci_devices:
                self.device_list.addItem(text)

    def reject(self):
        self.done(0)

    def save_and_apply(self):
        self.done(0)

    def show(self):
        super(PCIDeviceListWindow, self).show()
        self.fill_device_list()
