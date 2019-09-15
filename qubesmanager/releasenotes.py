#!/usr/bin/python3
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

from . import ui_releasenotes  # pylint: disable=no-name-in-module


class ReleaseNotesDialog(ui_releasenotes.Ui_ReleaseNotesDialog, QDialog):
    # pylint: disable=too-few-public-methods
    def __init__(self):
        super(ReleaseNotesDialog, self).__init__()

        self.setupUi(self)

        with open('/usr/share/doc/qubes-release-notes/README.Qubes-Release'
                  '-Notes', 'r') as release_notes:
            self.releaseNotes.setText(release_notes.read())
