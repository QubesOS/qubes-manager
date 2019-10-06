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

from qubesadmin import exc

from PyQt5 import QtWidgets, QtGui, QtCore  # pylint: disable=import-error

from . import ui_templatemanager  # pylint: disable=no-name-in-module
from . import utils

column_names = ['State', 'Qube', 'Current template', 'New template']


class TemplateManagerWindow(
        ui_templatemanager.Ui_MainWindow, QtWidgets.QMainWindow):

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

        self.prepare_lists()
        self.initialize_table_events()

        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).clicked.connect(
            self.apply)
        self.buttonBox.button(
            QtWidgets.QDialogButtonBox.Cancel).clicked.connect(self.cancel)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Reset).clicked.connect(
            self.reset)

        self.change_all_combobox.currentIndexChanged.connect(
            self.change_all_changed)
        self.clear_selection_button.clicked.connect(self.clear_selection)

        self.vm_list.show()

    def prepare_lists(self):
        self.templates = [vm.name for vm in self.qubes_app.domains
                          if vm.klass == 'TemplateVM']

        self.change_all_combobox.addItem('(select template)')
        for template in self.templates:
            self.change_all_combobox.addItem(template)

        vms_with_templates = [vm for vm in self.qubes_app.domains
                              if getattr(vm, 'template', None) and
                              vm.klass != 'DispVM']

        self.vm_list.setColumnCount(len(column_names))
        self.vm_list.setRowCount(len(vms_with_templates))

        row_count = 0
        for vm in vms_with_templates:
            row = VMRow(vm, row_count, self.vm_list, column_names,
                        self.templates)
            self.rows_in_table[vm.name] = row
            row_count += 1

        self.vm_list.setHorizontalHeaderLabels(['', 'Qube', 'Current', 'New'])
        self.vm_list.resizeColumnsToContents()

    def initialize_table_events(self):
        self.vm_list.cellDoubleClicked.connect(self.table_double_click)
        self.vm_list.cellClicked.connect(self.table_click)

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
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._vm_added(vm, timer))
        self.timers.append(timer)
        timer.start(1000)  # 1s

    def _vm_added(self, vm_name, timer):
        self.timers.remove(timer)
        try:
            vm = self.qubes_app.domains[vm_name]
            if not getattr(vm, 'template', None) or vm.klass == 'DispVM':
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
        if index == column_names.index('New template') or \
                index == column_names.index('State'):
            self.vm_list.horizontalHeader().setSortIndicator(
                -1, QtCore.Qt.AscendingOrder)

    def clear_selection(self):
        for row in self.rows_in_table.values():
            if row.checkbox:
                row.checkbox.setChecked(False)

    def change_all_changed(self):
        if self.change_all_combobox.currentIndex() == 0:
            return
        selected_template = self.change_all_combobox.currentText()

        for row in self.rows_in_table.values():
            if row.checkbox and row.checkbox.isChecked():
                row.new_item.setCurrentIndex(
                    row.new_item.findText(selected_template))

        self.change_all_combobox.setCurrentIndex(0)

    def table_double_click(self, row, column):
        template_column = column_names.index('Current template')

        if column != template_column:
            return

        template_name = self.vm_list.item(row, column).text()

        for row_number in range(0, self.vm_list.rowCount()):
            if self.vm_list.item(
                    row_number, template_column).text() == template_name:
                checkbox = self.vm_list.cellWidget(
                    row_number, column_names.index('State'))
                if checkbox:
                    if row_number == row:
                        # this is because double click registers as a
                        # single click and a double click
                        checkbox.setChecked(False)
                    else:
                        checkbox.setChecked(True)

    def table_click(self, row, column):
        if column == column_names.index('New template'):
            return

        checkbox = self.vm_list.cellWidget(row, column_names.index('State'))
        if not checkbox:
            return

        checkbox.setChecked(not checkbox.isChecked())

    def reset(self):
        for row in self.rows_in_table.values():
            if row.new_item:
                row.new_item.reset_choice()
            if row.checkbox:
                row.checkbox.setChecked(False)

    def cancel(self):
        self.close()

    def apply(self):
        errors = {}
        for vm, row in self.rows_in_table.items():
            if row.new_item and row.new_item.changed:
                try:
                    setattr(self.qubes_app.domains[vm],
                            'template', row.new_item.currentText())
                except Exception as ex:  # pylint: disable=broad-except
                    errors[vm] = str(ex)
        if errors:
            error_messages = [vm + ": " + errors[vm] for vm in errors]
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Errors encountered!"),
                self.tr(
                    "Errors encountered on template change in the following "
                    "qubes: <br> {}.").format("<br> ".join(error_messages)))
        self.close()


