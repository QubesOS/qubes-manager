#!/usr/bin/python2.6
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2010  Joanna Rutkowska <joanna@invisiblethingslab.com>
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
from qubes.qubes import QubesException
from qubes.qubes import qubes_store_filename
from qubes.qubes import QubesVmLabels
from qubes.qubes import dry_run
from qubes.qubes import qubes_guid_path
from qubes.qubes import QubesDaemonPidfile
from qubes.qubes import QubesHost
from qubes import qubesutils

import qubesmanager.resources_rc
import ui_newappvmdlg
from ui_mainwindow import *
from settings import VMSettingsWindow
from restore import RestoreVMsWindow
from backup import BackupVMsWindow
from global_settings import GlobalSettingsWindow
from thread_monitor import *

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time
from datetime import datetime,timedelta

updates_stat_file = 'last_update.stat'
qubes_guid_path = '/usr/bin/qubes_guid'

update_suggestion_interval = 14 # 14 days

power_order = Qt.DescendingOrder
update_order = Qt.AscendingOrder


class QubesConfigFileWatcher(ProcessEvent):
    def __init__ (self, update_func):
        self.update_func = update_func

    def process_IN_MODIFY (self, event):
        self.update_func()


class VmIconWidget (QWidget):
    def __init__(self, icon_path, enabled=True, size_multiplier=0.7, tooltip = None, parent=None):
        super(VmIconWidget, self).__init__(parent)

        label_icon = QLabel()
        icon = QIcon (icon_path)
        icon_sz = QSize (VmManagerWindow.row_height * size_multiplier, VmManagerWindow.row_height * size_multiplier)
        icon_pixmap = icon.pixmap(icon_sz, QIcon.Disabled if not enabled else QIcon.Normal)
        label_icon.setPixmap (icon_pixmap)
        label_icon.setFixedSize (icon_sz)
        if tooltip != None:
            label_icon.setToolTip(tooltip)
        
        layout = QHBoxLayout()
        layout.addWidget(label_icon)
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)


class VmTypeWidget(VmIconWidget):
    
    class VmTypeItem(QTableWidgetItem):
        def __init__(self, value):
            super(VmTypeWidget.VmTypeItem, self).__init__()
            self.value = value

        def set_value(self, value):
            self.value = value            
        
        def __lt__(self, other):
            return self.value < other.value


    def __init__(self, vm, parent=None):
        (icon_path, tooltip) = self.get_vm_icon(vm)
        super (VmTypeWidget, self).__init__(icon_path, True, 0.9, tooltip, parent)
        self.vm = vm
        self.tableItem = self.VmTypeItem(self.value)

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
        elif vm.is_template():
            self.value = 3
            return (":/templatevm.png", "TemplateVM")
        elif vm.is_appvm() and vm.template is None:
            self.value = 4
            return (":/standalonevm.png", "StandaloneVM")
        elif vm.type == "HVM":
            self.value = 5
            return (":/hvm.png", "HVM")
        elif vm.is_appvm() or vm.is_disposablevm():
            self.value = 5 + vm.label.index
            return (":/off.png", "AppVM")


class VmLabelWidget(VmIconWidget):
    
    class VmLabelItem(QTableWidgetItem):
        def __init__(self, value):
            super(VmLabelWidget.VmLabelItem, self).__init__()
            self.value = value

        def set_value(self, value):
            self.value = value            
        
        def __lt__(self, other):
            return self.value < other.value


    def __init__(self, vm, parent=None):
        icon_path = self.get_vm_icon_path(vm)
        super (VmLabelWidget, self).__init__(icon_path, True, 0.8, None, parent)
        self.vm = vm
        self.tableItem = self.VmLabelItem(self.value)

    def get_vm_icon_path(self, vm):
        self.value = vm.label.index
        return vm.label.icon_path

        

class VmNameItem (QTableWidgetItem):
    def __init__(self, vm):
        super(VmNameItem, self).__init__()

        self.setText(vm.name)
        self.setTextAlignment(Qt.AlignVCenter)
        self.qid = vm.qid
        

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
        elif self.vm.last_power_state in ["Transient", "Halting", "Dying"]:
            icon = QIcon (":/transient.png")
        else:
            icon = QIcon (":/off.png")

        icon_sz = QSize (VmManagerWindow.row_height * 0.5, VmManagerWindow.row_height *0.5)
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
            self_val = self.upd_info_item.value
            other_val = other.upd_info_item.value
            if self.tableWidget().horizontalHeader().sortIndicatorOrder() == update_order:
                # the result will be sorted by upd, sorting order: Ascending
                self_val += 1 if self.vm.is_running() else 0
                other_val += 1 if other.vm.is_running() else 0
                return (self_val) > (other_val)
            elif self.tableWidget().horizontalHeader().sortIndicatorOrder() == power_order:
                #the result will be sorted by power state, sorting order: Descending
                self_val = -(self_val/10 + 10*(1 if self.vm.is_running() else 0))
                other_val = -(other_val/10 + 10*(1 if other.vm.is_running() else 0))
                return (self_val) > (other_val)
            else:
                #it would be strange if this happened
                return 

    def __init__(self, vm, parent = None):
        super (VmInfoWidget, self).__init__(parent)
        self.vm = vm
        layout = QHBoxLayout ()

        self.on_icon = VmStatusIcon(vm)
        self.upd_info = VmUpdateInfoWidget(vm, show_text=False)
        self.blk_icon = VmIconWidget(":/mount.png")

        layout.addWidget(self.on_icon)
        layout.addWidget(self.upd_info)
        layout.addItem(QSpacerItem(0, 10, QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding))
        layout.addWidget(self.blk_icon)

        layout.setContentsMargins(5,0,5,0)
        self.setLayout(layout)

        self.blk_icon.setVisible(False)

        self.tableItem = self.VmInfoItem(self.upd_info.tableItem, vm)

    def update_vm_state(self, vm, blk_visible):
        self.on_icon.update()
        self.upd_info.update_outdated(vm)
        if blk_visible != None:
            self.blk_icon.setVisible(blk_visible)


class VmTemplateItem (QTableWidgetItem):
    def __init__(self, vm):
        super(VmTemplateItem, self).__init__()
        
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

        self.setTextAlignment(Qt.AlignCenter)


class VmNetvmItem (QTableWidgetItem):
    def __init__(self, vm):
        super(VmNetvmItem, self).__init__()

        if vm.is_netvm() and not vm.is_proxyvm():
            self.setText("n/a")
        elif vm.netvm is not None:
            self.setText(vm.netvm.name)
        else:
            self.setText("---")

        self.setTextAlignment(Qt.AlignCenter)


