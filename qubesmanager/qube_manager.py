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
from datetime import datetime, timedelta
import traceback
from contextlib import suppress

import quamash
import asyncio

from qubesadmin import Qubes
from qubesadmin import exc
from qubesadmin import utils
from qubesadmin import events

from PyQt5 import QtWidgets, QtCore, QtGui  # pylint: disable=import-error

from qubesmanager.about import AboutDialog

from . import ui_qubemanager  # pylint: disable=no-name-in-module
from . import settings
from . import global_settings
from . import restore
from . import backup
from . import create_new_vm
from . import log_dialog
from . import utils as manager_utils
from . import common_threads


class SearchBox(QtWidgets.QLineEdit):
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

row_height = 30
size_multiplier = 1 #0.7


class VmInfo():
    def __init__(self, vm):
        self.vm = vm
        self.name = self.vm.name
        self.klass = self.vm.klass
        self.update(True)

    def update(self, update_size_on_disk=False, event=None):
        """
        Update VmInfo
        :param update_size_on_disk: should disk utilization be updated?
        :param event: name of the event that caused the update, to avoid
        updating unnecessary properties; if event is none, update everything
        :return: None
        """
        try:
            self.state = self.vm.get_power_state()
            if not event or event.endswith(':label'):
                self.label = self.vm.label
            if not event or event.endswith(':template'):
                try:
                    self.template = self.vm.template.name
                except:
                    self.template = self.vm.klass
            if not event or event.endswith(':netvm'):
                self.netvm = getattr(self.vm, 'netvm', None)
                if self.netvm:
                    self.netvm = self.netvm.name
            if not event or event.endswith(':internal'):
                self.internal = "Yes" if self.vm.features.get('internal', False) else ""
            if not event or event.endswith(':ip'):
                self.ip = getattr(self.vm, 'ip', None)
            if not event or event.endswith(':include_in_backups'):
                self.inc_backup = getattr(self.vm, 'include_in_backups', None)
            if not event or event.endswith(':backup_timestamp'):
                self.last_backup = getattr(self.vm, 'backup_timestamp', None)
                if self.last_backup:
                    self.last_backup = str(datetime.fromtimestamp(
                        self.last_backup))
            if not event or event.endswith(':default_dispvm'):
                self.dvm = getattr(self.vm, 'default_dispvm', None)
            if not event or event.endswith(':template_for_dispvms'):
                self.dvm_template = getattr(self.vm, 'template_for_dispvms', None)
            if update_size_on_disk:
                self.disk = str(round(self.vm.get_disk_utilization()/(1024*1024),2))+"MiB"
        except exc.QubesPropertyAccessError:
            pass
        except exc.QubesDaemonNoResponseError:
            # TODO: this will be fixed by a rewrite moving the event system to
            # AdminAPI
            pass

