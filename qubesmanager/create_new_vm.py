#!/usr/bin/python2
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski <marmarek@mimuw.edu.pl>
# Copyright (C) 2017  Wojtek Porczyk <woju@invisiblethingslab.com>
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
import sys
import threading
import time

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import qubesadmin
import qubesadmin.tools

import qubesmanager.resources_rc

from . import utils

from .ui_newappvmdlg import Ui_NewVMDlg
from .thread_monitor import ThreadMonitor


class NewVmDlg(QDialog, Ui_NewVMDlg):
    def __init__(self, qtapp, app, parent = None):
        super(NewVmDlg, self).__init__(parent)
        self.setupUi(self)

        self.qtapp = qtapp
        self.app = app

        # Theoretically we should be locking for writing here and unlock
        # only after the VM creation finished. But the code would be more messy...
        # Instead we lock for writing in the actual worker thread

        self.label_list, self.label_idx = utils.prepare_label_choice(
            self.label,
            self.app, None,
            None,
            allow_default=False)

        self.template_list, self.template_idx = utils.prepare_vm_choice(
            self.template_vm,
            self.app, None,
            self.app.default_template,
            (lambda vm: isinstance(vm, qubesadmin.vm.TemplateVM)),
            allow_internal=False, allow_default=True, allow_none=False)

        self.netvm_list, self.netvm_idx = utils.prepare_vm_choice(
            self.netvm,
            self.app, None,
            self.app.default_netvm,
            (lambda vm: vm.provides_network),
            allow_internal=False, allow_default=True, allow_none=True)

        self.name.setValidator(QRegExpValidator(
            QRegExp("[a-zA-Z0-9-]*", Qt.CaseInsensitive), None))
        self.name.selectAll()
        self.name.setFocus()

        if len(self.template_list) == 0:
            QMessageBox.warning(None,
                self.tr('No template available!'),
                self.tr('Cannot create a qube when no template exists.'))

    def reject(self):
        self.done(0)

    def accept(self):
        vmclass = ('StandaloneVM' if self.standalone.isChecked() else 'AppVM')

        name = str(self.name.text())
        try:
            self.app.domains[name]
        except LookupError:
            pass
        else:
            QMessageBox.warning(None,
                self.tr('Incorrect qube name!'),
                self.tr('A qube with the name <b>{}</b> already exists in the '
                        'system!').format(name))
            return

        label = self.label_list[self.label.currentIndex()]
        template = self.template_list[self.template_vm.currentIndex()]

        properties = {}
        properties['provides_network'] = self.provides_network.isChecked()
        properties['virt_mode'] = 'hvm' if self.hvm.isChecked() else 'pv'
        properties['netvm'] = self.netvm_list[self.netvm.currentIndex()]

        thread_monitor = ThreadMonitor()
        thread = threading.Thread(target=self.do_create_vm,
            args=(self.app, vmclass, name, label, template, properties,
                 thread_monitor))
        thread.daemon = True
        thread.start()

        progress = QProgressDialog(
            self.tr("Creating new qube <b>{}</b>...").format(name), "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not thread_monitor.is_finished():
            self.qtapp.processEvents()
            time.sleep (0.1)

        progress.hide()

        if not thread_monitor.success:
            QMessageBox.warning(None,
                self.tr("Error creating the qube!"),
                self.tr("ERROR: {}").format(thread_monitor.error_msg))

        self.done(0)

    @staticmethod
    def do_create_vm(app, vmclass, name, label, template, properties,
            thread_monitor):
        try:
            vm = app.add_new_vm(vmclass,
                name=name, label=label, template=template)
            for k, v in properties.items():
                setattr(vm, k, v)

        except Exception as ex:
            thread_monitor.set_error_msg(str(ex))

        thread_monitor.set_finished()

parser = qubesadmin.tools.QubesArgumentParser()

def main(args=None):
    args = parser.parse_args(args)

    qtapp = QApplication(sys.argv)
    qtapp.setOrganizationName('Invisible Things Lab')
    qtapp.setOrganizationDomain('https://www.qubes-os.org/')
    qtapp.setApplicationName('Create qube')

    dialog = NewVmDlg(qtapp, args.app)
    dialog.exec_()