class VmUsageBarWidget (QWidget):

    class VmUsageBarItem (QTableWidgetItem):
        def __init__(self, value):
            super(VmUsageBarWidget.VmUsageBarItem, self).__init__()
            self.value = value

        def set_value(self, value):
            self.value = value            
        
        def __lt__(self, other):
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
        self.widget.setFormat(format);

        self.widget.setStyleSheet(
                                    "QProgressBar:horizontal{" +\
                                        "border: 1px solid hsv({0}, 100, 250);".format(hue) +\
                                        "border-radius: 4px;\
                                        background: white;\
                                        text-align: center;\
                                    }\
                                    QProgressBar::chunk:horizontal {\
                                        background: qlineargradient(x1: 0, y1: 0.5, x2: 1, y2: 0.5, " +\
                                        "stop: 0 hsv({0}, 170, 207),".format(hue) +
                                        " stop: 1 white); \
                                    }"
            )

        layout = QHBoxLayout()
        layout.addWidget(self.widget)

        self.setLayout(layout)
        self.tableItem = self.VmUsageBarItem(min)

        self.update_load(vm, load)

    
        
    def update_load(self, vm, load):
        self.value = self.update_func(vm, load)
        self.widget.setValue(self.value)
        self.tableItem.set_value(self.value)

class ChartWidget (QWidget):
    
    class ChartItem (QTableWidgetItem):
        def __init__(self, value):
            super(ChartWidget.ChartItem, self).__init__()
            self.value = value

        def set_value(self, value):
            self.value = value            
        
        def __lt__(self, other):
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
        self.tableItem = ChartWidget.ChartItem(self.load)

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
        def __init__(self, value):
            super(VmUpdateInfoWidget.VmUpdateInfoItem, self).__init__()
            self.value = 0
            self.set_value(value)

        def set_value(self, value):
            if value == "outdated":
                self.value = 30
            elif value == "update":
                self.value = 20 
            elif value == "ok":
                self.value = 10
            else:
                self.value = 0
 
        def __lt__(self, other):
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

        self.previous_outdated = False
        self.previous_update_recommended = None
        self.value = None
        self.tableItem = VmUpdateInfoWidget.VmUpdateInfoItem(self.value)

    def update_outdated(self, vm):
        if vm.type == "HVM":
            return

        outdated = vm.is_outdated()
        if outdated and not self.previous_outdated:
            self.update_status_widget("outdated")
                 
        self.previous_outdated = outdated

        if vm.is_updateable():
            update_recommended = self.previous_update_recommended
            stat_file = vm.dir_path + '/' + updates_stat_file
            if not os.path.exists(stat_file) or \
                time.time() - os.path.getmtime(stat_file) > \
                update_suggestion_interval * 24 * 3600:
                    update_recommended = True
            else:
                update_recommended = False
                if not self.show_text and self.previous_update_recommended != False:
                    self.update_status_widget("ok")
        
            if update_recommended and not self.previous_update_recommended:
                self.update_status_widget("update")
            self.previous_update_recommended = update_recommended

    def update_status_widget(self, state):
        self.value = state
        self.tableItem.set_value(state)
        if state == "ok":
            label_text = ""
            icon_path = ":/flag-green.png"
            tooltip_text = "VM up to date"
        elif state == "update":
            label_text = "<font color=\"#CCCC00\">Check updates</font>"
            icon_path = ":/flag-yellow.png"
            tooltip_text = "Update recommended"
        elif state == "outdated":
            label_text = "<font color=\"red\">VM outdated</font>"
            icon_path = ":/flag-red.png"
            tooltip_text = "VM outdated"

        if self.show_text:
            self.label.setText(label_text)
        else:    
            self.layout().removeWidget(self.icon)
            self.icon.deleteLater()
            self.icon = VmIconWidget(icon_path, True, 0.7)
            self.icon.setToolTip(tooltip_text)
            self.layout().addWidget(self.icon, alignment=Qt.AlignCenter)



class VmRowInTable(object):
    cpu_graph_hue = 210
    mem_graph_hue = 120

    def __init__(self, vm, row_no, table, block_manager):
        self.vm = vm
        self.row_no = row_no

        table.setRowHeight (row_no, VmManagerWindow.row_height)

        self.type_widget = VmTypeWidget(vm)
        table.setCellWidget(row_no, VmManagerWindow.columns_indices['Type'], self.type_widget)
        table.setItem(row_no, VmManagerWindow.columns_indices['Type'], self.type_widget.tableItem)

        self.label_widget = VmLabelWidget(vm)
        table.setCellWidget(row_no, VmManagerWindow.columns_indices['Label'], self.label_widget)
        table.setItem(row_no, VmManagerWindow.columns_indices['Label'], self.label_widget.tableItem)

        self.name_widget = VmNameItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices['Name'], self.name_widget)

        self.info_widget = VmInfoWidget(vm)
        table.setCellWidget(row_no, VmManagerWindow.columns_indices['State'], self.info_widget) 
        table.setItem(row_no, VmManagerWindow.columns_indices['State'], self.info_widget.tableItem)

        self.template_widget = VmTemplateItem(vm)
        table.setItem(row_no,  VmManagerWindow.columns_indices['Template'], self.template_widget)
                
        self.netvm_widget = VmNetvmItem(vm)
        table.setItem(row_no,  VmManagerWindow.columns_indices['NetVM'], self.netvm_widget)

        self.cpu_usage_widget = VmUsageBarWidget(0, 100, "%v %", 
                            lambda vm, val: val if vm.last_running else 0, vm, 0, self.cpu_graph_hue)
        table.setCellWidget(row_no,  VmManagerWindow.columns_indices['CPU'], self.cpu_usage_widget)
        table.setItem(row_no,  VmManagerWindow.columns_indices['CPU'], self.cpu_usage_widget.tableItem)

        self.load_widget = ChartWidget(vm, lambda vm, val: val if vm.last_running else 0, self.cpu_graph_hue, 0 )
        table.setCellWidget(row_no,  VmManagerWindow.columns_indices['CPU Graph'], self.load_widget)
        table.setItem(row_no,  VmManagerWindow.columns_indices['CPU Graph'], self.load_widget.tableItem)

        self.mem_usage_widget = VmUsageBarWidget(0, qubes_host.memory_total/1024, "%v MB", 
                            lambda vm, val: vm.get_mem()/1024 if vm.last_running else 0, vm, 0, self.mem_graph_hue)
        table.setCellWidget(row_no,  VmManagerWindow.columns_indices['MEM'], self.mem_usage_widget)
        table.setItem(row_no,  VmManagerWindow.columns_indices['MEM'], self.mem_usage_widget.tableItem)

        self.mem_widget = ChartWidget(vm, lambda vm, val: vm.get_mem()*100/qubes_host.memory_total if vm.last_running else 0, self.mem_graph_hue, 0)
        table.setCellWidget(row_no,  VmManagerWindow.columns_indices['MEM Graph'], self.mem_widget)
        table.setItem(row_no,  VmManagerWindow.columns_indices['MEM Graph'], self.mem_widget.tableItem)
 

    def update(self, counter, blk_visible = None, cpu_load = None):
        self.info_widget.update_vm_state(self.vm, blk_visible)
        if cpu_load is not None:
            self.cpu_usage_widget.update_load(self.vm, cpu_load)
            self.mem_usage_widget.update_load(self.vm, None)
            self.load_widget.update_load(self.vm, cpu_load)
            self.mem_widget.update_load(self.vm, None)

class NewAppVmDlg (QDialog, ui_newappvmdlg.Ui_NewAppVMDlg):
    def __init__(self, parent = None):
        super (NewAppVmDlg, self).__init__(parent)
        self.setupUi(self)

vm_shutdown_timeout = 15000 # in msec

