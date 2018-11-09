#!/usr/bin/python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2018  Marta Marczykowska-Górecka
# <marmarta@invisiblethingslab.com>
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
import traceback
import quamash
import asyncio
from contextlib import suppress

from qubesadmin import Qubes
from qubesadmin import exc
from qubesadmin import events

from PyQt4 import QtGui  # pylint: disable=import-error
from PyQt4 import QtCore  # pylint: disable=import-error
from PyQt4 import Qt  # pylint: disable=import-error


import ui_templatemanager  # pylint: disable=no-name-in-module

column_names = ['Qube', 'State', 'Current template', 'New template']


class TemplateManagerWindow(
        ui_templatemanager.Ui_MainWindow, QtGui.QMainWindow):

    def __init__(self, qt_app, qubes_app, dispatcher, parent=None):
        # pylint: disable=unused-argument
        super(TemplateManagerWindow, self).__init__()
        self.setupUi(self)

        self.qubes_app = qubes_app
        self.qt_app = qt_app
        self.dispatcher = dispatcher

        self.rows_in_table = {}
        self.templates = []
        self.timers = []

        self.prepare_vm_list()
        self.initialize_table_events()

        self.buttonBox.button(QtGui.QDialogButtonBox.Ok).clicked.connect(
            self.apply)
        self.buttonBox.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(
            self.cancel)
        self.buttonBox.button(QtGui.QDialogButtonBox.Reset).clicked.connect(
            self.reset)

        self.vm_list.show()

    def prepare_vm_list(self):
        self.templates = [vm.name for vm in self.qubes_app.domains
                     if vm.klass == 'TemplateVM']
        vms_with_templates = [vm for vm in self.qubes_app.domains
                              if getattr(vm, 'template', None)]

        self.vm_list.setColumnCount(len(column_names))
        self.vm_list.setRowCount(len(vms_with_templates))

        row_count = 0
        for vm in vms_with_templates:
            row = VMRow(vm, row_count, self.vm_list, column_names,
                        self.templates)
            self.rows_in_table[vm.name] = row
            row_count += 1

        self.vm_list.setHorizontalHeaderLabels(['Qube', '', 'Current', 'New'])
        self.vm_list.resizeColumnsToContents()

    def initialize_table_events(self):
        self.vm_list.cellDoubleClicked.connect(self.table_double_click)
        self.vm_list.horizontalHeader().sortIndicatorChanged.connect(
            self.sorting_changed)

        self.dispatcher.add_handler('domain-pre-start', self.vm_state_changed)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.vm_state_changed)
        self.dispatcher.add_handler('domain-stopped', self.vm_state_changed)
        self.dispatcher.add_handler('domain-shutdown', self.vm_state_changed)

        self.dispatcher.add_handler('domain-add', self.vm_added)
        self.dispatcher.add_handler('domain-delete', self.vm_removed)

    def vm_added(self, _submitter, _event, vm, **_kwargs):
        # unfortunately, a VM just in the moment of creation may not have
        # a template it will have in a second - e.g., when cloning
        timer = Qt.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._vm_added(vm, timer))
        self.timers.append(timer)
        timer.start(1000)  # 1s

    def _vm_added(self, vm_name, timer):
        self.timers.remove(timer)
        try:
            vm = self.qubes_app.domains[vm_name]
            if not getattr(vm, 'template', None):
                return
        except (exc.QubesException, KeyError):
            return  # it was a dispVM that crashed on start

        row_no = self.vm_list.rowCount()
        self.vm_list.setRowCount(self.vm_list.rowCount() + 1)
        row = VMRow(vm, row_no, self.vm_list, column_names,
                    self.templates)
        self.rows_in_table[vm.name] = row
        self.vm_list.show()

    def vm_removed(self, _submitter, _event, **kwargs):
        if kwargs['vm'] not in self.rows_in_table:
            return

        self.vm_list.removeRow(self.rows_in_table[kwargs['vm']].name_item.row())

    def vm_state_changed(self, vm, event, **_kwargs):
        try:
            if vm.name not in self.rows_in_table:
                return
        except exc.QubesException:
            return  # it was a crashing DispVM or closed DispVM

        if event == 'domain-pre-start':
            self.rows_in_table[vm.name].vm_state_change(is_running=True)
        elif event == 'domain-start-failed':
            self.rows_in_table[vm.name].vm_state_change(is_running=False)
        elif event == 'domain-stopped':
            self.rows_in_table[vm.name].vm_state_change(is_running=False)
        elif event == 'domain-shutdown':
            self.rows_in_table[vm.name].vm_state_change(is_running=False)

    def sorting_changed(self, index, _order):
        # this is very much not perfect, but QTableWidget does not
        # want to be sorted on custom widgets
        # possible fix - try to set data of dummy items.
        if index == column_names.index('New template'):
            self.vm_list.horizontalHeader().setSortIndicator(
                -1, QtCore.Qt.AscendingOrder)

    def table_double_click(self, row, column):
        template_column = column_names.index('Current template')

        if column != template_column:
            return

        template_name = self.vm_list.item(row, column).text()

        self.vm_list.clearSelection()

        for row_number in range(0, self.vm_list.rowCount()):
            if self.vm_list.item(
                    row_number, template_column).text() == template_name:
                self.vm_list.selectRow(row_number)

    def reset(self):
        for row in self.rows_in_table.values():
            row.new_item.reset_choice()

    def cancel(self):
        self.close()

    def apply(self):
        errors = {}
        for vm, row in self.rows_in_table.items():
            if row.new_item.changed:
                try:
                    setattr(self.qubes_app.domains[vm],
                            'template', row.new_item.currentText())
                except Exception as ex:  # pylint: disable=broad-except
                    errors[vm] = str(ex)
        if errors:
            error_messages = [vm + ": " + errors[vm] for vm in errors]
            QtGui.QMessageBox.warning(
                self,
                self.tr("Errors encountered!"),
                self.tr(
                    "Errors encountered on template change in the following "
                    "qubes: <br> {}.").format("<br> ".join(error_messages)))

        self.close()


