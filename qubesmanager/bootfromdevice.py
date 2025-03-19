#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org/
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

import functools
import subprocess
from . import utils
from . import ui_bootfromdevice  # pylint: disable=no-name-in-module
from PyQt6 import QtWidgets, QtGui, QtCore  # pylint: disable=import-error
from qubesadmin import tools
from qubesadmin import exc
from qubesadmin.tools import qvm_start

# this is needed for icons to actually work
# pylint: disable=unused-import, no-name-in-module
from . import resources

class VMBootFromDeviceWindow(ui_bootfromdevice.Ui_BootDialog,
                             QtWidgets.QDialog):
    def __init__(self, vm, qapp, qubesapp=None, *, parent=None, new_vm=False):
        super().__init__(parent)

        self.vm = vm
        self.qapp = qapp
        self.qubesapp = qubesapp
        self.cdrom_location = None
        self.new_vm = new_vm

        self.setupUi(self)
        self.setWindowTitle(
            self.tr("Boot {vm} from device").format(vm=self.vm))
        self.setWindowFlags(self.windowFlags() |
                            QtCore.Qt.WindowType.WindowMaximizeButtonHint |
                            QtCore.Qt.WindowType.WindowMinimizeButtonHint)

        self.buttonBox.accepted.connect(self.save_and_apply)
        self.buttonBox.rejected.connect(self.reject)

        # populate buttons and such
        self.__init_buttons__()
        # warn user if the VM is currently running
        self.__warn_if_running__()

    def setup_application(self):
        self.qapp.setApplicationName(self.tr("Boot Qube From Device"))
        self.qapp.setWindowIcon(QtGui.QIcon.fromTheme("qubes-manager"))

    def save_and_apply(self):
        if self.blockDeviceRadioButton.isChecked():
            self.cdrom_location = self.blockDeviceComboBox.currentText()
        elif self.fileRadioButton.isChecked():
            self.cdrom_location = str(self.fileVM.currentData()) + \
                             ":" + self.pathText.text()
        else:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("ERROR!"),
                self.tr("No file or block device selected; please select one."))
            return

        # warn user if the VM is currently running
        self.__warn_if_running__()
        self.accept()

    def __warn_if_running__(self):
        if self.new_vm:
            return

        try:
            if self.qubesapp.domains[self.vm].is_running():
                QtWidgets.QMessageBox.warning(
                    self,
                    self.tr("Warning!"),
                    self.tr("Qube must be turned off before booting it from "
                            "device. Please turn off the qube."))
        except exc.QubesDaemonAccessError:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Warning!"),
                self.tr("Insufficient permissions to determine if qube is "
                        "running. It must be turned off before booting it from "
                        "device."))

    def __init_buttons__(self):
        self.fileVM.setEnabled(False)
        self.selectFileButton.setEnabled(False)
        self.blockDeviceComboBox.setEnabled(False)

        self.blockDeviceRadioButton.clicked.connect(self.radio_button_clicked)
        self.fileRadioButton.clicked.connect(self.radio_button_clicked)
        self.selectFileButton.clicked.connect(self.select_file_dialog)

        utils.initialize_widget_with_vms(
            widget=self.fileVM,
            qubes_app=self.qubesapp,
            filter_function=(lambda x: x != self.vm),
            allow_internal=True
        )

        device_choice = []

        for domain in self.qubesapp.domains:
            try:
                for device in domain.devices["block"]:
                    device_choice.append((str(device), device))
            except exc.QubesDaemonAccessError:
                # insufficient permissions
                pass

        if device_choice:
            utils.initialize_widget(
                widget=self.blockDeviceComboBox,
                choices=device_choice,
                selected_value=device_choice[0][1],
                add_current_label=False
            )
        else:
            self.blockDeviceRadioButton.setEnabled(False)
            self.blockDeviceComboBox.setEnabled(False)
            self.blockDeviceComboBox.addItem("no block devices found!")
            self.blockDeviceComboBox.setCurrentIndex(0)

    def radio_button_clicked(self):
        self.blockDeviceComboBox.setEnabled(
            self.blockDeviceRadioButton.isChecked())
        self.fileVM.setEnabled(self.fileRadioButton.isChecked())
        self.selectFileButton.setEnabled(self.fileRadioButton.isChecked())
        self.pathText.setEnabled(self.fileRadioButton.isChecked())

    def select_file_dialog(self):
        backend_vm = self.fileVM.currentData()
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

    window = utils.run_synchronous(
        functools.partial(VMBootFromDeviceWindow, vm))
    if window.result() == 1 and window.cdrom_location is not None:
        qvm_start.main(['--cdrom', window.cdrom_location, vm.name])

if __name__ == "__main__":
    main()
