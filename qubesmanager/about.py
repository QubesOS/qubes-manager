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
from PyQt5.QtGui import QIcon  # pylint: disable=import-error
from qubesmanager.releasenotes import ReleaseNotesDialog
from qubesmanager.informationnotes import InformationNotesDialog

from . import ui_about  # pylint: disable=no-name-in-module


# pylint: disable=too-few-public-methods
class AboutDialog(ui_about.Ui_AboutDialog, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self)

        self.icon.setPixmap(QIcon().fromTheme("qubes-manager").pixmap(96))
        with open('/etc/qubes-release', 'r', encoding='ascii') as release_file:
            self.release.setText(release_file.read())

        self.ok.clicked.connect(self.accept)
        self.releaseNotes.clicked.connect(self.on_release_notes_clicked)
        self.informationNotes.clicked.connect(self.on_information_notes_clicked)

    def on_release_notes_clicked(self):
        release_notes_dialog = ReleaseNotesDialog(self)
        release_notes_dialog.exec_()

    def on_information_notes_clicked(self):
        information_notes_dialog = InformationNotesDialog(self)
        information_notes_dialog.exec_()
