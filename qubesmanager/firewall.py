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
import xml.etree.ElementTree

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesException
from qubes.qubes import qubes_store_filename
from qubes.qubes import QubesVmLabels
from qubes.qubes import dry_run
from qubes.qubes import qubes_guid_path

import ui_editfwrulesdlg
import ui_newfwruledlg

class EditFwRulesDlg (QDialog, ui_editfwrulesdlg.Ui_EditFwRulesDlg):
    def __init__(self, parent = None):
        super (EditFwRulesDlg, self).__init__(parent)
        self.setupUi(self)
        self.newRuleButton.clicked.connect(self.new_rule_button_pressed)
        self.deleteRuleButton.clicked.connect(self.delete_rule_button_pressed)

    def set_model(self, model):
        self.__model = model
        self.rulesTreeView.setModel(model)
        self.rulesTreeView.header().setResizeMode(QHeaderView.ResizeToContents)
        self.rulesTreeView.header().setResizeMode(0, QHeaderView.Stretch)

    def new_rule_button_pressed(self):
        dialog = NewFwRuleDlg()

        if dialog.exec_():
            name = dialog.nameEdit.text()
            allow = dialog.allowCheckBox.isChecked()
            address = dialog.addressEdit.text()
            netmask = dialog.netmasks[dialog.netmaskComboBox.currentIndex()]
            portBegin = dialog.portBeginSpinBox.value()
            portEnd   = dialog.portEndSpinBox.value()
            if portEnd <= portBegin:
                portEnd = None

            if portBegin == 0 and portEnd is None:
                return

            if name == "":
                QMessageBox.warning(None, "Incorrect name", "You need to name the rule.")
                return

            if address == "":
                QMessageBox.warning(None, "Incorrect address", "Pleas give an address for the rule.")
                return

            self.__model.appendChild(QubesFirewallRuleItem(name, allow, address, netmask, portBegin, portEnd))

    def delete_rule_button_pressed(self):
        for i in set([index.row() for index in self.rulesTreeView.selectedIndexes()]):
            self.__model.removeChild(i)

class NewFwRuleDlg (QDialog, ui_newfwruledlg.Ui_NewFwRuleDlg):
    def __init__(self, parent = None):
        super (NewFwRuleDlg, self).__init__(parent)
        self.setupUi(self)

        self.netmasks = [ 32, 24, 16, 0 ]
        for mask in self.netmasks:
            self.netmaskComboBox.addItem(str(mask))

class QubesFirewallRuleItem(object):
    def __init__(self, name = str(), allow = bool(), address = str(), netmask = 32, portBegin = 0, portEnd = None):
        self.__name = name
        self.__allow = allow
        self.__address = address
        self.__netmask = netmask
        self.__portBegin = portBegin
        self.__portEnd = portEnd

    @property
    def name(self):
        return self.__name

    @property
    def allow(self):
        return self.__allow

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
                0: lambda x: self.children[x].name,
                1: lambda x: self.children[x].address,
                2: lambda x: "/{0}".format(self.children[x].netmask),
                3: lambda x: "{0}-{1}".format(self.children[x].portBegin, self.children[x].portEnd) if self.children[x].portEnd is not None \
                        else self.children[x].portBegin,
                4: lambda x: "ALLOW" if self.children[x].allow else "DENY",
        }
        self.__columnNames = {
                0: "Name",
                1: "Address",
                2: "Mask",
                3: "Port(s)",
                4: "Allow",
        }

    def set_vm(self, vm):
        self.__vm = vm

        self.clearChildren()

        root = vm.get_firewall_conf()
        for element in root:
            try:
                kwargs = { "allow": element.tag=="allow" }
                attr_list = ("name", "address", "netmask", "port", "toport")

                for attribute in attr_list:
                    kwargs[attribute] = element.get(attribute)

                kwargs["netmask"] = int(kwargs["netmask"])
                kwargs["portBegin"] = int(kwargs["port"])
                if kwargs["toport"] is not None:
                    kwargs["portEnd"] = int(kwargs["toport"])
                del(kwargs["port"])
                del(kwargs["toport"])

                self.appendChild(QubesFirewallRuleItem(**kwargs))

            except (ValueError, LookupError) as err:
                print "{0}: load error: {1}".format(
                        os.path.basename(sys.argv[0]), err)
                return False

        return True

    def apply_rules(self):
        assert self.__vm is not None

        root = xml.etree.ElementTree.Element(
                "QubesFirwallRules",
                policy="allow"
        )

        for rule in self.children:
            element = xml.etree.ElementTree.Element(
                    "allow" if rule.allow else "deny",
                    name=rule.name,
                    address=rule.address,
                    netmask=str(rule.netmask),
                    port=str(rule.portBegin),
            )
            if rule.portEnd is not None:
                element.set("toport", str(rule.portEnd)) 
            root.append(element)

        tree = xml.etree.ElementTree.ElementTree(root)

        try:
            self.__vm.write_firewall_conf(tree)
        except EnvironmentError as err:
            print "{0}: save error: {1}".format(
                    os.path.basename(sys.argv[0]), err)
            return False

        return True

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
        
    def clearChildren(self):
        self.__children = list()

    def __len__(self):
        return len(self.children)
