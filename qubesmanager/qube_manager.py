#!/usr/bin/python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski-Górecki
#                       <marmarek@invisiblethingslab.com>
# Copyright (C) 2017  Wojtek Porczyk <woju@invisiblethingslab.com>
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

import sys
import os
import os.path
import subprocess
import time
from datetime import datetime, timedelta
import traceback

from qubesadmin import Qubes
from qubesadmin import exc

from PyQt4 import QtGui  # pylint: disable=import-error
from PyQt4 import QtCore  # pylint: disable=import-error

from . import ui_qubemanager  # pylint: disable=no-name-in-module
from . import thread_monitor
from . import table_widgets
from . import settings
from . import global_settings
from . import restore
from . import backup
from . import log_dialog
import threading

from qubesmanager.about import AboutDialog


class SearchBox(QtGui.QLineEdit):
    def __init__(self, parent=None):
        super(SearchBox, self).__init__(parent)
        self.focusing = False

    def focusInEvent(self, e):  # pylint: disable=invalid-name
        super(SearchBox, self).focusInEvent(e)
        self.selectAll()
        self.focusing = True

    def mousePressEvent(self, e):  # pylint: disable=invalid-name
        super(SearchBox, self).mousePressEvent(e)
        if self.focusing:
            self.selectAll()
            self.focusing = False


class VmRowInTable(object):
    # pylint: disable=too-few-public-methods

    def __init__(self, vm, row_no, table):
        self.vm = vm
        self.row_no = row_no
        # TODO: replace a various different widgets with a more generic
        # VmFeatureWidget or VMPropertyWidget

        table_widgets.row_height = VmManagerWindow.row_height
        table.setRowHeight(row_no, VmManagerWindow.row_height)

        self.type_widget = table_widgets.VmTypeWidget(vm)
        table.setCellWidget(row_no, VmManagerWindow.columns_indices['Type'],
                            self.type_widget)
        table.setItem(row_no, VmManagerWindow.columns_indices['Type'],
                      self.type_widget.table_item)

        self.label_widget = table_widgets.VmLabelWidget(vm)
        table.setCellWidget(row_no, VmManagerWindow.columns_indices['Label'],
                            self.label_widget)
        table.setItem(row_no, VmManagerWindow.columns_indices['Label'],
                      self.label_widget.table_item)

        self.name_widget = table_widgets.VmNameItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices['Name'],
                      self.name_widget)

        self.info_widget = table_widgets.VmInfoWidget(vm)
        table.setCellWidget(row_no, VmManagerWindow.columns_indices['State'],
                            self.info_widget)
        table.setItem(row_no, VmManagerWindow.columns_indices['State'],
                      self.info_widget.table_item)

        self.template_widget = table_widgets.VmTemplateItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices['Template'],
                      self.template_widget)

        self.netvm_widget = table_widgets.VmNetvmItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices['NetVM'],
                      self.netvm_widget)

        self.size_widget = table_widgets.VmSizeOnDiskItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices['Size'],
                      self.size_widget)

        self.internal_widget = table_widgets.VmInternalItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices['Internal'],
                      self.internal_widget)

        self.ip_widget = table_widgets.VmIPItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices['IP'],
                      self.ip_widget)

        self.include_in_backups_widget = \
            table_widgets.VmIncludeInBackupsItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices[
            'Backups'], self.include_in_backups_widget)

        self.last_backup_widget = table_widgets.VmLastBackupItem(vm)
        table.setItem(row_no, VmManagerWindow.columns_indices[
            'Last backup'], self.last_backup_widget)

    def update(self, update_size_on_disk=False):
        """
        Update info in a single VM row
        :param update_size_on_disk: should disk utilization be updated? the
        widget will extract the data from VM object
        :return: None
        """
        self.info_widget.update_vm_state(self.vm)
        if update_size_on_disk:
            self.size_widget.update()


vm_shutdown_timeout = 20000  # in msec
vm_restart_check_timeout = 1000  # in msec


