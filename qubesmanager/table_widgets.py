#!/usr/bin/python3
# -*- coding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2014 Marek Marczykowski-Górecki
#                       <marmarek@invisiblethingslab.com>
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
import datetime

from PyQt4 import QtGui  # pylint: disable=import-error
from PyQt4 import QtCore  # pylint: disable=import-error
# pylint: disable=too-few-public-methods

power_order = QtCore.Qt.DescendingOrder
update_order = QtCore.Qt.AscendingOrder


row_height = 30


class VmIconWidget(QtGui.QWidget):
    def __init__(self, icon_path, enabled=True, size_multiplier=0.7,
                 tooltip=None, parent=None,
                 icon_sz=(32, 32)):   # pylint: disable=unused-argument
        super(VmIconWidget, self).__init__(parent)

        self.enabled = enabled
        self.size_multiplier = size_multiplier
        self.label_icon = QtGui.QLabel()
        self.set_icon(icon_path)

        if tooltip is not None:
            self.label_icon.setToolTip(tooltip)

        layout = QtGui.QHBoxLayout()
        layout.addWidget(self.label_icon)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def setToolTip(self, tooltip):  # pylint: disable=invalid-name
        if tooltip is not None:
            self.label_icon.setToolTip(tooltip)
        else:
            self.label_icon.setToolTip('')

    def set_icon(self, icon_path):

        if icon_path[0] in ':/':
            icon = QtGui.QIcon(icon_path)
        else:
            icon = QtGui.QIcon.fromTheme(icon_path)
        icon_sz = QtCore.QSize(row_height * self.size_multiplier,
                               row_height * self.size_multiplier)
        icon_pixmap = icon.pixmap(
            icon_sz,
            QtGui.QIcon.Disabled if not self.enabled else QtGui.QIcon.Normal)
        self.label_icon.setPixmap(icon_pixmap)
        self.label_icon.setFixedSize(icon_sz)


class VmTypeWidget(VmIconWidget):
    class VmTypeItem(QtGui.QTableWidgetItem):
        def __init__(self, value, vm):
            super(VmTypeWidget.VmTypeItem, self).__init__()
            self.value = value
            self.qid = vm.qid
            self.name = vm.name

        def set_value(self, value):
            self.value = value

        #pylint: disable=too-many-return-statements
        def __lt__(self, other):
            if self.qid == 0:
                return True
            if other.qid == 0:
                return False
            if self.value == other.value:
                return self.name < other.name
            return self.value < other.value

    def __init__(self, vm, parent=None):
        (icon_path, tooltip) = self.get_vm_icon(vm)
        super(VmTypeWidget, self).__init__(
            icon_path, True, 0.8, tooltip, parent)
        self.vm = vm
        self.table_item = self.VmTypeItem(self.value, vm)
        self.value = None

    # TODO: add "provides network" column

    def get_vm_icon(self, vm):
        if vm.klass == 'AdminVM':
            self.value = 0
            icon_name = "dom0"
        elif vm.klass == 'TemplateVM':
            self.value = 3
            icon_name = "templatevm"
        elif vm.klass == 'StandaloneVM':
            self.value = 4
            icon_name = "standalonevm"
        else:
            self.value = 5 + vm.label.index
            icon_name = "appvm"

        return ":/" + icon_name + ".png", vm.klass


class VmLabelWidget(VmIconWidget):
    class VmLabelItem(QtGui.QTableWidgetItem):
        def __init__(self, value, vm):
            super(VmLabelWidget.VmLabelItem, self).__init__()
            self.value = value
            self.qid = vm.qid
            self.name = vm.name

        def set_value(self, value):
            self.value = value

        #pylint: disable=too-many-return-statements
        def __lt__(self, other):
            if self.qid == 0:
                return True
            if other.qid == 0:
                return False
            if self.value == other.value:
                return self.name < other.name
            return self.value < other.value

    def __init__(self, vm, parent=None):
        self.icon_path = self.get_vm_icon_path(vm)
        super(VmLabelWidget, self).__init__(self.icon_path,
                                            True, 0.8, None, parent)
        self.vm = vm
        self.table_item = self.VmLabelItem(self.value, vm)
        self.value = None

    def get_vm_icon_path(self, vm):
        self.value = vm.label.index
        return vm.label.icon

    def update(self):
        icon_path = self.get_vm_icon_path(self.vm)
        if icon_path != self.icon_path:
            self.icon_path = icon_path
            self.set_icon(icon_path)


