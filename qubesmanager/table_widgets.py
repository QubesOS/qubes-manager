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

from PyQt4 import QtGui  # pylint: disable=import-error
from PyQt4 import QtCore  # pylint: disable=import-error
import datetime
# pylint: disable=too-few-public-methods

power_order = QtCore.Qt.DescendingOrder
update_order = QtCore.Qt.AscendingOrder


row_height = 30


class VmIconWidget(QtGui.QWidget):
    def __init__(self, icon_path, enabled=True, size_multiplier=0.7,
                 tooltip=None, parent=None, icon_sz=(32, 32)):
        super(VmIconWidget, self).__init__(parent)

        self.label_icon = QtGui.QLabel()
        if icon_path[0] in ':/':
            icon = QtGui.QIcon(icon_path)
        else:
            icon = QtGui.QIcon.fromTheme(icon_path)
        icon_sz = QtCore.QSize(row_height * size_multiplier,
                               row_height * size_multiplier)
        icon_pixmap = icon.pixmap(
            icon_sz,
            QtGui.QIcon.Disabled if not enabled else QtGui.QIcon.Normal)
        self.label_icon.setPixmap(icon_pixmap)
        self.label_icon.setFixedSize(icon_sz)
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


class VmTypeWidget(VmIconWidget):
    class VmTypeItem(QtGui.QTableWidgetItem):
        def __init__(self, value, vm):
            super(VmTypeWidget.VmTypeItem, self).__init__()
            self.value = value
            self.vm = vm

        def set_value(self, value):
            self.value = value

        def __lt__(self, other):
            if self.vm.qid == 0:
                return True
            elif other.vm.qid == 0:
                return False
            elif self.value == other.value:
                return self.vm.name < other.vm.name
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
            self.vm = vm

        def set_value(self, value):
            self.value = value

        def __lt__(self, other):
            if self.vm.qid == 0:
                return True
            elif other.vm.qid == 0:
                return False
            elif self.value == other.value:
                return self.vm.name < other.vm.name
            return self.value < other.value

    def __init__(self, vm, parent=None):
        icon_path = self.get_vm_icon_path(vm)
        super(VmLabelWidget, self).__init__(icon_path, True, 0.8, None, parent)
        self.vm = vm
        self.table_item = self.VmLabelItem(self.value, vm)
        self.value = None

    def get_vm_icon_path(self, vm):
        self.value = vm.label.index
        return vm.label.icon


class VmNameItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmNameItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.setText(vm.name)
        self.setTextAlignment(QtCore.Qt.AlignVCenter)
        self.qid = vm.qid

    def __lt__(self, other):
        if self.qid == 0:
            return True
        elif other.qid == 0:
            return False
        return super(VmNameItem, self).__lt__(other)


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
        elif self.vm.get_power_state() in ["Paused", "Suspended"]:
            icon = QtGui.QIcon(":/paused.png")
        elif self.vm.get_power_state() in ["Transient", "Halting", "Dying"]:
            icon = QtGui.QIcon(":/transient.png")
        else:
            icon = QtGui.QIcon(":/off.png")

        icon_sz = QtCore.QSize(row_height * 0.5, row_height * 0.5)
        icon_pixmap = icon.pixmap(icon_sz)
        self.setPixmap(icon_pixmap)
        self.setFixedSize(icon_sz)


class VmInfoWidget(QtGui.QWidget):
    class VmInfoItem(QtGui.QTableWidgetItem):
        def __init__(self, upd_info_item, vm):
            super(VmInfoWidget.VmInfoItem, self).__init__()
            self.upd_info_item = upd_info_item
            self.vm = vm

        def __lt__(self, other):
            # pylint: disable=too-many-return-statements
            if self.vm.qid == 0:
                return True
            elif other.vm.qid == 0:
                return False

            self_val = self.upd_info_item.value
            other_val = other.upd_info_item.value

            if self.tableWidget().\
                    horizontalHeader().sortIndicatorOrder() == update_order:
                # the result will be sorted by upd, sorting order: Ascending
                self_val += 1 if self.vm.is_running() else 0
                other_val += 1 if other.vm.is_running() else 0
                if self_val == other_val:
                    return self.vm.name < other.vm.name
                return self_val > other_val
            elif self.tableWidget().\
                    horizontalHeader().sortIndicatorOrder() == power_order:
                # the result will be sorted by power state,
                # sorting order: Descending
                self_val = -(self_val/10 +
                             10*(1 if self.vm.is_running() else 0))
                other_val = -(other_val/10 +
                              10*(1 if other.vm.is_running() else 0))
                if self_val == other_val:
                    return self.vm.name < other.vm.name
                return self_val > other_val
            else:
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

        self.table_item = self.VmInfoItem(self.upd_info.table_item, vm)

    def update_vm_state(self, vm):
        self.on_icon.update()
        self.upd_info.update_outdated(vm)


class VmTemplateItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmTemplateItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.vm = vm

        if getattr(vm, 'template', None) is not None:
            self.setText(vm.template.name)
        else:
            font = QtGui.QFont()
            font.setStyle(QtGui.QFont.StyleItalic)
            self.setFont(font)
            self.setTextColor(QtGui.QColor("gray"))

            self.setText(vm.klass)

        self.setTextAlignment(QtCore.Qt.AlignVCenter)

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.text() == other.text():
            return self.vm.name < other.vm.name
        return super(VmTemplateItem, self).__lt__(other)


class VmNetvmItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmNetvmItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        self.vm = vm

        if getattr(vm, 'netvm', None) is None:
            self.setText("n/a")
        else:
            self.setText(vm.netvm.name)

        self.setTextAlignment(QtCore.Qt.AlignVCenter)

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.text() == other.text():
            return self.vm.name < other.vm.name
        return super(VmNetvmItem, self).__lt__(other)


class VmInternalItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmInternalItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        self.vm = vm
        self.internal = vm.features.get('internal', False)

        self.setText("Yes" if self.internal else "")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        return super(VmInternalItem, self).__lt__(other)


# features man qvm-features
class VmUpdateInfoWidget(QtGui.QWidget):

    class VmUpdateInfoItem(QtGui.QTableWidgetItem):
        def __init__(self, value, vm):
            super(VmUpdateInfoWidget.VmUpdateInfoItem, self).__init__()
            self.value = 0
            self.vm = vm
            self.set_value(value)

        def set_value(self, value):
            if value in ("outdated", "to-be-outdated"):
                self.value = 30
            elif value == "update":
                self.value = 20
            else:
                self.value = 0

        def __lt__(self, other):
            if self.vm.qid == 0:
                return True
            elif other.vm.qid == 0:
                return False
            elif self.value == other.value:
                return self.vm.name < other.vm.name
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

        self.previous_outdated_state = None
        self.previous_update_recommended = None
        self.value = None
        self.table_item = VmUpdateInfoWidget.VmUpdateInfoItem(self.value, vm)

    def update_outdated(self, vm):

        outdated_state = False

        try:
            for vol in vm.volumes:
                if vol.is_outdated():
                    outdated_state = "outdated"
                    break
        except AttributeError:
            pass

        if not outdated_state and getattr(vm, 'template', None)\
                and vm.template.is_running():
            outdated_state = "to-be-outdated"
        if outdated_state != self.previous_outdated_state:
            self.update_status_widget(outdated_state)
        self.previous_outdated_state = outdated_state

        updates_available = vm.features.get('updates-available', False)
        if updates_available != self.previous_update_recommended:
            self.update_status_widget("update" if updates_available else None)
        self.previous_update_recommended = updates_available

    def update_status_widget(self, state):
        self.value = state
        self.table_item.set_value(state)
        if state == "update":
            label_text = "<font color=\"#CCCC00\">Check updates</font>"
            icon_path = ":/update-recommended.png"
            tooltip_text = self.tr("Updates pending!")
        elif state == "outdated":
            label_text = "<font color=\"red\">VM outdated</font>"
            icon_path = ":/outdated.png"
            tooltip_text = self.tr(
                "The VM must be restarted for its filesystem to reflect the "
                "template's recent committed changes.")
        elif state == "to-be-outdated":
            label_text = "<font color=\"#800000\">TemplateVM running</font>"
            icon_path = ":/to-be-outdated.png"
            tooltip_text = self.tr(
                "The TemplateVM must be stopped before changes from its "
                "current session can be picked up by this VM.")
        else:
            label_text = ""
            icon_path = None
            tooltip_text = None

        if self.show_text:
            self.label.setText(label_text)
        else:
            self.layout().removeWidget(self.icon)
            self.icon.deleteLater()
            if icon_path is not None:
                self.icon = VmIconWidget(icon_path, True, 0.7)
                self.icon.setToolTip(tooltip_text)
            else:
                self.icon = QtGui.QLabel(label_text)
            self.layout().addWidget(self.icon, alignment=QtCore.Qt.AlignCenter)


class VmSizeOnDiskItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmSizeOnDiskItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        self.vm = vm
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
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.value == other.value:
            return self.vm.name < other.vm.name
        return self.value < other.value


class VmIPItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmIPItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        self.vm = vm
        self.ip = getattr(self.vm, 'ip', None)
        self.setText(self.ip if self.ip is not None else 'n/a')

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        return super(VmIPItem, self).__lt__(other)


class VmIncludeInBackupsItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmIncludeInBackupsItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        self.vm = vm
        if getattr(self.vm, 'include_in_backups', None):
            self.setText("Yes")
        else:
            self.setText("")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.vm.include_in_backups == other.vm.include_in_backups:
            return self.vm.name < other.vm.name
        return self.vm.include_in_backups < other.vm.include_in_backups


class VmLastBackupItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(VmLastBackupItem, self).__init__()
        self.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        self.vm = vm
        self.backup_timestamp = getattr(self.vm, 'backup_timestamp', None)

        if self.backup_timestamp:
            self.setText(
                str(datetime.datetime.fromtimestamp(self.backup_timestamp)))
        else:
            self.setText("")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.backup_timestamp == other.backup_timestamp:
            return self.vm.name < other.vm.name
        elif not self.backup_timestamp:
            return False
        elif not other.backup_timestamp:
            return True
        return self.backup_timestamp < other.backup_timestamp