class VmShutdownMonitor(QtCore.QObject):
    def __init__(self, vm, shutdown_time=vm_shutdown_timeout,
                 check_time=vm_restart_check_timeout,
                 and_restart=False, caller=None):
        QtCore.QObject.__init__(self)
        self.vm = vm
        self.shutdown_time = shutdown_time
        self.check_time = check_time
        self.and_restart = and_restart
        self.shutdown_started = datetime.now()
        self.caller = caller

    def restart_vm_if_needed(self):
        if self.and_restart and self.caller:
            self.caller.start_vm(self.vm)

    def check_again_later(self):
        # noinspection PyTypeChecker,PyCallByClass
        QtCore.QTimer.singleShot(self.check_time, self.check_if_vm_has_shutdown)

    def timeout_reached(self):
        actual = datetime.now() - self.shutdown_started
        allowed = timedelta(milliseconds=self.shutdown_time)

        return actual > allowed

    def check_if_vm_has_shutdown(self):
        vm = self.vm
        vm_is_running = vm.is_running()
        try:
            vm_start_time = datetime.fromtimestamp(float(vm.start_time))
        except (AttributeError, TypeError, ValueError):
            vm_start_time = None

        if vm_is_running and vm_start_time \
                and vm_start_time < self.shutdown_started:
            if self.timeout_reached():
                reply = QtGui.QMessageBox.question(
                    None, self.tr("Qube Shutdown"),
                    self.tr(
                        "The Qube <b>'{0}'</b> hasn't shutdown within the last "
                        "{1} seconds, do you want to kill it?<br>").format(
                        vm.name, self.shutdown_time / 1000),
                    self.tr("Kill it!"),
                    self.tr("Wait another {0} seconds...").format(
                        self.shutdown_time / 1000))
                if reply == 0:
                    vm.force_shutdown()
                    self.restart_vm_if_needed()
                else:
                    self.shutdown_started = datetime.now()
                    self.check_again_later()
            else:
                self.check_again_later()
        else:
            if vm_is_running:
                # Due to unknown reasons, Xen sometimes reports that a domain
                # is running even though its start-up timestamp is not valid.
                # Make sure that "restart_vm_if_needed" is not called until
                # the domain has been completely shut down according to Xen.
                self.check_again_later()
                return

            self.restart_vm_if_needed()


