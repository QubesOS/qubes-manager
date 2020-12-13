#!/usr/bin/python3
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

import os
import sys
import subprocess

from PyQt5 import QtCore, QtWidgets, QtGui  # pylint: disable=import-error

import qubesadmin
import qubesadmin.tools
import qubesadmin.exc

from . import utils

from .ui_newappvmdlg import Ui_NewVMDlg  # pylint: disable=import-error


# pylint: disable=too-few-public-methods
class CreateVMThread(QtCore.QThread):
    def __init__(self, app, vmclass, name, label, template, properties,
                 pool):
        QtCore.QThread.__init__(self)
        self.app = app
        self.vmclass = vmclass
        self.name = name
        self.label = label
        self.template = template
        self.properties = properties
        self.pool = pool
        self.msg = None

    def run(self):
        try:
            if self.vmclass == 'TemplateVM' and self.template is not None:
                args = {}
                if self.pool:
                    args['pool'] = self.pool

                vm = self.app.clone_vm(self.template, self.name,
                                       self.vmclass, **args)

                vm.label = self.label
            elif self.vmclass == 'StandaloneVM' and self.template is not None:
                args = {
                    'ignore_volumes': ['private']
                }
                if self.pool:
                    args['pool'] = self.pool

                vm = self.app.clone_vm(self.template, self.name,
                                       self.vmclass, **args)

                vm.label = self.label
            else:
                args = {
                    "name": self.name,
                    "label": self.label,
                    "template": self.template
                }
                if self.pool:
                    args['pool'] = self.pool

                vm = self.app.add_new_vm(self.vmclass, **args)

            for k, v in self.properties.items():
                setattr(vm, k, v)

        except qubesadmin.exc.QubesException as qex:
            self.msg = str(qex)
        except Exception as ex:  # pylint: disable=broad-except
            self.msg = repr(ex)


