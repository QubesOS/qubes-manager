#!/usr/bin/python3

# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only


# coding=utf-8
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2015  Marek Marczykowski-Górecki
#                              <marmarek@invisiblethingslab.com>
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
from PyQt5.QtWidgets import QDialog  # pylint: disable=import-error

from . import ui_informationnotes  # pylint: disable=no-name-in-module
import subprocess


class InformationNotesDialog(ui_informationnotes.Ui_InformationNotesDialog,
                             QDialog):
    # pylint: disable=too-few-public-methods
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self)
        details = subprocess.check_output(
            ['/usr/libexec/qubes-manager/qvm_about.sh'])
        self.informationNotes.setText(details.decode())
