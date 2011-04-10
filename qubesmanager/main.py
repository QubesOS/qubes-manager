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

import qubesmanager.qrc_resources
import ui_newappvmdlg

from firewall import EditFwRulesDlg, QubesFirewallRulesModel

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time
import threading

qubes_guid_path = '/usr/bin/qubes_guid'

class QubesConfigFileWatcher(ProcessEvent):
    def __init__ (self, update_func):
        self.update_func = update_func

    def process_IN_MODIFY (self, event):
        self.update_func()

class VmStatusIcon(QLabel):
    def __init__(self, vm, parent=None):
        super (VmStatusIcon, self).__init__(parent)
        self.vm = vm
        (icon_pixmap, icon_sz) = self.set_vm_icon(self.vm)
        self.setPixmap (icon_pixmap)
        self.setFixedSize (icon_sz)
        self.previous_power_state = vm.last_power_state

    def update(self):
        if self.previous_power_state != self.vm.last_power_state:
            (icon_pixmap, icon_sz) = self.set_vm_icon(self.vm)
            self.setPixmap (icon_pixmap)
            self.setFixedSize (icon_sz)
            self.previous_power_state = self.vm.last_power_state

    def set_vm_icon(self, vm):
        if vm.qid == 0:
            icon = QIcon (":/dom0.png")
        elif vm.is_appvm():
            icon = QIcon (vm.label.icon_path)
        elif vm.is_template():
            icon = QIcon (":/templatevm.png")
        elif vm.is_netvm():
            icon = QIcon (":/netvm.png")
        else:
            icon = QIcon()

        icon_sz = QSize (VmManagerWindow.row_height * 0.8, VmManagerWindow.row_height * 0.8)
        if vm.last_power_state:
            icon_pixmap = icon.pixmap(icon_sz)
        else:
            icon_pixmap = icon.pixmap(icon_sz, QIcon.Disabled)

        return (icon_pixmap, icon_sz)


class VmInfoWidget (QWidget):

    def __init__(self, vm, parent = None):
        super (VmInfoWidget, self).__init__(parent)

        layout0 = QHBoxLayout()

        self.label_name = QLabel (vm.name)

        self.vm_running = vm.last_power_state
        layout0.addWidget(self.label_name, alignment=Qt.AlignLeft)

        layout1 = QHBoxLayout()

        if vm.template_vm is not None:
            self.label_tmpl = QLabel ("<i><font color=\"gray\">" + (vm.template_vm.name) + "</i></font>")
        elif vm.is_appvm(): # and vm.template_vm is None
            self.label_tmpl = QLabel ("<i><font color=\"gray\">StandaloneVM</i></font>")
        elif vm.is_template():
            self.label_tmpl = QLabel ("<i><font color=\"gray\">TemplateVM</i></font>")
        elif vm.qid == 0:
            self.label_tmpl = QLabel ("<i><font color=\"gray\">AdminVM</i></font>")
        elif vm.is_netvm():
            self.label_tmpl = QLabel ("<i><font color=\"gray\">NetVM</i></font>")
        else:
            self.label_tmpl = QLabel ("")

        label_icon_networked = self.set_icon(":/networking.png", vm.is_networked())
        layout1.addWidget(label_icon_networked, alignment=Qt.AlignLeft)

        if vm.is_updateable():
            label_icon_updtbl = self.set_icon(":/updateable.png", True)
            layout1.addWidget(label_icon_updtbl, alignment=Qt.AlignLeft)

        layout1.addWidget(self.label_tmpl, alignment=Qt.AlignLeft)

        layout1.addStretch()

        layout2 = QVBoxLayout ()
        layout2.addLayout(layout0)
        layout2.addLayout(layout1)

        layout3 = QHBoxLayout ()
        self.vm_icon = VmStatusIcon(vm)
        layout3.addWidget(self.vm_icon)
        layout3.addSpacing (10)
        layout3.addLayout(layout2)

        self.setLayout(layout3)

        self.previous_outdated = False

    def set_icon(self, icon_path, enabled = True):
        label_icon = QLabel()
        icon = QIcon (icon_path)
        icon_sz = QSize (VmManagerWindow.row_height * 0.3, VmManagerWindow.row_height * 0.3)
        icon_pixmap = icon.pixmap(icon_sz, QIcon.Disabled if not enabled else QIcon.Normal)
        label_icon.setPixmap (icon_pixmap)
        label_icon.setFixedSize (icon_sz)
        return label_icon

    def update_vm_state (self, vm):
        self.vm_icon.update()

    def update_outdated(self, vm):
        outdated = vm.is_outdated()
        if outdated != self.previous_outdated:
            if outdated:
                self.label_name.setText(vm.name + "<small><font color=\"red\"> (outdated)</font></small>")
            else:
                self.label_name.setText(vm.name)
        self.previous_outdated = outdated

