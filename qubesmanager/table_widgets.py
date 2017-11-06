#!/usr/bin/python2
# -*- coding: utf8 -*-
# pylint: skip-file
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2014 Marek Marczykowski-Górecki <marmarek@invisiblethingslab.com>
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

import os

from PyQt4 import QtGui

from PyQt4.QtCore import QSize, Qt

from PyQt4.QtGui import QTableWidgetItem, QHBoxLayout, QIcon, QLabel, QWidget, \
    QSizePolicy, QSpacerItem, QFont, QColor, QProgressBar, QPainter, QPen
import time
from qubes.qubes import vm_files
import main

qubes_dom0_updates_stat_file = '/var/lib/qubes/updates/dom0-updates-available'
power_order = Qt.DescendingOrder
update_order = Qt.AscendingOrder


row_height = 30


class VmIconWidget (QWidget):
    def __init__(self, icon_path, enabled=True, size_multiplier=0.7,
                 tooltip  = None, parent=None, icon_sz = (32, 32)):
        super(VmIconWidget, self).__init__(parent)

        self.label_icon = QLabel()
        if icon_path[0] in ':/':
            icon = QIcon (icon_path)
        else:
            icon = QIcon.fromTheme(icon_path)
        icon_sz = QSize (row_height * size_multiplier, row_height * size_multiplier)
        icon_pixmap = icon.pixmap(icon_sz, QIcon.Disabled if not enabled else QIcon.Normal)
        self.label_icon.setPixmap (icon_pixmap)
        self.label_icon.setFixedSize (icon_sz)
        if tooltip != None:
            self.label_icon.setToolTip(tooltip)

        layout = QHBoxLayout()
        layout.addWidget(self.label_icon)
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)

    def setToolTip(self, tooltip):
        if tooltip is not None:
            self.label_icon.setToolTip(tooltip)
        else:
            self.label_icon.setToolTip('')

class VmTypeWidget(VmIconWidget):

    class VmTypeItem(QTableWidgetItem):
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
                return self.vm.qid < other.vm.qid
            else:
                return self.value < other.value

    def __init__(self, vm, parent=None):
        (icon_path, tooltip) = self.get_vm_icon(vm)
        super (VmTypeWidget, self).__init__(icon_path, True, 0.8, tooltip, parent)
        self.vm = vm
        self.tableItem = self.VmTypeItem(self.value, vm)

    def get_vm_icon(self, vm):
        if vm.qid == 0:
            self.value = 0
            return (":/dom0.png", "Dom0")
        elif vm.is_netvm() and not vm.is_proxyvm():
            self.value = 1
            return (":/netvm.png", "NetVM")
        elif vm.is_proxyvm():
            self.value = 2
            return (":/proxyvm.png", "ProxyVM")
        elif vm.is_appvm() and vm.template is None:
            self.value = 4
            return (":/standalonevm.png", "StandaloneVM")
        elif vm.is_template():
            self.value = 3
            return (":/templatevm.png", "TemplateVM")
        elif vm.is_appvm() or vm.is_disposablevm():
            self.value = 5 + vm.label.index
            return (":/appvm.png", "AppVM")


class VmLabelWidget(VmIconWidget):

    class VmLabelItem(QTableWidgetItem):
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
                return self.vm.qid < other.vm.qid
            else:
                return self.value < other.value

    def __init__(self, vm, parent=None):
        icon_path = self.get_vm_icon_path(vm)
        super (VmLabelWidget, self).__init__(icon_path, True, 0.8, None, parent)
        self.vm = vm
        self.tableItem = self.VmLabelItem(self.value, vm)

    def get_vm_icon_path(self, vm):
        if vm.qid == 0:
            self.value = 100
            return ":/off.png"
        else:
            self.value = vm.label.index
            return vm.label.icon



