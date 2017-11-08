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
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
#
#

import sys
import threading
import time
import subprocess

from PyQt4 import QtCore, QtGui

import qubesadmin
import qubesadmin.tools
import qubesadmin.exc

from . import utils

from .ui_newappvmdlg import Ui_NewVMDlg
from .thread_monitor import ThreadMonitor


class NewVmDlg(QtGui.QDialog, Ui_NewVMDlg):
    def __init__(self, qtapp, app, parent=None):
        super(NewVmDlg, self).__init__(parent)
        self.setupUi(self)

        self.qtapp = qtapp
        self.app = app

        # Theoretically we should be locking for writing here and unlock
        # only after the VM creation finished. But the code would be
        # more messy...
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
            (lambda vm: vm.klass == 'TemplateVM'),
            allow_internal=False, allow_default=True, allow_none=False)

        self.netvm_list, self.netvm_idx = utils.prepare_vm_choice(
            self.netvm,
            self.app, None,
            self.app.default_netvm,
            (lambda vm: vm.provides_network),
            allow_internal=False, allow_default=True, allow_none=True)

        self.name.setValidator(QtGui.QRegExpValidator(
            QtCore.QRegExp("[a-zA-Z0-9-]*", QtCore.Qt.CaseInsensitive), None))
        self.name.selectAll()
        self.name.setFocus()

        if len(self.template_list) == 0:
            QtGui.QMessageBox.warning(None,
                self.tr('No template available!'),
                self.tr('Cannot create a qube when no template exists.'))

        # Order of types is important and used elsewhere; if it's changed
        # check for changes needed in self.type_change and TODO
        type_list = [self.tr("AppVM"),
                     self.tr("Standalone VM based on a template"),
                     self.tr("Standalone VM not based on a template")]
        self.vm_type.addItems(type_list)

        self.vm_type.currentIndexChanged.connect(self.type_change)

        self.launch_settings.stateChanged.connect(self.settings_change)
        self.install_system.stateChanged.connect(self.install_change)

    def reject(self):
        self.done(0)

    def accept(self):
        vmclass = ('AppVM' if self.vm_type.currentIndex() == 0
                   else 'StandaloneVM')

        name = str(self.name.text())
        try:
            self.app.domains[name]
        except LookupError:
            pass
        else:
            QtGui.QMessageBox.warning(None,
                self.tr('Incorrect qube name!'),
                self.tr('A qube with the name <b>{}</b> already exists in the '
                        'system!').format(name))
            return

        label = self.label_list[self.label.currentIndex()]

        if self.template_vm.currentIndex() == -1:
            template = None
        else:
            template = self.template_list[self.template_vm.currentIndex()]

        properties = {}
        properties['provides_network'] = self.provides_network.isChecked()
        properties['virt_mode'] = 'hvm'
        properties['netvm'] = self.netvm_list[self.netvm.currentIndex()]

        thread_monitor = ThreadMonitor()
        thread = threading.Thread(target=self.do_create_vm,
            args=(self.app, vmclass, name, label, template, properties,
                 thread_monitor))
        thread.daemon = True
        thread.start()

        progress = QtGui.QProgressDialog(
            self.tr("Creating new qube <b>{}</b>...").format(name), "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not thread_monitor.is_finished():
            self.qtapp.processEvents()
            time.sleep(0.1)

        progress.hide()

        if not thread_monitor.success:
            QtGui.QMessageBox.warning(None,
                self.tr("Error creating the qube!"),
                self.tr("ERROR: {}").format(thread_monitor.error_msg))

        self.done(0)

        if thread_monitor.success:
            if self.launch_settings.isChecked():
                subprocess.check_call(['qubes-vm-settings', name])
            if self.install_system.isChecked():
                subprocess.check_call(
                    ['qubes-vm-boot-from-device', name])

    @staticmethod
    def do_create_vm(app, vmclass, name, label, template, properties,
            thread_monitor):
        try:
            if vmclass == 'StandaloneVM' and template is not None:
                if template is qubesadmin.DEFAULT:
                    src_vm = app.default_template
                else:
                    src_vm = template
                vm = app.clone_vm(src_vm, name, vmclass)
                vm.label = label
                for k, v in properties.items():
                    setattr(vm, k, v)
            else:
                vm = app.add_new_vm(vmclass,
                    name=name, label=label, template=template)
                for k, v in properties.items():
                    setattr(vm, k, v)

        except qubesadmin.exc.QubesException as qex:
            thread_monitor.set_error_msg(str(qex))
        except Exception as ex:  # pylint: disable=broad-except
            thread_monitor.set_error_msg(repr(ex))

        thread_monitor.set_finished()

    def type_change(self):

        # AppVM
        if self.vm_type.currentIndex() == 0:
            self.template_vm.setEnabled(True)
            self.template_vm.setCurrentIndex(0)
            self.install_system.setEnabled(False)
            self.install_system.setChecked(False)

        # Standalone - based on a template
        if self.vm_type.currentIndex() == 1:
            self.template_vm.setEnabled(True)
            self.template_vm.setCurrentIndex(0)
            self.install_system.setEnabled(False)
            self.install_system.setChecked(False)

        # Standalone - not based on a template
        if self.vm_type.currentIndex() == 2:
            self.template_vm.setEnabled(False)
            self.template_vm.setCurrentIndex(-1)
            self.install_system.setEnabled(True)
            self.install_system.setChecked(True)

    def install_change(self):
        if self.install_system.isChecked():
            self.launch_settings.setChecked(False)

    def settings_change(self):
        if self.launch_settings.isChecked() and self.install_system.isEnabled():
            self.install_system.setChecked(False)

parser = qubesadmin.tools.QubesArgumentParser()

def main(args=None):
    args = parser.parse_args(args)

    qtapp = QtGui.QApplication(sys.argv)
    qtapp.setOrganizationName('Invisible Things Lab')
    qtapp.setOrganizationDomain('https://www.qubes-os.org/')
    qtapp.setApplicationName('Create qube')

    dialog = NewVmDlg(qtapp, args.app)
    dialog.exec_()