class VmUsageWidget (QWidget):
    def __init__(self, vm, parent = None):
        super (VmUsageWidget, self).__init__(parent)

        self.cpu_widget = QProgressBar()
        self.mem_widget = QProgressBar()
        self.cpu_widget.setMinimum(0)
        self.cpu_widget.setMaximum(100)
        self.mem_widget.setMinimum(0)
        self.mem_widget.setMaximum(qubes_host.memory_total/(1024*1024))
        self.mem_widget.setFormat ("%v MB");
        self.cpu_label = QLabel("CPU")
        self.mem_label = QLabel("MEM")

        layout_cpu = QHBoxLayout()
        layout_cpu.addWidget(self.cpu_label)
        layout_cpu.addWidget(self.cpu_widget)

        layout_mem = QHBoxLayout()
        layout_mem.addWidget(self.mem_label)
        layout_mem.addWidget(self.mem_widget)

        layout = QVBoxLayout()
        layout.addLayout(layout_cpu)
        layout.addLayout(layout_mem)

        self.setLayout(layout)

        self.update_load(vm)

    def update_load(self, vm):
        self.cpu_load = vm.get_cpu_total_load() if vm.last_power_state else 0
        self.mem_load = vm.get_mem()/(1024*1024) if vm.last_power_state else 0

        self.cpu_widget.setValue(self.cpu_load)
        self.mem_widget.setValue(self.mem_load)

    def resizeEvent(self, Event = None):
        label_width = max(self.mem_label.width(), self.cpu_label.width())
        self.mem_label.setMinimumWidth(label_width)
        self.cpu_label.setMinimumWidth(label_width)
        super (VmUsageWidget, self).resizeEvent(Event)

class LoadChartWidget (QWidget):

    def __init__(self, vm, parent = None):
        super (LoadChartWidget, self).__init__(parent)
        self.load = vm.get_cpu_total_load() if vm.last_power_state else 0
        assert self.load >= 0 and self.load <= 100, "load = {0}".format(self.load)
        self.load_history = [self.load]

    def update_load (self, vm):
        self.load = vm.get_cpu_total_load() if vm.last_power_state else 0
        assert self.load >= 0 and self.load <= 100, "load = {0}".format(self.load)
        self.load_history.append (self.load)
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
            hue = 200
            sat = 70 + val*(255-70)/100
            color = QColor.fromHsv (hue, sat, 255)
            pen = QPen (color)
            pen.setWidth(dx-1)
            p.setPen(pen)
            if val > 0:
                p.drawLine (W - i*dx - dx, H , W - i*dx - dx, H - (H - 5) * val/100)

class MemChartWidget (QWidget):

    def __init__(self, vm, parent = None):
        super (MemChartWidget, self).__init__(parent)
        self.load = vm.get_mem()*100/qubes_host.memory_total if vm.last_power_state else 0
        assert self.load >= 0 and self.load <= 100, "mem = {0}".format(self.load)
        self.load_history = [self.load]

    def update_load (self, vm):
        self.load = vm.get_mem()*100/qubes_host.memory_total if vm.last_power_state else 0
        assert self.load >= 0 and self.load <= 100, "load = {0}".format(self.load)
        self.load_history.append (self.load)
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
            hue = 120
            sat = 70 + val*(255-70)/100
            color = QColor.fromHsv (hue, sat, 255)
            pen = QPen (color)
            pen.setWidth(dx-1)
            p.setPen(pen)
            if val > 0:
                p.drawLine (W - i*dx - dx, H , W - i*dx - dx, H - (H - 5) * val/100)



class VmRowInTable(object):
    def __init__(self, vm, row_no, table):
        self.vm = vm
        self.row_no = row_no

        table.setRowHeight (row_no, VmManagerWindow.row_height)

        self.info_widget = VmInfoWidget(vm)
        table.setCellWidget(row_no, 0, self.info_widget)

        self.usage_widget = VmUsageWidget(vm)
        table.setCellWidget(row_no, 1, self.usage_widget)

        self.load_widget = LoadChartWidget(vm)
        table.setCellWidget(row_no, 2, self.load_widget)

        self.mem_widget = MemChartWidget(vm)
        table.setCellWidget(row_no, 3, self.mem_widget)


    def update(self, counter):
        self.info_widget.update_vm_state(self.vm)
        if counter % 3 == 0:
            self.usage_widget.update_load(self.vm)
            self.load_widget.update_load(self.vm)
            self.mem_widget.update_load(self.vm)
            self.info_widget.update_outdated(self.vm)

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
        if not vm.is_running():
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