class VmShutdownMonitor(QObject):
    def __init__(self, vm):
        self.vm = vm

    def check_if_vm_has_shutdown(self):
        vm = self.vm
        vm_start_time = vm.get_start_time()
        if not vm.is_running() or (vm_start_time and vm_start_time >= datetime.utcnow() - timedelta(0,vm_shutdown_timeout/1000)):
            if vm.is_template():
                trayIcon.showMessage ("Qubes Manager", "You have just modified template '{0}'. You should now restart all the VMs based on it, so they could see the changes.".format(vm.name), msecs=8000)
            return

        reply = QMessageBox.question(None, "VM Shutdown",
                                     "The VM <b>'{0}'</b> hasn't shutdown within the last {1} seconds, do you want to kill it?<br>".format(vm.name, vm_shutdown_timeout/1000),
                                     "Kill it!", "Wait another {0} seconds...".format(vm_shutdown_timeout/1000))

        if reply == 0:
            vm.force_shutdown()
        else:
            QTimer.singleShot (vm_shutdown_timeout, self.check_if_vm_has_shutdown)


class VmManagerWindow(Ui_VmManagerWindow, QMainWindow):
    row_height = 30
    column_width = 200
    min_visible_rows = 10
    update_interval = 1000 # in msec
    show_inactive_vms = True
    columns_indices = { "Type": 0,
                        "Label": 1,
                        "Name": 2,
                        "State": 3,
                        "Template": 4,
                        "NetVM": 5,
                        "CPU": 6,
                        "CPU Graph": 7,
                        "MEM": 8,
                        "MEM Graph": 9,}



    def __init__(self, parent=None):
        super(VmManagerWindow, self).__init__()
        self.setupUi(self)
        self.toolbar = self.toolBar
        
        self.qubes_watch = qubesutils.QubesWatch()
        self.qvm_collection = QubesVmCollection()
        self.blk_manager = QubesBlockDevicesManager(self.qvm_collection)
        self.qubes_watch.setup_block_watch(self.blk_manager.block_devs_event)
        self.blk_watch_thread = threading.Thread(target=self.qubes_watch.watch_loop)
        self.blk_watch_thread.daemon = True
        self.blk_watch_thread.start()

        self.connect(self.table, SIGNAL("itemSelectionChanged()"), self.table_selection_changed)
        
        self.table.setColumnWidth(0, self.column_width)
        self.setSizeIncrement(QtCore.QSize(200, 30))
        self.centralwidget.setSizeIncrement(QtCore.QSize(200, 30))
        self.table.setSizeIncrement(QtCore.QSize(200, 30))

        self.sort_by_mem = None
        self.sort_by_cpu = None
        self.sort_by_state = None

        self.screen_number = -1
        self.screen_changed = False

        self.frame_width = 0
        self.frame_height = 0

        self.fill_table()
        self.move(self.x(), 0)
 
        self.table.setColumnHidden( self.columns_indices["NetVM"], True)
        self.actionNetVM.setChecked(False)
        self.table.setColumnHidden( self.columns_indices["CPU Graph"], True)
        self.actionCPU_Graph.setChecked(False)
        self.table.setColumnHidden( self.columns_indices["MEM Graph"], True)
        self.actionMEM_Graph.setChecked(False)
        self.table.setColumnWidth(self.columns_indices["State"], 80)
        self.table.setColumnWidth(self.columns_indices["Name"], 150)
        self.table.setColumnWidth(self.columns_indices["Label"], 40)
        self.table.setColumnWidth(self.columns_indices["Type"], 40)

        self.table.horizontalHeader().setResizeMode(QHeaderView.Fixed)
    
        self.table.sortItems(self.columns_indices["Type"], Qt.AscendingOrder)

        self.context_menu = QMenu(self)
        self.context_menu.addAction(self.action_settings)
        self.context_menu.addAction(self.action_removevm)
        self.context_menu.addAction(self.action_resumevm)
        self.context_menu.addAction(self.action_pausevm)
        self.context_menu.addAction(self.action_shutdownvm)
        self.context_menu.addAction(self.action_killvm)
        self.context_menu.addAction(self.action_appmenus)
        self.context_menu.addAction(self.action_editfwrules)
        self.context_menu.addAction(self.action_updatevm)
        self.context_menu.addAction(self.action_set_keyboard_layout)

        self.table_selection_changed()
        
        self.logs_menu = QMenu("Logs")
        log_icon = QtGui.QIcon()
        log_icon.addPixmap(QPixmap(":/log.png"))
        self.logs_menu.setIcon(log_icon)
        self.context_menu.addMenu(self.logs_menu)


        self.blk_menu = QMenu("Block devices")
        blk_icon = QtGui.QIcon()
        blk_icon.addPixmap(QPixmap(":/mount.png"))
        self.blk_menu.setIcon(blk_icon)
        self.context_menu.addMenu(self.blk_menu)
        self.context_menu.addSeparator()

        self.connect(self.table.horizontalHeader(), SIGNAL("sortIndicatorChanged(int, Qt::SortOrder)"), self.sortIndicatorChanged)
        self.connect(self.table, SIGNAL("customContextMenuRequested(const QPoint&)"), self.open_context_menu)
        self.connect(self.blk_menu, SIGNAL("triggered(QAction *)"), self.attach_dettach_device_triggered)
        self.connect(self.logs_menu, SIGNAL("triggered(QAction *)"), self.show_log)

        self.table.setContentsMargins(0,0,0,0)
        self.centralwidget.layout().setContentsMargins(0,0,0,0)
        self.layout().setContentsMargins(0,0,0,0)

        self.action_toolbar = QAction("Show tool bar", None)
        self.action_toolbar.setCheckable(True)
        self.action_toolbar.setChecked(True)
        self.action_menubar = QAction("Show menu bar", None)
        self.action_menubar.setCheckable(True)
        self.action_menubar.setChecked(True)
        
        self.connect(self.action_menubar, SIGNAL("toggled(bool)"), self.showhide_menubar)
        self.connect(self.action_toolbar, SIGNAL("toggled(bool)"), self.showhide_toolbar)

        self.counter = 0
        self.shutdown_monitor = {}
        self.last_measure_results = {}
        self.last_measure_time = time.time()
        QTimer.singleShot (self.update_interval, self.update_table)


    def show(self):
        super(VmManagerWindow, self).show()
        self.screen_number = app.desktop().screenNumber(self)

    def set_table_geom_size(self):

        desktop_width = app.desktop().availableGeometry(self).width() - self.frame_width # might be wrong...
        desktop_height = app.desktop().availableGeometry(self).height() - self.frame_height # might be wrong...
        desktop_height -= self.row_height #UGLY! to somehow ommit taskbar... 
 
        W = self.table.horizontalHeader().length() +\
            self.table.verticalScrollBar().width() +\
            2*self.table.frameWidth() +1

        H = self.table.horizontalHeader().height() +\
            2*self.table.frameWidth()

        mainwindow_to_add = 0

        available_space = desktop_height
        if self.menubar.isVisible():
            menubar_height = self.menubar.height() + self.menubar.contentsMargins().top() + self.menubar.contentsMargins().bottom()
            available_space -= menubar_height
            mainwindow_to_add += menubar_height
        if self.toolbar.isVisible():
            toolbar_height = self.toolbar.height() + self.toolbar.contentsMargins().top() + self.toolbar.contentsMargins().bottom()
            available_space -= toolbar_height
            mainwindow_to_add += toolbar_height
        if W >= desktop_width:
            available_space -= self.table.horizontalScrollBar().height()
            H += self.table.horizontalScrollBar().height()
        default_rows = int(available_space/self.row_height)

        n = self.table.rowCount();
        
        if n > default_rows:
            H += default_rows*self.row_height
            self.table.verticalScrollBar().show()
        else:
            H += n*self.row_height
            self.table.verticalScrollBar().hide()
            W -= self.table.verticalScrollBar().width()

        W = min(desktop_width, W)
        
        self.centralwidget.setFixedHeight(H)

        H += mainwindow_to_add

        self.setMaximumHeight(H)
        self.setMinimumHeight(H)

        self.table.setFixedWidth(W)
        self.centralwidget.setFixedWidth(W)
        # don't change the following two lines to setFixedWidth!
        self.setMaximumWidth(W)
        self.setMinimumWidth(W)


    def moveEvent(self, event):
        super(VmManagerWindow, self).moveEvent(event)
        screen_number = app.desktop().screenNumber(self)
        if self.screen_number != screen_number:
                self.screen_changed = True
                self.screen_number = screen_number


    def get_vms_list(self):
        self.qvm_collection.lock_db_for_reading()
        self.qvm_collection.load()
        self.qvm_collection.unlock_db()

        vms_list = [vm for vm in self.qvm_collection.values()]
        for vm in vms_list:
            vm.last_power_state = vm.get_power_state()
            vm.last_running = vm.last_power_state in ["Running", "Transient"]

        no_vms = len (vms_list)
        vms_to_display = []

        # First, the NetVMs...
        for netvm in vms_list:
            if netvm.is_netvm():
                vms_to_display.append (netvm)

        # Now, the templates...
        for tvm in vms_list:
            if tvm.is_template():
                vms_to_display.append (tvm)

        label_list = QubesVmLabels.values()
        label_list.sort(key=lambda l: l.index)
       
 
        for label in [label.name for label in label_list]:
            for appvm in [vm for vm in vms_list if ((vm.is_appvm() or vm.is_disposablevm()) and vm.label.name == label)]:
                vms_to_display.append(appvm)

        assert len(vms_to_display) == no_vms
        return vms_to_display

    def fill_table(self):
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        vms_list = self.get_vms_list()
        self.table.setRowCount(len(vms_list))

        vms_in_table = {}

        row_no = 0
        for vm in vms_list:
            if (not self.show_inactive_vms) and (not vm.last_running):
                continue
            if vm.internal:
                continue
            vm_row = VmRowInTable (vm, row_no, self.table, self.blk_manager)
            vms_in_table[vm.qid] = vm_row
            row_no += 1

        self.table.setRowCount(row_no)
        self.vms_list = vms_list
        self.vms_in_table = vms_in_table
        self.reload_table = False
        self.table.setSortingEnabled(True)
        
    def mark_table_for_update(self):
        self.reload_table = True

    # When calling update_table() directly, always use out_of_schedule=True!
    def update_table(self, out_of_schedule=False):

        update_devs = self.update_block_devices() or out_of_schedule
        if manager_window.isVisible():
            some_vms_have_changed_power_state = False
            for vm in self.vms_list:
                state = vm.get_power_state()
                if vm.last_power_state != state:
                    vm.last_power_state = state
                    vm.last_running = (state in ["Running", "Transient"])
                    some_vms_have_changed_power_state = True

            reload_table = self.reload_table

            if self.screen_changed == True:
                reload_table = True
                self.screen_changed = False

            
            if reload_table or ((not self.show_inactive_vms) and some_vms_have_changed_power_state): 
                self.fill_table()
                self.set_table_geom_size()
                update_devs=True


            if self.sort_by_state != None and some_vms_have_changed_power_state:
                self.table.sortItems(self.columns_indices["State"], self.sort_by_state)

            blk_visible = None
            rows_with_blk = None
            if update_devs == True:
                rows_with_blk = []
                self.blk_manager.blk_lock.acquire()
                for d in self.blk_manager.attached_devs:
                    rows_with_blk.append( self.blk_manager.attached_devs[d]['attached_to']['vm'])
                self.blk_manager.blk_lock.release()

            if self.counter % 3 == 0 or out_of_schedule:
                (self.last_measure_time, self.last_measure_results) = \
                    qubes_host.measure_cpu_usage(self.last_measure_results,
                    self.last_measure_time)

                for vm_row in self.vms_in_table.values():
                    cur_cpu_load = None
                    if vm_row.vm.get_xid() in self.last_measure_results:
                        cur_cpu_load = self.last_measure_results[vm_row.vm.xid]['cpu_usage']
                    else:
                        cur_cpu_load = 0

                    if rows_with_blk != None: 
                        if vm_row.vm.name in rows_with_blk:
                            blk_visible = True
                        else:
                            blk_visible = False
                    
                    vm_row.update(self.counter, blk_visible=blk_visible, cpu_load = cur_cpu_load)

            else:
                for vm_row in self.vms_in_table.values():
                    if rows_with_blk != None:
                        if vm_row.vm.name in rows_with_blk:
                            blk_visible = True
                        else:
                            blk_visible = False

                    vm_row.update(self.counter, blk_visible=blk_visible)

            if self.sort_by_cpu != None:
                self.table.sortItems(self.columns_indices["CPU"], self.sort_by_cpu)
            elif self.sort_by_mem != None:
                self.table.sortItems(self.columns_indices["MEM"], self.sort_by_mem)
            elif self.sort_by_state != None and reload_table:
                #needed to sort after reload (fill_table sorts items with setSortingEnabled, but by that time the widgets values are not correct yet).
                self.table.sortItems(self.columns_indices["State"], self.sort_by_state)
            
            self.table_selection_changed()

        if not out_of_schedule:
            self.counter += 1
            QTimer.singleShot (self.update_interval, self.update_table)

 
    def update_block_devices(self):
        res, msg = self.blk_manager.check_for_updates()
        if msg != None and len(msg) > 0:
            str = "\n".join(msg)
            trayIcon.showMessage ("Qubes Manager", str, msecs=5000)
        return res


    def sortIndicatorChanged(self, column, order):
        if column == self.columns_indices["CPU"] or column == self.columns_indices["CPU Graph"]:
            self.sort_by_mem = None
            self.sort_by_state = None
            self.sort_by_cpu = order
            return
        elif column == self.columns_indices["MEM"] or column == self.columns_indices["MEM Graph"]:
            self.sort_by_cpu = None
            self.sort_by_state = None
            self.sort_by_mem = order
            return
        elif column == self.columns_indices["State"]:
            
            self.sort_by_cpu = None
            self.sort_by_mem = None
            self.sort_by_state = order
            return
        else:
            self.sort_by_cpu = None
            self.sort_by_mem = None
            self.sort_by_state = None

       
    def table_selection_changed (self):

        vm = self.get_selected_vm()

        if vm != None:
            # Update available actions:
            self.action_settings.setEnabled(True)
            self.action_removevm.setEnabled(not vm.installed_by_rpm and not (vm.last_running))
            self.action_resumevm.setEnabled(not vm.last_running)
            self.action_pausevm.setEnabled(vm.last_running and vm.qid != 0)
            self.action_shutdownvm.setEnabled(vm.last_running and vm.qid != 0)
            self.action_killvm.setEnabled(vm.last_running and vm.qid != 0)
            self.action_appmenus.setEnabled(not vm.is_netvm())
            self.action_editfwrules.setEnabled(vm.is_networked() and not (vm.is_netvm() and not vm.is_proxyvm()))
            self.action_updatevm.setEnabled(vm.is_updateable() or vm.qid == 0)
            self.action_set_keyboard_layout.setEnabled(vm.qid != 0 and vm.last_running)
        else:
            self.action_settings.setEnabled(False)
            self.action_removevm.setEnabled(False)
            self.action_resumevm.setEnabled(False)
            self.action_pausevm.setEnabled(False)
            self.action_shutdownvm.setEnabled(False)
            self.action_killvm.setEnabled(False)
            self.action_appmenus.setEnabled(False)
            self.action_editfwrules.setEnabled(False)
            self.action_updatevm.setEnabled(False)
            self.action_set_keyboard_layout.setEnabled(False)



    def closeEvent (self, event):
        if event.spontaneous(): # There is something borked in Qt, as the logic here is inverted on X11
            self.hide()
            event.ignore()

    
    @pyqtSlot(name='on_action_createvm_triggered')
    def action_createvm_triggered(self):
        dialog = NewAppVmDlg()

        # Theoretically we should be locking for writing here and unlock
        # only after the VM creation finished. But the code would be more messy...
        # Instead we lock for writing in the actual worker thread

        self.qvm_collection.lock_db_for_reading()
        self.qvm_collection.load()
        self.qvm_collection.unlock_db()

        label_list = QubesVmLabels.values()
        label_list.sort(key=lambda l: l.index)
        for (i, label) in enumerate(label_list):
            dialog.vmlabel.insertItem(i, label.name)
            dialog.vmlabel.setItemIcon (i, QIcon(label.icon_path))

        template_vm_list = [vm for vm in self.qvm_collection.values() if not vm.internal and vm.is_template()]

        default_index = 0
        for (i, vm) in enumerate(template_vm_list):
            if vm is self.qvm_collection.get_default_template():
                default_index = i
                dialog.template_name.insertItem(i, vm.name + " (default)")
            else:
                dialog.template_name.insertItem(i, vm.name)
        dialog.template_name.setCurrentIndex(default_index)

        dialog.vmname.selectAll()
        dialog.vmname.setFocus()

        if dialog.exec_():
            vmname = str(dialog.vmname.text())
            if self.qvm_collection.get_vm_by_name(vmname) is not None:
                QMessageBox.warning (None, "Incorrect AppVM Name!", "A VM with the name <b>{0}</b> already exists in the system!".format(vmname))
                return

            label = label_list[dialog.vmlabel.currentIndex()]
            template_vm = template_vm_list[dialog.template_name.currentIndex()]

            allow_networking = dialog.allow_networking.isChecked()

            thread_monitor = ThreadMonitor()
            thread = threading.Thread (target=self.do_create_appvm, args=(vmname, label, template_vm, allow_networking, thread_monitor))
            thread.daemon = True
            thread.start()

            progress = QProgressDialog ("Creating new AppVM <b>{0}</b>...".format(vmname), "", 0, 0)
            progress.setCancelButton(None)
            progress.setModal(True)
            progress.show()

            while not thread_monitor.is_finished():
                app.processEvents()
                time.sleep (0.1)

            progress.hide()

            if thread_monitor.success:
                trayIcon.showMessage ("Qubes Manager", "VM '{0}' has been created.".format(vmname), msecs=3000)
            else:
                QMessageBox.warning (None, "Error creating AppVM!", "ERROR: {0}".format(thread_monitor.error_msg))


    def do_create_appvm (self, vmname, label, template_vm, allow_networking, thread_monitor):
        vm = None
        try:
            self.qvm_collection.lock_db_for_writing()
            self.qvm_collection.load()

            vm = self.qvm_collection.add_new_appvm(vmname, template_vm, label = label)
            vm.create_on_disk(verbose=False)
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


    def get_selected_vm(self):
        #vm selection relies on the VmInfo widget's value used for sorting by VM name
        row_index = self.table.currentRow()
        if row_index != -1:
            qid = self.table.item(row_index, self.columns_indices["Name"]).qid
            assert self.vms_in_table[qid] is not None
            vm = self.vms_in_table[qid].vm
            return vm
        else:
            return None

    @pyqtSlot(name='on_action_removevm_triggered')
    def action_removevm_triggered(self):

        vm = self.get_selected_vm()
        assert not vm.is_running()
        assert not vm.installed_by_rpm

        self.qvm_collection.lock_db_for_reading()
        self.qvm_collection.load()
        self.qvm_collection.unlock_db()
 
        if vm.is_template():
            dependent_vms = self.qvm_collection.get_vms_based_on(vm.qid)
            if len(dependent_vms) > 0:
                QMessageBox.warning (None, "Warning!",
                                     "This Template VM cannot be removed, because there is at least one AppVM that is based on it.<br>"
                                     "<small>If you want to remove this Template VM and all the AppVMs based on it,"
                                     "you should first remove each individual AppVM that uses this template.</small>")

                return

        reply = QMessageBox.question(None, "VM Removal Confirmation",
                                     "Are you sure you want to remove the VM <b>'{0}'</b>?<br>"
                                     "<small>All data on this VM's private storage will be lost!</small>".format(vm.name),
                                     QMessageBox.Yes | QMessageBox.Cancel)


        if reply == QMessageBox.Yes:

            thread_monitor = ThreadMonitor()
            thread = threading.Thread (target=self.do_remove_vm, args=(vm, thread_monitor))
            thread.daemon = True
            thread.start()

            progress = QProgressDialog ("Removing VM: <b>{0}</b>...".format(vm.name), "", 0, 0)
            progress.setCancelButton(None)
            progress.setModal(True)
            progress.show()

            while not thread_monitor.is_finished():
                app.processEvents()
                time.sleep (0.1)

            progress.hide()

            if thread_monitor.success:
                trayIcon.showMessage ("Qubes Manager", "VM '{0}' has been removed.".format(vm.name), msecs=3000)
            else:
                QMessageBox.warning (None, "Error removing VM!", "ERROR: {0}".format(thread_monitor.error_msg))

    def do_remove_vm (self, vm, thread_monitor):
        try:
            self.qvm_collection.lock_db_for_writing()
            self.qvm_collection.load()

            #TODO: the following two conditions should really be checked by qvm_collection.pop() overload...
            if vm.is_template() and self.qvm_collection.default_template_qid == vm.qid:
                self.qvm_collection.default_template_qid = None
            if vm.is_netvm() and self.qvm_collection.default_netvm_qid == vm.qid:
                self.qvm_collection.default_netvm_qid = None

            vm.remove_from_disk()
            self.qvm_collection.pop(vm.qid)
            self.qvm_collection.save()
        except Exception as ex:
            thread_monitor.set_error_msg (str(ex))
        finally:
            self.qvm_collection.unlock_db()

        thread_monitor.set_finished()

    @pyqtSlot(name='on_action_resumevm_triggered')
    def action_resumevm_triggered(self):
        vm = self.get_selected_vm()
        assert not vm.is_running()

        if vm.is_paused():
            try:
                subprocess.check_call (["/usr/sbin/xl", "unpause", vm.name])
            except Exception as ex:
                QMessageBox.warning (None, "Error unpausing VM!", "ERROR: {0}".format(ex))
            return

        thread_monitor = ThreadMonitor()
        thread = threading.Thread (target=self.do_start_vm, args=(vm, thread_monitor))
        thread.daemon = True
        thread.start()

        trayIcon.showMessage ("Qubes Manager", "Starting '{0}'...".format(vm.name), msecs=3000)

        while not thread_monitor.is_finished():
            app.processEvents()
            time.sleep (0.1)

        if thread_monitor.success:
            trayIcon.showMessage ("Qubes Manager", "VM '{0}' has been started.".format(vm.name), msecs=3000)
        else:
            QMessageBox.warning (None, "Error starting VM!", "ERROR: {0}".format(thread_monitor.error_msg))

    def do_start_vm(self, vm, thread_monitor):
        try:
            vm.verify_files()
            xid = vm.start()
        except Exception as ex:
            thread_monitor.set_error_msg(str(ex))
            thread_monitor.set_finished()
            return

        retcode = subprocess.call ([qubes_guid_path, "-d", str(xid), "-c", vm.label.color, "-i", vm.label.icon, "-l", str(vm.label.index)])
        if (retcode != 0):
            thread_monitor.set_error_msg("Cannot start qubes_guid!")

        thread_monitor.set_finished()
 
    @pyqtSlot(name='on_action_pausevm_triggered')
    def action_pausevm_triggered(self):
        vm = self.get_selected_vm()
        assert vm.is_running()
        try:
            subprocess.check_call (["/usr/sbin/xl", "pause", vm.name])

        except Exception as ex:
            QMessageBox.warning (None, "Error pausing VM!", "ERROR: {0}".format(ex))
            return

    @pyqtSlot(name='on_action_shutdownvm_triggered')
    def action_shutdownvm_triggered(self):
        vm = self.get_selected_vm()
        assert vm.is_running()

        reply = QMessageBox.question(None, "VM Shutdown Confirmation",
                                     "Are you sure you want to power down the VM <b>'{0}'</b>?<br>"
                                     "<small>This will shutdown all the running applications within this VM.</small>".format(vm.name),
                                     QMessageBox.Yes | QMessageBox.Cancel)

        app.processEvents()

        if reply == QMessageBox.Yes:
            self.shutdown_vm(vm)


    def shutdown_vm(self, vm):
        try:
            subprocess.check_call (["/usr/sbin/xl", "shutdown", vm.name])
        except Exception as ex:
            QMessageBox.warning (None, "Error shutting down VM!", "ERROR: {0}".format(ex))
            return

        trayIcon.showMessage ("Qubes Manager", "VM '{0}' is shutting down...".format(vm.name), msecs=3000)

        self.shutdown_monitor[vm.qid] = VmShutdownMonitor (vm)
        QTimer.singleShot (vm_shutdown_timeout, self.shutdown_monitor[vm.qid].check_if_vm_has_shutdown)


    @pyqtSlot(name='on_action_killvm_triggered')
    def action_killvm_triggered(self):
        vm = self.get_selected_vm()
        assert vm.is_running()

        reply = QMessageBox.question(None, "VM Kill Confirmation",
                                     "Are you sure you want to kill the VM <b>'{0}'</b>?<br>"
                                     "<small>This will end <b>(not shutdown!)</b> all the running applications within this VM.</small>".format(vm.name),
                                     QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)

        app.processEvents()

        if reply == QMessageBox.Yes:
            try:
                vm.force_shutdown()
            except Exception as ex:
                QMessageBox.critical (None, "Error while killing VM!", "<b>An exception ocurred while killing {0}.</b><br>ERROR: {1}".format(vm.name, ex))
                return

            trayIcon.showMessage ("Qubes Manager", "VM '{0}' killed!".format(vm.name), msecs=3000)



    @pyqtSlot(name='on_action_settings_triggered')
    def action_settings_triggered(self):
        vm = self.get_selected_vm()
        settings_window = VMSettingsWindow(vm, app, self.qvm_collection, "basic")
        settings_window.exec_()
   

    @pyqtSlot(name='on_action_appmenus_triggered')
    def action_appmenus_triggered(self):
        vm = self.get_selected_vm()
        settings_window = VMSettingsWindow(vm, app, self.qvm_collection, "applications")
        settings_window.exec_()


    @pyqtSlot(name='on_action_updatevm_triggered')
    def action_updatevm_triggered(self):
        vm = self.get_selected_vm()

        if not vm.is_running():
            reply = QMessageBox.question(None, "VM Update Confirmation",
                    "VM need to be running for update. Do you want to start this VM?<br>",
                    QMessageBox.Yes | QMessageBox.Cancel)
            if reply != QMessageBox.Yes:
                return
            trayIcon.showMessage ("Qubes Manager", "Starting '{0}'...".format(vm.name), msecs=3000)

        app.processEvents()

        thread_monitor = ThreadMonitor()
        thread = threading.Thread (target=self.do_update_vm, args=(vm, thread_monitor))
        thread.daemon = True
        thread.start()

        while not thread_monitor.is_finished():
            app.processEvents()
            time.sleep (0.2)

        if vm.qid != 0:    
            if thread_monitor.success:
                # gpk-update-viewer was started, don't know if user installs updates, but touch stat file anyway
                open(vm.dir_path + '/' + updates_stat_file, 'w').close()
            else:
                QMessageBox.warning (None, "Error VM update!", "ERROR: {0}".format(thread_monitor.error_msg))

    def do_update_vm(self, vm, thread_monitor):
        try:
            if vm.qid == 0:
                subprocess.check_call (["/usr/bin/qvm-dom0-update", "--gui"])
            else:
                vm.run("user:gpk-update-viewer", verbose=False, autostart=True)
        except Exception as ex:
            thread_monitor.set_error_msg(str(ex))
            thread_monitor.set_finished()
            return
        thread_monitor.set_finished()

 
    @pyqtSlot(name='on_action_set_keyboard_layout_triggered')
    def action_set_keyboard_layout_triggered(self):
        print "change layout!"
        vm = self.get_selected_vm()
        subprocess.Popen( ['qvm-run', vm.name, 'qubes-change-keyboard-layout'])


    @pyqtSlot(name='on_action_showallvms_triggered')
    def action_showallvms_triggered(self):
        self.show_inactive_vms = self.action_showallvms.isChecked()
        self.mark_table_for_update()
        self.update_table(out_of_schedule = True)
        self.set_table_geom_size()

    @pyqtSlot(name='on_action_editfwrules_triggered')
    def action_editfwrules_triggered(self):
        vm = self.get_selected_vm()
        settings_window = VMSettingsWindow(vm, app, self.qvm_collection, "firewall")
        settings_window.exec_()

    @pyqtSlot(name='on_action_global_settings_triggered')
    def action_global_settings_triggered(self):
        global_settings_window = GlobalSettingsWindow(app, self.qvm_collection)
        global_settings_window.exec_()


    @pyqtSlot(name='on_action_restore_triggered')
    def action_restore_triggered(self):
        restore_window = RestoreVMsWindow(app, self.qvm_collection, self.blk_manager)
        restore_window.exec_()

    @pyqtSlot(name='on_action_backup_triggered')
    def action_backup_triggered(self):
        backup_window = BackupVMsWindow(app, self.qvm_collection, self.blk_manager, self.shutdown_vm)
        backup_window.exec_()


    def showhide_menubar(self, checked):
        self.menuWidget().setVisible(checked)
        self.set_table_geom_size()
        if not checked:
            self.context_menu.addAction(self.action_menubar)
        else:
            self.context_menu.removeAction(self.action_menubar)
            

    def showhide_toolbar(self, checked):
        self.toolbar.setVisible(checked)
        self.set_table_geom_size()
        if not checked:
            self.context_menu.addAction(self.action_toolbar)
        else:
            self.context_menu.removeAction(self.action_toolbar)


    def showhide_column(self, col_num, show):
        self.table.setColumnHidden( col_num, not show)
        self.set_table_geom_size()

    def on_actionState_toggled(self, checked):
        self.showhide_column( self.columns_indices['State'], checked)
 
    def on_actionTemplate_toggled(self, checked):
        self.showhide_column( self.columns_indices['Template'], checked)

    def on_actionNetVM_toggled(self, checked):
        self.showhide_column( self.columns_indices['NetVM'], checked)
    
    def on_actionCPU_toggled(self, checked):
        self.showhide_column( self.columns_indices['CPU'], checked)
    
    def on_actionCPU_Graph_toggled(self, checked):
        self.showhide_column( self.columns_indices['CPU Graph'], checked)    

    def on_actionMEM_toggled(self, checked):
        self.showhide_column( self.columns_indices['MEM'], checked)   
    
    def on_actionMEM_Graph_toggled(self, checked):
        self.showhide_column( self.columns_indices['MEM Graph'], checked)


    def createPopupMenu(self):
        menu = QMenu()
        menu.addAction(self.action_toolbar)
        menu.addAction(self.action_menubar)
        return menu


    @pyqtSlot('const QPoint&')
    def open_context_menu(self, point):
        vm = self.get_selected_vm()

        running = vm.is_running()

        #logs menu
        self.logs_menu.clear()
        if vm.qid == 0:
            text = "/var/log/xen/console/hypervisor.log"
            action = self.logs_menu.addAction(QIcon(":/log.png"), text)
            action.setData(QVariant(text))
            self.logs_menu.setEnabled(True)
        else:
            menu_empty = True
            text = "/var/log/xen/console/guest-"+vm.name+".log"
            if os.path.exists(text):
                action = self.logs_menu.addAction(QIcon(":/log.png"), text)
                action.setData(QVariant(text))
                menu_empty = False

            text = "/var/log/xen/console/guest-"+vm.name+"-dm.log"
            if os.path.exists(text):
                action = self.logs_menu.addAction(QIcon(":/log.png"), text)
                action.setData(QVariant(text))
                menu_empty = False

            if running:
                xid = vm.xid
                if xid != None:
                    text = "/var/log/qubes/guid."+str(xid)+".log"
                    action = self.logs_menu.addAction(QIcon(":/log.png"), text)
                    action.setData(QVariant(text))

                    text = "/var/log/qubes/qrexec."+str(xid)+".log"
                    action = self.logs_menu.addAction(QIcon(":/log.png"), text)
                    action.setData(QVariant(text))

                    menu_empty = False
            self.logs_menu.setEnabled(not menu_empty)
                    
        # blk menu
        if not running:
            self.blk_menu.setEnabled(False)
        else:
            self.blk_menu.clear()
            self.blk_menu.setEnabled(True)

            self.blk_manager.blk_lock.acquire()
            if len(self.blk_manager.attached_devs) > 0 :
                for d in self.blk_manager.attached_devs:
                    if self.blk_manager.attached_devs[d]['attached_to']['vm'] == vm.name:
                        text = "Detach " + d + " " + unicode(self.blk_manager.attached_devs[d]['size']) + " " + self.blk_manager.attached_devs[d]['desc']
                        action = self.blk_menu.addAction(QIcon(":/remove.png"), text)
                        action.setData(QVariant(d))

            if len(self.blk_manager.free_devs) > 0:
                for d in self.blk_manager.free_devs:
                    if d.startswith(vm.name):
                        continue
                    text = "Attach  " + d + " " + unicode(self.blk_manager.free_devs[d]['size']) + " " + self.blk_manager.free_devs[d]['desc']
                    action = self.blk_menu.addAction(QIcon(":/add.png"), text)
                    action.setData(QVariant(d))

            self.blk_manager.blk_lock.release()

            if self.blk_menu.isEmpty():
                self.blk_menu.setEnabled(False)
 
        self.context_menu.exec_(self.table.mapToGlobal(point))

    @pyqtSlot('QAction *')
    def show_log(self, action):
        log = str(action.data().toString())
        
        cmd = ['kdialog', '--textbox', log, '700', '450', '--title', log]
        subprocess.Popen(cmd)


    @pyqtSlot('QAction *')
    def attach_dettach_device_triggered(self, action):
        dev = str(action.data().toString())
        vm = self.get_selected_vm()

        self.blk_manager.blk_lock.acquire()
        if dev in self.blk_manager.attached_devs:
            self.blk_manager.detach_device(vm, dev)
        else:
            self.blk_manager.attach_device(vm, dev)
        self.blk_manager.blk_lock.release()


