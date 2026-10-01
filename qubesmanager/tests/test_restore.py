# The Qubes OS Project, https://www.qubes-os.org/
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

from unittest import mock

from qubesmanager import restore


@mock.patch("PyQt6.QtWidgets.QMessageBox.warning")
def test_rejects_manually_entered_path_with_invalid_characters(mock_warning):
    dialog = restore.RestoreVMsWindow.__new__(restore.RestoreVMsWindow)
    dialog.tr = lambda text: text
    dialog.select_dir_page = object()
    dialog.currentPage = lambda: dialog.select_dir_page
    dialog.dir_line_edit = mock.Mock()
    dialog.dir_line_edit.text.return_value = "/home/zażółć"

    assert not restore.RestoreVMsWindow.validateCurrentPage(dialog)
    mock_warning.assert_called_once()
