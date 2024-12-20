# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2015  Marek Marczykowski-Górecki
#                              <marmarek@invisiblethingslab.com>
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
from PyQt6.QtWidgets import QDialog  # pylint: disable=import-error
from PyQt6.QtGui import QIcon  # pylint: disable=import-error
from qubesmanager.informationnotes import InformationNotesDialog

from . import ui_about  # pylint: disable=no-name-in-module

# this is needed for icons to actually work
# pylint: disable=unused-import, no-name-in-module
from . import resources


# pylint: disable=too-few-public-methods
class AboutDialog(ui_about.Ui_AboutDialog, QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self)

        self.icon.setPixmap(QIcon().fromTheme("qubes-manager").pixmap(96))
        try:
            with open('/etc/qubes-release', 'r', encoding='ascii') \
                    as release_file:
                self.release.setText(release_file.read())
        except FileNotFoundError:
            # running in a VM?
            try:
                with open('/usr/share/qubes/marker-vm', 'r', encoding='ascii') \
                        as marker_file:
                    release = [l.strip() for l in marker_file.readlines()
                               if l.strip() and not l.startswith('#')]
                    if release and release[0] and release[0][0].isdigit():
                        self.release.setText(release[0])
                    else:
                        self.release.setText('unknown')
            except FileNotFoundError:
                self.release.setText('unknown')

        self.ok.clicked.connect(self.accept)
        self.informationNotes.clicked.connect(self.on_information_notes_clicked)

    def on_information_notes_clicked(self):
        information_notes_dialog = InformationNotesDialog(self)
        information_notes_dialog.exec()