class QubesTableModel(QtCore.QAbstractTableModel):
    def __init__(self, qubes_app):
        QtCore.QAbstractTableModel.__init__(self)
        self.qubes_app = qubes_app
        self.info_list =  []
        self.template = {}
        self.klass_pixmap = {}
        self.label_pixmap = {}
        self.columns_indices = [
                "Type",
                "Label",
                "Name",
                "State",
                "Template",
                "NetVM",
                "Size",
                "Internal",
                "IP",
                "Include in backups",
                "Last backup",
                "Default DispVM",
                "Is DVM Template"
                ]

        self.fill_list()

    def fill_list(self):
        vms_list = self.get_vms_list()

        progress = QtWidgets.QProgressDialog(
            self.tr(
                "Loading Qube Manager..."), "", 0, len(vms_list))
        progress.setWindowTitle(self.tr("Qube Manager"))
        progress.setMinimumDuration(1000)
        progress.setCancelButton(None)

        row_no = 0
        for vm in vms_list:
            progress.setValue(row_no)
            self.info_list.append(VmInfo(vm))
            row_no += 1

        progress.setValue(row_no)

    def change(self, current, previous):
        print("CHANGED")

    def get_vms_list(self):
        return [vm for vm in self.qubes_app.domains]

    def rowCount(self, parent):
        return len(self.info_list) 

    def columnCount(self, parent):
        return len(self.columns_indices)

    def data(self, index, role):
        if not index.isValid():
            return  None

        col = index.column()
        row = index.row()
        vm = self.info_list[row]

        if role == QtCore.Qt.DisplayRole:
            if col in [0,1]:
                return None
            if col == 2:
                return self.info_list[index.row()].name
            elif col == 4:
                return self.info_list[index.row()].template
            elif col == 5:
                return self.info_list[index.row()].netvm
            elif col == 6:
                return self.info_list[index.row()].disk
            elif col == 8:
                return self.info_list[index.row()].ip
            elif col == 9:
                return self.info_list[index.row()].inc_backup
            elif col == 10:
                return self.info_list[index.row()].last_backup
            elif col == 11:
                return self.info_list[index.row()].dvm
            elif col == 12:
                return self.info_list[index.row()].dvm_template

        elif role == QtCore.Qt.DecorationRole:
            if col == 0:
                try:
                    return self.klass_pixmap[vm.klass]
                except:
                    self.klass_pixmap[vm.klass] =  QtGui.QPixmap(row_height*size_multiplier,row_height*size_multiplier)
                    self.klass_pixmap[vm.klass].load(":/"+vm.klass.lower()+".png")
                    self.klass_pixmap[vm.klass] = self.klass_pixmap[vm.klass].scaled(row_height*size_multiplier,row_height*size_multiplier)
                    return self.klass_pixmap[vm.klass]
            if col == 1:
                try:
                    return self.label_pixmap[vm.label]
                except:
                    self.label_pixmap[vm.label] = QtGui.QIcon.fromTheme(vm.label.icon)
                    return self.label_pixmap[vm.label]
        return None

    def headerData(self, col, orientation, role):
        if(col < 2):
            return None
        if(orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole):
            return self.columns_indices[col]
        return None



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

                msgbox = QtWidgets.QMessageBox(self.caller)
                msgbox.setIcon(QtWidgets.QMessageBox.Question)
                msgbox.setWindowTitle(self.tr("Qube Shutdown"))
                msgbox.setText(self.tr(
                        "The Qube <b>'{0}'</b> hasn't shutdown within the last "
                        "{1} seconds, do you want to kill it?<br>").format(
                            vm.name, self.shutdown_time / 1000))
                kill_button = msgbox.addButton(
                    self.tr("Kill it!"), QtWidgets.QMessageBox.YesRole)
                wait_button = msgbox.addButton(
                    self.tr("Wait another {0} seconds...").format(
                        self.shutdown_time / 1000),
                    QtWidgets.QMessageBox.NoRole)
                msgbox.setDefaultButton(wait_button)
                msgbox.exec_()
                msgbox.deleteLater()

                if msgbox.clickedButton() is kill_button:
                    try:
                        vm.kill()
                    except exc.QubesVMNotStartedError:
                        # the VM shut down while the user was thinking about
                        # shutting it down
                        pass
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


# pylint: disable=too-few-public-methods
class StartVMThread(common_threads.QubesThread):
    def run(self):
        try:
            self.vm.start()
        except exc.QubesException as ex:
            self.msg = ("Error starting Qube!", str(ex))


# pylint: disable=too-few-public-methods
class UpdateVMThread(common_threads.QubesThread):
    def run(self):
        try:
            if self.vm.qid == 0:
                subprocess.check_call(
                    ["/usr/bin/qubes-dom0-update", "--clean", "--gui"])
            else:
                if not self.vm.is_running():
                    self.vm.start()
                # apply DSA-4371
                with open('/usr/libexec/qubes-manager/dsa-4371-update', 'rb') \
                        as dsa4371update:
                    stdout, stderr = self.vm.run_service_for_stdio(
                            "qubes.VMShell",
                            user="root",
                            input=dsa4371update.read())
                if stdout == b'changed=yes\n':
                    subprocess.call(
                        ['notify-send', '-i', 'dialog-information',
                         'Debian DSA-4371 fix installed in {}'.format(
                                self.vm.name)])
                elif stdout == b'changed=no\n':
                    pass
                else:
                    raise exc.QubesException(
                            "Failed to apply DSA-4371 fix: {}".format(
                                stderr.decode('ascii')))
                self.vm.run_service("qubes.InstallUpdatesGUI",
                                    user="root", wait=False)
        except (ChildProcessError, exc.QubesException) as ex:
            self.msg = ("Error on qube update!", str(ex))


