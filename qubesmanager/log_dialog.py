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

import sys
import os
import fcntl
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qubes.qubes import QubesException

import qubesmanager.resources_rc

from ui_logdlg import *

# Display only this size of log
LOG_DISPLAY_SIZE = 1024*1024

class LogDialog(Ui_LogDialog, QDialog):

    def __init__(self, app, log_path, parent=None):
        super(LogDialog, self).__init__(parent)

        self.app = app
        self.log_path = log_path

        self.setupUi(self)
        self.setWindowTitle(log_path)
 
        self.connect(self.copy_to_qubes_clipboard, SIGNAL("clicked()"), self.copy_to_qubes_clipboard_triggered)
       
        self.__init_log_text__()

    def __init_log_text__(self):
        self.displayed_text = ""
        log = open(self.log_path)
        log.seek(0, os.SEEK_END)
        if log.tell() > LOG_DISPLAY_SIZE:
            self.displayed_text = "(Showing only last %d bytes of file)\n" % LOG_DISPLAY_SIZE
            log.seek(-LOG_DISPLAY_SIZE, os.SEEK_END)
        else:
            log.seek(0, os.SEEK_SET)
        self.displayed_text += log.read()
        log.close()
        self.log_text.setPlainText(self.displayed_text)


    def copy_to_qubes_clipboard_triggered(self):
        copy_text_to_qubes_clipboard(self.displayed_text)
        
########################COPY TEXT TO QUBES CLIPBOARD

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
    