class NewVmDlg(QtWidgets.QDialog, Ui_NewVMDlg):
    def __init__(self, qtapp, app, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.qtapp = qtapp
        self.app = app

        self.thread = None
        self.progress = None

        utils.initialize_widget_with_labels(
            widget=self.label,
            qubes_app=self.app)

        utils.initialize_widget_with_vms(
            widget=self.template_vm,
            qubes_app=self.app,
            filter_function=(lambda vm: not utils.is_internal(vm) and
                             vm.klass == 'TemplateVM'),
                             allow_none=True)

        default_template = self.app.default_template
        for i in range(self.template_vm.count()):
            if self.template_vm.itemData(i) == default_template:
                self.template_vm.setCurrentIndex(i)
                self.template_vm.setItemText(
                    i, str(default_template) + " (default)")

        self.template_type = "template"

        utils.initialize_widget_with_default(
            widget=self.netvm,
            choices=[(vm.name, vm) for vm in self.app.domains
                     if not utils.is_internal(vm) and
                     getattr(vm, 'provides_network', False)],
            add_none=True,
            add_qubes_default=True,
            default_value=getattr(self.app, 'default_netvm', None))

        try:
            utils.initialize_widget_with_default(
                widget=self.storage_pool,
                choices=[(str(pool), pool) for pool in self.app.pools.values()],
                add_qubes_default=True,
                mark_existing_as_default=True,
                default_value=self.app.default_pool)
        except qubesadmin.exc.QubesDaemonAccessError:
            self.storage_pool.clear()
            self.storage_pool.addItem("(default)", qubesadmin.DEFAULT)

        self.name.setValidator(QtGui.QRegExpValidator(
            QtCore.QRegExp("[a-zA-Z0-9_-]*", QtCore.Qt.CaseInsensitive), None))
        self.name.selectAll()
        self.name.setFocus()

        if self.template_vm.count() < 1:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr('No template available!'),
                self.tr('Cannot create a qube when no template exists.'))

        type_list = [
            (self.tr("AppVM (persistent home, volatile root)"), 'AppVM'),
            (self.tr("TemplateVM (template home, persistent root)"),
                'TemplateVM'),
            (self.tr("StandaloneVM (fully persistent)"), 'StandaloneVM'),
            (self.tr("DisposableVM (fully volatile)"), 'DispVM')]

        utils.initialize_widget(widget=self.vm_type,
                                choices=type_list,
                                selected_value='AppVM',
                                add_current_label=False)

        self.vm_type.currentIndexChanged.connect(self.type_change)

        self.launch_settings.stateChanged.connect(self.settings_change)
        self.install_system.stateChanged.connect(self.install_change)

    def reject(self):
        self.done(0)

    def accept(self):
        vmclass = self.vm_type.currentData()

        name = str(self.name.text())

        if name in self.app.domains:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr('Incorrect qube name!'),
                self.tr('A qube with the name <b>{}</b> already exists in the '
                        'system!').format(name))
            return

        label = self.label.currentData()

        template = self.template_vm.currentData()

        if vmclass in ['AppVM', 'DispVM'] and template is None:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr('Unspecified template'),
                self.tr('{}s must be based on a template!'.format(vmclass)))
            return

        properties = {'provides_network': self.provides_network.isChecked()}
        if self.netvm.currentIndex() != 0:
            properties['netvm'] = self.netvm.currentData()

        # Standalone - not based on a template
        if vmclass == 'StandaloneVM' and template is None:
            properties['virt_mode'] = 'hvm'
            properties['kernel'] = None

        if self.storage_pool.currentData() is not qubesadmin.DEFAULT:
            pool = self.storage_pool.currentData()
        else:
            pool = None

        if self.init_ram.value() > 0:
            properties['memory'] = self.init_ram.value()

        self.thread = CreateVMThread(
            self.app, vmclass, name, label, template, properties, pool)
        self.thread.finished.connect(self.create_finished)
        self.thread.start()

        self.progress = QtWidgets.QProgressDialog(
            self.tr("Creating new qube <b>{0}</b>...").format(name), "", 0, 0)
        self.progress.setCancelButton(None)
        self.progress.setModal(True)
        self.progress.show()

    def create_finished(self):
        self.progress.hide()

        if self.thread.msg:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Error creating the qube!"),
                self.tr("ERROR: {0}").format(self.thread.msg))

        self.done(0)

        if not self.thread.msg:
            if self.launch_settings.isChecked():
                subprocess.check_call(['qubes-vm-settings',
                                       str(self.name.text())])
            if self.install_system.isChecked():
                subprocess.check_call(
                    ['qubes-vm-boot-from-device', str(self.name.text())])

    def type_change(self):
        template = self.template_vm.currentData()
        klass = self.vm_type.currentData()

        if klass in ['TemplateVM', 'StandaloneVM'] and template is None:
            self.install_system.setEnabled(True)
            self.install_system.setChecked(True)
        else:
            self.install_system.setEnabled(False)
            self.install_system.setChecked(False)

        if klass == 'DispVM':
            self.template_vm.clear()

            for vm in self.app.domains:
                if utils.is_internal(vm):
                    continue
                if vm.klass != 'AppVM':
                    continue
                if getattr(vm, 'template_for_dispvms', True):
                    self.template_vm.addItem(vm.name, userData=vm)

            self.template_vm.insertItem(self.template_vm.count(),
                                        utils.translate("(none)"), None)

            self.template_vm.setCurrentIndex(0)
            self.template_type = "dispvm"
        elif self.template_type == "dispvm":
            self.template_vm.clear()

            for vm in self.app.domains:
                if utils.is_internal(vm):
                    continue
                if vm.klass == 'TemplateVM':
                    self.template_vm.addItem(vm.name, userData=vm)

            self.template_vm.insertItem(self.template_vm.count(),
                                        utils.translate("(none)"), None)

            self.template_vm.setCurrentIndex(0)
            self.template_type = "template"

    def install_change(self):
        if self.install_system.isChecked():
            self.launch_settings.setChecked(False)

    def settings_change(self):
        if self.launch_settings.isChecked() and self.install_system.isEnabled():
            self.install_system.setChecked(False)


parser = qubesadmin.tools.QubesArgumentParser()


def main(args=None):
    args = parser.parse_args(args)

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
        "appname", 'Create qube'))

    dialog = NewVmDlg(qtapp, args.app)
    dialog.exec_()
