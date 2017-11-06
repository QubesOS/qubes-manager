#!/usr/bin/python2
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2011  Marek Marczykowski <marmarek@mimuw.edu.pl>
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


import PyQt4.QtCore

import threading

class ThreadMonitor(PyQt4.QtCore.QObject):
    def __init__(self):
        self.success = True
        self.error_msg = None
        self.event_finished = threading.Event()

    def set_error_msg(self, error_msg):
        self.success = False
        self.error_msg = error_msg
        self.set_finished()

    def is_finished(self):
        return self.event_finished.is_set()

    def set_finished(self):
        self.event_finished.set()

