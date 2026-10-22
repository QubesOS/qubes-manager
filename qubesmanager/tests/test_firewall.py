# The Qubes OS Project, https://www.qubes-os.org/
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

import string
from unittest import mock

import pytest
from PyQt6 import QtGui, QtWidgets

from qubesmanager import firewall


@pytest.fixture
def rule_dialog(qtbot):
    dialog = firewall.NewFwRuleDlg()
    qtbot.addWidget(dialog)
    model = firewall.QubesFirewallRulesModel()
    model.clear_children()
    model.run_rule_dialog(dialog)
    dialog.addressComboBox.setCurrentText('*')
    return dialog, model


def test_comment_character_whitelist(rule_dialog):
    dialog, _ = rule_dialog
    allowed = string.ascii_letters + string.digits + ':;,./-_[] '
    validator = dialog.commentLineEdit.validator()
    # Cover every ASCII character, plus non-ASCII letters, digits and spaces.
    for character in ''.join(map(chr, range(128))) + 'ä٤\u00a0':
        state, _, _ = validator.validate(character, 1)
        assert (state == QtGui.QValidator.State.Acceptable) == (character in allowed)


@pytest.mark.parametrize('comment', ['', '   ', 'Web 01:;,./-_[]'])
def test_valid_comments(rule_dialog, comment, qtbot):
    dialog, model = rule_dialog
    dialog.commentLineEdit.setText(comment)
    button = dialog.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert button.isEnabled()
    with qtbot.waitSignal(dialog.accepted):
        button.click()
    assert len(model) == 1
    expected = 'action=accept'
    if comment.strip():
        expected += ' comment=' + comment.strip()
    assert model.children[0].rule == expected


@pytest.mark.parametrize('comment', ['Access?', 'Access!', 'ä', '٤', 'a\tb'])
def test_invalid_comment_can_be_corrected(rule_dialog, comment, qtbot):
    dialog, model = rule_dialog
    dialog.commentLineEdit.setText(comment)
    # Changing the address must not bypass comment validation.
    dialog.addressComboBox.setCurrentText('example.com')
    button = dialog.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert not button.isEnabled()
    assert dialog.commentLineEdit.styleSheet()
    with mock.patch('PyQt6.QtWidgets.QMessageBox.warning') as warning:
        dialog.accept()
    warning.assert_called_once()
    assert len(model) == 0
    assert dialog.isVisible()
    assert dialog.commentLineEdit.text() == comment

    dialog.commentLineEdit.setText('Corrected comment')
    assert button.isEnabled()
    assert not dialog.commentLineEdit.styleSheet()
    with qtbot.waitSignal(dialog.accepted):
        button.click()
    assert len(model) == 1
    assert str(model.children[0].comment) == 'Corrected comment'


def test_typing_disallowed_characters(rule_dialog, qtbot):
    dialog, _ = rule_dialog
    qtbot.keyClicks(dialog.commentLineEdit, 'Allow?')
    assert dialog.commentLineEdit.text() == 'Allow'


def test_comment_does_not_enable_ok_before_address(qtbot):
    dialog = firewall.NewFwRuleDlg()
    qtbot.addWidget(dialog)
    button = dialog.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    assert not button.isEnabled()
    dialog.commentLineEdit.setText('Valid comment')
    assert not button.isEnabled()

