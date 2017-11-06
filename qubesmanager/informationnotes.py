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
from PyQt4.QtCore import SIGNAL
from PyQt4.QtGui import QDialog, QIcon

from .ui_informationnotes import *
import subprocess


class InformationNotesDialog(Ui_InformationNotesDialog, QDialog):
    def __init__(self):
        super(InformationNotesDialog, self).__init__()

        self.setupUi(self)
        details = subprocess.check_output(['/usr/libexec/qubes-manager/qvm_about.sh'])
        self.informationNotes.setText(details)
