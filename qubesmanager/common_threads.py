# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2018  Donoban <donoban@riseup.net>
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


from PyQt6 import QtCore, QtWidgets  # pylint: disable=import-error
from contextlib import contextmanager

from qubesadmin import exc


@contextmanager
def busy_cursor():
    try:
        QtWidgets.QApplication.setOverrideCursor(
            QtCore.Qt.CursorShape.BusyCursor)
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
            self.msg = (self.tr("Error removing qube!"), str(ex))


# pylint: disable=too-few-public-methods
class CloneVMThread(QubesThread):
    def __init__(self, vm, dst_name, pool=None, label=None):
        super().__init__(vm)
        self.dst_name = dst_name
        self.pool = pool
        self.label = label

    def run(self):
        try:
            self.vm.app.clone_vm(self.vm, self.dst_name, pool=self.pool)
            if self.label:
                result_vm = self.vm.app.domains[self.dst_name]
                result_vm.label = self.label
            self.msg = (self.tr("Success"),
                        self.tr("The qube was cloned successfully."))
            self.msg_is_success = True
        except exc.QubesException as ex:
            self.msg = (self.tr("Error while cloning qube!"), str(ex))


class ChangeTemplatesThread(QtCore.QThread):
    def __init__(self, progress_dialog, items_to_change, qubes_app):
        super().__init__()
        self.dialog = progress_dialog
        self.items = items_to_change
        self.qubes_app = qubes_app
        self.errors = {}

    def run(self):
        i = 0
        for vm, row in self.items:
            i += 1
            try:
                setattr(self.qubes_app.domains[vm],
                        'template', row.new_item.currentText())
            except Exception as ex:  # pylint: disable=broad-except
                self.errors[vm] = str(ex)
            self.dialog.setValue(i)
