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
from qubes.qubes import qubes_appmenu_create_cmd
from qubes.qubes import qubes_appmenu_remove_cmd
from qubes.qubes import QubesDaemonPidfile
from qubes.qubes import QubesHost
from qubes.qubes import qrexec_client_path

import qubesmanager.resources_rc

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time
import threading
from operator import itemgetter

from ui_settingsdlg import *
from multiselectwidget import *
from appmenu_select import *
from firewall import *


class VMSettingsWindow(Ui_SettingsDialog, QDialog):
    tabs_indices = {"basic": 0,
                    "advanced": 1,
                    "firewall": 2,
                    "devices": 3,
                    "applications": 4,
                    "services": 5,}

    def __init__(self, vm, app, qvm_collection, init_page="basic", parent=None):
        super(VMSettingsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection
        self.vm = vm
        if self.vm.template_vm:
            self.source_vm = self.vm.template_vm
        else:
            self.source_vm = self.vm
 
        self.setupUi(self)
        if init_page in self.tabs_indices:
            idx = self.tabs_indices[init_page]
            assert (idx in range(self.tabWidget.count()))
            self.tabWidget.setCurrentIndex(idx)

        self.connect(self.buttonBox, SIGNAL("accepted()"), self.save_and_apply)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.reject)

        self.tabWidget.currentChanged.connect(self.current_tab_changed)

        ###### basic tab
        self.__init_basic_tab__()

        ###### firewall tab

        model = QubesFirewallRulesModel()
        model.set_vm(vm)
        self.set_fw_model(model)

        
        self.newRuleButton.clicked.connect(self.new_rule_button_pressed)
        self.editRuleButton.clicked.connect(self.edit_rule_button_pressed)
        self.deleteRuleButton.clicked.connect(self.delete_rule_button_pressed)
        self.policyAllowRadioButton.toggled.connect(self.policy_radio_toggled)
        self.dnsCheckBox.toggled.connect(self.dns_checkbox_toggled)
        self.icmpCheckBox.toggled.connect(self.icmp_checkbox_toggled)

        ####### devices tab
        self.dev_list = MultiSelectWidget(self)
        self.devices_layout.addWidget(self.dev_list)
 
        ####### apps tab
        if not vm.is_netvm():
            self.app_list = MultiSelectWidget(self)
            self.apps_layout.addWidget(self.app_list)
            self.AppListManager = AppmenuSelectManager(self.vm, self.app_list)
        else:
            self.tabWidget.setTabEnabled(self.tabs_indices["applications"], False)

    def reject(self):
        self.done(0)

    #needed not to close the dialog before applying changes
    def accept(self):
        pass

    def save_and_apply(self):
        thread_monitor = ThreadMonitor()
        thread = threading.Thread (target=self.__save_changes__, args=(thread_monitor,))
        thread.daemon = True
        thread.start()
        
        progress = QProgressDialog ("Applying settings to <b>{0}</b>...".format(self.vm.name), "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not thread_monitor.is_finished():
            self.app.processEvents()
            time.sleep (0.1)

        progress.hide()
        
        if not thread_monitor.success:
            QMessageBox.warning (None, "Error while changing settings for {0}!", "ERROR: {1}".format(self.vm.name, thread_monitor.error_msg))

        self.done(0)

    def __save_changes__(self, thread_monitor):
        ret = self.__apply_basic_tab__()
        if len(ret) > 0 :
            thread_monitor.set_error_msg('\n'.join(ret))
            thread_monitor.set_finished()
            return
        self.fw_model.apply_rules()
        self.AppListManager.save_appmenu_select_changes()
        thread_monitor.set_finished()

    def current_tab_changed(self, idx):
        if idx == self.tabs_indices["firewall"]:
            if self.vm.netvm_vm is not None and not self.vm.netvm_vm.is_proxyvm():
                QMessageBox.warning (None, "VM configuration problem!", "The '{0}' AppVM is not network connected to a FirewallVM!<p>".format(self.vm.name) +\
                    "You may edit the '{0}' VM firewall rules, but these will not take any effect until you connect it to a working Firewall VM.".format(self.vm.name))



    ######### basic tab

    def __init_basic_tab__(self):
        self.vmname.setText(self.vm.name)
        
        #self.qvm_collection.lock_db_for_reading()
        #self.qvm_collection.load()
        #self.qvm_collection.unlock_db()
        
        self.label_list = QubesVmLabels.values()
        self.label_list.sort(key=lambda l: l.index)
        self.label_idx = 0
        for (i, label) in enumerate(self.label_list):
            if label == self.vm.label:
                self.label_idx = i
            self.vmlabel.insertItem(i, label.name)
            self.vmlabel.setItemIcon (i, QIcon(label.icon_path))
        self.vmlabel.setCurrentIndex(self.label_idx)

        if not self.vm.is_template() and self.vm.template_vm is not None:
            template_vm_list = [vm for vm in self.qvm_collection.values() if not vm.internal and vm.is_template()]
            self.template_idx = 0
            for (i, vm) in enumerate(template_vm_list):
                text = vm.name
                if vm is self.qvm_collection.get_default_template_vm():
                    text += " (default)"
                if vm.qid == self.vm.template_vm.qid:
                    self.template_idx = i
                    text += " (current)"
                self.template_name.insertItem(i, text)
            self.template_name.setCurrentIndex(self.template_idx)
        else:
            self.template_name.setEnabled(False)

        if not self.vm.is_netvm():
            netvm_list = [vm for vm in self.qvm_collection.values() if not vm.internal and vm.is_netvm()]
            self.netvm_idx = 0
            for (i, vm) in enumerate(netvm_list):
                text = vm.name
                if vm is self.qvm_collection.get_default_netvm_vm():
                    text += " (default)"
                if vm.qid == self.vm.netvm_vm.qid:
                    self.netvm_idx = i
                    text += " (current)"
                self.netVM.insertItem(i, text)
            self.netVM.setCurrentIndex(self.netvm_idx)
        else:
            self.netVM.setEnabled(False)

        #self.vmname.selectAll()
        #self.vmname.setFocus()

    def __apply_basic_tab__(self):
        msg = []

        if self.vm.is_running():
            msg.append("Can't change settings of a running VM.")
            msg.append("telemele")
            return msg

        # vmname changed
        vmname = str(self.vmname.text())
        if self.vm.name != vmname:
            if self.qvm_collection.get_vm_by_name(vmname) is not None:
                msg.append("A VM named <b>{0}</b> already exists in the system!".format(vmname))
            else:
                oldname = self.vm.name
                try:
                    self.qvm_collection.lock_db_for_writing()
                    self.vm.pre_rename(vmname)
                    self.vm.set_name(vmname)
                    self.vm.post_rename(oldname)
                    self.qvm_collection.save()
                except Exception as ex:
                    msg.append(str(ex))
                finally:
                    self.qvm_collection.unlock_db()

        #vm label changed
        if self.vmlabel.currentIndex() != self.label_idx:
            label = self.label_list[self.vmlabel.currentIndex()]
            self.qvm_collection.lock_db_for_writing()
            self.vm.label = label
            self.qvm_collection.save()
            self.qvm_collection.unlock_db()

        return msg

       # template_vm = template_vm_list[dialog.template_name.currentIndex()]
       # allow_networking = dialog.allow_networking.isChecked()

    ######### firewall tab related

    def set_fw_model(self, model):
        self.fw_model = model
        self.rulesTreeView.setModel(model)
        self.rulesTreeView.header().setResizeMode(QHeaderView.ResizeToContents)
        self.rulesTreeView.header().setResizeMode(0, QHeaderView.Stretch)
        self.set_allow(model.allow)
        self.dnsCheckBox.setChecked(model.allowDns)
        self.icmpCheckBox.setChecked(model.allowIcmp)

    def set_allow(self, allow):
        self.policyAllowRadioButton.setChecked(allow)
        self.policyDenyRadioButton.setChecked(not allow)

    def policy_radio_toggled(self, on):
        self.fw_model.allow = self.policyAllowRadioButton.isChecked()

    def dns_checkbox_toggled(self, on):
        self.fw_model.allowDns = on

    def icmp_checkbox_toggled(self, on):
        self.fw_model.allowIcmp = on

    def new_rule_button_pressed(self):
        dialog = NewFwRuleDlg()
        self.run_rule_dialog(dialog)

    def edit_rule_button_pressed(self):
        dialog = NewFwRuleDlg()
        dialog.set_ok_enabled(True)
        selected = self.rulesTreeView.selectedIndexes()
        if len(selected) > 0:
            row = self.rulesTreeView.selectedIndexes().pop().row()
            address = self.fw_model.get_column_string(0, row).replace(' ', '')
            dialog.addressComboBox.setItemText(0, address)
            dialog.addressComboBox.setCurrentIndex(0)
            service = self.fw_model.get_column_string(1, row)
            dialog.serviceComboBox.setItemText(0, service)
            dialog.serviceComboBox.setCurrentIndex(0)
            self.run_rule_dialog(dialog, row)

    def delete_rule_button_pressed(self):
        for i in set([index.row() for index in self.rulesTreeView.selectedIndexes()]):
            self.fw_model.removeChild(i)

    def run_rule_dialog(self, dialog, row = None):
        if dialog.exec_():
            address = str(dialog.addressComboBox.currentText())
            service = str(dialog.serviceComboBox.currentText())
            port = None
            port2 = None

            unmask = address.split("/", 1)
            if len(unmask) == 2:
                address = unmask[0]
                netmask = int(unmask[1])
            else:
                netmask = 32

            if address == "*":
                address = "0.0.0.0"
                netmask = 0

            if service == "*":
                service = "0"
            try:
                range = service.split("-", 1)
                if len(range) == 2:
                    port = int(range[0])
                    port2 = int(range[1])
                else:
                    port = int(service)
            except (TypeError, ValueError) as ex:
                port = self.fw_model.get_service_port(service)

            if port is not None:
                if port2 is not None and port2 <= port:
                    QMessageBox.warning(None, "Invalid service ports range", "Port {0} is lower than port {1}.".format(port2, port))
                else:
                    item = QubesFirewallRuleItem(address, netmask, port, port2)
                    if row is not None:
                        self.fw_model.setChild(row, item)
                    else:
                        self.fw_model.appendChild(item)
            else:
                QMessageBox.warning(None, "Invalid service name", "Service '{0} is unknown.".format(service))


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception( exc_type, exc_value, exc_traceback ):
    import sys
    import os.path
    import traceback

    filename, line, dummy, dummy = traceback.extract_tb( exc_traceback ).pop()
    filename = os.path.basename( filename )
    error    = "%s: %s" % ( exc_type.__name__, exc_value )

    QMessageBox.critical(None, "Houston, we have a problem...",
                         "Whoops. A critical error has occured. This is most likely a bug "
                         "in Qubes VM Settings application.<br><br>"
                         "<b><i>%s</i></b>" % error +
                         "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
                         % ( line, filename ))


def main():

    global qubes_host
    qubes_host = QubesHost()

    global app
    app = QApplication(sys.argv)
    app.setOrganizationName("The Qubes Project")
    app.setOrganizationDomain("http://qubes-os.org")
    app.setApplicationName("Qubes VM Settings")

    sys.excepthook = handle_exception

    qvm_collection = QubesVmCollection()
    qvm_collection.lock_db_for_reading()
    qvm_collection.load()
    qvm_collection.unlock_db()

    vm = None

    if len(sys.argv) > 1:
        vm = qvm_collection.get_vm_by_name(sys.argv[1])
        if vm is None or vm.qid not in qvm_collection:
            QMessageBox.critical(None, "Qubes VM Settings Error",
                    "A VM with the name '{0}' does not exist in the system.".format(sys.argv[1]))
            sys.exit(1)
    else:
        vms_list = [vm.name for vm in qvm_collection.values() if (vm.is_appvm() or vm.is_template())]
        vmname = QInputDialog.getItem(None, "Select VM", "Select VM:", vms_list, editable = False)
        if not vmname[1]:
            sys.exit(1)
        vm = qvm_collection.get_vm_by_name(vmname[0])


    global settings_window
    settings_window = VMSettingsWindow(vm, app, qvm_collection, "basic")

    settings_window.show()

    app.exec_()
    app.exit()


if __name__ == "__main__":
    main()
