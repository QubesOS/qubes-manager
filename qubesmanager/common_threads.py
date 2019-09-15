#!/usr/bin/python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2018  Donoban <donoban@riseup.net>
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


from PyQt5 import QtCore, QtWidgets  # pylint: disable=import-error
from contextlib import contextmanager

from qubesadmin import exc


@contextmanager
def busy_cursor():
    try:
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.BusyCursor)
        yield
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()


# pylint: disable=too-few-public-methods
class QubesThread(QtCore.QThread):
    def __init__(self, vm):
        QtCore.QThread.__init__(self)
        self.vm = vm
        self.msg = None
        self.msg_is_success = False


# pylint: disable=too-few-public-methods
class RemoveVMThread(QubesThread):
    def run(self):
        try:
            del self.vm.app.domains[self.vm.name]
        except (exc.QubesException, KeyError) as ex:
            self.msg = ("Error removing qube!", str(ex))


# pylint: disable=too-few-public-methods
class CloneVMThread(QubesThread):
    def __init__(self, vm, dst_name):
        super(CloneVMThread, self).__init__(vm)
        self.dst_name = dst_name

    def run(self):
        try:
            self.vm.app.clone_vm(self.vm, self.dst_name)
            self.msg = ("Sucess", "The qube was cloned sucessfully.")
            self.msg_is_success = True
        except exc.QubesException as ex:
            self.msg = ("Error while cloning qube!", str(ex))