class QubesBlockDevicesManager():
    def __init__(self, qvm_collection):
        self.qvm_collection = qvm_collection
        self.attached_devs = {}
        self.free_devs = {}

        self.current_blk = {}
        self.current_attached = {}
        self.devs_changed = False

        self.last_update_time = time.time()
        self.blk_state_changed = True
        self.msg = []
        self.check_counter = 0
        self.blk_lock = threading.Lock()

        self.update()

    def block_devs_event(self, xid):
        now = time.time()
        #don't update more often than 1/10 s
        if now - self.last_update_time >= 0.1:
            self.last_update_time = now

            self.blk_lock.acquire()

            self.blk_state_changed = True

            self.blk_lock.release()

    def check_for_updates(self):
        self.blk_lock.acquire()

        ret = (self.blk_state_changed, self.msg)
        
        if self.blk_state_changed == True:
            self.check_counter += 1
            
            self.update()
            ret = (self.blk_state_changed, self.msg)
            
            #let the update last for 3 manager-update cycles
            if self.check_counter == 3:
                self.check_counter = 0
                self.blk_state_changed = False
        self.msg = []            

        self.blk_lock.release()

        return ret
            
            
    def update(self):
        blk = qubesutils.block_list()
        for b in blk:
            att = qubesutils.block_check_attached(None, blk[b]['device'], backend_xid = blk[b]['xid'])
            if b in self.current_blk:
                if blk[b] == self.current_blk[b]:
                    if self.current_attached[b] != att: #devices the same, sth with attaching changed
                        self.current_attached[b] = att
                else:   #device changed ?!
                    self.current_blk[b] = blk[b]
                    self.current_attached[b] = att
            else: #new device
                self.current_blk[b] = blk[b]
                self.current_attached[b] = att
                self.msg.append("Attached new device: {0}".format(blk[b]['device']))

        to_delete = []
        for b in self.current_blk: #remove devices that are not there anymore
            if b not in blk:
                to_delete.append(b)
                self.msg.append("Detached device: {0}".format(self.current_blk[b]['device']))

        for d in to_delete:
            del self.current_blk[d]
            del self.current_attached[d]

        self.__update_blk_entries__()


    def __update_blk_entries__(self):
        self.free_devs.clear()
        self.attached_devs.clear()

        for b in self.current_attached:
            if self.current_attached[b]:
                self.attached_devs[b] = self.__make_entry__(b, self.current_blk[b], self.current_attached[b])
            else:
                self.free_devs[b] = self.__make_entry__(b, self.current_blk[b], None)
                
    def __make_entry__(self, k, dev, att):
        size_str = qubesutils.bytes_to_kmg(dev['size'])
        entry = {   'dev': dev['device'],
                    'backend_name': dev['vm'],
                    'desc': dev['desc'],
                    'size': size_str,
                    'attached_to': att, }
        return entry

    def attach_device(self, vm, dev):
        backend_vm_name = self.free_devs[dev]['backend_name']
        dev_id = self.free_devs[dev]['dev']
        backend_vm = self.qvm_collection.get_vm_by_name(backend_vm_name)
        trayIcon.showMessage ("Qubes Manager", "{0} - attaching {1}".format(vm.name, dev), msecs=3000)
        qubesutils.block_attach(vm, backend_vm, dev_id)
      
    def detach_device(self, vm, dev_name):
        dev_id = self.attached_devs[dev_name]['attached_to']['devid']
        vm_xid = self.attached_devs[dev_name]['attached_to']['xid']
        trayIcon.showMessage ("Qubes Manager", "{0} - detaching {1}".format(vm.name, dev_name), msecs=3000)
        qubesutils.block_detach(None, dev_id, vm_xid)


