# SPDX-License-Identifier: GPL-2.0-or-later
"""Check that the firewall dialog leaves room for its wrapped warning."""
import pytest
from PyQt6 import QtGui, QtWidgets

from qubesmanager.ui_newfwruledlg import Ui_NewFwRuleDlg


@pytest.mark.parametrize("font_size", [9, 10, 12, 14])
@pytest.mark.parametrize("width", [381, 600])
def test_firewall_warning_fits(qtbot, font_size, width):
    """The warning must fit even when a larger font wraps onto more lines."""
    dialog = QtWidgets.QDialog()
    font = QtGui.QFont(dialog.font())
    font.setPointSize(font_size)
    dialog.setFont(font)
    ui = Ui_NewFwRuleDlg()
    ui.setupUi(dialog)
    qtbot.addWidget(dialog)
    dialog.resize(width, dialog.height())
    dialog.show()
    qtbot.waitUntil(dialog.isVisible)
    QtWidgets.QApplication.processEvents()

    warning = ui.label_3
    assert warning.height() >= warning.heightForWidth(warning.width())
    assert warning.geometry().bottom() < ui.buttonBox.geometry().top()