class VmManagerWindow(ui_qubemanager.Ui_VmManagerWindow, QtGui.QMainWindow):
    # pylint: disable=too-many-instance-attributes
    row_height = 30
    column_width = 200
    search = ""
    # suppress saving settings while initializing widgets
    settings_loaded = False
    columns_indices = {"Type": 0,
                       "Label": 1,
                       "Name": 2,
                       "State": 3,
                       "Template": 4,
                       "NetVM": 5,
                       "Size": 6,
                       "Internal": 7,
                       "IP": 8,
                       "Backups": 9,
                       "Last backup": 10,
                       }

    def __init__(self, qubes_app, qt_app, parent=None):
        # pylint: disable=unused-argument
        super(VmManagerWindow, self).__init__()
        self.setupUi(self)

        self.manager_settings = QtCore.QSettings(self)

        self.qubes_app = qubes_app
        self.qt_app = qt_app

        self.searchbox = SearchBox()
        self.searchbox.setValidator(QtGui.QRegExpValidator(
            QtCore.QRegExp("[a-zA-Z0-9-]*", QtCore.Qt.CaseInsensitive), None))
        self.searchContainer.addWidget(self.searchbox)

        self.connect(self.table, QtCore.SIGNAL("itemSelectionChanged()"),
                     self.table_selection_changed)

        self.table.setColumnWidth(0, self.column_width)

        self.sort_by_column = "Type"
        self.sort_order = QtCore.Qt.AscendingOrder

        self.vms_list = []
        self.vms_in_table = {}

        self.frame_width = 0
        self.frame_height = 0

        self.move(self.x(), 0)

        self.columns_actions = {
            self.columns_indices["Type"]: self.action_vm_type,
            self.columns_indices["Label"]: self.action_label,
            self.columns_indices["Name"]: self.action_name,
            self.columns_indices["State"]: self.action_state,
            self.columns_indices["Template"]: self.action_template,
            self.columns_indices["NetVM"]: self.action_netvm,
            self.columns_indices["Size"]: self.action_size_on_disk,
            self.columns_indices["Internal"]: self.action_internal,
            self.columns_indices["IP"]: self
                .action_ip, self.columns_indices["Backups"]: self
                .action_backups, self.columns_indices["Last backup"]: self
            .action_last_backup
        }

        self.visible_columns_count = len(self.columns_indices)

        self.table.setColumnWidth(self.columns_indices["State"], 80)
        self.table.setColumnWidth(self.columns_indices["Name"], 150)
        self.table.setColumnWidth(self.columns_indices["Label"], 40)
        self.table.setColumnWidth(self.columns_indices["Type"], 40)
        self.table.setColumnWidth(self.columns_indices["Size"], 100)
        self.table.setColumnWidth(self.columns_indices["Internal"], 60)
        self.table.setColumnWidth(self.columns_indices["IP"], 100)
        self.table.setColumnWidth(self.columns_indices["Backups"], 60)
        self.table.setColumnWidth(self.columns_indices["Last backup"], 90)

        self.table.horizontalHeader().setResizeMode(
            QtGui.QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.table.sortItems(self.columns_indices[self.sort_by_column],
                             self.sort_order)

        self.context_menu = QtGui.QMenu(self)

        self.context_menu.addAction(self.action_settings)
        self.context_menu.addAction(self.action_editfwrules)
        self.context_menu.addAction(self.action_appmenus)
        self.context_menu.addAction(self.action_set_keyboard_layout)
        self.context_menu.addSeparator()

        self.context_menu.addAction(self.action_updatevm)
        self.context_menu.addAction(self.action_run_command_in_vm)
        self.context_menu.addAction(self.action_resumevm)
        self.context_menu.addAction(self.action_startvm_tools_install)
        self.context_menu.addAction(self.action_pausevm)
        self.context_menu.addAction(self.action_shutdownvm)
        self.context_menu.addAction(self.action_restartvm)
        self.context_menu.addAction(self.action_killvm)
        self.context_menu.addSeparator()

        self.context_menu.addAction(self.action_clonevm)
        self.context_menu.addAction(self.action_removevm)
        self.context_menu.addSeparator()

        self.context_menu.addMenu(self.logs_menu)
        self.context_menu.addSeparator()

        self.tools_context_menu = QtGui.QMenu(self)
        self.tools_context_menu.addAction(self.action_toolbar)
        self.tools_context_menu.addAction(self.action_menubar)

        self.connect(
            self.table.horizontalHeader(),
            QtCore.SIGNAL("sortIndicatorChanged(int, Qt::SortOrder)"),
            self.sort_indicator_changed)
        self.connect(self.table,
                     QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
                     self.open_context_menu)
        self.connect(self.menubar,
                     QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
                     lambda pos: self.open_tools_context_menu(self.menubar,
                                                              pos))
        self.connect(self.toolbar,
                     QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
                     lambda pos: self.open_tools_context_menu(self.toolbar,
                                                              pos))
        self.connect(self.logs_menu, QtCore.SIGNAL("triggered(QAction *)"),
                     self.show_log)

        self.connect(self.searchbox,
                     QtCore.SIGNAL("textChanged(const QString&)"),
                     self.do_search)

        self.table.setContentsMargins(0, 0, 0, 0)
        self.centralwidget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.connect(self.action_menubar, QtCore.SIGNAL("toggled(bool)"),
                     self.showhide_menubar)
        self.connect(self.action_toolbar, QtCore.SIGNAL("toggled(bool)"),
                     self.showhide_toolbar)

        self.load_manager_settings()

        self.fill_table()

        self.counter = 0
        self.update_size_on_disk = False
        self.shutdown_monitor = {}

    def load_manager_settings(self):
        # visible columns
        self.visible_columns_count = 0
        for col in self.columns_indices:
            col_no = self.columns_indices[col]
            visible = self.manager_settings.value(
                'columns/%s' % col,
                defaultValue="true")
            self.columns_actions[col_no].setChecked(visible == "true")
            self.visible_columns_count += 1

        self.sort_by_column = str(
            self.manager_settings.value("view/sort_column",
                                        defaultValue=self.sort_by_column))
        self.sort_order = QtCore.Qt.SortOrder(
            self.manager_settings.value("view/sort_order",
                                        defaultValue=self.sort_order))
        self.table.sortItems(self.columns_indices[self.sort_by_column],
                             self.sort_order)
        if not self.manager_settings.value("view/menubar_visible",
                                           defaultValue=True):
            self.action_menubar.setChecked(False)
        if not self.manager_settings.value("view/toolbar_visible",
                                           defaultValue=True):
            self.action_toolbar.setChecked(False)
        self.settings_loaded = True

    def get_vms_list(self):
        return [vm for vm in self.qubes_app.domains]

    def update_single_row(self, vm):
        if vm in self.qubes_app.domains:
            self.vms_in_table[vm.qid].update()

    def fill_table(self):
        # save current selection
        row_index = self.table.currentRow()
        selected_qid = -1
        if row_index != -1:
            vm_item = self.table.item(row_index, self.columns_indices["Name"])
            if vm_item:
                selected_qid = vm_item.qid

        self.table.setSortingEnabled(False)
        self.table.clearContents()
        vms_list = self.get_vms_list()

        vms_in_table = {}

        row_no = 0
        for vm in vms_list:
            vm_row = VmRowInTable(vm, row_no, self.table)
            vms_in_table[vm.qid] = vm_row

            row_no += 1

        self.table.setRowCount(row_no)
        self.vms_list = vms_list
        self.vms_in_table = vms_in_table
        if selected_qid in vms_in_table.keys():
            self.table.setCurrentItem(
                self.vms_in_table[selected_qid].name_widget)
        self.table.setSortingEnabled(True)

        self.showhide_vms()

    def showhide_vms(self):
        if not self.search:
            for row_no in range(self.table.rowCount()):
                self.table.setRowHidden(row_no, False)
        else:
            for row_no in range(self.table.rowCount()):
                widget = self.table.cellWidget(row_no,
                                               self.columns_indices["State"])
                show = (self.search in widget.vm.name)
                self.table.setRowHidden(row_no, not show)

    @QtCore.pyqtSlot(str)
    def do_search(self, search):
        self.search = str(search)
        self.showhide_vms()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_search_triggered')
    def action_search_triggered(self):
        self.searchbox.setFocus()

    def update_table(self):

        self.fill_table()
        # TODO: instead of manually refreshing the entire table, use dbus events

        # reapply sorting
        if self.sort_by_column:
            self.table.sortByColumn(self.columns_indices[self.sort_by_column])

        self.table_selection_changed()

    # noinspection PyPep8Naming
    def sort_indicator_changed(self, column, order):
        self.sort_by_column = [name for name in self.columns_indices if
                               self.columns_indices[name] == column][0]
        self.sort_order = order
        if self.settings_loaded:
            self.manager_settings.setValue('view/sort_column',
                                           self.sort_by_column)
            self.manager_settings.setValue('view/sort_order', self.sort_order)
            self.manager_settings.sync()

    def table_selection_changed(self):

        vm = self.get_selected_vm()

        if vm is not None and vm in self.qubes_app.domains:

            #  TODO: add boot from device to menu and add windows tools there
            # Update available actions:
            self.action_settings.setEnabled(vm.klass != 'AdminVM')
            self.action_removevm.setEnabled(
                vm.klass != 'AdminVM' and not vm.is_running())
            self.action_clonevm.setEnabled(vm.klass != 'AdminVM')
            self.action_resumevm.setEnabled(
                not vm.is_running() or vm.get_power_state() == "Paused")
            self.action_pausevm.setEnabled(
                vm.is_running() and vm.get_power_state() != "Paused"
                and vm.klass != 'AdminVM')
            self.action_shutdownvm.setEnabled(
                vm.is_running() and vm.get_power_state() != "Paused"
                and vm.klass != 'AdminVM')
            self.action_restartvm.setEnabled(
                vm.is_running() and vm.get_power_state() != "Paused"
                and vm.klass != 'AdminVM' and vm.klass != 'DispVM')
            self.action_killvm.setEnabled(
                (vm.get_power_state() == "Paused" or vm.is_running())
                and vm.klass != 'AdminVM')

            self.action_appmenus.setEnabled(
                vm.klass != 'AdminVM' and vm.klass != 'DispVM'
                and not vm.features.get('internal', False))
            self.action_editfwrules.setEnabled(vm.klass != 'AdminVM')
            self.action_updatevm.setEnabled(getattr(vm, 'updateable', False)
                                            or vm.qid == 0)
            self.action_run_command_in_vm.setEnabled(
                not vm.get_power_state() == "Paused" and vm.qid != 0)
            self.action_set_keyboard_layout.setEnabled(
                vm.qid != 0 and
                vm.get_power_state() != "Paused" and vm.is_running())

            self.update_single_row(vm)
        else:
            self.action_settings.setEnabled(False)
            self.action_removevm.setEnabled(False)
            self.action_clonevm.setEnabled(False)
            self.action_resumevm.setEnabled(False)
            self.action_pausevm.setEnabled(False)
            self.action_shutdownvm.setEnabled(False)
            self.action_restartvm.setEnabled(False)
            self.action_killvm.setEnabled(False)
            self.action_appmenus.setEnabled(False)
            self.action_editfwrules.setEnabled(False)
            self.action_updatevm.setEnabled(False)
            self.action_run_command_in_vm.setEnabled(False)
            self.action_set_keyboard_layout.setEnabled(False)

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_createvm_triggered')
    def action_createvm_triggered(self):  # pylint: disable=no-self-use
        subprocess.check_call('qubes-vm-create')

    def get_selected_vm(self):
        # vm selection relies on the VmInfo widget's value used
        # for sorting by VM name
        row_index = self.table.currentRow()
        if row_index != -1:
            vm_item = self.table.item(row_index, self.columns_indices["Name"])
            # here is possible race with update_table timer so check
            # if really got the item
            if vm_item is None:
                return None
            qid = vm_item.qid
            assert self.vms_in_table[qid] is not None
            vm = self.vms_in_table[qid].vm
            return vm
        else:
            return None

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_removevm_triggered')
    def action_removevm_triggered(self):

        vm = self.get_selected_vm()

        if vm.klass == 'TemplateVM':
            dependent_vms = 0
            for single_vm in self.qubes_app.domains:
                if getattr(single_vm, 'template', None) == vm:
                    dependent_vms += 1
            if dependent_vms > 0:
                QtGui.QMessageBox.warning(
                    None, self.tr("Warning!"),
                    self.tr("This Template Qube cannot be removed, "
                            "because there is at least one Qube that is based "
                            "on it.<br><small>If you want to remove this "
                            "Template Qube and all the Qubes based on it, you "
                            "should first remove each individual Qube that "
                            "uses this template.</small>"))
                return

        (requested_name, ok) = QtGui.QInputDialog.getText(
            None, self.tr("Qube Removal Confirmation"),
            self.tr("Are you sure you want to remove the Qube <b>'{0}'</b>"
                    "?<br> All data on this Qube's private storage will be "
                    "lost!<br><br>Type the name of the Qube (<b>{1}</b>) below "
                    "to confirm:").format(vm.name, vm.name))

        if not ok:
            # user clicked cancel
            return

        elif requested_name != vm.name:
            # name did not match
            QtGui.QMessageBox.warning(
                None,
                self.tr("Qube removal confirmation failed"),
                self.tr(
                    "Entered name did not match! Not removing "
                    "{0}.").format(vm.name))
            return

        else:
            # remove the VM
            t_monitor = thread_monitor.ThreadMonitor()
            thread = threading.Thread(target=self.do_remove_vm,
                                      args=(vm, self.qubes_app, t_monitor))
            thread.daemon = True
            thread.start()

            progress = QtGui.QProgressDialog(
                self.tr(
                    "Removing Qube: <b>{0}</b>...").format(vm.name), "", 0, 0)
            progress.setCancelButton(None)
            progress.setModal(True)
            progress.show()

            while not t_monitor.is_finished():
                self.qt_app.processEvents()
                time.sleep(0.1)

            progress.hide()

            if t_monitor.success:
                pass
            else:
                QtGui.QMessageBox.warning(None, self.tr("Error removing Qube!"),
                                          self.tr("ERROR: {0}").format(
                                              t_monitor.error_msg))

            self.update_table()

    @staticmethod
    def do_remove_vm(vm, qubes_app, t_monitor):
        try:
            del qubes_app.domains[vm.name]
        except exc.QubesException as ex:
            t_monitor.set_error_msg(str(ex))

        t_monitor.set_finished()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_clonevm_triggered')
    def action_clonevm_triggered(self):
        vm = self.get_selected_vm()

        name_number = 1
        name_format = vm.name + '-clone-%d'
        while name_format % name_number in self.qubes_app.domains.keys():
            name_number += 1

        (clone_name, ok) = QtGui.QInputDialog.getText(
            self, self.tr('Qubes clone Qube'),
            self.tr('Enter name for Qube <b>{}</b> clone:').format(vm.name),
            text=(name_format % name_number))
        if not ok or clone_name == "":
            return

        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(target=self.do_clone_vm,
                                  args=(vm, self.qubes_app,
                                        clone_name, t_monitor))
        thread.daemon = True
        thread.start()

        progress = QtGui.QProgressDialog(
            self.tr("Cloning Qube <b>{0}</b> to <b>{1}</b>...").format(
                vm.name, clone_name), "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not t_monitor.is_finished():
            self.qt_app.processEvents()
            time.sleep(0.2)

        progress.hide()

        if not t_monitor.success:
            QtGui.QMessageBox.warning(
                None,
                self.tr("Error while cloning Qube"),
                self.tr("Exception while cloning:<br>{0}").format(
                    t_monitor.error_msg))

        self.update_table()

    @staticmethod
    def do_clone_vm(src_vm, qubes_app, dst_name, t_monitor):
        dst_vm = None
        try:
            dst_vm = qubes_app.clone_vm(src_vm, dst_name)
        except exc.QubesException as ex:
            t_monitor.set_error_msg(str(ex))
            if dst_vm:
                pass
        t_monitor.set_finished()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_resumevm_triggered')
    def action_resumevm_triggered(self):
        vm = self.get_selected_vm()

        if vm.get_power_state() in ["Paused", "Suspended"]:
            try:
                vm.unpause()
            except exc.QubesException as ex:
                QtGui.QMessageBox.warning(
                    None, self.tr("Error unpausing Qube!"),
                    self.tr("ERROR: {0}").format(ex))
            return

        self.start_vm(vm)
        self.update_single_row(vm)

    def start_vm(self, vm):
        if vm.is_running():
            return
        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(target=self.do_start_vm,
                                  args=(vm, t_monitor))
        thread.daemon = True
        thread.start()

        while not t_monitor.is_finished():
            self.qt_app.processEvents()
            time.sleep(0.1)

        if not t_monitor.success:
            QtGui.QMessageBox.warning(
                None,
                self.tr("Error starting Qube!"),
                self.tr("ERROR: {0}").format(t_monitor.error_msg))

        self.update_single_row(vm)

    @staticmethod
    def do_start_vm(vm, t_monitor):
        try:
            vm.start()
        except exc.QubesException as ex:
            t_monitor.set_error_msg(str(ex))
            t_monitor.set_finished()
            return

        t_monitor.set_finished()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_startvm_tools_install_triggered')
    # TODO: replace with boot from device
    def action_startvm_tools_install_triggered(self):
        # pylint: disable=invalid-name
        pass

    @QtCore.pyqtSlot(name='on_action_pausevm_triggered')
    def action_pausevm_triggered(self):
        vm = self.get_selected_vm()
        assert vm.is_running()
        try:
            vm.pause()
            self.update_single_row(vm)
        except exc.QubesException as ex:
            QtGui.QMessageBox.warning(
                None,
                self.tr("Error pausing Qube!"),
                self.tr("ERROR: {0}").format(ex))
            return

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_shutdownvm_triggered')
    def action_shutdownvm_triggered(self):
        vm = self.get_selected_vm()
        assert vm.is_running()

        reply = QtGui.QMessageBox.question(
            None, self.tr("Qube Shutdown Confirmation"),
            self.tr("Are you sure you want to power down the Qube"
                    " <b>'{0}'</b>?<br><small>This will shutdown all the "
                    "running applications within this Qube.</small>").format(
                vm.name), QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel)

        self.qt_app.processEvents()

        if reply == QtGui.QMessageBox.Yes:
            self.shutdown_vm(vm)

        self.update_single_row(vm)

    def shutdown_vm(self, vm, shutdown_time=vm_shutdown_timeout,
                    check_time=vm_restart_check_timeout, and_restart=False):
        try:
            vm.shutdown()
        except exc.QubesException as ex:
            QtGui.QMessageBox.warning(
                None,
                self.tr("Error shutting down Qube!"),
                self.tr("ERROR: {0}").format(ex))
            return

        self.shutdown_monitor[vm.qid] = VmShutdownMonitor(vm, shutdown_time,
                                                          check_time,
                                                          and_restart, self)
        # noinspection PyCallByClass,PyTypeChecker
        QtCore.QTimer.singleShot(check_time, self.shutdown_monitor[
            vm.qid].check_if_vm_has_shutdown)

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_restartvm_triggered')
    def action_restartvm_triggered(self):
        vm = self.get_selected_vm()
        assert vm.is_running()

        reply = QtGui.QMessageBox.question(
            None, self.tr("Qube Restart Confirmation"),
            self.tr("Are you sure you want to restart the Qube <b>'{0}'</b>?"
                    "<br><small>This will shutdown all the running "
                    "applications within this Qube.</small>").format(vm.name),
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel)

        self.qt_app.processEvents()

        if reply == QtGui.QMessageBox.Yes:
            self.shutdown_vm(vm, and_restart=True)

        self.update_single_row(vm)

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_killvm_triggered')
    def action_killvm_triggered(self):
        vm = self.get_selected_vm()
        assert vm.is_running() or vm.is_paused()

        reply = QtGui.QMessageBox.question(
            None, self.tr("Qube Kill Confirmation"),
            self.tr("Are you sure you want to kill the Qube <b>'{0}'</b>?<br>"
                    "<small>This will end <b>(not shutdown!)</b> all the "
                    "running applications within this Qube.</small>").format(
                vm.name),
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel,
            QtGui.QMessageBox.Cancel)

        self.qt_app.processEvents()

        if reply == QtGui.QMessageBox.Yes:
            try:
                vm.force_shutdown()
            except exc.QubesException as ex:
                QtGui.QMessageBox.critical(
                    None, self.tr("Error while killing Qube!"),
                    self.tr(
                        "<b>An exception ocurred while killing {0}.</b><br>"
                        "ERROR: {1}").format(vm.name, ex))
                return

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_settings_triggered')
    def action_settings_triggered(self):
        vm = self.get_selected_vm()
        if vm:
            settings_window = settings.VMSettingsWindow(
                vm, self.qt_app, "basic")
            settings_window.exec_()
            self.update_single_row(vm)

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_appmenus_triggered')
    def action_appmenus_triggered(self):
        vm = self.get_selected_vm()
        if vm:
            settings_window = settings.VMSettingsWindow(
                vm, self.qt_app, "applications")
            settings_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_refresh_list_triggered')
    def action_refresh_list_triggered(self):
        self.qubes_app.domains.clear_cache()
        self.update_table()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_updatevm_triggered')
    def action_updatevm_triggered(self):
        vm = self.get_selected_vm()

        if not vm.is_running():
            reply = QtGui.QMessageBox.question(
                None, self.tr("Qube Update Confirmation"),
                self.tr(
                    "<b>{0}</b><br>The Qube has to be running to be updated."
                    "<br>Do you want to start it?<br>").format(vm.name),
                QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel)
            if reply != QtGui.QMessageBox.Yes:
                return

        self.qt_app.processEvents()

        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(target=self.do_update_vm,
                                  args=(vm, t_monitor))
        thread.daemon = True
        thread.start()

        progress = QtGui.QProgressDialog(
                self.tr(
                    "<b>{0}</b><br>Please wait for the updater to "
                    "launch...").format(vm.name), "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not t_monitor.is_finished():
            self.qt_app.processEvents()
            time.sleep(0.2)

        progress.hide()

        if vm.qid != 0:
            if not t_monitor.success:
                QtGui.QMessageBox.warning(
                    None,
                    self.tr("Error on Qube update!"),
                    self.tr("ERROR: {0}").format(t_monitor.error_msg))

        self.update_single_row(vm)

    @staticmethod
    def do_update_vm(vm, t_monitor):
        try:
            if vm.qid == 0:
                subprocess.check_call(
                    ["/usr/bin/qubes-dom0-update", "--clean", "--gui"])
            else:
                if not vm.is_running():
                    vm.start()
                vm.run_service("qubes.InstallUpdatesGUI",
                               user="root", wait=False)
        except (ChildProcessError, exc.QubesException) as ex:
            t_monitor.set_error_msg(str(ex))
            t_monitor.set_finished()
            return
        t_monitor.set_finished()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_run_command_in_vm_triggered')
    def action_run_command_in_vm_triggered(self):
        # pylint: disable=invalid-name
        vm = self.get_selected_vm()

        (command_to_run, ok) = QtGui.QInputDialog.getText(
            self, self.tr('Qubes command entry'),
            self.tr('Run command in <b>{}</b>:').format(vm.name))
        if not ok or command_to_run == "":
            return
        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(target=self.do_run_command_in_vm, args=(
            vm, command_to_run, t_monitor))
        thread.daemon = True
        thread.start()

        while not t_monitor.is_finished():
            self.qt_app.processEvents()
            time.sleep(0.2)

        if not t_monitor.success:
            QtGui.QMessageBox.warning(
                None, self.tr("Error while running command"),
                self.tr("Exception while running command:<br>{0}").format(
                    t_monitor.error_msg))

    @staticmethod
    def do_run_command_in_vm(vm, command_to_run, t_monitor):
        try:
            vm.run(command_to_run)
        except (ChildProcessError, exc.QubesException) as ex:
            t_monitor.set_error_msg(str(ex))
        t_monitor.set_finished()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_set_keyboard_layout_triggered')
    def action_set_keyboard_layout_triggered(self):
        # pylint: disable=invalid-name
        vm = self.get_selected_vm()
        vm.run('qubes-change-keyboard-layout')

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_editfwrules_triggered')
    def action_editfwrules_triggered(self):
        vm = self.get_selected_vm()
        settings_window = settings.VMSettingsWindow(vm, self.qt_app, "firewall")
        settings_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_global_settings_triggered')
    def action_global_settings_triggered(self):  # pylint: disable=invalid-name
        global_settings_window = global_settings.GlobalSettingsWindow(
            self.qt_app,
            self.qubes_app)
        global_settings_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_show_network_triggered')
    def action_show_network_triggered(self):
        pass
        # TODO: revive for 4.1
        # network_notes_dialog = NetworkNotesDialog()
        # network_notes_dialog.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_restore_triggered')
    def action_restore_triggered(self):
        restore_window = restore.RestoreVMsWindow(self.qt_app, self.qubes_app)
        restore_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_backup_triggered')
    def action_backup_triggered(self):
        backup_window = backup.BackupVMsWindow(self.qt_app, self.qubes_app)
        backup_window.exec_()

    def showhide_menubar(self, checked):
        self.menubar.setVisible(checked)
        if not checked:
            self.context_menu.addAction(self.action_menubar)
        else:
            self.context_menu.removeAction(self.action_menubar)
        if self.settings_loaded:
            self.manager_settings.setValue('view/menubar_visible', checked)
            self.manager_settings.sync()

    def showhide_toolbar(self, checked):
        self.toolbar.setVisible(checked)
        if not checked:
            self.context_menu.addAction(self.action_toolbar)
        else:
            self.context_menu.removeAction(self.action_toolbar)
        if self.settings_loaded:
            self.manager_settings.setValue('view/toolbar_visible', checked)
            self.manager_settings.sync()

    def showhide_column(self, col_num, show):
        self.table.setColumnHidden(col_num, not show)

        val = 1 if show else -1
        self.visible_columns_count += val

        if self.visible_columns_count == 1:
            # disable hiding the last one
            for col in self.columns_actions:
                if self.columns_actions[col].isChecked():
                    self.columns_actions[col].setEnabled(False)
                    break
        elif self.visible_columns_count == 2 and val == 1:
            # enable hiding previously disabled column
            for col in self.columns_actions:
                if not self.columns_actions[col].isEnabled():
                    self.columns_actions[col].setEnabled(True)
                    break

        if self.settings_loaded:
            col_name = [name for name in self.columns_indices if
                        self.columns_indices[name] == col_num][0]
            self.manager_settings.setValue('columns/%s' % col_name, show)
            self.manager_settings.sync()

    def on_action_vm_type_toggled(self, checked):
        self.showhide_column(self.columns_indices['Type'], checked)

    def on_action_label_toggled(self, checked):
        self.showhide_column(self.columns_indices['Label'], checked)

    def on_action_name_toggled(self, checked):
        self.showhide_column(self.columns_indices['Name'], checked)

    def on_action_state_toggled(self, checked):
        self.showhide_column(self.columns_indices['State'], checked)

    def on_action_internal_toggled(self, checked):
        self.showhide_column(self.columns_indices['Internal'], checked)

    def on_action_ip_toggled(self, checked):
        self.showhide_column(self.columns_indices['IP'], checked)

    def on_action_backups_toggled(self, checked):
        self.showhide_column(self.columns_indices['Backups'], checked)

    def on_action_last_backup_toggled(self, checked):
        self.showhide_column(self.columns_indices['Last backup'], checked)

    def on_action_template_toggled(self, checked):
        self.showhide_column(self.columns_indices['Template'], checked)

    def on_action_netvm_toggled(self, checked):
        self.showhide_column(self.columns_indices['NetVM'], checked)

    def on_action_size_on_disk_toggled(self, checked):
        self.showhide_column(self.columns_indices['Size'], checked)

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_about_qubes_triggered')
    def action_about_qubes_triggered(self):  # pylint: disable=no-self-use
        about = AboutDialog()
        about.exec_()

    def createPopupMenu(self):  # pylint: disable=invalid-name
        menu = QtGui.QMenu()
        menu.addAction(self.action_toolbar)
        menu.addAction(self.action_menubar)
        return menu

    def open_tools_context_menu(self, widget, point):
        self.tools_context_menu.exec_(widget.mapToGlobal(point))

    @QtCore.pyqtSlot('const QPoint&')
    def open_context_menu(self, point):
        vm = self.get_selected_vm()

        # logs menu
        self.logs_menu.clear()

        if vm.qid == 0:
            logfiles = ["/var/log/xen/console/hypervisor.log"]
        else:
            logfiles = [
                "/var/log/xen/console/guest-" + vm.name + ".log",
                "/var/log/xen/console/guest-" + vm.name + "-dm.log",
                "/var/log/qubes/guid." + vm.name + ".log",
                "/var/log/qubes/qrexec." + vm.name + ".log",
            ]

        menu_empty = True
        for logfile in logfiles:
            if os.path.exists(logfile):
                action = self.logs_menu.addAction(QtGui.QIcon(":/log.png"),
                                                  logfile)
                action.setData(logfile)
                menu_empty = False

        self.logs_menu.setEnabled(not menu_empty)
        self.context_menu.exec_(self.table.mapToGlobal(point))

    @QtCore.pyqtSlot('QAction *')
    def show_log(self, action):
        log = str(action.data())
        log_dlg = log_dialog.LogDialog(self.qt_app, log)
        log_dlg.exec_()


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception(exc_type, exc_value, exc_traceback):

    filename, line, dummy, dummy = traceback.extract_tb(exc_traceback).pop()
    filename = os.path.basename(filename)
    error = "%s: %s" % (exc_type.__name__, exc_value)

    strace = ""
    stacktrace = traceback.extract_tb(exc_traceback)
    while stacktrace:
        (filename, line, func, txt) = stacktrace.pop()
        strace += "----\n"
        strace += "line: %s\n" % txt
        strace += "func: %s\n" % func
        strace += "line no.: %d\n" % line
        strace += "file: %s\n" % filename

    msg_box = QtGui.QMessageBox()
    msg_box.setDetailedText(strace)
    msg_box.setIcon(QtGui.QMessageBox.Critical)
    msg_box.setWindowTitle("Houston, we have a problem...")
    msg_box.setText("Whoops. A critical error has occured. "
                    "This is most likely a bug in Qubes Manager.<br><br>"
                    "<b><i>%s</i></b>" % error +
                    "<br/>at line <b>%d</b><br/>of file %s.<br/><br/>"
                    % (line, filename))

    msg_box.exec_()


def main():
    qt_app = QtGui.QApplication(sys.argv)
    qt_app.setOrganizationName("The Qubes Project")
    qt_app.setOrganizationDomain("http://qubes-os.org")
    qt_app.setApplicationName("Qube Manager")
    qt_app.setWindowIcon(QtGui.QIcon.fromTheme("qubes-manager"))

    sys.excepthook = handle_exception

    qubes_app = Qubes()

    manager_window = VmManagerWindow(qubes_app, qt_app)

    manager_window.show()
    manager_window.update_table()
    qt_app.exec_()


if __name__ == "__main__":
    main()