class VmStatusIcon(QtGui.QLabel):
    def __init__(self, vm, parent=None):
        super(VmStatusIcon, self).__init__(parent)
        self.vm = vm
        self.set_on_icon()
        self.previous_power_state = self.vm.get_power_state()

    def update(self):
        if self.previous_power_state != self.vm.get_power_state():
            self.set_on_icon()
            self.previous_power_state = self.vm.get_power_state()

    def set_on_icon(self):
        if self.vm.get_power_state() == "Running":
            icon = QtGui.QIcon(":/on.png")
            self.status = 3
        elif self.vm.get_power_state() in ["Paused", "Suspended"]:
            icon = QtGui.QIcon(":/paused.png")
            self.status = 2
        elif self.vm.get_power_state() in ["Transient", "Halting", "Dying"]:
            icon = QtGui.QIcon(":/transient.png")
            self.status = 1
        else:
            icon = QtGui.QIcon(":/off.png")
            self.status = 0

        icon_sz = QtCore.QSize(row_height * 0.5, row_height * 0.5)
        icon_pixmap = icon.pixmap(icon_sz)
        self.setPixmap(icon_pixmap)
        self.setFixedSize(icon_sz)


class VmInfoWidget(QtGui.QWidget):
    class VmInfoItem(QtGui.QTableWidgetItem):
        def __init__(self, on_icon, upd_info_item, vm):
            super(VmInfoWidget.VmInfoItem, self).__init__()
            self.on_icon = on_icon
            self.upd_info_item = upd_info_item
            self.vm = vm
            self.qid = vm.qid
            self.name = vm.name

        def __lt__(self, other):
            # pylint: disable=too-many-return-statements
            if self.qid == 0:
                return True
            if other.qid == 0:
                return False

            self_val = self.upd_info_item.value
            other_val = other.upd_info_item.value

            if self.tableWidget().\
                    horizontalHeader().sortIndicatorOrder() == update_order:
                # the result will be sorted by upd, sorting order: Ascending
                self_val += 1 if self.on_icon.status > 0 else 0
                other_val += 1 if other.on_icon.status > 0 else 0
                if self_val == other_val:
                    return self.name < other.name
                return self_val > other_val
            if self.tableWidget().\
                    horizontalHeader().sortIndicatorOrder() == power_order:
                # the result will be sorted by power state,
                # sorting order: Descending
                if self.on_icon.status == other.on_icon.status:
                    return self.name < other.name
                return self_val > other_val
            # it would be strange if this happened
            return

    def __init__(self, vm, parent=None):
        super(VmInfoWidget, self).__init__(parent)
        self.vm = vm
        layout = QtGui.QHBoxLayout()

        self.on_icon = VmStatusIcon(vm)
        self.upd_info = VmUpdateInfoWidget(vm, show_text=False)
        self.error_icon = VmIconWidget(":/warning.png")
        self.blk_icon = VmIconWidget(":/mount.png")
        self.rec_icon = VmIconWidget(":/mic.png")

        layout.addWidget(self.on_icon)
        layout.addWidget(self.upd_info)
        layout.addWidget(self.error_icon)
        layout.addItem(QtGui.QSpacerItem(0, 10,
                                         QtGui.QSizePolicy.Expanding,
                                         QtGui.QSizePolicy.Expanding))
        layout.addWidget(self.blk_icon)
        layout.addWidget(self.rec_icon)

        layout.setContentsMargins(5, 0, 5, 0)
        self.setLayout(layout)

        self.rec_icon.setVisible(False)
        self.blk_icon.setVisible(False)
        self.error_icon.setVisible(False)

        self.table_item = self.VmInfoItem(self.on_icon,\
                self.upd_info.table_item, vm)

    def update_vm_state(self):
        self.on_icon.update()
        self.upd_info.update_outdated()


