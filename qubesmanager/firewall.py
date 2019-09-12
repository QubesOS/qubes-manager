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
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
#
#

import datetime
import re

from PyQt4 import QtCore, QtGui  # pylint: disable=import-error
import qubesadmin.firewall

from . import ui_newfwruledlg  # pylint: disable=no-name-in-module


class FirewallModifiedOutsideError(ValueError):
    pass

class QIPAddressValidator(QtGui.QValidator):
    # pylint: disable=too-few-public-methods
    def __init__(self, parent=None):
        super(QIPAddressValidator, self).__init__(parent)

    def validate(self, input_string, pos):
        # pylint: disable=too-many-return-statements,no-self-use
        hostname = str(input_string)

        if len(hostname) > 255 or not hostname:
            return (QtGui.QValidator.Intermediate, input_string, pos)

        if hostname == "*":
            return (QtGui.QValidator.Acceptable, input_string, pos)

        unmask = hostname.split("/", 1)
        if len(unmask) == 2:
            hostname = unmask[0]
            mask = unmask[1]
            if mask.isdigit() or mask == "":
                if re.match(r"^([0-9]{1,3}\.){3}[0-9]{1,3}$", hostname) is None:
                    return (QtGui.QValidator.Invalid, input_string, pos)
                if mask != "":
                    mask = int(unmask[1])
                    if mask < 0 or mask > 32:
                        return (QtGui.QValidator.Invalid, input_string, pos)
            else:
                return (QtGui.QValidator.Invalid, input_string, pos)

        if hostname[-1:] == ".":
            hostname = hostname[:-1]

        if hostname[-1:] == "-":
            return (QtGui.QValidator.Intermediate, input_string, pos)

        allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
        if all(allowed.match(x) for x in hostname.split(".")):
            return (QtGui.QValidator.Acceptable, input_string, pos)

        return (QtGui.QValidator.Invalid, input_string, pos)

class NewFwRuleDlg(QtGui.QDialog, ui_newfwruledlg.Ui_NewFwRuleDlg):
    def __init__(self, parent=None):
        super(NewFwRuleDlg, self).__init__(parent)
        self.setupUi(self)

        self.set_ok_state(False)
        self.addressComboBox.setValidator(QIPAddressValidator())
        self.addressComboBox.editTextChanged.connect(
            self.address_editing_finished)
        self.serviceComboBox.setValidator(QtGui.QRegExpValidator(
            QtCore.QRegExp("[a-z][a-z0-9-]+|[0-9]+(-[0-9]+)?",
                           QtCore.Qt.CaseInsensitive), None))
        self.serviceComboBox.setEnabled(False)
        self.serviceComboBox.setInsertPolicy(QtGui.QComboBox.InsertAtBottom)
        self.populate_combos()
        self.serviceComboBox.setInsertPolicy(QtGui.QComboBox.InsertAtTop)

        self.model = None

    def try_to_create_rule(self):
        # return True if successful, False otherwise
        address = str(self.addressComboBox.currentText())
        service = str(self.serviceComboBox.currentText())

        rule = qubesadmin.firewall.Rule(None, action='accept')

        if address is not None and address != "*":
            try:
                rule.dsthost = address
            except ValueError:
                QtGui.QMessageBox.warning(
                    self, self.tr("Invalid address"),
                    self.tr("Address '{0}' is invalid.").format(address))
                return False

        if self.tcp_radio.isChecked():
            rule.proto = 'tcp'
        elif self.udp_radio.isChecked():
            rule.proto = 'udp'

        if self.model.port_range_pattern.fullmatch(service):
            try:
                rule.dstports = service
            except ValueError:
                QtGui.QMessageBox.warning(
                    self,
                    self.tr("Invalid port or service"),
                    self.tr("Port number or service '{0}' is "
                            "invalid.").format(service))
                return False
        elif service:
            if self.model.service_port_pattern.fullmatch(service):
                parsed_service = self.model.service_port_pattern.match(
                    service).groups()[0]
            else:
                parsed_service = service

            try:
                rule.dstports = parsed_service
            except (TypeError, ValueError):
                if self.model.get_service_port(parsed_service) is not None:
                    rule.dstports = self.model.get_service_port(parsed_service)
                else:
                    QtGui.QMessageBox.warning(
                        self,
                        self.tr("Invalid port or service"),
                        self.tr(
                            "Port number or service '{0}' is "
                            "invalid.".format(parsed_service)))
                    return False

        if self.model.current_row is not None:
            self.model.set_child(self.model.current_row, rule)
        else:
            self.model.append_child(rule)
        return True

    def accept(self):
        if self.tcp_radio.isChecked() or self.udp_radio.isChecked():
            if not self.serviceComboBox.currentText():
                msg = QtGui.QMessageBox()
                msg.warning(self, self.tr("Firewall rule"),
                    self.tr("You need to fill service "
                            "name/port for TCP/UDP rule"))
                return
        if self.try_to_create_rule():
            QtGui.QDialog.accept(self)

    def populate_combos(self):
        example_addresses = [
                "", "www.example.com",
                "192.168.1.100", "192.168.0.0/16",
                "*"
            ]
        example_services = [
                '', '22', '80', '1024-1234',
                'http', 'https', 'ftp', 'ftps', 'smtp',
                'pop3', 'pop3s', 'imap', 'imaps', 'odmr',
                'nntp', 'nntps', 'ssh', 'telnet', 'telnets', 'ntp',
                'snmp', 'ldap', 'ldaps', 'irc', 'ircs-u', 'xmpp-client',
                'syslog', 'printer', 'nfs', 'x11'
            ]
        for address in example_addresses:
            self.addressComboBox.addItem(address)
        for service in example_services:
            self.serviceComboBox.addItem(service)

    def address_editing_finished(self):
        self.set_ok_state(True)

    def set_ok_state(self, ok_state):
        ok_button = self.buttonBox.button(QtGui.QDialogButtonBox.Ok)
        if ok_button is not None:
            ok_button.setEnabled(ok_state)

    def on_tcp_radio_toggled(self, checked):
        if checked:
            self.serviceComboBox.setEnabled(True)

    def on_udp_radio_toggled(self, checked):
        if checked:
            self.serviceComboBox.setEnabled(True)

    def on_any_radio_toggled(self, checked):
        if checked:
            self.serviceComboBox.setEnabled(False)