# pylint: disable=too-few-public-methods
class RunCommandThread(common_threads.QubesThread):
    def __init__(self, vm, command_to_run):
        super(RunCommandThread, self).__init__(vm)
        self.command_to_run = command_to_run

    def run(self):
        try:
            self.vm.run(self.command_to_run)
        except (ChildProcessError, exc.QubesException) as ex:
            self.msg = ("Error while running command!", str(ex))


class VmManagerWindow(ui_qubemanager.Ui_VmManagerWindow, QtWidgets.QMainWindow):
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
                       "Include in backups": 9,
                       "Last backup": 10,
                       "Default DispVM": 11,
                       "Is DVM Template": 12,
                       "Virtualization Mode": 13
                      }

    def __init__(self, qt_app, qubes_app, dispatcher, parent=None):
        # pylint: disable=unused-argument
        super(VmManagerWindow, self).__init__()
        self.setupUi(self)

        self.manager_settings = QtCore.QSettings(self)

        self.qubes_app = qubes_app
        self.qt_app = qt_app

        self.searchbox = SearchBox()
        self.searchbox.setValidator(QtGui.QRegExpValidator(
            QtCore.QRegExp("[a-zA-Z0-9_-]*", QtCore.Qt.CaseInsensitive), None))
        self.searchContainer.addWidget(self.searchbox)

       # self.connect(self.table, QtCore.SIGNAL("itemSelectionChanged()"),
       #              self.table_selection_changed)

        self.sort_by_column = "Type"
        self.sort_order = QtCore.Qt.AscendingOrder

        self.vms_list = []
        self.vms_in_table = {}

        self.frame_width = 0
        self.frame_height = 0

        self.columns_actions = {
            self.columns_indices["Type"]: self.action_vm_type,
            self.columns_indices["Label"]: self.action_label,
            self.columns_indices["Name"]: self.action_name,
            self.columns_indices["State"]: self.action_state,
            self.columns_indices["Template"]: self.action_template,
            self.columns_indices["NetVM"]: self.action_netvm,
            self.columns_indices["Size"]: self.action_size_on_disk,
            self.columns_indices["Internal"]: self.action_internal,
            self.columns_indices["IP"]: self.action_ip,
            self.columns_indices["Include in backups"]: self.action_backups,
            self.columns_indices["Last backup"]: self.action_last_backup,
            self.columns_indices["Default DispVM"]: self.action_dispvm_template,
            self.columns_indices["Is DVM Template"]:
                self.action_is_dvm_template,
            self.columns_indices["Virtualization Mode"]: self.action_virt_mode
        }

        self.context_menu = QtWidgets.QMenu(self)
        self.visible_columns_count = len(self.columns_indices)

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

        self.tools_context_menu = QtWidgets.QMenu(self)
        self.tools_context_menu.addAction(self.action_toolbar)
        self.tools_context_menu.addAction(self.action_menubar)

        self.dom0_context_menu = QtWidgets.QMenu(self)
        self.dom0_context_menu.addAction(self.action_global_settings)
        self.dom0_context_menu.addAction(self.action_updatevm)
        self.dom0_context_menu.addSeparator()

        self.dom0_context_menu.addMenu(self.logs_menu)
        self.dom0_context_menu.addSeparator()

        #self.connect(
        #    self.table.horizontalHeader(),
        #    QtCore.SIGNAL("sortIndicatorChanged(int, Qt::SortOrder)"),
        #    self.sort_indicator_changed)
        #self.connect(self.table,
        #             QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
        #             self.open_context_menu)
        #self.connect(self.menubar,
        #             QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
        #             lambda pos: self.open_tools_context_menu(self.menubar,
        #                                                      pos))
        #self.connect(self.toolbar,
        #             QtCore.SIGNAL("customContextMenuRequested(const QPoint&)"),
        #             lambda pos: self.open_tools_context_menu(self.toolbar,
        #                                                      pos))
        #self.connect(self.logs_menu, QtCore.SIGNAL("triggered(QAction *)"),
        #             self.show_log)

        #self.connect(self.searchbox,
        #             QtCore.SIGNAL("textChanged(const QString&)"),
        #             self.do_search)

        #self.table.setContentsMargins(0, 0, 0, 0)
        self.centralwidget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.action_menubar.toggled.connect(self.showhide_menubar)
        self.action_toolbar.toggled.connect(self.showhide_toolbar)

        try:
            self.load_manager_settings()
        except Exception as ex:  # pylint: disable=broad-except
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Manager settings unreadable"),
                self.tr("Qube Manager settings cannot be parsed. Previously "
                        "saved display settings may not be restored "
                        "correctly.\nError: {}".format(str(ex))))

        self.settings_loaded = True

        #self.fill_table()

        self.update_size_on_disk = False
        self.shutdown_monitor = {}

        qubes_model = QubesTableModel(qubes_app)
        self.table.setModel(qubes_model)
        self.table.resizeColumnsToContents()

        # Connect events
        self.dispatcher = dispatcher
        dispatcher.add_handler('domain-pre-start',
                               self.on_domain_status_changed)
        dispatcher.add_handler('domain-start', self.on_domain_status_changed)
        dispatcher.add_handler('domain-start-failed',
                               self.on_domain_status_changed)
        dispatcher.add_handler('domain-stopped', self.on_domain_status_changed)
        dispatcher.add_handler('domain-pre-shutdown',
                               self.on_domain_status_changed)
        dispatcher.add_handler('domain-shutdown', self.on_domain_status_changed)
        dispatcher.add_handler('domain-paused', self.on_domain_status_changed)
        dispatcher.add_handler('domain-unpaused', self.on_domain_status_changed)

        dispatcher.add_handler('domain-add', self.on_domain_added)
        dispatcher.add_handler('domain-delete', self.on_domain_removed)

        dispatcher.add_handler('property-set:*',
                               self.on_domain_changed)
        dispatcher.add_handler('property-del:*',
                               self.on_domain_changed)
        dispatcher.add_handler('property-load',
                               self.on_domain_changed)

        # It needs to store threads until they finish
        self.threads_list = []
        self.progress = None

        # Check Updates Timer
        timer = QtCore.QTimer(self)
        timer.timeout.connect(self.check_updates)
        timer.start(1000 * 30)  # 30s
        self.check_updates()

        # select the first row of the table to make sure menu actions are
        # correctly initialized
        self.table.selectRow(0)

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        if event.key() == QtCore.Qt.Key_Escape:
            self.searchbox.clear()
        super(VmManagerWindow, self).keyPressEvent(event)

    def clear_threads(self):
        for thread in self.threads_list:
            if thread.isFinished():
                if self.progress:
                    self.progress.hide()
                    self.progress = None

                if thread.msg:
                    (title, msg) = thread.msg
                    if thread.msg_is_success:
                        QtWidgets.QMessageBox.information(
                            self,
                            self.tr(title),
                            self.tr(msg))
                    else:
                        QtWidgets.QMessageBox.warning(
                            self,
                            self.tr(title),
                            self.tr(msg))

                self.threads_list.remove(thread)
                return

        raise RuntimeError('No finished thread found')

    def closeEvent(self, event):
        # pylint: disable=invalid-name
        # save window size at close
        self.manager_settings.setValue("window_size", self.size())
        event.accept()

    def check_updates(self):
        for vm in self.qubes_app.domains:
            if vm.klass in {'TemplateVM', 'StandaloneVM'}:
                try:
                    self.vms_in_table[vm.qid].info_widget.update_vm_state()
                except (exc.QubesException, KeyError):
                    # the VM might have vanished in the meantime or
                    # the signal might have been handled in the wrong order
                    pass

    def on_domain_added(self, _submitter, _event, vm, **_kwargs):
        pass

    def on_domain_removed(self, _submitter, _event, **kwargs):
        pass

    def on_domain_status_changed(self, vm, _event, **_kwargs):
        pass

    def on_domain_changed(self, vm, event, **_kwargs):
        pass

    def load_manager_settings(self):
        for col in self.columns_indices:
            col_no = self.columns_indices[col]
            if col == 'Name':
                # 'Name' column should be always visible
                self.columns_actions[col_no].setChecked(True)
            else:
                visible = self.manager_settings.value(
                    'columns/%s' % col,
                    defaultValue="true")
                self.columns_actions[col_no].setChecked(visible == "true")

        self.sort_by_column = str(
            self.manager_settings.value("view/sort_column",
                                        defaultValue=self.sort_by_column))
        self.sort_order = QtCore.Qt.SortOrder(
            self.manager_settings.value("view/sort_order",
                                        defaultValue=self.sort_order))

        if not self.manager_settings.value("view/menubar_visible",
                                           defaultValue=True):
            self.action_menubar.setChecked(False)
        if not self.manager_settings.value("view/toolbar_visible",
                                           defaultValue=True):
            self.action_toolbar.setChecked(False)

        # load last window size
        self.resize(self.manager_settings.value("window_size",
                                                QtCore.QSize(1100, 600)))

    def get_vms_list(self):
        return [vm for vm in self.qubes_app.domains]

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
                and vm.klass != 'AdminVM'
                and (vm.klass != 'DispVM' or not vm.auto_cleanup))
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

        self.update_logs_menu()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_createvm_triggered')
    def action_createvm_triggered(self):  # pylint: disable=no-self-use
        with common_threads.busy_cursor():
            create_window = create_new_vm.NewVmDlg(self.qt_app, self.qubes_app)
        create_window.exec_()

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
        return None

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_removevm_triggered')
    def action_removevm_triggered(self):
        # pylint: disable=no-else-return

        vm = self.get_selected_vm()

        dependencies = utils.vm_dependencies(self.qubes_app, vm)

        if dependencies:
            list_text = "<br>" + \
                        manager_utils.format_dependencies_list(dependencies) + \
                        "<br>"

            info_dialog = QtWidgets.QMessageBox(self)
            info_dialog.setWindowTitle(self.tr("Warning!"))
            info_dialog.setText(
                self.tr("This qube cannot be removed. It is used as:"
                        " <br> {} <small>If you want to  remove this qube, "
                        "you should remove or change settings of each qube "
                        "or setting that uses it.</small>").format(list_text))
            info_dialog.setModal(False)
            info_dialog.show()

            return

        (requested_name, ok) = QtWidgets.QInputDialog.getText(
            self, self.tr("Qube Removal Confirmation"),
            self.tr("Are you sure you want to remove the Qube <b>'{0}'</b>"
                    "?<br> All data on this Qube's private storage will be "
                    "lost!<br><br>Type the name of the Qube (<b>{1}</b>) below "
                    "to confirm:").format(vm.name, vm.name))

        if not ok:
            # user clicked cancel
            return

        if requested_name != vm.name:
            # name did not match
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Qube removal confirmation failed"),
                self.tr(
                    "Entered name did not match! Not removing "
                    "{0}.").format(vm.name))
            return

        else:
            # remove the VM
            thread = common_threads.RemoveVMThread(vm)
            self.threads_list.append(thread)
            thread.finished.connect(self.clear_threads)
            thread.start()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_clonevm_triggered')
    def action_clonevm_triggered(self):
        vm = self.get_selected_vm()

        name_number = 1
        name_format = vm.name + '-clone-%d'
        while name_format % name_number in self.qubes_app.domains.keys():
            name_number += 1

        (clone_name, ok) = QtWidgets.QInputDialog.getText(
            self, self.tr('Qubes clone Qube'),
            self.tr('Enter name for Qube <b>{}</b> clone:').format(vm.name),
            text=(name_format % name_number))
        if not ok or clone_name == "":
            return

        name_in_use = clone_name in self.qubes_app.domains

        if name_in_use:
            QtWidgets.QMessageBox.warning(
                self, self.tr("Name already in use!"),
                self.tr("There already exists a qube called '{}'. "
                        "Cloning aborted.").format(clone_name))
            return

        self.progress = QtWidgets.QProgressDialog(
            self.tr(
                "Cloning Qube..."), "", 0, 0)
        self.progress.setCancelButton(None)
        self.progress.setModal(True)
        self.progress.setWindowTitle("Cloning qube...")
        self.progress.show()

        thread = common_threads.CloneVMThread(vm, clone_name)
        thread.finished.connect(self.clear_threads)
        self.threads_list.append(thread)
        thread.start()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_resumevm_triggered')
    def action_resumevm_triggered(self):
        vm = self.get_selected_vm()

        if vm.get_power_state() in ["Paused", "Suspended"]:
            try:
                vm.unpause()
            except exc.QubesException as ex:
                QtWidgets.QMessageBox.warning(
                    self, self.tr("Error unpausing Qube!"),
                    self.tr("ERROR: {0}").format(ex))
            return

        self.start_vm(vm)

    def start_vm(self, vm):
        if vm.is_running():
            return

        thread = StartVMThread(vm)
        self.threads_list.append(thread)
        thread.finished.connect(self.clear_threads)
        thread.start()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_startvm_tools_install_triggered')
    # TODO: replace with boot from device
    def action_startvm_tools_install_triggered(self):
        # pylint: disable=invalid-name
        pass

    @QtCore.pyqtSlot(name='on_action_pausevm_triggered')
    def action_pausevm_triggered(self):
        vm = self.get_selected_vm()
        try:
            vm.pause()
        except exc.QubesException as ex:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Error pausing Qube!"),
                self.tr("ERROR: {0}").format(ex))
            return

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_shutdownvm_triggered')
    def action_shutdownvm_triggered(self):
        vm = self.get_selected_vm()

        reply = QtWidgets.QMessageBox.question(
            self, self.tr("Qube Shutdown Confirmation"),
            self.tr("Are you sure you want to power down the Qube"
                    " <b>'{0}'</b>?<br><small>This will shutdown all the "
                    "running applications within this Qube.</small>").format(
                     vm.name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)

        if reply == QtWidgets.QMessageBox.Yes:
            self.shutdown_vm(vm)

    def shutdown_vm(self, vm, shutdown_time=vm_shutdown_timeout,
                    check_time=vm_restart_check_timeout, and_restart=False):
        try:
            vm.shutdown()
        except exc.QubesException as ex:
            QtWidgets.QMessageBox.warning(
                self,
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

        reply = QtWidgets.QMessageBox.question(
            self, self.tr("Qube Restart Confirmation"),
            self.tr("Are you sure you want to restart the Qube <b>'{0}'</b>?"
                    "<br><small>This will shutdown all the running "
                    "applications within this Qube.</small>").format(vm.name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)

        if reply == QtWidgets.QMessageBox.Yes:
            # in case the user shut down the VM in the meantime
            if vm.is_running():
                self.shutdown_vm(vm, and_restart=True)
            else:
                self.start_vm(vm)

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_killvm_triggered')
    def action_killvm_triggered(self):
        vm = self.get_selected_vm()
        if not (vm.is_running() or vm.is_paused()):
            info = self.tr("Qube <b>'{0}'</b> is not running. Are you "
                           "absolutely sure you want to try to kill it?<br>"
                           "<small>This will end <b>(not shutdown!)</b> all "
                           "the running applications within this "
                           "Qube.</small>").format(vm.name)
        else:
            info = self.tr("Are you sure you want to kill the Qube "
                           "<b>'{0}'</b>?<br><small>This will end <b>(not "
                           "shutdown!)</b> all the running applications within "
                           "this Qube.</small>").format(vm.name)

        reply = QtWidgets.QMessageBox.question(
            self, self.tr("Qube Kill Confirmation"), info,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel)

        if reply == QtWidgets.QMessageBox.Yes:
            try:
                vm.kill()
            except exc.QubesException as ex:
                QtWidgets.QMessageBox.critical(
                    self, self.tr("Error while killing Qube!"),
                    self.tr(
                        "<b>An exception ocurred while killing {0}.</b><br>"
                        "ERROR: {1}").format(vm.name, ex))
                return

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_settings_triggered')
    def action_settings_triggered(self):
        vm = self.get_selected_vm()
        if vm:
            with common_threads.busy_cursor():
                settings_window = settings.VMSettingsWindow(
                    vm, self.qt_app, "basic")
            settings_window.exec_()

            vm_deleted = False

            try:
                # the VM might not exist after running Settings - it might
                # have been cloned or removed
                self.vms_in_table[vm.qid].update()
            except exc.QubesException:
                # TODO: this will be replaced by proper signal handling once
                # settings are migrated to AdminAPI
                vm_deleted = True

            if vm_deleted:
                for row in self.vms_in_table:
                    try:
                        self.vms_in_table[row].update()
                    except exc.QubesException:
                        pass

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_appmenus_triggered')
    def action_appmenus_triggered(self):
        vm = self.get_selected_vm()
        if vm:
            with common_threads.busy_cursor():
                settings_window = settings.VMSettingsWindow(
                    vm, self.qt_app, "applications")
            settings_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_updatevm_triggered')
    def action_updatevm_triggered(self):
        vm = self.get_selected_vm()

        if not vm.is_running():
            reply = QtWidgets.QMessageBox.question(
                self, self.tr("Qube Update Confirmation"),
                self.tr(
                    "<b>{0}</b><br>The Qube has to be running to be updated."
                    "<br>Do you want to start it?<br>").format(vm.name),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
            if reply != QtWidgets.QMessageBox.Yes:
                return

        thread = UpdateVMThread(vm)
        self.threads_list.append(thread)
        thread.finished.connect(self.clear_threads)
        thread.start()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_run_command_in_vm_triggered')
    def action_run_command_in_vm_triggered(self):
        # pylint: disable=invalid-name
        vm = self.get_selected_vm()

        (command_to_run, ok) = QtWidgets.QInputDialog.getText(
            self, self.tr('Qubes command entry'),
            self.tr('Run command in <b>{}</b>:').format(vm.name))
        if not ok or command_to_run == "":
            return

        thread = RunCommandThread(vm, command_to_run)
        self.threads_list.append(thread)
        thread.finished.connect(self.clear_threads)
        thread.start()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_set_keyboard_layout_triggered')
    def action_set_keyboard_layout_triggered(self):
        # pylint: disable=invalid-name
        vm = self.get_selected_vm()
        vm.run('qubes-change-keyboard-layout')

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_editfwrules_triggered')
    def action_editfwrules_triggered(self):
        with common_threads.busy_cursor():
            vm = self.get_selected_vm()
            settings_window = settings.VMSettingsWindow(vm, self.qt_app,
                                                        "firewall")
        settings_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_global_settings_triggered')
    def action_global_settings_triggered(self):  # pylint: disable=invalid-name
        with common_threads.busy_cursor():
            global_settings_window = global_settings.GlobalSettingsWindow(
                self.qt_app,
                self.qubes_app)
        global_settings_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_manage_templates_triggered')
    def action_manage_templates_triggered(self):
        # pylint: disable=invalid-name, no-self-use
        subprocess.check_call('qubes-template-manager')

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
        with common_threads.busy_cursor():
            restore_window = restore.RestoreVMsWindow(self.qt_app,
                                                      self.qubes_app)
        restore_window.exec_()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_backup_triggered')
    def action_backup_triggered(self):
        with common_threads.busy_cursor():
            backup_window = backup.BackupVMsWindow(
                self.qt_app, self.qubes_app, self.dispatcher, self)
        backup_window.show()

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_exit_triggered')
    def action_exit_triggered(self):
        self.close()

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
        self.showhide_column(
            self.columns_indices['Include in backups'], checked)

    def on_action_last_backup_toggled(self, checked):
        self.showhide_column(self.columns_indices['Last backup'], checked)

    def on_action_template_toggled(self, checked):
        self.showhide_column(self.columns_indices['Template'], checked)

    def on_action_netvm_toggled(self, checked):
        self.showhide_column(self.columns_indices['NetVM'], checked)

    def on_action_size_on_disk_toggled(self, checked):
        self.showhide_column(self.columns_indices['Size'], checked)

    def on_action_virt_mode_toggled(self, checked):
        self.showhide_column(self.columns_indices['Virtualization Mode'],
                             checked)

    # pylint: disable=invalid-name
    def on_action_dispvm_template_toggled(self, checked):
        self.showhide_column(self.columns_indices['Default DispVM'], checked)

    # pylint: disable=invalid-name
    def on_action_is_dvm_template_toggled(self, checked):
        self.showhide_column(self.columns_indices['Is DVM Template'], checked)

    # noinspection PyArgumentList
    @QtCore.pyqtSlot(name='on_action_about_qubes_triggered')
    def action_about_qubes_triggered(self):  # pylint: disable=no-self-use
        about = AboutDialog()
        about.exec_()

    def createPopupMenu(self):  # pylint: disable=invalid-name
        menu = QtWidgets.QMenu()
        menu.addAction(self.action_toolbar)
        menu.addAction(self.action_menubar)
        return menu

    def open_tools_context_menu(self, widget, point):
        self.tools_context_menu.exec_(widget.mapToGlobal(point))

    def update_logs_menu(self):
        try:
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

        except exc.QubesPropertyAccessError:
            pass

    @QtCore.pyqtSlot('const QPoint&')
    def open_context_menu(self, point):
        vm = self.get_selected_vm()

        if vm.qid == 0:
            self.dom0_context_menu.exec_(self.table.mapToGlobal(
                point + QtCore.QPoint(10, 0)))
        else:
            self.context_menu.exec_(self.table.mapToGlobal(
                point + QtCore.QPoint(10, 0)))

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

    msg_box = QtWidgets.QMessageBox()
    msg_box.setDetailedText(strace)
    msg_box.setIcon(QtWidgets.QMessageBox.Critical)
    msg_box.setWindowTitle("Houston, we have a problem...")
    msg_box.setText("Whoops. A critical error has occured. "
                    "This is most likely a bug in Qubes Manager.<br><br>"
                    "<b><i>%s</i></b>" % error +
                    "<br/>at line <b>%d</b><br/>of file %s.<br/><br/>"
                    % (line, filename))

    msg_box.exec_()


def loop_shutdown():
    pending = asyncio.Task.all_tasks()
    for task in pending:
        with suppress(asyncio.CancelledError):
            task.cancel()


def main():
    qt_app = QtWidgets.QApplication(sys.argv)
    qt_app.setOrganizationName("The Qubes Project")
    qt_app.setOrganizationDomain("http://qubes-os.org")
    qt_app.setApplicationName("Qube Manager")
    qt_app.setWindowIcon(QtGui.QIcon.fromTheme("qubes-manager"))
    qt_app.lastWindowClosed.connect(loop_shutdown)

    qubes_app = Qubes()

    loop = quamash.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)
    dispatcher = events.EventsDispatcher(qubes_app)

    manager_window = VmManagerWindow(qt_app, qubes_app, dispatcher)
    manager_window.show()

    try:
        loop.run_until_complete(
            asyncio.ensure_future(dispatcher.listen_for_events()))
    except asyncio.CancelledError:
        pass
    except Exception:  # pylint: disable=broad-except
        loop_shutdown()
        exc_type, exc_value, exc_traceback = sys.exc_info()[:3]
        handle_exception(exc_type, exc_value, exc_traceback)


if __name__ == "__main__":
    main()