class VMNameItem(QtGui.QTableWidgetItem):
    # pylint: disable=too-few-public-methods
    def __init__(self, vm):
        super(VMNameItem, self).__init__()
        self.vm = vm

        self.setText(self.vm.name)
        self.setIcon(QtGui.QIcon.fromTheme(vm.label.icon))


class StatusItem(QtGui.QTableWidgetItem):
    def __init__(self, vm):
        super(StatusItem, self).__init__()
        self.vm = vm

        self.state = None

    def set_state(self, is_running):
        self.state = is_running

        if self.state:
            self.setIcon(QtGui.QIcon.fromTheme('dialog-warning'))
            self.setToolTip("Cannot change template on a running VM.")
        else:
            self.setIcon(QtGui.QIcon())
            self.setToolTip("")

    def __lt__(self, other):
        if self.state == other.state:
            return self.vm.name < other.vm.name
        return self.state < other.state


class CurrentTemplateItem(QtGui.QTableWidgetItem):
    # pylint: disable=too-few-public-methods
    def __init__(self, vm):
        super(CurrentTemplateItem, self).__init__()
        self.vm = vm

        self.setText(self.vm.template.name)

    def __lt__(self, other):
        if self.text() == other.text():
            return self.vm.name < other.vm.name
        return self.text() < other.text()


class NewTemplateItem(QtGui.QComboBox):
    def __init__(self, vm, templates, table_widget):
        super(NewTemplateItem, self).__init__()
        self.vm = vm
        self.table_widget = table_widget
        self.changed = False

        for template in templates:
            self.addItem(template)
        self.setCurrentIndex(self.findText(vm.template.name))
        self.start_value = self.currentText()

        self.currentIndexChanged.connect(self.choice_changed)

    def choice_changed(self):
        if self.currentText() != self.start_value:
            self.changed = True
            self.setStyleSheet('font-weight: bold')
        else:
            self.changed = False
            self.setStyleSheet('font-weight: normal')

        for row_index in self.table_widget.selectionModel().selectedRows():
            widget = self.table_widget.cellWidget(
                row_index.row(), column_names.index('New template'))
            if widget.isEnabled() and widget.currentText() !=\
                    self.currentText():
                widget.setCurrentIndex(widget.findText(self.currentText()))

        self.table_widget.clearSelection()

    def reset_choice(self):
        self.setCurrentIndex(self.findText(self.start_value))


class VMRow:
    # pylint: disable=too-few-public-methods
    def __init__(self, vm, row_no, table_widget, columns, templates):
        self.vm = vm

        # icon and name
        self.name_item = VMNameItem(self.vm)
        table_widget.setItem(row_no, columns.index('Qube'), self.name_item)

        # state
        self.state_item = StatusItem(self.vm)
        table_widget.setItem(row_no, columns.index('State'), self.state_item)

        # current template
        self.current_item = CurrentTemplateItem(self.vm)
        table_widget.setItem(row_no, columns.index('Current template'),
                             self.current_item)

        # new template
        # this is needed to make the cell correctly selectable/non-selectable
        self.dummy_new_item = QtGui.QTableWidgetItem()
        self.new_item = NewTemplateItem(self.vm, templates, table_widget)

        table_widget.setCellWidget(row_no, columns.index('New template'),
                                   self.new_item)
        table_widget.setItem(row_no, columns.index('New template'),
                             self.dummy_new_item)

        self.vm_state_change(self.vm.is_running())

    def vm_state_change(self, is_running):
        self.new_item.setEnabled(not is_running)
        self.state_item.set_state(is_running)

        items = [self.name_item, self.state_item, self.current_item,
                 self.dummy_new_item]

        for item in items:
            if is_running:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)
            else:
                item.setFlags(item.flags() | QtCore.Qt.ItemIsSelectable)

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


def loop_shutdown():
    pending = asyncio.Task.all_tasks()
    for task in pending:
        with suppress(asyncio.CancelledError):
            task.cancel()


def main():
    qt_app = QtGui.QApplication(sys.argv)
    qt_app.setOrganizationName("The Qubes Project")
    qt_app.setOrganizationDomain("http://qubes-os.org")
    qt_app.setApplicationName("Qube Manager")
    qt_app.setWindowIcon(QtGui.QIcon.fromTheme("qubes-manager"))
    qt_app.lastWindowClosed.connect(loop_shutdown)

    qubes_app = Qubes()

    loop = quamash.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)
    dispatcher = events.EventsDispatcher(qubes_app)

    manager_window = TemplateManagerWindow(qt_app, qubes_app, dispatcher)
    manager_window.show()

    try:
        loop.run_until_complete(
            asyncio.ensure_future(dispatcher.listen_for_events()))
    except asyncio.CancelledError:
        pass
    except Exception: # pylint: disable=broad-except
        loop_shutdown()
        exc_type, exc_value, exc_traceback = sys.exc_info()[:3]
        handle_exception(exc_type, exc_value, exc_traceback)


if __name__ == "__main__":
    main()
