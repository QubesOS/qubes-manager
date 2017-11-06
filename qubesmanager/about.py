#!/usr/bin/python2
# coding=utf-8
# pylint: skip-file
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#
from PyQt4.QtCore import SIGNAL, SLOT
from PyQt4.QtGui import QDialog, QIcon
from qubesmanager.releasenotes import ReleaseNotesDialog
from qubesmanager.informationnotes import InformationNotesDialog

from .ui_about import *



class AboutDialog(Ui_AboutDialog, QDialog):
    def __init__(self):
        super(AboutDialog, self).__init__()

        self.setupUi(self)

        self.icon.setPixmap(QIcon().fromTheme("qubes-manager").pixmap(96))
        with open('/etc/qubes-release', 'r') as release_file:
            self.release.setText(release_file.read())

        self.connect(self.ok, SIGNAL("clicked()"), SLOT("accept()"))
        self.connect(self.releaseNotes, SIGNAL("clicked()"),
                     self.on_release_notes_clicked)
        self.connect(self.informationNotes, SIGNAL("clicked()"),
                     self.on_information_notes_clicked)

    def on_release_notes_clicked(self):
        release_notes_dialog = ReleaseNotesDialog()
        release_notes_dialog.exec_()
        self.accept()

    def on_information_notes_clicked(self):
        information_notes_dialog = InformationNotesDialog()
        information_notes_dialog.exec_()
        self.accept()
