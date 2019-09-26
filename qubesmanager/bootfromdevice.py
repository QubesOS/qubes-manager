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

import functools
import subprocess
from . import utils
from . import ui_bootfromdevice  # pylint: disable=no-name-in-module
from PyQt5 import QtWidgets  # pylint: disable=import-error
from qubesadmin import tools
from qubesadmin.tools import qvm_start


class VMBootFromDeviceWindow(ui_bootfromdevice.Ui_BootDialog,
                             QtWidgets.QDialog):
    def __init__(self, vm, qapp, qubesapp=None, parent=None):
        super(VMBootFromDeviceWindow, self).__init__(parent)

        self.vm = vm
        self.qapp = qapp
        self.qubesapp = qubesapp

        self.setupUi(self)
        self.setWindowTitle(
            self.tr("Boot {vm} from device").format(vm=self.vm.name))

        self.buttonBox.accepted.connect(self.save_and_apply)
        self.buttonBox.rejected.connect(self.reject)

        # populate buttons and such
        self.__init_buttons__()
        # warn user if the VM is currently running
        self.__warn_if_running__()

    def reject(self):
        self.done(0)

    def save_and_apply(self):
        if self.blockDeviceRadioButton.isChecked():
            cdrom_location = self.blockDeviceComboBox.currentText()
        elif self.fileRadioButton.isChecked():
            cdrom_location = str(
                self.vm_list[self.fileVM.currentIndex()]) + \
                             ":" + self.pathText.text()
        else:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("ERROR!"),
                self.tr("No file or block device selected; please select one."))
            return

        # warn user if the VM is currently running
        self.__warn_if_running__()

        qvm_start.main(['--cdrom', cdrom_location, self.vm.name])

        self.done(0)

    def __warn_if_running__(self):
        if self.vm.is_running():
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Warning!"),
                self.tr("Qube must be turned off before booting it from "
                        "device. Please turn off the qube.")
            )

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
        self.blockDeviceComboBox.setEnabled(
            self.blockDeviceRadioButton.isChecked())
        self.fileVM.setEnabled(self.fileRadioButton.isChecked())
        self.selectFileButton.setEnabled(self.fileRadioButton.isChecked())
        self.pathText.setEnabled(self.fileRadioButton.isChecked())

    def select_file_dialog(self):
        backend_vm = self.vm_list[self.fileVM.currentIndex()]
        error_occurred = False

        try:
            new_path = utils.get_path_from_vm(backend_vm, "qubes.SelectFile")
        except subprocess.CalledProcessError as ex:
            if ex.returncode != 1:
                # Error other than 'user did not select a file'
                error_occurred = True
            new_path = None
        except Exception:  # pylint: disable=broad-except
            error_occurred = True
            new_path = None

        if error_occurred:
            QtWidgets.QMessageBox.warning(
                None,
                self.tr("Failed to display file selection dialog"),
                self.tr("Check if the qube {0} can be started and has a file"
                        " manager installed.").format(backend_vm)
            )

        if new_path:
            self.pathText.setText(new_path)


parser = tools.QubesArgumentParser(vmname_nargs=1)


def main(args=None):
    args = parser.parse_args(args)
    vm = args.domains.pop()

    utils.run_synchronous("Boot Qube From Device",
                          functools.partial(VMBootFromDeviceWindow, vm))


if __name__ == "__main__":
    main()