class VMNameItem(QtWidgets.QTableWidgetItem):
    # pylint: disable=too-few-public-methods
    def __init__(self, vm):
        super(VMNameItem, self).__init__()
        self.vm = vm

        self.setText(self.vm.name)
        self.setIcon(QtGui.QIcon.fromTheme(vm.label.icon))


class StatusItem(QtWidgets.QTableWidgetItem):
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


class CurrentTemplateItem(QtWidgets.QTableWidgetItem):
    # pylint: disable=too-few-public-methods
    def __init__(self, vm):
        super(CurrentTemplateItem, self).__init__()
        self.vm = vm

        self.setText(self.vm.template.name)

    def __lt__(self, other):
        if self.text() == other.text():
            return self.vm.name < other.vm.name
        return self.text() < other.text()


class NewTemplateItem(QtWidgets.QComboBox):
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

    def reset_choice(self):
        self.setCurrentIndex(self.findText(self.start_value))


class VMRow:
    # pylint: disable=too-few-public-methods
    def __init__(self, vm, row_no, table_widget, columns, templates):
        self.vm = vm
        self.table_widget = table_widget
        self.templates = templates

        # state
        self.state_item = StatusItem(self.vm)
        table_widget.setItem(row_no, columns.index('State'), self.state_item)
        self.checkbox = QtWidgets.QCheckBox()

        # icon and name
        self.name_item = VMNameItem(self.vm)
        table_widget.setItem(row_no, columns.index('Qube'), self.name_item)

        # current template
        self.current_item = CurrentTemplateItem(self.vm)
        table_widget.setItem(row_no, columns.index('Current template'),
                             self.current_item)

        # new template
        self.dummy_new_item = QtWidgets.QTableWidgetItem("qube is running")
        self.new_item = NewTemplateItem(self.vm, templates, table_widget)

        table_widget.setItem(row_no, columns.index('New template'),
                             self.dummy_new_item)

        self.vm_state_change(self.vm.is_running(), row_no)

    def vm_state_change(self, is_running, row=None):
        self.state_item.set_state(is_running)

        if not row:
            row = 0
            while row < self.table_widget.rowCount():
                if self.table_widget.item(
                        row, column_names.index('Qube')).text() == \
                        self.name_item.text():
                    break
                row += 1

        # hiding cellWidgets does not work in a qTableWidget
        if not is_running:
            self.new_item = NewTemplateItem(self.vm, self.templates,
                                            self.table_widget)
            self.checkbox = QtWidgets.QCheckBox()

            self.table_widget.setCellWidget(
                row, column_names.index('New template'), self.new_item)
            self.table_widget.setCellWidget(
                row, column_names.index('State'), self.checkbox)
        else:
            new_template = self.table_widget.cellWidget(
                row, column_names.index('New template'))
            if new_template:
                self.table_widget.removeCellWidget(
                    row, column_names.index('New template'))
                self.new_item = None

            checkbox = self.table_widget.cellWidget(
                row, column_names.index('State'))
            if checkbox:
                self.table_widget.removeCellWidget(
                    row, column_names.index('State'))
                self.checkbox = None


def main():
    utils.run_asynchronous("Template Manager",
                           "qubes-manager",
                           TemplateManagerWindow)


if __name__ == "__main__":
    main()
