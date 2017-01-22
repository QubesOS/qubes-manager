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
import datetime

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesException
from qubes.qubes import dry_run

import ui_newfwruledlg


class QIPAddressValidator(QValidator):
    def __init__(self, parent = None):
        super (QIPAddressValidator, self).__init__(parent)

    def validate(self, input, pos):
        hostname = str(input)

        if len(hostname) > 255 or len(hostname) == 0:
            return (QValidator.Intermediate, pos)

        if hostname == "*":
            return (QValidator.Acceptable, pos)

        unmask = hostname.split("/", 1)
        if len(unmask) == 2:
            hostname = unmask[0]
            mask = unmask[1]
            if mask.isdigit() or mask == "":
                if re.match("^([0-9]{1,3}\.){3}[0-9]{1,3}$", hostname) is None:
                    return (QValidator.Invalid, pos)
                if mask != "":
                    mask = int(unmask[1])
                    if mask < 0 or mask > 32:
                        return (QValidator.Invalid, pos)
            else:
                return (QValidator.Invalid, pos)

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
        self.addressComboBox.setValidator(QIPAddressValidator())
        self.addressComboBox.editTextChanged.connect(self.address_editing_finished)
        self.serviceComboBox.setValidator(QRegExpValidator(QRegExp("[a-z][a-z0-9-]+|[0-9]+(-[0-9]+)?", Qt.CaseInsensitive), None))
        self.serviceComboBox.setEnabled(False)
        self.serviceComboBox.setInsertPolicy(QComboBox.InsertAtBottom)
        self.populate_combos()
        self.serviceComboBox.setInsertPolicy(QComboBox.InsertAtTop)

    def accept(self):
        if self.tcp_radio.isChecked() or self.udp_radio.isChecked():
            if len(self.serviceComboBox.currentText()) == 0:
                msg = QMessageBox()
                msg.warning(self, self.tr("Firewall rule"),
                    self.tr("You need to fill service name/port for TCP/UDP rule"))
                return
        QDialog.accept(self)

    def populate_combos(self):
        example_addresses = [
                "", "www.example.com",
                "192.168.1.100", "192.168.0.0/16",
                "*"
            ]
        displayed_services = [
                '',
                'http', 'https', 'ftp', 'ftps', 'smtp',
                'smtps', 'pop3', 'pop3s', 'imap', 'imaps', 'odmr', 
                'nntp', 'nntps', 'ssh', 'telnet', 'telnets', 'ntp', 
                'snmp', 'ldap', 'ldaps', 'irc', 'ircs', 'xmpp-client',
                'syslog', 'printer', 'nfs', 'x11',
                '1024-1234'
            ]
        for address in example_addresses:
            self.addressComboBox.addItem(address)
        for service in displayed_services:
            self.serviceComboBox.addItem(service)

    def address_editing_finished(self):
        self.set_ok_enabled(True)

    def set_ok_enabled(self, on):
        ok_button = self.buttonBox.button(QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(on)

    def on_tcp_radio_toggled(self, checked):
        if checked:
            self.serviceComboBox.setEnabled(True)

    def on_udp_radio_toggled(self, checked):
        if checked:
            self.serviceComboBox.setEnabled(True)

    def on_any_radio_toggled(self, checked):
        if checked:
            self.serviceComboBox.setEnabled(False)

class QubesFirewallRulesModel(QAbstractItemModel):
    def __init__(self, parent=None):
        QAbstractItemModel.__init__(self, parent)

        self.__columnValues = {
            0: lambda x: "*" if self.children[x]["address"] == "0.0.0.0" and
                                self.children[x]["netmask"] == 0  else
            self.children[x]["address"] + ("" if self.children[x][ "netmask"] == 32  else
                                           " /{0}".format(self.children[x][
                                               "netmask"])),
            1: lambda x: "any" if self.children[x]["portBegin"] == 0  else
            "{0}-{1}".format(self.children[x]["portBegin"], self.children[x][
                "portEnd"]) if self.children[x]["portEnd"] is not None  else \
                self.get_service_name(self.children[x]["portBegin"]),
            2: lambda x: self.children[x]["proto"], }
        self.__columnNames = {0: "Address", 1: "Service", 2: "Protocol", }
        self.__services = list()
        pattern = re.compile("(?P<name>[a-z][a-z0-9-]+)\s+(?P<port>[0-9]+)/(?P<protocol>[a-z]+)", re.IGNORECASE)
        f = open('/etc/services', 'r')
        for line in f:
            match = pattern.match(line)
            if match is not None:
                service = match.groupdict()
                self.__services.append( (service["name"], int(service["port"]),) )
        f.close()

        self.fw_changed = False

    def sort(self, idx, order):
        from operator import attrgetter

        rev = (order == Qt.AscendingOrder)
        if idx==0:
            self.children.sort(key=lambda x: x['address'], reverse = rev)
        if idx==1:
            self.children.sort(key=lambda x: self.get_service_name(x[
                "portBegin"]) if x["portEnd"] == None else x["portBegin"],
                               reverse = rev)
        if idx==2:
            self.children.sort(key=lambda x: x['proto'], reverse
            = rev)
        index1 = self.createIndex(0, 0)
        index2 = self.createIndex(len(self)-1, len(self.__columnValues)-1)
        self.dataChanged.emit(index1, index2)


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

    def get_column_string(self, col, row):
        return self.__columnValues[col](row)

    def set_vm(self, vm):
        self.__vm = vm

        self.clearChildren()

        conf = vm.get_firewall_conf()

        self.allow = conf["allow"]
        self.allowDns = conf["allowDns"]
        self.allowIcmp = conf["allowIcmp"]
        self.allowYumProxy = conf["allowYumProxy"]
        self.tempFullAccessExpireTime = 0

        for rule in conf["rules"]:
            self.appendChild(rule)
            if "expire" in rule and rule["address"] == "0.0.0.0":
                self.tempFullAccessExpireTime = rule["expire"]

    def get_vm_name(self):
        return self.__vm.name

    def apply_rules(self, allow, dns, icmp, yumproxy, tempFullAccess=False,
                    tempFullAccessTime=None):
        assert self.__vm is not None

        if self.allow != allow or self.allowDns != dns or \
                self.allowIcmp != icmp or self.allowYumProxy != yumproxy or \
                (self.tempFullAccessExpireTime != 0) != tempFullAccess:
            self.fw_changed = True

        conf = { "allow": allow,
                "allowDns": dns,
                "allowIcmp": icmp,
                "allowYumProxy": yumproxy,
                "rules": list()
            }

        for rule in self.children:
            if "expire" in rule and rule["address"] == "0.0.0.0" and \
                    rule["netmask"] == 0 and rule["proto"] == "any":
                # rule already present, update its time
                if tempFullAccess:
                    rule["expire"] = \
                        int(datetime.datetime.now().strftime("%s")) + \
                        tempFullAccessTime*60
                tempFullAccess = False
            conf["rules"].append(rule)

        if tempFullAccess and not allow:
            conf["rules"].append({"address": "0.0.0.0",
                                  "netmask": 0,
                                  "proto": "any",
                                  "expire": int(
                                      datetime.datetime.now().strftime("%s"))+\
                                        tempFullAccessTime*60
                                  })

        if self.fw_changed:
            self.__vm.write_firewall_conf(conf)

            if self.__vm.is_running():
                vm = self.__vm.netvm
                while vm is not None:
                    if vm.is_proxyvm() and vm.is_running():
                        vm.write_iptables_qubesdb_entry()
                    vm = vm.netvm

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
            return False
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
        self.fw_changed = True

    def removeChild(self, i):
        if i >= len(self):
            return

        self.beginRemoveRows(QModelIndex(), i, i)
        del self.children[i]
        self.endRemoveRows()
        index = self.createIndex(i, 0)
        self.dataChanged.emit(index, index)
        self.fw_changed = True

    def setChild(self, i, child):
        self.children[i] = child
        index = self.createIndex(i, 0, child)
        self.dataChanged.emit(index, index)
        self.fw_changed = True

    def clearChildren(self):
        self.__children = list()

    def __len__(self):
        return len(self.children)

