#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2011  Tomasz Sterna <tomek@xiaoka.com>
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
import re
import xml.etree.ElementTree

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesException
from qubes.qubes import dry_run

import ui_editfwrulesdlg
import ui_newfwruledlg

class EditFwRulesDlg (QDialog, ui_editfwrulesdlg.Ui_EditFwRulesDlg):
    def __init__(self, parent = None):
        super (EditFwRulesDlg, self).__init__(parent)
        self.setupUi(self)
        self.newRuleButton.clicked.connect(self.new_rule_button_pressed)
        self.editRuleButton.clicked.connect(self.edit_rule_button_pressed)
        self.deleteRuleButton.clicked.connect(self.delete_rule_button_pressed)
        self.policyAllowRadioButton.toggled.connect(self.policy_radio_toggled)
        self.dnsCheckBox.toggled.connect(self.dns_checkbox_toggled)

    def set_model(self, model):
        self.__model = model
        self.rulesTreeView.setModel(model)
        self.rulesTreeView.header().setResizeMode(QHeaderView.ResizeToContents)
        self.rulesTreeView.header().setResizeMode(0, QHeaderView.Stretch)
        self.set_allow(model.allow)
        self.dnsCheckBox.setChecked(model.allowDns)
        self.setWindowTitle(model.get_vm_name() + " firewall")

    def set_allow(self, allow):
        self.policyAllowRadioButton.setChecked(allow)
        self.policyDenyRadioButton.setChecked(not allow)

    def policy_radio_toggled(self, on):
        self.__model.allow = self.policyAllowRadioButton.isChecked()

    def dns_checkbox_toggled(self, on):
        self.__model.allowDns = on

    def new_rule_button_pressed(self):
        dialog = NewFwRuleDlg()
        self.run_rule_dialog(dialog)

    def edit_rule_button_pressed(self):
        dialog = NewFwRuleDlg()
        row = self.rulesTreeView.selectedIndexes().pop().row()
        item = self.__model.children[row]
        dialog.addressEdit.setText(item.address)
        service = self.__model.get_service_name(item.portBegin)
        dialog.serviceComboBox.insertItem(0, service)
        dialog.serviceComboBox.setCurrentIndex(0)
        self.run_rule_dialog(dialog, row)

    def run_rule_dialog(self, dialog, row = None):
        if dialog.exec_():
            address = dialog.addressEdit.text()
            service = dialog.serviceComboBox.currentText()
            port = None

            try:
                port = int(service)
            except (TypeError, ValueError) as ex:
                port = self.__model.get_service_port(service)

            if port is not None:
                item = QubesFirewallRuleItem(address, 32, port, None)
                if row is not None:
                    self.__model.setChild(row, item)
                else:
                    self.__model.appendChild(item)
            else:
                QMessageBox.warning(None, "Invalid service name", "Service '{0} is unknown.".format(service))

    def delete_rule_button_pressed(self):
        for i in set([index.row() for index in self.rulesTreeView.selectedIndexes()]):
            self.__model.removeChild(i)

class QIPAddressValidator(QValidator):
    def __init__(self, parent = None):
        super (QIPAddressValidator, self).__init__(parent)

    def validate(self, input, pos):
        hostname = input

        if len(hostname) > 255 or len(hostname) == 0:
            return (QValidator.Intermediate, pos)

        if hostname[-1:] == ".":
            hostname = hostname[:-1]

        if hostname[-1:] == "-":
            return (QValidator.Intermediate, pos)

        allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
        if all(allowed.match(x) for x in hostname.split(".")):
            return (QValidator.Acceptable, pos)

        return (QValidator.Invalid, pos)

class NewFwRuleDlg (QDialog, ui_newfwruledlg.Ui_NewFwRuleDlg):
    def __init__(self, parent = None):
        super (NewFwRuleDlg, self).__init__(parent)
        self.setupUi(self)

        self.set_ok_enabled(False)
        self.addressEdit.setValidator(QIPAddressValidator())
        self.addressEdit.editingFinished.connect(self.address_editing_finished)
        self.serviceComboBox.setValidator(QRegExpValidator(QRegExp("[a-z][a-z0-9-]+|[0-9]+", Qt.CaseInsensitive), None))

        self.serviceComboBox.setInsertPolicy(QComboBox.InsertAtBottom)
        self.populate_services_combo()
        self.serviceComboBox.setInsertPolicy(QComboBox.InsertAtTop)

    def populate_services_combo(self):
        displayed_services = [
                'http', 'https', 'ftp', 'ftps',
                'smtp', 'pop3', 'pop3s', 'imap', 'imaps', 'nntp', 'nntps',
                'ssh', 'telnet', 'telnets', 'ntp', 'snmp',
                'ldap', 'ldaps', 'irc', 'ircs', 'xmpp-client',
                'syslog', 'printer', 'nfs', 'x11',
            ]
        for service in displayed_services:
            self.serviceComboBox.addItem(service)

    def address_editing_finished(self):
        self.set_ok_enabled(True)

    def set_ok_enabled(self, on):
        ok_button = self.buttonBox.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(on)

