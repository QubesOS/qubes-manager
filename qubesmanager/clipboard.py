#!/usr/bin/python2
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski <marmarek@mimuw.edu.pl>
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

import os
import fcntl

from qubes.qubes import QubesException
from PyQt4.QtGui import QApplication

def do_dom0_copy():
    copy_text_to_qubes_clipboard(QApplication.clipboard().text())

def copy_text_to_qubes_clipboard(text):
    #inter-appviewer lock

    try:
        fd = os.open("/var/run/qubes/appviewer.lock", os.O_RDWR|os.O_CREAT, 0666)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except IOError:
        QMessageBox.warning (None, "Warning!", "Error while accessing Qubes clipboard!")
        return

    qubes_clipboard = open("/var/run/qubes/qubes-clipboard.bin", 'w')
    qubes_clipboard.write(text)
    qubes_clipboard.close()

    qubes_clip_source = open("/var/run/qubes/qubes-clipboard.bin.source", 'w')
    qubes_clip_source.write("dom0")
    qubes_clip_source.close()

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except IOError:
        QMessageBox.warning (None, "Warning!", "Error while writing to Qubes clipboard!")
        return