class QubesTrayIcon(QSystemTrayIcon):
    def __init__(self, icon):
        QSystemTrayIcon.__init__(self, icon)
        self.menu = QMenu()

        action_showmanager = self.createAction ("Open VM Manager", slot=show_manager, icon="qubes")
        action_backup = self.createAction ("Make backup")
        action_preferences = self.createAction ("Preferences")
        action_set_netvm = self.createAction ("Set default NetVM", icon="networking")
        action_sys_info = self.createAction ("System Info", icon="dom0")
        action_exit = self.createAction ("Exit", slot=exit_app)

        action_backup.setDisabled(True)
        action_preferences.setDisabled(True)
        action_set_netvm.setDisabled(True)
        action_sys_info.setDisabled(True)

        self.addActions (self.menu, (action_showmanager, action_backup, action_sys_info, None, action_preferences, action_set_netvm, None, action_exit))

        self.setContextMenu(self.menu)

        self.connect (self, SIGNAL("activated (QSystemTrayIcon::ActivationReason)"), self.icon_clicked)

    def icon_clicked(self, reason):
        if reason == QSystemTrayIcon.Context:
            # Handle the right click normally, i.e. display the context menu
            return
        else:
            toggle_manager()

    def addActions(self, target, actions):
        for action in actions:
            if action is None:
                target.addSeparator()
            else:
                target.addAction(action)


    def createAction(self, text, slot=None, shortcut=None, icon=None,
                     tip=None, checkable=False, signal="triggered()"):
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(QIcon(":/%s.png" % icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            self.connect(action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable(True)
        return action

def get_frame_size():
    w = 0
    h = 0
    cmd = ['xprop', '-name', 'Qubes VM Manager', '|', 'grep', '_NET_FRAME_EXTENTS'] 
    xprop = subprocess.Popen(cmd, stdout = subprocess.PIPE)
    for l in xprop.stdout:
        line = l.split('=')
        if len(line) == 2:
            line = line[1].strip().split(',')
            if len(line) == 4:
                w = int(line[0].strip())+ int(line[1].strip())
                h = int(line[2].strip())+ int(line[3].strip())
                break;
    #in case of some weird window managers we have to assume sth...
    if w<= 0:
        w = 10
    if h <= 0:
        h = 30
    
    manager_window.frame_width = w
    manager_window.frame_height = h
    return


def show_manager():
    manager_window.show()

def toggle_manager():
    if manager_window.isVisible():
        manager_window.hide()
    else:
        manager_window.show()
        manager_window.set_table_geom_size()
        manager_window.update_table(True)

        get_frame_size() 
        print manager_window.frame_width, " x ", manager_window.frame_height
        manager_window.set_table_geom_size()


def exit_app():
    notifier.stop()
    app.exit()


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception( exc_type, exc_value, exc_traceback ):
    import sys
    import os.path
    import traceback

    filename, line, dummy, dummy = traceback.extract_tb( exc_traceback ).pop()
    filename = os.path.basename( filename )
    error    = "%s: %s" % ( exc_type.__name__, exc_value )

    strace = ""
    stacktrace = traceback.extract_tb( exc_traceback )
    while len(stacktrace) > 0:
        (filename, line, func, txt) = stacktrace.pop()
        strace += "----\n"
        strace += "line: %s\n" %txt
        strace += "func: %s\n" %func
        strace += "line no.: %d\n" %line
        strace += "file: %s\n" %filename

    msg_box = QMessageBox()
    msg_box.setDetailedText(strace)
    msg_box.setIcon(QMessageBox.Critical)
    msg_box.setWindowTitle( "Houston, we have a problem...")
    msg_box.setText("Whoops. A critical error has occured. This is most likely a bug "
                    "in Qubes Manager.<br><br>"
                    "<b><i>%s</i></b>" % error +
                    "<br/>at line <b>%d</b><br/>of file %s.<br/><br/>"
                    % ( line, filename ))
    
    msg_box.exec_()


def main():


    # Avoid starting more than one instance of the app
    lock = QubesDaemonPidfile ("qubes-manager")
    if lock.pidfile_exists():
        if lock.pidfile_is_stale():
            lock.remove_pidfile()
            print "Removed stale pidfile (has the previous daemon instance crashed?)."
        else:
            exit (0)

    lock.create_pidfile()

    global qubes_host
    qubes_host = QubesHost()

    global app
    app = QApplication(sys.argv)
    app.setOrganizationName("The Qubes Project")
    app.setOrganizationDomain("http://qubes-os.org")
    app.setApplicationName("Qubes VM Manager")
    app.setWindowIcon(QIcon(":/qubes.png"))

    sys.excepthook = handle_exception

    global manager_window
    manager_window = VmManagerWindow()
    wm = WatchManager()
    mask = EventsCodes.OP_FLAGS.get('IN_MODIFY')

    global notifier
    notifier = ThreadedNotifier(wm, QubesConfigFileWatcher(manager_window.mark_table_for_update))
    notifier.start()
    wdd = wm.add_watch(qubes_store_filename, mask)

    global trayIcon
    trayIcon = QubesTrayIcon(QIcon(":/qubes.png"))
    trayIcon.show()

    app.exec_()
    trayIcon = None