class QubesFirewallRuleItem(object):
    def __init__(self, address = str(), netmask = 32, portBegin = 0, portEnd = None):
        self.__address = address
        self.__netmask = netmask
        self.__portBegin = portBegin
        self.__portEnd = portEnd

    @property
    def address(self):
        return self.__address

    @property
    def netmask(self):
        return self.__netmask

    @property
    def portBegin(self):
        return self.__portBegin

    @property
    def portEnd(self):
        return self.__portEnd

    def hasChildren(self):
        return False

class QubesFirewallRulesModel(QAbstractItemModel):
    def __init__(self, parent=None):
        QAbstractItemModel.__init__(self, parent)

        self.__columnValues = {
                0: lambda x: self.children[x].address,
                1: lambda x: "{0}-{1}".format(self.children[x].portBegin, self.children[x].portEnd) if self.children[x].portEnd is not None \
                        else self.get_service_name(self.children[x].portBegin),
        }
        self.__columnNames = {
                0: "Address",
                1: "Service",
        }

        self.__services = list()
        pattern = re.compile("(?P<name>[a-z][a-z0-9-]+)\s+(?P<port>[0-9]+)/(?P<protocol>[a-z]+)", re.IGNORECASE)
        f = open('/etc/services', 'r')
        for line in f:
            match = pattern.match(line)
            if match is not None:
                service = match.groupdict()
                self.__services.append( (service["name"], int(service["port"]), service["protocol"]) )
        f.close()

    def get_service_name(self, port):
        for service in self.__services:
            if service[1] == port:
                return service[0]
        return str(port)

    def get_service_port(self, name):
        for service in self.__services:
            if service[0] == name:
                return service[1]
        return None

    def set_vm(self, vm):
        self.__vm = vm

        self.clearChildren()

        conf = vm.get_firewall_conf()

        self.allow = conf["allow"]
        self.allowDns = conf["allowDns"]

        for rule in conf["rules"]:
            self.appendChild(QubesFirewallRuleItem(
                rule["address"], rule["netmask"], rule["portBegin"], rule["portEnd"]
                ))

    def get_vm_name(self):
        return self.__vm.name

    def apply_rules(self):
        assert self.__vm is not None

        conf = { "allow": self.allow, "allowDns": self.allowDns, "rules": list() }

        for rule in self.children:
            conf["rules"].append(
                    {
                        "address": rule.address,
                        "netmask": rule.netmask,
                        "portBegin": rule.portBegin,
                        "portEnd": rule.portEnd
                    }
            )

        self.__vm.write_firewall_conf(conf)

        qvm_collection = QubesVmCollection()
        qvm_collection.lock_db_for_reading()
        qvm_collection.load()
        qvm_collection.unlock_db()

        for vm in qvm_collection.values():
            if vm.is_fwvm():
                vm.write_iptables_xenstore_entry()

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        return self.createIndex(row, column, self.children[row])

    def parent(self, child):
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        return len(self)

    def columnCount(self, parent=QModelIndex()):
        return len(self.__columnValues)

    def hasChildren(self, index=QModelIndex()):
        parentItem = index.internalPointer()
        if parentItem is not None:
            return parentItem.hasChildren()
        else:
            return True

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            return self.__columnValues[index.column()](index.row())

        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if section < len(self.__columnNames) \
                and orientation == Qt.Horizontal and role == Qt.DisplayRole:
                    return self.__columnNames[section]

        return QVariant()

    @property
    def children(self):
        return self.__children

    def appendChild(self, child):
        row = len(self)
        self.beginInsertRows(QModelIndex(), row, row)
        self.children.append(child)
        self.endInsertRows()
        index = self.createIndex(row, 0, child)
        self.dataChanged.emit(index, index)

    def removeChild(self, i):
        if i >= len(self):
            return

        self.beginRemoveRows(QModelIndex(), i, i)
        del self.children[i]
        self.endRemoveRows()
        index = self.createIndex(i, 0)
        self.dataChanged.emit(index, index)

    def setChild(self, i, child):
        self.children[i] = child
        index = self.createIndex(i, 0, child)
        self.dataChanged.emit(index, index)

    def clearChildren(self):
        self.__children = list()

    def __len__(self):
        return len(self.children)
