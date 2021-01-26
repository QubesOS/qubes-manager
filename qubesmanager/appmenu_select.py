#!/usr/bin/python2
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2011  Marek Marczykowski <marmarek@mimuw.edu.pl>
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

import subprocess
from PyQt5.QtCore import (Qt, QAbstractTableModel,
                          QCoreApplication)  # pylint: disable=import-error
from qubesadmin import exc

SHOW_HEADER = "Show \nin Menu"
APP_HEADER = "Application"
DISPVM_HEADER = "Open Files in \nDisposable VM"
DESCR_HEADER = "Description"


# TODO Add icon
class ApplicationData:
    def __init__(self, name, identifier,
                 description=None, dispvm=False, enabled=False):
        self.name = name
        self.identifier = identifier
        self.description = description
        self.tooltip = ".desktop filename: " + str(identifier)
        if description:
            self.tooltip = description + "\n" + self.tooltip
        self.dispvm = dispvm
        self.enabled = enabled

    @classmethod
    def from_line(cls, line):
        identifier, name, comment = line.split('|', maxsplit=3)
        return cls(name=name, identifier=identifier, description=comment)

    @classmethod
    def from_identifier(cls, identifier):
        name = 'Application missing in template! ({})'.format(identifier)
        comment = 'The listed application was available at some point to ' \
                  'this qube, but not any more. The most likely cause is ' \
                  'template change. Install the application in the template ' \
                  'if you want to restore it.'
        return cls(name=name, identifier=identifier, description=comment,
                   enabled=True)


class ApplicationModel(QAbstractTableModel):
    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.app_list = []
        self.apps_by_identifier = {}

    def get_application(self, row=None, identifier=None):
        if row is not None:
            return self.app_list[row]
        return self.apps_by_identifier[identifier]

    def add_application(self, application_data):
        self.app_list.append(application_data)
        self.apps_by_identifier[application_data.identifier] = application_data

    def clear(self):
        self.app_list.clear()
        self.apps_by_identifier.clear()

    def __len__(self):
        return len(self.app_list)

    def __iter__(self):
        return iter(self.app_list)


class ApplicationsTableModel(QAbstractTableModel):
    def __init__(self, app_data):
        QAbstractTableModel.__init__(self)
        self.app_data = app_data
        self.columns_indices = \
            [SHOW_HEADER, APP_HEADER, DISPVM_HEADER, DESCR_HEADER]

    # pylint: disable=invalid-name
    def rowCount(self, _):
        return len(self.app_data)

    # pylint: disable=invalid-name
    def columnCount(self, _):
        return len(self.columns_indices)

    # pylint: disable=too-many-return-statements
    def data(self, index, role):
        if not index.isValid():
            return None

        col = index.column()
        row = index.row()

        col_name = self.columns_indices[col]
        application = self.app_data.get_application(row=row)

        if role == Qt.DisplayRole:
            if col_name == APP_HEADER:
                return application.name
            if col_name == DESCR_HEADER:
                return application.description
        if role == Qt.CheckStateRole:
            if col_name == SHOW_HEADER:
                return Qt.Checked if application.enabled else Qt.Unchecked
            if col_name == DISPVM_HEADER:
                return Qt.Checked if application.dispvm else Qt.Unchecked
        if role == Qt.ToolTipRole:
            return application.tooltip
        # Used for sorting
        if role == Qt.UserRole + 1:
            if col_name == SHOW_HEADER:
                return application.enabled
            if col_name == DISPVM_HEADER:
                return application.dispvm
            return self.data(index, Qt.DisplayRole)

    # pylint: disable=invalid-name
    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns_indices[col]
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False

        if role == Qt.CheckStateRole:
            col_name = self.columns_indices[index.column()]
            if col_name == SHOW_HEADER:
                self.app_data.get_application(index.row()).enabled = \
                    (value == Qt.Checked)
                return True
            if col_name == DISPVM_HEADER:
                self.app_data.get_application(index.row()).dispvm = \
                    (value == Qt.Checked)
                return True
        return False

    def flags(self, index):
        if not index.isValid():
            return False

        def_flags = QAbstractTableModel.flags(self, index)
        if self.columns_indices[index.column()] in [SHOW_HEADER, DISPVM_HEADER]:
            return def_flags | Qt.ItemIsUserCheckable
        return def_flags


class AppmenuSelectManager:
    def __init__(self, vm, table_widget):
        self.vm = vm
        self.table_widget = table_widget
        self.app_list = ApplicationModel()
        self.whitelisted = None
        self.has_missing = False

        self.fill_apps_list(template=None)
        self.table_model = ApplicationsTableModel(self.app_list)

        # needed to avoid problems with alignment
        self.table_widget.setModel(None)

        self.table_widget.setModel(self.table_model)

        self.fix_formatting()

    def fix_formatting(self):
        # TODO: fix sorting
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.resizeColumnsToContents()

    def fill_apps_list(self, template=None):
        try:
            self.whitelisted = [line for line in subprocess.check_output(
                    ['qvm-appmenus', '--get-whitelist', self.vm.name]
                ).decode().strip().split('\n') if line]
        except exc.QubesException:
            self.whitelisted = []

        currently_selected =\
            [app.identifier for app in self.app_list.app_list if app.enabled]

        whitelist = set(self.whitelisted + currently_selected)

        # Check if appmenu entry is really installed
        # whitelisted = [a for a in whitelisted
        #  if os.path.exists('%s/apps/%s-%s' %
        # (self.vm.dir_path, self.vm.name, a))]

        self.app_list.clear()

        command = ['qvm-appmenus', '--get-available',
                   '--i-understand-format-is-unstable', '--file-field',
                   'Comment']
        if template:
            command.extend(['--template', template.name])
        command.append(self.vm.name)

        try:
            for line in subprocess.check_output(command).decode().splitlines():
                application = ApplicationData.from_line(line)
                application.enabled = (application.identifier in whitelist)
                if application.identifier in whitelist:
                    whitelist.remove(application.identifier)
                # TODO: add the dispvm part
                self.app_list.add_application(application)
        except exc.QubesException:
            self.app_list.clear() # TODO: make this more resilient

        self.has_missing = bool(whitelist)

        for app_ident in whitelist:
            application = ApplicationData.from_identifier(app_ident)
            self.app_list.add_application(application)

    def save_appmenu_select_changes(self):
        # TODO: add using DispVM settings
        new_whitelisted =\
            [app.identifier for app in self.app_list.app_list if app.enabled]

        if set(new_whitelisted) == set(self.whitelisted):
            return False

        p = subprocess.Popen([
            'qvm-appmenus', '--set-whitelist', '-', '--update', self.vm.name],
            stdin=subprocess.PIPE)
        p.communicate('\n'.join(new_whitelisted).encode())
        if p.returncode != 0:
            exception_text = QCoreApplication.translate(
                "Command {command} failed", "exception").format(
                command='qvm-appmenus --set-whitelist')
            raise RuntimeError(exception_text)

        return True
