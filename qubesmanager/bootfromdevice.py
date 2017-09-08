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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#

import subprocess
from . import utils
from .firewall import *
from .ui_bootfromdevice import *
import qubesadmin.tools.qvm_start as qvm_start


class VMBootFromDeviceWindow(Ui_BootDialog, QDialog):
    def __init__(self, vm, qapp, parent=None):
        super(VMBootFromDeviceWindow, self).__init__(parent)

        self.vm = vm
        self.qapp = qapp

        self.setupUi(self)
        self.setWindowTitle(self.tr("Boot {vm} from device").format(vm=self.vm.name))

        self.connect(self.buttonBox, SIGNAL("accepted()"), self.save_and_apply)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.reject)

        # populate buttons and such
        self.__init_buttons__()


    def reject(self):
        self.done(0)

    def save_and_apply(self):
        if self.blockDeviceRadioButton.isChecked():
            cdrom_location = self.blockDeviceComboBox.currentText()
        elif self.fileRadioButton.isChecked():
            cdrom_location = self.vm_list[self.fileVM.currentIndex()] + ":" + self.pathText.text()
        else:
            QMessageBox.warning(None,
                                self.tr(
                                    "ERROR!"),
                                self.tr("No file or block device selected; please select one."))
            return

        qvm_start.main(['--cdrom', cdrom_location, self.vm.name])

    def __init_buttons__(self):
        self.fileVM.setEnabled(False)
        self.selectFileButton.setEnabled(False)
        self.blockDeviceComboBox.setEnabled(False)

        self.blockDeviceRadioButton.clicked.connect(self.radio_button_clicked)
        self.fileRadioButton.clicked.connect(self.radio_button_clicked)
        self.selectFileButton.clicked.connect(self.select_file_dialog)

        self.vm_list, self.vm_idx = utils.prepare_vm_choice(
            self.fileVM,
            self.vm, None,
            None,
            None,
            allow_default=False, allow_none=False)

        self.block_list, self.block_idx = utils.prepare_choice(
            self.blockDeviceComboBox,
            self.vm,
            None,
            [device for domain in self.vm.app.domains
                    for device in domain.devices["block"]],
            None,
            None,
            allow_default=False, allow_none=False
        )

    def radio_button_clicked(self):
        self.blockDeviceComboBox.setEnabled(self.blockDeviceRadioButton.isChecked())
        self.fileVM.setEnabled(self.fileRadioButton.isChecked())
        self.selectFileButton.setEnabled(self.fileRadioButton.isChecked())
        self.pathText.setEnabled(self.fileRadioButton.isChecked())

    def select_file_dialog(self):
        backend_vm = self.vm_list[self.fileVM.currentIndex()]

        try:
            new_path = utils.get_path_from_vm(backend_vm, "qubes.SelectFile")
        except subprocess.CalledProcessError:
            new_path = None

        if new_path:
            self.pathText.setText(new_path)


parser = qubesadmin.tools.QubesArgumentParser(vmname_nargs=1)

def main(args=None):
    global bootfromdevice_window

    args = parser.parse_args(args)
    vm = args.domains.pop()

    qapp = QApplication(sys.argv)
    qapp.setOrganizationName('Invisible Things Lab')
    qapp.setOrganizationDomain("https://www.qubes-os.org/")
    qapp.setApplicationName("Qubes VM Settings")

#    if not utils.is_debug(): #FIXME
#        sys.excepthook = handle_exception

    bootfromdevice_window = VMBootFromDeviceWindow(vm, qapp)
    bootfromdevice_window.show()

    qapp.exec_()
    qapp.exit()

if __name__ == "__main__":
    main()
