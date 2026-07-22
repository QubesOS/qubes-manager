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
from unittest import mock

from qubesmanager import bootfromdevice, utils


def _boot_dialog():
    dialog = bootfromdevice.VMBootFromDeviceWindow.__new__(
        bootfromdevice.VMBootFromDeviceWindow
    )
    dialog.tr = lambda text: text
    return dialog


@mock.patch("qubesmanager.bootfromdevice.utils.initialize_widget")
@mock.patch("qubesmanager.bootfromdevice.utils.initialize_widget_with_vms")
def test_00_init_buttons_sets_path_tooltips(
    mock_initialize_widget_with_vms, mock_initialize_widget
):
    dialog = _boot_dialog()
    dialog.fileVM = mock.Mock()
    dialog.selectFileButton = mock.Mock()
    dialog.blockDeviceComboBox = mock.Mock()
    dialog.blockDeviceRadioButton = mock.Mock()
    dialog.fileRadioButton = mock.Mock()
    dialog.pathText = mock.Mock()
    dialog.vm = "test-vm"
    dialog.qubesapp = mock.Mock()
    dialog.qubesapp.domains = []

    bootfromdevice.VMBootFromDeviceWindow.__init_buttons__(dialog)

    message = utils.get_path_chars_message()
    dialog.pathText.setToolTip.assert_called_once_with(message)
    dialog.selectFileButton.setToolTip.assert_called_once_with(message)
    mock_initialize_widget_with_vms.assert_called_once()
    mock_initialize_widget.assert_not_called()


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
@mock.patch("qubesmanager.bootfromdevice.utils.get_path_from_vm")
def test_01_select_file_dialog_invalid_characters(mock_get_path, mock_warning):
    dialog = _boot_dialog()
    dialog.fileVM = mock.Mock()
    dialog.pathText = mock.Mock()
    backend_vm = mock.Mock(name="backend-vm")
    dialog.fileVM.currentData.return_value = backend_vm
    mock_get_path.side_effect = ValueError(utils.get_path_chars_message())

    bootfromdevice.VMBootFromDeviceWindow.select_file_dialog(dialog)

    mock_warning.assert_called_once_with(
        dialog,
        "Unexpected characters in path!",
        utils.get_path_chars_message(),
    )
    dialog.pathText.setText.assert_not_called()