class VmNameItem (QTableWidgetItem):
    def __init__(self, vm):
        super(VmNameItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.setText(vm.name)
        self.setTextAlignment(Qt.AlignVCenter)
        self.qid = vm.qid

    def __lt__(self, other):
        if self.qid == 0:
            return True
        elif other.qid == 0:
            return False
        return super(VmNameItem, self).__lt__(other)


class VmStatusIcon(QLabel):
    def __init__(self, vm, parent=None):
        super (VmStatusIcon, self).__init__(parent)
        self.vm = vm
        self.set_on_icon()
        self.previous_power_state = vm.last_power_state

    def update(self):
        if self.previous_power_state != self.vm.last_power_state:
            self.set_on_icon()
            self.previous_power_state = self.vm.last_power_state

    def set_on_icon(self):
        if self.vm.last_power_state == "Running":
            icon = QIcon (":/on.png")
        elif self.vm.last_power_state in ["Paused", "Suspended"]:
            icon = QIcon (":/paused.png")
        elif self.vm.last_power_state in ["Transient", "Halting", "Dying"]:
            icon = QIcon (":/transient.png")
        else:
            icon = QIcon (":/off.png")

        icon_sz = QSize (row_height * 0.5, row_height *0.5)
        icon_pixmap = icon.pixmap(icon_sz)
        self.setPixmap (icon_pixmap)
        self.setFixedSize (icon_sz)



class VmInfoWidget (QWidget):

    class VmInfoItem (QTableWidgetItem):
        def __init__(self, upd_info_item, vm):
            super(VmInfoWidget.VmInfoItem, self).__init__()
            self.upd_info_item = upd_info_item
            self.vm = vm

        def __lt__(self, other):
            if self.vm.qid == 0:
                return True
            elif other.vm.qid == 0:
                return False

            self_val = self.upd_info_item.value
            other_val = other.upd_info_item.value
            if self.tableWidget().horizontalHeader().sortIndicatorOrder() == update_order:
                # the result will be sorted by upd, sorting order: Ascending
                self_val += 1 if self.vm.is_running() else 0
                other_val += 1 if other.vm.is_running() else 0
                if self_val == other_val:
                    return self.vm.qid < other.vm.qid
                else:
                    return self_val > other_val
            elif self.tableWidget().horizontalHeader().sortIndicatorOrder() == power_order:
                #the result will be sorted by power state, sorting order: Descending
                self_val = -(self_val/10 + 10*(1 if self.vm.is_running() else 0))
                other_val = -(other_val/10 + 10*(1 if other.vm.is_running() else 0))
                if self_val == other_val:
                    return self.vm.qid < other.vm.qid
                else:
                    return self_val > other_val
            else:
                #it would be strange if this happened
                return

    def __init__(self, vm, parent = None):
        super (VmInfoWidget, self).__init__(parent)
        self.vm = vm
        layout = QHBoxLayout ()

        self.on_icon = VmStatusIcon(vm)
        self.upd_info = VmUpdateInfoWidget(vm, show_text=False)
        self.error_icon = VmIconWidget(":/warning.png")
        self.blk_icon = VmIconWidget(":/mount.png")
        self.rec_icon = VmIconWidget(":/mic.png")

        layout.addWidget(self.on_icon)
        layout.addWidget(self.upd_info)
        layout.addWidget(self.error_icon)
        layout.addItem(QSpacerItem(0, 10, QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding))
        layout.addWidget(self.blk_icon)
        layout.addWidget(self.rec_icon)

        layout.setContentsMargins(5,0,5,0)
        self.setLayout(layout)

        self.rec_icon.setVisible(False)
        self.blk_icon.setVisible(False)
        self.error_icon.setVisible(False)

        self.tableItem = self.VmInfoItem(self.upd_info.tableItem, vm)

    def update_vm_state(self, vm, blk_visible, rec_visible=None):
        self.on_icon.update()
        self.upd_info.update_outdated(vm)
        if blk_visible != None:
            self.blk_icon.setVisible(blk_visible)
        if rec_visible != None:
            self.rec_icon.setVisible(rec_visible)
        self.error_icon.setToolTip(vm.qubes_manager_state[main.QMVmState
            .ErrorMsg])
        self.error_icon.setVisible(vm.qubes_manager_state[main.QMVmState
                                   .ErrorMsg] is not None)


class VmTemplateItem (QTableWidgetItem):
    def __init__(self, vm):
        super(VmTemplateItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.vm = vm

        if vm.template is not None:
            self.setText(vm.template.name)
        else:
            font = QFont()
            font.setStyle(QFont.StyleItalic)
            self.setFont(font)
            self.setTextColor(QColor("gray"))

            if vm.is_appvm(): # and vm.template is None
                self.setText("StandaloneVM")
            elif vm.is_template():
                self.setText("TemplateVM")
            elif vm.qid == 0:
                self.setText("AdminVM")
            elif vm.is_netvm():
                self.setText("NetVM")
            else:
                self.setText("---")

        self.setTextAlignment(Qt.AlignVCenter)

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.text() == other.text():
            return self.vm.qid < other.vm.qid
        else:
            return super(VmTemplateItem, self).__lt__(other)




class VmNetvmItem (QTableWidgetItem):
    def __init__(self, vm):
        super(VmNetvmItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.vm = vm

        if vm.is_netvm() and not vm.is_proxyvm():
            self.setText("n/a")
        elif vm.netvm is not None:
            self.setText(vm.netvm.name)
        else:
            self.setText("---")

        self.setTextAlignment(Qt.AlignVCenter)

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.text() == other.text():
            return self.vm.qid < other.vm.qid
        else:
            return super(VmNetvmItem, self).__lt__(other)

class VmInternalItem(QTableWidgetItem):
    def __init__(self, vm):
        super(VmInternalItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

        self.vm = vm
        self.internal = self.vm.internal

        if self.internal:
            self.setText("Yes")
        else:
            self.setText("")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        return super(VmInternalItem, self).__lt__(other)


class VmUsageBarWidget (QWidget):

    class VmUsageBarItem (QTableWidgetItem):
        def __init__(self, value, vm):
            super(VmUsageBarWidget.VmUsageBarItem, self).__init__()
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
                return self.vm.qid < other.vm.qid
            else:
                return int(self.value) < int(other.value)

    def __init__(self, min, max, format, update_func, vm, load, hue=210, parent = None):
        super (VmUsageBarWidget, self).__init__(parent)


        self.min = min
        self.max = max
        self.update_func = update_func
        self.value = min

        self.widget = QProgressBar()
        self.widget.setMinimum(min)
        self.widget.setMaximum(max)
        self.widget.setFormat(format)

        self.widget.setStyleSheet(
                                    "QProgressBar:horizontal{" +\
                                        "border: 1px solid hsv({0}, 100, 250);".format(hue) +\
                                        "border-radius: 4px;\
                                        background: transparent;\
                                        text-align: center;\
                                    }\
                                    QProgressBar::chunk:horizontal {\
                                        background: qlineargradient(x1: 1, y1: 0.5, x2: 1, y2: 0.5, " +\
                                        "stop: 0 hsv({0}, 170, 207),".format(hue) +
                                        " stop: 1 white); \
                                    }"
            )

        layout = QHBoxLayout()
        layout.addWidget(self.widget)

        self.setLayout(layout)
        self.tableItem = self.VmUsageBarItem(min, vm)

        self.update_load(vm, load)



    def update_load(self, vm, load):
        self.value = self.update_func(vm, load)
        self.widget.setValue(self.value)
        self.tableItem.set_value(self.value)

class ChartWidget (QWidget):

    class ChartItem (QTableWidgetItem):
        def __init__(self, value, vm):
            super(ChartWidget.ChartItem, self).__init__()
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
                return self.vm.qid < other.vm.qid
            else:
                return self.value < other.value

    def __init__(self, vm, update_func, hue, load = 0, parent = None):
        super (ChartWidget, self).__init__(parent)
        self.update_func = update_func
        self.hue = hue
        if hue < 0 or hue > 255:
            self.hue = 255
        self.load = load
        assert self.load >= 0 and self.load <= 100, "load = {0}".format(self.load)
        self.load_history = [self.load]
        self.tableItem = ChartWidget.ChartItem(self.load, vm)

    def update_load (self, vm, load):
        self.load = self.update_func(vm, load)

        assert self.load >= 0, "load = {0}".format(self.load)
        # assert self.load >= 0 and self.load <= 100, "load = {0}".format(self.load)
        if self.load > 100:
            # FIXME: This is an ugly workaround for cpu_load:/
            self.load = 100

        self.load_history.append (self.load)
        self.tableItem.set_value(self.load)
        self.repaint()

    def paintEvent (self, Event = None):
        p = QPainter (self)
        dx = 4

        W = self.width()
        H = self.height() - 5
        N = len(self.load_history)
        if N > W/dx:
            tail = N - W/dx
            N = W/dx
            self.load_history = self.load_history[tail:]

        assert len(self.load_history) == N

        for i in range (0, N-1):
            val = self.load_history[N- i - 1]
            sat = 70 + val*(255-70)/100
            color = QColor.fromHsv (self.hue, sat, 255)
            pen = QPen (color)
            pen.setWidth(dx-1)
            p.setPen(pen)
            if val > 0:
                p.drawLine (W - i*dx - dx, H , W - i*dx - dx, H - (H - 5) * val/100)



class VmUpdateInfoWidget(QWidget):

    class VmUpdateInfoItem (QTableWidgetItem):
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
                return self.vm.qid < other.vm.qid
            else:
                return self.value < other.value

    def __init__(self, vm, show_text=True, parent = None):
        super (VmUpdateInfoWidget, self).__init__(parent)
        layout = QHBoxLayout ()
        self.show_text = show_text
        if self.show_text:
            self.label=QLabel("")
            layout.addWidget(self.label, alignment=Qt.AlignCenter)
        else:
            self.icon =  QLabel("")
            layout.addWidget(self.icon, alignment=Qt.AlignCenter)
        self.setLayout(layout)

        self.previous_outdated_state = None
        self.previous_update_recommended = None
        self.value = None
        self.tableItem = VmUpdateInfoWidget.VmUpdateInfoItem(self.value, vm)

    def update_outdated(self, vm):
        if vm.type == "HVM":
            return

        if vm.is_outdated():
            outdated_state = "outdated"
        # During TemplateVM shutdown, there's an interval of a few seconds
        # during which vm.template.is_running() returns false but
        # vm.is_outdated() does not yet return true, so the icon disappears.
        # This looks goofy, but we've decided not to fix it at this time
        # (2015-02-09).
        elif vm.template and vm.template.is_running():
            outdated_state = "to-be-outdated"
        else:
            outdated_state = None

        if outdated_state != self.previous_outdated_state:
            self.update_status_widget(outdated_state)

        self.previous_outdated_state = outdated_state

        if not vm.is_updateable():
            return

        if vm.qid == 0:
            update_recommended = self.previous_update_recommended
            if os.path.exists(qubes_dom0_updates_stat_file):
                update_recommended = True
            else:
                update_recommended = False

        else:
            update_recommended = self.previous_update_recommended
            stat_file_path = vm.dir_path + '/' + vm_files["updates_stat_file"]
            if not os.path.exists(stat_file_path):
                update_recommended = False
            else:
                if (not hasattr(vm, "updates_stat_file_read_time")) or vm.updates_stat_file_read_time <= os.path.getmtime(stat_file_path):

                        stat_file = open(stat_file_path, "r")
                        updates = stat_file.read().strip()
                        stat_file.close()
                        if updates.isdigit():
                            updates = int(updates)
                        else:
                            updates = 0

                        if updates == 0:
                            update_recommended = False
                        else:
                            update_recommended = True
                        vm.updates_stat_file_read_time = time.time()

        if update_recommended and not self.previous_update_recommended:
            self.update_status_widget("update")
        elif self.previous_update_recommended and not update_recommended:
            self.update_status_widget(None)

        self.previous_update_recommended = update_recommended


    def update_status_widget(self, state):
        self.value = state
        self.tableItem.set_value(state)
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
        elif state is None:
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
                self.icon = QLabel(label_text)
            self.layout().addWidget(self.icon, alignment=Qt.AlignCenter)


class VmSizeOnDiskItem (QTableWidgetItem):
    def __init__(self, vm):
        super(VmSizeOnDiskItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

        self.vm = vm
        self.value = 0
        self.update()
        self.setTextAlignment(Qt.AlignVCenter)

    def update(self):
        if self.vm.qid == 0:
            self.setText("n/a")
        else:
            self.value = self.vm.get_disk_utilization()/(1024*1024)
            self.setText( str(self.value) + " MiB")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.value == other.value:
            return self.vm.qid < other.vm.qid
        else:
            return self.value < other.value

class VmIPItem(QTableWidgetItem):
    def __init__(self, vm):
        super(VmIPItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

        self.vm = vm
        self.ip = self.vm.ip
        if self.ip:
            self.setText(self.ip)
        else:
            self.setText("n/a")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        return super(VmIPItem, self).__lt__(other)

class VmIncludeInBackupsItem(QTableWidgetItem):
    def __init__(self, vm):
        super(VmIncludeInBackupsItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

        self.vm = vm
        if self.vm.include_in_backups:
            self.setText("Yes")
        else:
            self.setText("")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.vm.include_in_backups == other.vm.include_in_backups:
            return self.vm.qid < other.vm.qid
        else:
            return self.vm.include_in_backups < other.vm.include_in_backups

class VmLastBackupItem(QTableWidgetItem):
    def __init__(self, vm):
        super(VmLastBackupItem, self).__init__()
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

        self.vm = vm
        if self.vm.backup_timestamp:
            self.setText(str(self.vm.backup_timestamp.date()))
        else:
            self.setText("")

    def __lt__(self, other):
        if self.vm.qid == 0:
            return True
        elif other.vm.qid == 0:
            return False
        elif self.vm.backup_timestamp == other.vm.backup_timestamp:
            return self.vm.qid < other.vm.qid
        elif not self.vm.backup_timestamp:
            return False
        elif not other.vm.backup_timestamp:
            return True
        else:
            return self.vm.backup_timestamp < other.vm.backup_timestamp