class QubesFirewallRulesModel(QtCore.QAbstractItemModel):
    def __init__(self, parent=None):
        QtCore.QAbstractItemModel.__init__(self, parent)

        self.current_row = None

        self.__column_names = {0: "Address", 1: "Port/Service", 2: "Protocol", }
        self.__services = list()

        self.port_range_pattern = re.compile(r'\d+-\d+')
        self.service_port_pattern = re.compile(r'(\d*) \([a-zA-Z0-9-]*\)')

        pattern = re.compile(
            r"(?P<name>[a-z][a-z0-9-]+)\s+(?P<port>[0-9]+)/"
            r"(?P<protocol>[a-z]+)",
            re.IGNORECASE)
        with open('/etc/services', 'r', encoding='utf-8') as file:
            for line in file:
                match = pattern.match(line)
                if match is not None:
                    service = match.groupdict()
                    self.__services.append(
                        (service["name"], int(service["port"]),))

        self.fw_changed = False
        self.allow = None # is the default policy allow or deny
        self.temp_full_access_expire_time = None # temporary full access time
        self.__vm = None # VM that the model applies to
        self.__children = None # list of rules in the FW

    def sort(self, idx, order):
        rev = (order == QtCore.Qt.AscendingOrder)
        self.children.sort(key=lambda x: self.get_column_string(idx, x),
                           reverse=rev)

        index1 = self.createIndex(0, 0)
        index2 = self.createIndex(len(self) - 1, len(self.__column_names) - 1)
        self.dataChanged.emit(index1, index2)


    def get_service_name(self, port):
        for service in self.__services:
            if str(service[1]) == str(port):
                return "{0} ({1})".format(str(port), service[0])
        return str(port)

    def get_service_port(self, name):
        for service in self.__services:
            if service[0] == name:
                return service[1]
        return None

    def get_column_string(self, col, rule):
        # pylint: disable=too-many-return-statements
        # Address
        if col == 0:
            if rule.dsthost is None:
                return "*"
            if rule.dsthost.type == 'dst4' and rule.dsthost.prefixlen == '32':
                return str(rule.dsthost)[:-3]
            if rule.dsthost.type == 'dst6' and rule.dsthost.prefixlen == '128':
                return str(rule.dsthost)[:-4]
            return str(rule.dsthost)

        # Service
        if col == 1:
            if rule.dstports is None:
                return "any"
            if rule.dstports.range[0] != rule.dstports.range[1]:
                return str(rule.dstports)
            return self.get_service_name(rule.dstports)

        # Protocol
        if col == 2:
            if rule.proto is None:
                return "any"
            return str(rule.proto)
        return "unknown"

    @staticmethod
    def get_firewall_conf(vm):
        conf = {
            'allow': None,
            'expire': 0,
            'rules': [],
        }

        allow_dns = False
        allow_icmp = False
        common_action = None

        reversed_rules = reversed(vm.firewall.rules)
        last_rule = next(reversed_rules, None)

        if last_rule is None:
            raise FirewallModifiedOutsideError('At least one rule must exist.')

        if last_rule == qubesadmin.firewall.Rule('action=accept') \
                or last_rule == qubesadmin.firewall.Rule('action=drop'):
            common_action = last_rule.action
        else:
            raise FirewallModifiedOutsideError('Last rule must be either '
                                               'drop all or accept all.')

        dns_rule = qubesadmin.firewall.Rule(None,
                                        action='accept', specialtarget='dns')
        icmp_rule = qubesadmin.firewall.Rule(None,
                                        action='accept', proto='icmp')
        for rule in reversed_rules:
            if rule == dns_rule:
                allow_dns = True
                continue

            if rule == icmp_rule:
                allow_icmp = True
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

        if not allow_icmp and not conf['allow']:
            raise FirewallModifiedOutsideError('ICMP must be allowed.')

        if not allow_dns and not conf['allow']:
            raise FirewallModifiedOutsideError('DNS must be allowed')

        return conf

    @staticmethod
    def write_firewall_conf(vm, conf):
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
                action='drop'))

        vm.firewall.rules = rules

    def set_vm(self, vm):
        self.__vm = vm

        self.clear_children()

        conf = self.get_firewall_conf(vm)

        self.allow = conf["allow"]

        self.temp_full_access_expire_time = conf['expire']

        for rule in conf["rules"]:
            self.append_child(rule)

    def get_vm_name(self):
        return self.__vm.name

    def apply_rules(self, allow, temp_full_access=False,
                    temp_full_access_time=None):
        assert self.__vm is not None

        if self.allow != allow or \
                (self.temp_full_access_expire_time != 0) != temp_full_access:
            self.fw_changed = True

        conf = {"allow": allow,
                "rules": list()
            }

        conf['rules'].extend(self.children)

        if temp_full_access and not allow:
            conf["rules"].append(qubesadmin.firewall.Rule(
                None,
                action='accept',
                expire=int(datetime.datetime.now().strftime("%s")) +
                       temp_full_access_time * 60))

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

    def run_rule_dialog(self, dialog, row=None):
        self.current_row = row
        dialog.model = self
        dialog.exec_()

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()

        return self.createIndex(row, column, self.children[row])

    def parent(self, child): # pylint: disable=unused-argument,no-self-use
        return QtCore.QModelIndex()

    # pylint: disable=invalid-name,unused-argument
    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self)

    # pylint: disable=invalid-name,unused-argument
    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.__column_names)

    # pylint: disable=invalid-name,no-self-use
    def hasChildren(self, index=QtCore.QModelIndex()):
        parent_item = index.internalPointer()
        return parent_item is None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid() and role == QtCore.Qt.DisplayRole:
            return self.get_column_string(index.column(),
                                          self.children[index.row()])

    # pylint: disable=invalid-name
    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if section < len(self.__column_names) \
                and orientation == QtCore.Qt.Horizontal \
                and role == QtCore.Qt.DisplayRole:
            return self.__column_names[section]

    @property
    def children(self):
        return self.__children

    def append_child(self, child):
        row = len(self)
        self.beginInsertRows(QtCore.QModelIndex(), row, row)
        self.children.append(child)
        self.endInsertRows()
        index = self.createIndex(row, 0, child)
        self.dataChanged.emit(index, index)
        self.fw_changed = True

    def remove_child(self, i):
        if i >= len(self):
            return

        self.beginRemoveRows(QtCore.QModelIndex(), i, i)
        del self.children[i]
        self.endRemoveRows()
        index = self.createIndex(i, 0)
        self.dataChanged.emit(index, index)
        self.fw_changed = True

    def set_child(self, i, child):
        self.children[i] = child
        index = self.createIndex(i, 0, child)
        self.dataChanged.emit(index, index)
        self.fw_changed = True

    def clear_children(self):
        self.__children = list()

    def __len__(self):
        return len(self.children)
