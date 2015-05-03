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
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesVmLabels
from qubes.qubes import QubesException
from qubes.qubes import QubesVm,QubesHVm

import qubesmanager.resources_rc

import time
import threading

from ui_newappvmdlg import *
from thread_monitor import *


class NewVmDlg (QDialog, Ui_NewVMDlg):
    def __init__(self, app, qvm_collection, trayIcon, parent = None):
        super (NewVmDlg, self).__init__(parent)
        self.setupUi(self)

        self.app = app
        self.trayIcon = trayIcon
        self.qvm_collection = qvm_collection

        # Theoretically we should be locking for writing here and unlock
        # only after the VM creation finished. But the code would be more messy...
        # Instead we lock for writing in the actual worker thread

        try:
            from qubes.qubes import QubesHVm
        except ImportError:
            pass
        else: 
            self.hvm_radio.setEnabled(True)
            self.hvmtpl_radio.setEnabled(True)

        self.qvm_collection.lock_db_for_reading()
        self.qvm_collection.load()
        self.qvm_collection.unlock_db()

        self.label_list = QubesVmLabels.values()
        self.label_list.sort(key=lambda l: l.index)
        for (i, label) in enumerate(self.label_list):
            self.vmlabel.insertItem(i, label.name)
            self.vmlabel.setItemIcon (i, QIcon(label.icon_path))

        self.fill_template_list()
        self.fill_netvm_list()

        self.vmname.setValidator(QRegExpValidator(QRegExp("[a-zA-Z0-9-]*", Qt.CaseInsensitive), None))
        self.vmname.selectAll()
        self.vmname.setFocus()

        self.hvmtemplatewarningbox.hide()

    def fill_template_list(self):
        def filter_template(vm):
            if vm.internal:
                return False
            if not vm.is_template():
                return False
            if self.hvm_radio.isChecked():
                return QubesHVm.is_template_compatible(vm)
            elif self.hvmtpl_radio.isChecked():
                return False
            else:
                return QubesVm.is_template_compatible(vm)
        self.template_vm_list = filter(filter_template, self.qvm_collection.values())

        self.template_name.clear()
        default_index = 0
        for (i, vm) in enumerate(self.template_vm_list):
            if vm is self.qvm_collection.get_default_template():
                default_index = i
                self.template_name.insertItem(i, vm.name + " (default)")
            else:
                self.template_name.insertItem(i, vm.name)
        self.template_name.setCurrentIndex(default_index)

    def fill_netvm_list(self):
        def filter_netvm(vm):
            if vm.internal:
                return False
            if vm.qid == 0:
                return False
            if vm.is_netvm():
                return True
            if vm.is_proxyvm():
                return True
            else:
                return False
        self.netvm_list = filter(filter_netvm, self.qvm_collection.values())

        self.netvm_name.clear()
        default_index = 0
        for (i, vm) in enumerate(self.netvm_list):
            if vm is self.qvm_collection.get_default_netvm():
                default_index = i
                self.netvm_name.insertItem(i, vm.name + " (default)")
            else:
                self.netvm_name.insertItem(i, vm.name)
        self.netvm_name.setCurrentIndex(default_index)

    def on_allow_networking_toggled(self, checked):
        if checked:
            self.fill_netvm_list()
            self.netvm_name.setEnabled(True)
        else:    
            self.netvm_name.clear()
            self.netvm_name.setEnabled(False)

    def on_appvm_radio_toggled(self, checked):
        if checked:
            self.template_name.setEnabled(True)
            self.allow_networking.setEnabled(True)
            self.netvm_name.setEnabled(self.allow_networking.isChecked())

    def on_netvm_radio_toggled(self, checked):
        if checked:
            self.template_name.setEnabled(True)
            self.allow_networking.setChecked(True)
            self.allow_networking.setEnabled(False)
            self.netvm_name.setEnabled(False)

    def on_proxyvm_radio_toggled(self, checked):
        if checked:
            self.template_name.setEnabled(True)
            self.allow_networking.setEnabled(True)
            self.netvm_name.setEnabled(self.allow_networking.isChecked())

    def on_hvm_radio_toggled(self, checked):
        if self.hvm_radio.isChecked() or self.hvmtpl_radio.isChecked():
            self.standalone.setChecked(True)
            self.allow_networking.setEnabled(True)
            self.netvm_name.setEnabled(self.allow_networking.isChecked())
            self.standalone.setEnabled(self.hvm_radio.isChecked())
        else:
            self.standalone.setChecked(False)
            self.standalone.setEnabled(True)
        self.fill_template_list()

    def on_hvmtpl_radio_toggled(self, checked):
        return self.on_hvm_radio_toggled(checked)

    def on_standalone_toggled(self, checked):
        if checked and (self.hvm_radio.isChecked() or
                        self.hvmtpl_radio.isChecked()):
            self.template_name.setEnabled(False)
        else:
            self.template_name.setEnabled(True)

        if not checked and self.hvm_radio.isChecked():
            self.hvmtemplatewarningbox.show()
        else:
            self.hvmtemplatewarningbox.hide()

    def reject(self):
        self.done(0)

    def accept(self):
        vmname = str(self.vmname.text())
        if self.qvm_collection.get_vm_by_name(vmname) is not None:
            QMessageBox.warning (None, "Incorrect AppVM Name!", "A VM with the name <b>{0}</b> already exists in the system!".format(vmname))
            return

        label = self.label_list[self.vmlabel.currentIndex()]
        
        template_vm = None
        if self.template_name.isEnabled():
            if len(self.template_vm_list) == 0:
                QMessageBox.warning (None, "No template available!", "Cannot create non-standalone VM when no compatible template exists. Create template VM first or choose to create standalone VM.")
                return
            template_vm = self.template_vm_list[self.template_name.currentIndex()]

        netvm = None
        if self.netvm_name.isEnabled():
            netvm = self.netvm_list[self.netvm_name.currentIndex()]

        standalone = self.standalone.isChecked()

        allow_networking = None
        if self.allow_networking.isEnabled():
            allow_networking = self.allow_networking.isChecked()

        if self.appvm_radio.isChecked():
            vmtype = "AppVM"
        elif self.netvm_radio.isChecked():
            vmtype = "NetVM"
        elif self.proxyvm_radio.isChecked():
            vmtype = "ProxyVM"
        elif self.hvm_radio.isChecked():
            vmtype = "HVM"
        elif self.hvmtpl_radio.isChecked():
            vmtype = "TemplateHVM"
        else:
            QErrorMessage.showMessage(None, "Error creating AppVM!", "Unknown "
                                                                   "VM type, this is error in Qubes Manager")
            self.done(0)


        vmclass = "Qubes" + vmtype.replace("VM", "Vm")
        thread_monitor = ThreadMonitor()
        thread = threading.Thread (target=self.do_create_vm, args=(vmclass, vmname, label, template_vm, netvm, standalone, allow_networking, thread_monitor))
        thread.daemon = True
        thread.start()

        progress = QProgressDialog ("Creating new {0} <b>{1}</b>...".format(vmtype, vmname), "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not thread_monitor.is_finished():
            self.app.processEvents()
            time.sleep (0.1)

        progress.hide()

        if thread_monitor.success:
            self.trayIcon.showMessage(
                "VM '{0}' has been created.".format(vmname), msecs=3000)
        else:
            QMessageBox.warning (None, "Error creating AppVM!", "ERROR: {0}".format(thread_monitor.error_msg))

        self.done(0)

    @staticmethod
    def do_create_vm(vmclass, vmname, label, template_vm, netvm,
                     standalone, allow_networking, thread_monitor):
        vm = None
        qc = QubesVmCollection()
        qc.lock_db_for_writing()
        qc.load()
        try:
            if not standalone:
                vm = qc.add_new_vm(vmclass, name=vmname, template=template_vm,
                                   label=label)
            else:
                vm = qc.add_new_vm(vmclass, name=vmname, template=None,
                                   label=label)
            vm.create_on_disk(verbose=False, source_template=template_vm)

            if not allow_networking:
                vm.uses_default_netvm = False
                vm.netvm = None
            else:
                vm.netvm = netvm
                if vm.netvm.qid == qc.get_default_netvm().qid:
                    vm.uses_default_netvm = True
                else:
                    vm.uses_default_netvm = False

            qc.save()
        except Exception as ex:
            thread_monitor.set_error_msg(str(ex))
            if vm:
                vm.remove_from_disk()
                qc.pop(vm.qid)
        finally:
            qc.unlock_db()

        thread_monitor.set_finished()


