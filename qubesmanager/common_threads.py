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


from PyQt4 import QtCore  # pylint: disable=import-error
from qubesadmin import exc


# pylint: disable=too-few-public-methods
class RemoveVMThread(QtCore.QThread):
    def __init__(self, vm):
        QtCore.QThread.__init__(self)
        self.vm = vm
        self.msg = None

    def run(self):
        try:
            del self.vm.app.domains[self.vm.name]
        except (exc.QubesException, KeyError) as ex:
            self.msg = ("Error removing qube!", str(ex))


# pylint: disable=too-few-public-methods
class CloneVMThread(QtCore.QThread):
    def __init__(self, src_vm, dst_name):
        QtCore.QThread.__init__(self)
        self.src_vm = src_vm
        self.dst_name = dst_name
        self.msg = None

    def run(self):
        try:
            self.src_vm.app.clone_vm(self.src_vm, self.dst_name)
            self.msg = ("Sucess", "The qube was cloned sucessfully.")
        except exc.QubesException as ex:
            self.msg = ("Error while cloning qube!", str(ex))
