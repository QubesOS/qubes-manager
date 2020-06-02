#!/usr/bin/python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2020  Marta Marczykowska-Górecka
# <marmarta@invisiblethingslab.com>
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

import os
import sys
import subprocess

from PyQt5 import QtCore, QtWidgets, QtGui  # pylint: disable=import-error

import qubesadmin
import qubesadmin.tools
import qubesadmin.exc

from . import common_threads
from . import utils

from .ui_clonevmdlg import Ui_CloneVMDlg  # pylint: disable=import-error


class CloneVMDlg(QtWidgets.QDialog, Ui_CloneVMDlg):
    def __init__(self, qtapp, app, parent=None, src_vm=None):
        super(CloneVMDlg, self).__init__(parent)
        self.setupUi(self)

        self.qtapp = qtapp
        self.app = app

        self.thread = None
        self.progress = None

        self.vm_list, self.vm_idx = utils.prepare_vm_choice(
            self.src_vm,
            self.app, None,
            None,
            (lambda vm: vm.klass != 'AdminVM'),
            allow_internal=False
        )

        if src_vm and self.src_vm.findText(src_vm.name) > -1:
            self.src_vm.setCurrentIndex(self.src_vm.findText(src_vm.name))

        self.label_list, self.label_idx = utils.prepare_label_choice(
                self.label,
                self.app, None,
                None,
                allow_default=False
        )

        self.update_label()

        self.pool_list, self.pool_idx = utils.prepare_choice(
            widget=self.storage_pool,
            holder=None,
            propname=None,
            choice=self.app.pools.values(),
            default=self.app.default_pool,
            allow_default=True,
            allow_none=False
        )

        self.set_clone_name()

        self.name.setValidator(QtGui.QRegExpValidator(
            QtCore.QRegExp("[a-zA-Z0-9_-]*", QtCore.Qt.CaseInsensitive), None))
        self.name.selectAll()
        self.name.setFocus()

        if src_vm:
            self.src_vm.setEnabled(False)
        else:
            self.src_vm.currentIndexChanged.connect(self.set_clone_name)
            self.src_vm.currentIndexChanged.connect(self.update_label)

    def reject(self):
        self.done(0)

    def accept(self):
        name = self.name.text()

        if name in self.app.domains:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr('Incorrect qube name!'),
                self.tr('A qube with the name <b>{}</b> already exists in the '
                        'system!').format(self.name.text()))
            return

        label = self.label_list[self.label.currentIndex()]

        if self.pool_list[self.storage_pool.currentIndex()] is not \
                qubesadmin.DEFAULT:
            pool = self.pool_list[self.storage_pool.currentIndex()]
        else:
            pool = None

        src_vm = self.vm_list[self.src_vm.currentIndex()]

        self.thread = common_threads.CloneVMThread(
            src_vm, name, pool=pool, label=label)
        self.thread.finished.connect(self.clone_finished)
        self.thread.start()

        self.progress = QtWidgets.QProgressDialog(
            self.tr("Cloning qube <b>{0}</b>...").format(name), "", 0, 0)
        self.progress.setCancelButton(None)
        self.progress.setModal(True)
        self.progress.show()

    def set_clone_name(self):
        vm_name = self.src_vm.currentText()
        name_number = 1
        name_format = vm_name + '-clone-%d'
        while name_format % name_number in self.app.domains.keys():
            name_number += 1
        self.name.setText(name_format % name_number)

    def update_label(self):
        vm_label = self.vm_list[self.src_vm.currentIndex()].label

        label_idx = self.label.findText(str(vm_label))

        if label_idx > -1:
            self.label.setCurrentIndex(label_idx)


    def clone_finished(self):
        self.progress.hide()

        if not self.thread.msg_is_success:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Error cloning the qube!"),
                self.tr("ERROR: {0}").format(self.thread.msg))

        self.done(0)

        if self.thread.msg_is_success:
            if self.launch_settings.isChecked():
                subprocess.check_call(['qubes-vm-settings',
                                       str(self.name.text())])


parser = qubesadmin.tools.QubesArgumentParser(vmname_nargs='?')


def main(args=None):
    args = parser.parse_args(args)
    if args.domains:
        src_vm = args.domains.pop()
    else:
        src_vm = None

    qtapp = QtWidgets.QApplication(sys.argv)

    translator = QtCore.QTranslator(qtapp)
    locale = QtCore.QLocale.system().name()
    i18n_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'i18n')
    translator.load("qubesmanager_{!s}.qm".format(locale), i18n_dir)
    qtapp.installTranslator(translator)
    QtCore.QCoreApplication.installTranslator(translator)

    qtapp.setOrganizationName('Invisible Things Lab')
    qtapp.setOrganizationDomain('https://www.qubes-os.org/')
    qtapp.setApplicationName(QtCore.QCoreApplication.translate(
        "appname", 'Clone qube'))

    dialog = CloneVMDlg(qtapp, args.app, src_vm=src_vm)
    dialog.exec_()
