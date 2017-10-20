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

import datetime
import ipaddress
import os
import re
import sys
import xml.etree.ElementTree

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import qubesadmin.firewall

from . import ui_newfwruledlg


class FirewallModifiedOutsideError(ValueError):
    pass

class QIPAddressValidator(QValidator):
    def __init__(self, parent = None):
        super (QIPAddressValidator, self).__init__(parent)

    def validate(self, input, pos):
        hostname = str(input)

        if len(hostname) > 255 or len(hostname) == 0:
            return (QValidator.Intermediate, input, pos)

        if hostname == "*":
            return (QValidator.Acceptable, input, pos)

        unmask = hostname.split("/", 1)
        if len(unmask) == 2:
            hostname = unmask[0]
            mask = unmask[1]
            if mask.isdigit() or mask == "":
                if re.match("^([0-9]{1,3}\.){3}[0-9]{1,3}$", hostname) is None:
                    return (QValidator.Invalid, input, pos)
                if mask != "":
                    mask = int(unmask[1])
                    if mask < 0 or mask > 32:
                        return (QValidator.Invalid, input, pos)
            else:
                return (QValidator.Invalid, input, pos)

        if hostname[-1:] == ".":
            hostname = hostname[:-1]

        if hostname[-1:] == "-":
            return (QValidator.Intermediate, input, pos)

        allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
        if all(allowed.match(x) for x in hostname.split(".")):
            return (QValidator.Acceptable, input, pos)

        return (QValidator.Invalid, input, pos)

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
        self.children.sort(key = lambda x: self.get_column_string(idx, x)
                           , reverse = rev)

        index1 = self.createIndex(0, 0)
        index2 = self.createIndex(len(self)-1, len(self.__columnNames)-1)
        self.dataChanged.emit(index1, index2)


    def get_service_name(self, port):
        for service in self.__services:
            if str(service[1]) == str(port):
                return service[0]
        return str(port)

    def get_service_port(self, name):
        for service in self.__services:
            if service[0] == name:
                return service[1]
        return None

    def get_column_string(self, col, rule):
        # Address
        if col == 0:
            if rule.dsthost is None:
                return "*"
            else:
                if rule.dsthost.type == 'dst4'\
                        and rule.dsthost.prefixlen == '32':
                    return str(rule.dsthost)[:-3]
                elif rule.dsthost.type == 'dst6'\
                        and rule.dsthost.prefixlen == '128':
                    return str(rule.dsthost)[:-4]
                else:
                    return str(rule.dsthost)

        # Service
        if col == 1:
            if rule.dstports is None:
                return "any"
            elif rule.dstports.range[0] != rule.dstports.range[1]:
                return str(rule.dstports)
            else:
                return self.get_service_name(rule.dstports)

        # Protocol
        if col == 2:
            if rule.proto is None:
                return "any"
            else:
                return str(rule.proto)
        return "unknown"

    def get_firewall_conf(self, vm):
        conf = {
            'allow': None,
            'expire': 0,
            'rules': [],
        }

        allowDns = False
        allowIcmp = False
        common_action = None

        reversed_rules = list(reversed(vm.firewall.rules))
        last_rule = reversed_rules.pop(0)

        if last_rule == qubesadmin.firewall.Rule('action=accept') \
                or last_rule == qubesadmin.firewall.Rule('action=drop'):
            common_action = last_rule.action
        else:
            FirewallModifiedOutsideError('Last rule must be either '
                                         'drop all or accept all.')

        dns_rule = qubesadmin.firewall.Rule(None,
                                        action='accept', specialtarget='dns')
        icmp_rule = qubesadmin.firewall.Rule(None,
                                        action='accept', proto='icmp')
        while reversed_rules:
            rule = reversed_rules.pop(0)

            if rule == dns_rule:
                allowDns = True
                continue

            if rule.proto == icmp_rule:
                allowIcmp = True
                continue

            if rule.specialtarget is not None or rule.icmptype is not None:
                raise FirewallModifiedOutsideError("Rule type unknown!")

            if (rule.dsthost is not None or rule.proto is not None) \
                    and rule.expire is None:
                if rule.action == 'accept':
                    conf['rules'].insert(0, rule)
                    continue
                else:
                    raise FirewallModifiedOutsideError('No blacklist support.')

            if rule.expire is not None and rule.dsthost is None \
                    and rule.proto is None:
                conf['expire'] = int(str(rule.expire))
                continue

            raise FirewallModifiedOutsideError('it does not add up.')

        conf['allow'] = (common_action == 'accept')

        if not allowIcmp and not conf['allow']:
            raise FirewallModifiedOutsideError('ICMP must be allowed.')

        if not allowDns and not conf['allow']:
            raise FirewallModifiedOutsideError('DNS must be allowed')

        return conf

    def write_firewall_conf(self, vm, conf):
        rules = []

        for rule in conf['rules']:
            rules.append(rule)

        if not conf['allow']:
            rules.append(qubesadmin.firewall.Rule(None,
                action='accept', specialtarget='dns'))

        if not conf['allow']:
            rules.append(qubesadmin.firewall.Rule(None,
                action='accept', proto='icmp'))

        if conf['allow']:
            rules.append(qubesadmin.firewall.Rule(None,
                action='accept'))
        else:
            rules.append(qubesadmin.firewall.Rule(None,
                action = 'drop'))

        vm.firewall.rules = rules

    def set_vm(self, vm):
        self.__vm = vm

        self.clearChildren()

        conf = self.get_firewall_conf(vm)

        self.allow = conf["allow"]

        self.tempFullAccessExpireTime = conf['expire']

        for rule in conf["rules"]:
            self.appendChild(rule)

    def get_vm_name(self):
        return self.__vm.name

    def apply_rules(self, allow, tempFullAccess=False,
                    tempFullAccessTime=None):
        assert self.__vm is not None

        if self.allow != allow or \
                (self.tempFullAccessExpireTime != 0) != tempFullAccess:
            self.fw_changed = True

        conf = { "allow": allow,
                "rules": list()
            }

        conf['rules'].extend(self.children)

        if tempFullAccess and not allow:
            conf["rules"].append(qubesadmin.firewall.Rule(None,action='accept'
                        , expire=int(datetime.datetime.now().strftime("%s"))+\
                                        tempFullAccessTime*60))

        if self.fw_changed:
            self.write_firewall_conf(self.__vm, conf)

    def populate_edit_dialog(self, dialog, row):
        address = self.get_column_string(0, self.children[row])
        dialog.addressComboBox.setItemText(0, address)
        dialog.addressComboBox.setCurrentIndex(0)
        service = self.get_column_string(1, self.children[row])
        if service == "any":
            service = ""
        dialog.serviceComboBox.setItemText(0, service)
        dialog.serviceComboBox.setCurrentIndex(0)
        protocol = self.get_column_string(2, self.children[row])
        if protocol == "tcp":
            dialog.tcp_radio.setChecked(True)
        elif protocol == "udp":
            dialog.udp_radio.setChecked(True)
        else:
            dialog.any_radio.setChecked(True)

    def run_rule_dialog(self, dialog, row = None):
        if dialog.exec_():

            address = str(dialog.addressComboBox.currentText())
            service = str(dialog.serviceComboBox.currentText())

            rule = qubesadmin.firewall.Rule(None,action='accept')

            if address is not None and address != "*":
                try:
                    rule.dsthost = address
                except ValueError:
                    QMessageBox.warning(None, self.tr("Invalid address"),
                        self.tr("Address '{0}' is invalid.").format(address))

            if dialog.tcp_radio.isChecked():
                rule.proto = 'tcp'
            elif dialog.udp_radio.isChecked():
                rule.proto = 'udp'

            if '-' in service:
                try:
                    rule.dstports = service
                except ValueError:
                    QMessageBox.warning(None, self.tr("Invalid port or service"),
                        self.tr("Port number or service '{0}' is invalid.")
                                        .format(service))
            elif service is not None:
                try:
                    rule.dstports = service
                except (TypeError, ValueError) as ex:
                    if self.get_service_port(service) is not None:
                        rule.dstports = self.get_service_port(service)
                    else:
                        QMessageBox.warning(None,
                            self.tr("Invalid port or service"),
                            self.tr("Port number or service '{0}' is invalid.")
                                            .format(service))

            if row is not None:
                self.setChild(row, rule)
            else:
                self.appendChild(rule)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        return self.createIndex(row, column, self.children[row])

    def parent(self, child):
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        return len(self)

    def columnCount(self, parent=QModelIndex()):
        return len(self.__columnNames)

    def hasChildren(self, index=QModelIndex()):
        parentItem = index.internalPointer()
        if parentItem is not None:
            return False
        else:
            return True

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            return self.get_column_string(index.column()
                                          ,self.children[index.row()])

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if section < len(self.__columnNames) \
                and orientation == Qt.Horizontal and role == Qt.DisplayRole:
                    return self.__columnNames[section]

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