class ThreadMonitor(QObject):
    def __init__(self):
        self.success = True
        self.error_msg = None
        self.event_finished = threading.Event()

    def set_error_msg(self, error_msg):
        self.success = False
        self.error_msg = error_msg
        self.set_finished()

    def is_finished(self):
        return self.event_finished.is_set()

    def set_finished(self):
        self.event_finished.set()


class VmManagerWindow(QMainWindow):
    columns_widths = [200, 200, 150, 150]
    row_height = 50
    max_visible_rows = 14
    update_interval = 1000 # in msec
    fw_rules_apply_check_interval = 5000
    show_inactive_vms = True
    columns_states = { 0: [0, 1], 1: [0, 2, 3] }

    def __init__(self, parent=None):
        super(VmManagerWindow, self).__init__(parent)


        self.action_createvm = self.createAction ("Create AppVM", slot=self.create_appvm,
                                             icon="createvm", tip="Create a new AppVM")

        self.action_removevm = self.createAction ("Remove AppVM", slot=self.remove_appvm,
                                             icon="removevm", tip="Remove an existing AppVM (must be stopped first)")

        self.action_resumevm = self.createAction ("Start/Resume VM", slot=self.resume_vm,
                                             icon="resumevm", tip="Start/Resusme a VM")

        self.action_pausevm = self.createAction ("Pause VM", slot=self.pause_vm,
                                             icon="pausevm", tip="Pause a running VM")

        self.action_shutdownvm = self.createAction ("Shutdown VM", slot=self.shutdown_vm,
                                             icon="shutdownvm", tip="Shutdown a running VM")

        self.action_updatevm = self.createAction ("Commit VM changes", slot=self.update_vm,
                                             icon="updateable", tip="Commit changes to template (only for 'updateable' template VMs); VM must be stopped")

        self.action_showallvms = self.createAction ("Show/Hide Inactive VMs", slot=self.toggle_inactive_view, checkable=True,
                                             icon="showallvms", tip="Show/Hide Inactive VMs")

        self.action_showcpuload = self.createAction ("Show/Hide CPU Load chart", slot=self.showcpuload, checkable=True,
                                             icon="showcpuload", tip="Show/Hide CPU Load chart")

        self.action_editfwrules = self.createAction ("Edit VM Firewall rules", slot=self.edit_fw_rules,
                                             icon="firewall", tip="Edit VM Firewall rules")


        self.action_removevm.setDisabled(True)
        self.action_resumevm.setDisabled(True)
        self.action_pausevm.setDisabled(True)
        self.action_shutdownvm.setDisabled(True)
        self.action_updatevm.setDisabled(True)

        self.action_showallvms.setChecked(self.show_inactive_vms)

        self.toolbar = self.addToolBar ("Toolbar")
        self.toolbar.setFloatable(False)
        self.addActions (self.toolbar, (self.action_createvm, self.action_removevm,
                                   None,
                                   self.action_resumevm, self.action_shutdownvm,
                                   self.action_editfwrules,
                                   None,
                                   self.action_showcpuload,
                                   self.action_showallvms,
                                   ))

        self.table = QTableWidget()
        self.setCentralWidget(self.table)
        self.table.clear()
        self.table.setColumnCount(len(VmManagerWindow.columns_widths))
        for (col, width) in enumerate (VmManagerWindow.columns_widths):
            self.table.setColumnWidth (col, width)

        self.table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setResizeMode(0, QHeaderView.Fixed)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().hide()
        self.table.setGridStyle(Qt.NoPen)
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        self.__cpugraphs = self.action_showcpuload.isChecked()
        self.update_table_columns()

        self.qvm_collection = QubesVmCollection()
        self.setWindowTitle("Qubes VM Manager")

        self.connect(self.table, SIGNAL("itemSelectionChanged()"), self.table_selection_changed)

        cur_pos = self.pos()
        self.setFixedWidth (self.get_minimum_table_width())
        self.fill_table()
        self.move(cur_pos)

        self.counter = 0
        self.shutdown_monitor = {}
        QTimer.singleShot (self.update_interval, self.update_table)
        QTimer.singleShot (self.fw_rules_apply_check_interval, self.check_apply_fw_rules)

    def set_table_geom_height(self):
        # TODO: '6' -- WTF?!
        tbl_H = self.toolbar.height() + 6 + \
                self.table.horizontalHeader().height() + 6

        n = self.table.rowCount();
        if n > VmManagerWindow.max_visible_rows:
            n = VmManagerWindow.max_visible_rows
        for i in range (0, n):
            tbl_H += self.table.rowHeight(i)

        self.setFixedHeight(tbl_H)


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


    def get_vms_list(self):
        self.qvm_collection.lock_db_for_reading()
        self.qvm_collection.load()
        self.qvm_collection.unlock_db()

        vms_list = [vm for vm in self.qvm_collection.values()]
        for vm in vms_list:
            vm.last_power_state = vm.is_running()

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
        self.table.clear()
        vms_list = self.get_vms_list()
        self.table.setRowCount(len(vms_list))

        vms_in_table = []

        row_no = 0
        for vm in vms_list:
            if (not self.show_inactive_vms) and (not vm.last_power_state):
                continue
            if vm.internal:
                continue
            vm_row = VmRowInTable (vm, row_no, self.table)
            vms_in_table.append (vm_row)
            row_no += 1

        self.table.setRowCount(row_no)
        self.set_table_geom_height()
        self.vms_list = vms_list
        self.vms_in_table = vms_in_table
        self.reload_table = False


    def mark_table_for_update(self):
        self.reload_table = True

    # When calling update_table() directly, always use out_of_schedule=True!
    def update_table(self, out_of_schedule=False):

        if manager_window.isVisible():
            some_vms_have_changed_power_state = False
            for vm in self.vms_list:
                state = vm.is_running();
                if vm.last_power_state != state:
                    vm.last_power_state = state
                    some_vms_have_changed_power_state = True

            if self.reload_table or ((not self.show_inactive_vms) and some_vms_have_changed_power_state): 
                self.fill_table()

            for vm_row in self.vms_in_table:
                vm_row.update(self.counter)

            self.table_selection_changed()

        if not out_of_schedule:
            self.counter += 1
            QTimer.singleShot (self.update_interval, self.update_table)

    def update_table_columns(self):
        state = 1 if self.__cpugraphs else 0
        columns = self.columns_states[state]

        for i in range(0, self.table.columnCount()):
            enabled = columns.count(i) > 0
            self.table.setColumnHidden(i, not enabled)

        self.setMinimumWidth(self.get_minimum_table_width())

    def table_selection_changed (self):
        vm = self.get_selected_vm()

        # Update available actions:

        self.action_removevm.setEnabled(not vm.installed_by_rpm and not vm.last_power_state)
        self.action_resumevm.setEnabled(not vm.last_power_state)
        self.action_pausevm.setEnabled(vm.last_power_state and vm.qid != 0)
        self.action_shutdownvm.setEnabled(not vm.is_netvm() and vm.last_power_state and vm.qid != 0)
        self.action_updatevm.setEnabled(vm.is_updateable() and not vm.last_power_state)
        self.action_editfwrules.setEnabled(vm.is_networked() and not (vm.is_netvm() and not vm.is_proxyvm()))

    def get_minimum_table_width(self):
        tbl_W = 0
        for (col, w) in enumerate(VmManagerWindow.columns_widths):
            if not self.table.isColumnHidden(col):
                tbl_W += w

        return tbl_W

    def closeEvent (self, event):
        if event.spontaneous(): # There is something borked in Qt, as the logic here is inverted on X11
            self.hide()
            event.ignore()

    def create_appvm(self):
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
            if vm is self.qvm_collection.get_default_template_vm():
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
            vm.add_to_xen_storage()
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
        row_index = self.table.currentRow()
        assert self.vms_in_table[row_index] is not None
        vm = self.vms_in_table[row_index].vm
        return vm

    def remove_appvm(self):
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
            if vm.is_template() and qvm_collection.default_template_qid == vm.qid:
                qvm_collection.default_template_qid = None
            if vm.is_netvm() and qvm_collection.default_netvm_qid == vm.qid:
                qvm_collection.default_netvm_qid = None

            vm.remove_from_xen_storage()
            vm.remove_from_disk()
            self.qvm_collection.pop(vm.qid)
            self.qvm_collection.save()
        except Exception as ex:
            thread_monitor.set_error_msg (str(ex))
        finally:
            self.qvm_collection.unlock_db()

        thread_monitor.set_finished()

    def resume_vm(self):
        vm = self.get_selected_vm()
        assert not vm.is_running()

        if vm.is_paused():
            try:
                subprocess.check_call (["/usr/sbin/xm", "unpause", vm.name])
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
 
    def pause_vm(self):
        vm = self.get_selected_vm()
        assert vm.is_running()
        try:
            subprocess.check_call (["/usr/sbin/xm", "pause", vm.name])
        except Exception as ex:
            QMessageBox.warning (None, "Error pausing VM!", "ERROR: {0}".format(ex))
            return

    def shutdown_vm(self):
        vm = self.get_selected_vm()
        assert vm.is_running()

        reply = QMessageBox.question(None, "VM Shutdown Confirmation",
                                     "Are you sure you want to power down the VM <b>'{0}'</b>?<br>"
                                     "<small>This will shutdown all the running applications within this VM.</small>".format(vm.name),
                                     QMessageBox.Yes | QMessageBox.Cancel)

        app.processEvents()

        if reply == QMessageBox.Yes:
            try:
                subprocess.check_call (["/usr/sbin/xm", "shutdown", vm.name])
            except Exception as ex:
                QMessageBox.warning (None, "Error shutting down VM!", "ERROR: {0}".format(ex))
                return

            trayIcon.showMessage ("Qubes Manager", "VM '{0}' is shutting down...".format(vm.name), msecs=3000)
            self.shutdown_monitor[vm.qid] = VmShutdownMonitor (vm)
            QTimer.singleShot (vm_shutdown_timeout, self.shutdown_monitor[vm.qid].check_if_vm_has_shutdown)

    def update_vm(self):
        vm = self.get_selected_vm()
        assert not vm.is_running()

        reply = QMessageBox.question(None, "VM Update Confirmation",
                                     "Are you sure you want to commit template <b>'{0}'</b> changes?<br>"
                                     "<small>AppVMs will see the changes after restart.</small>".format(vm.name),
                                     QMessageBox.Yes | QMessageBox.Cancel)

        app.processEvents()

        if reply == QMessageBox.Yes:
            try:
                vm.commit_changes();
            except Exception as ex:
                QMessageBox.warning (None, "Error commiting changes!", "ERROR: {0}".format(ex))
                return
            trayIcon.showMessage ("Qubes Manager", "Changes to template '{0}' commited.".format(vm.name), msecs=3000)

    def showcpuload(self):
        self.__cpugraphs = self.action_showcpuload.isChecked()
        self.update_table_columns()

    def toggle_inactive_view(self):
        self.show_inactive_vms = self.action_showallvms.isChecked()
        self.mark_table_for_update()
        self.update_table(out_of_schedule = True)

    def edit_fw_rules(self):
        vm = self.get_selected_vm()
        dialog = EditFwRulesDlg()
        model = QubesFirewallRulesModel()
        model.set_vm(vm)
        dialog.set_model(model)

        if vm.netvm_vm is not None and not vm.netvm_vm.is_proxyvm():
            QMessageBox.warning (None, "VM configuration problem!", "The '{0}' AppVM is not network connected to a FirewallVM!<p>".format(vm.name) +\
                    "You may edit the '{0}' VM firewall rules, but these will not take any effect until you connect it to a working Firewall VM.".format(vm.name))

        if dialog.exec_():
            model.apply_rules()

    def check_apply_fw_rules(self):
        qvm_collection = QubesVmCollection()
        qvm_collection.lock_db_for_reading()
        qvm_collection.load()
        qvm_collection.unlock_db()

        for vm in qvm_collection.values():
            if vm.is_proxyvm() and vm.is_running():
                error_file = "/local/domain/{0}/qubes_iptables_error".format(vm.get_xid())

                error = subprocess.Popen(
                        ["/usr/bin/xenstore-read", error_file],
                        stdout=subprocess.PIPE).communicate()[0]
                error = error.strip(" \n\t")
                if error != "":
                    vm.rules_applied = False
                    trayIcon.showMessage (
                            "Error applying firewall rules on '{0}'!".format(vm.name),
                            "ERROR: {0}".format(error.decode('string_escape')),
                            QSystemTrayIcon.Critical
                        )
                    retcode = subprocess.check_call (
                            ["/usr/bin/xenstore-write", error_file, ""])
                else:
                    vm.rules_applied = True

        QTimer.singleShot(self.fw_rules_apply_check_interval, self.check_apply_fw_rules)

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


def show_manager():
    manager_window.show()

def toggle_manager():
    if manager_window.isVisible():
        manager_window.hide()
    else:
        manager_window.show()

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

    QMessageBox.critical(None, "Houston, we have a problem...",
                         "Whoops. A critical error has occured. This is most likely a bug "
                         "in Qubes Manager.<br><br>"
                         "<b><i>%s</i></b>" % error +
                         "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
                         % ( line, filename ))

    #sys.exit(1)

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