class VMPropertyItem(QtGui.QTableWidgetItem):
    def __init__(self, vm, property_name, empty_function=(lambda x: False),
                 check_default=False):
        """
        Class used to represent Qube Manager table widget.
        :param vm: vm object
        :param property_name: name of the property the widget represents
        :param empty_function: a function that, when applied to values of
        vm.property_name, returns True when the property value should be
        represented as an empty string and False otherwise; by default this
        function always returns false (vm.property_name is represented by an
        empty string only when it actually is one)
        :param check_default: if True, the widget will prepend its text with
        "default" if the if the property is set to DEFAULT
        """
        super(VMPropertyItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.setTextAlignment(QtCore.Qt.AlignVCenter)
        self.vm = vm
        self.qid = vm.qid
        self.property_name = property_name
        self.name = vm.name
        self.empty_function = empty_function
        self.check_default = check_default
        self.update()

    def update(self):
        val = getattr(self.vm, self.property_name, None)
        if self.empty_function(val):
            text = ""
        elif val is None:
            text = "n/a"
        elif val is True:
            text = "Yes"
        else:
            text = str(val)

        if self.check_default and hasattr(self.vm, self.property_name) and \
                self.vm.property_is_default(self.property_name):
            text = 'default (' + text + ')'
        self.setText(text)

    def __lt__(self, other):
        if self.qid == 0:
            return True
        if other.qid == 0:
            return False
        if self.text() == other.text():
            return self.name < other.name
        return super(VMPropertyItem, self).__lt__(other)


class VmTemplateItem(VMPropertyItem):
    def __init__(self, vm):
        super(VmTemplateItem, self).__init__(vm, "template")

    def update(self):
        if getattr(self.vm, 'template', None) is not None:
            self.setText(self.vm.template.name)
        else:
            font = QtGui.QFont()
            font.setStyle(QtGui.QFont.StyleItalic)
            self.setFont(font)
            self.setTextColor(QtGui.QColor("gray"))

            self.setText(self.vm.klass)


class VmInternalItem(VMPropertyItem):
    def __init__(self, vm):
        super(VmInternalItem, self).__init__(vm, None)

    def update(self):
        internal = self.vm.features.get('internal', False)
        self.setText("Yes" if internal else "")


# features man qvm-features
class VmUpdateInfoWidget(QtGui.QWidget):
    class VmUpdateInfoItem(QtGui.QTableWidgetItem):
        def __init__(self, value, vm):
            super(VmUpdateInfoWidget.VmUpdateInfoItem, self).__init__()
            self.value = 0
            self.vm = vm
            self.qid = vm.qid
            self.name = vm.name
            self.set_value(value)

        def set_value(self, value):
            if value in ("outdated", "to-be-outdated"):
                self.value = 30
            elif value == "update":
                self.value = 20
            else:
                self.value = 0

        def __lt__(self, other):
            if self.qid == 0:
                return True
            if other.qid == 0:
                return False
            if self.value == other.value:
                return self.name < other.name
            return self.value < other.value

    def __init__(self, vm, show_text=True, parent=None):
        super(VmUpdateInfoWidget, self).__init__(parent)
        layout = QtGui.QHBoxLayout()
        self.show_text = show_text
        if self.show_text:
            self.label = QtGui.QLabel("")
            layout.addWidget(self.label, alignment=QtCore.Qt.AlignCenter)
        else:
            self.icon = QtGui.QLabel("")
            layout.addWidget(self.icon, alignment=QtCore.Qt.AlignCenter)
        self.setLayout(layout)

        self.vm = vm

        self.previous_outdated_state = None
        self.previous_update_recommended = None
        self.value = None
        self.table_item = VmUpdateInfoWidget.VmUpdateInfoItem(self.value, vm)
        self.update_outdated()

    def update_outdated(self):
        outdated_state = False
        is_disposable = getattr(self.vm, 'auto_cleanup', False)

        if not is_disposable and self.vm.is_running():
            if hasattr(self.vm, 'template') and self.vm.template.is_running():
                outdated_state = "to-be-outdated"

            if not outdated_state:
                for vol in self.vm.volumes.values():
                    if vol.is_outdated():
                        outdated_state = "outdated"
                        break

        if not is_disposable and \
                self.vm.klass in {'TemplateVM', 'StandaloneVM'} and \
                self.vm.features.get('updates-available', False):
            outdated_state = 'update'

        self.update_status_widget(outdated_state)

    def update_status_widget(self, state):
        if state == self.previous_outdated_state:
            return

        self.previous_outdated_state = state
        self.value = state
        self.table_item.set_value(state)
        if state == "update":
            label_text = "<font color=\"#CCCC00\">Check updates</font>"
            icon_path = ":/update-recommended.png"
            tooltip_text = self.tr("Updates pending!")
        elif state == "outdated":
            label_text = "<font color=\"red\">Qube outdated</font>"
            icon_path = ":/outdated.png"
            tooltip_text = self.tr(
                "The qube must be restarted for its filesystem to reflect the "
                "template's recent committed changes.")
        elif state == "to-be-outdated":
            label_text = "<font color=\"#800000\">Template running</font>"
            icon_path = ":/to-be-outdated.png"
            tooltip_text = self.tr(
                "The Template must be stopped before changes from its "
                "current session can be picked up by this qube.")
        else:
            icon_path = None

        if hasattr(self, 'icon'):
            self.icon.setVisible(False)
            self.layout().removeWidget(self.icon)
            del self.icon

        if self.show_text:
            self.label.setText(label_text)
        else:
            if icon_path is not None:
                self.icon = VmIconWidget(icon_path, True, 0.7)
                self.icon.setToolTip(tooltip_text)
                self.layout().addWidget(self.icon,\
                        alignment=QtCore.Qt.AlignCenter)
                self.icon.setVisible(True)


class VmSizeOnDiskItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmSizeOnDiskItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        self.vm = vm
        self.qid = vm.qid
        self.name = vm.name
        self.value = 0
        self.update()
        self.setTextAlignment(QtCore.Qt.AlignVCenter)

    def update(self):
        if self.vm.qid == 0:
            self.setText("n/a")
        else:
            self.value = 10
            self.value = round(self.vm.get_disk_utilization()/(1024*1024), 2)
            self.setText(str(self.value) + " MiB")

    def __lt__(self, other):
        if self.qid == 0:
            return True
        if other.qid == 0:
            return False
        if self.value == other.value:
            return self.name < other.name
        return self.value < other.value


class VmLastBackupItem(VMPropertyItem):
    def __init__(self, vm, property_name):
        super(VmLastBackupItem, self).__init__(vm, property_name)

    def update(self):
        backup_timestamp = getattr(self.vm, 'backup_timestamp', None)

        if backup_timestamp:
            self.setText(
                str(datetime.datetime.fromtimestamp(backup_timestamp)))
        else:
            self.setText("")
