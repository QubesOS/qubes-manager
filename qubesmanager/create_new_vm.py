#!/usr/bin/python2.6
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

import qubesmanager.resources_rc

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
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

        self.qvm_collection.lock_db_for_reading()
        self.qvm_collection.load()
        self.qvm_collection.unlock_db()

        self.label_list = QubesVmLabels.values()
        self.label_list.sort(key=lambda l: l.index)
        for (i, label) in enumerate(self.label_list):
            self.vmlabel.insertItem(i, label.name)
            self.vmlabel.setItemIcon (i, QIcon(label.icon_path))

        self.template_vm_list = [vm for vm in self.qvm_collection.values() if not vm.internal and vm.is_template()]

        default_index = 0
        for (i, vm) in enumerate(self.template_vm_list):
            if vm is self.qvm_collection.get_default_template():
                default_index = i
                self.template_name.insertItem(i, vm.name + " (default)")
            else:
                self.template_name.insertItem(i, vm.name)
        self.template_name.setCurrentIndex(default_index)

        self.vmname.setValidator(QRegExpValidator(QRegExp("[a-zA-Z0-9-]*", Qt.CaseInsensitive), None))
        self.vmname.selectAll()
        self.vmname.setFocus()

    def on_appvm_radio_toggled(self, checked):
        if checked:
            self.template_name.setEnabled(True)
            self.allow_networking.setEnabled(True)
    def on_netvm_radio_toggled(self, checked):
        if checked:
            self.template_name.setEnabled(True)
            self.allow_networking.setEnabled(False)
    def on_proxyvm_radio_toggled(self, checked):
        if checked:
            self.template_name.setEnabled(True)
            self.allow_networking.setEnabled(True)
    def on_hvm_radio_toggled(self, checked):
        if checked:
            self.template_name.setEnabled(False)
            self.allow_networking.setEnabled(True)


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
            template_vm = self.template_vm_list[self.template_name.currentIndex()]

        allow_networking = None
        if self.allow_networking.isEnabled():
            allow_networking = self.allow_networking.isChecked()

        if self.appvm_radio.isChecked():
            createvm_method = self.qvm_collection.add_new_appvm
            vmtype = "AppVM"
        elif self.netvm_radio.isChecked():
            createvm_method = self.qvm_collection.add_new_netvm
            vmtype = "NetVM"
        elif self.proxyvm_radio.isChecked():
            createvm_method = self.qvm_collection.add_new_proxyvm
            vmtype = "ProxyVM"
        else: #hvm_radio.isChecked()
            createvm_method = self.qvm_collection.add_new_hvm
            vmtype = "HVM"


        thread_monitor = ThreadMonitor()
        thread = threading.Thread (target=self.do_create_vm, args=(createvm_method, vmname, label, template_vm, allow_networking, thread_monitor))
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
            self.trayIcon.showMessage ("VM '{0}' has been created.".format(vmname), msecs=3000)
        else:
            QMessageBox.warning (None, "Error creating AppVM!", "ERROR: {0}".format(thread_monitor.error_msg))

        self.done(0)



    def do_create_vm (self, createvm_method, vmname, label, template_vm, allow_networking, thread_monitor):
        vm = None
        try:
            self.qvm_collection.lock_db_for_writing()
            self.qvm_collection.load()

            if template_vm is not None:
                vm = createvm_method(vmname, template_vm, label = label)
                vm.create_on_disk(verbose=False, source_template = template_vm)
            else:
                vm = createvm_method(vmname, label = label)
                vm.create_on_disk(verbose=False)

            if allow_networking is not None:
                firewall = vm.get_firewall_conf()
                firewall["allow"] = allow_networking
                firewall["allowDns"] = allow_networking
                vm.write_firewall_conf(firewall)
            self.qvm_collection.save()

        except Exception as ex:
            thread_monitor.set_error_msg (str(ex))
            if vm:
                vm.remove_from_disk()
        finally:
            self.qvm_collection.unlock_db()

        thread_monitor.set_finished()


