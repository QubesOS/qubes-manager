# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2011  Marek Marczykowski <marmarek@mimuw.edu.pl>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import subprocess
from PyQt6 import QtWidgets, QtCore  # pylint: disable=import-error
from qubesadmin import exc

# TODO description in tooltip
# TODO icon
# pylint: disable=too-few-public-methods
class AppListWidgetItem(QtWidgets.QListWidgetItem):
    def __init__(self, name, ident, tooltip=None, parent=None):
        super().__init__(name, parent)
        additional_description = ".desktop filename: " + str(ident)
        if not tooltip:
            tooltip = additional_description
        else:
            tooltip += "\n" + additional_description
        self.setToolTip(tooltip)
        self.setWhatsThis(ident)
        # Using identity as tooltip which also enables drag-and-drop
        self.setWhatsThis(ident)

    @classmethod
    def from_line(cls, line):
        ident, name, comment = line.split('|', maxsplit=3)
        return cls(name=name, ident=ident, tooltip=comment)

    @classmethod
    def from_ident(cls, ident):
        name = 'Application missing in template! ({})'.format(ident)
        comment = 'The listed application was available at some point to ' \
                  'this qube, but not any more. The most likely cause is ' \
                  'template change. Install the application in the template ' \
                  'if you want to restore it.'
        return cls(name=name, ident=ident, tooltip=comment)


class AppmenuSelectManager:
    def __init__(self, vm, apps_multiselect):
        self.vm = vm
        self.app_list = apps_multiselect # this is a multiselect wiget
        self.whitelisted = None
        self.has_missing = False
        self.fill_apps_list(template=None)

    def fill_apps_list(self, template=None):
        try:
            self.whitelisted = [line for line in subprocess.check_output(
                    ['qvm-appmenus', '--get-whitelist', self.vm.name]
                ).decode().strip().split('\n') if line]
        except exc.QubesException:
            self.whitelisted = []

        currently_selected = [
            self.app_list.selected_list.item(i).whatsThis()
            for i in range(self.app_list.selected_list.count())]

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
            available_appmenus = [
                AppListWidgetItem.from_line(line)
                for line in subprocess.check_output(
                    command).decode().splitlines()]
        except exc.QubesException:
            available_appmenus = []

        for app in available_appmenus:
            if app.whatsThis() in whitelist:
                self.app_list.selected_list.addItem(app)
                whitelist.remove(app.whatsThis())
            else:
                self.app_list.available_list.addItem(app)

        self.has_missing = bool(whitelist)

        for app in whitelist:
            item = AppListWidgetItem.from_ident(app)
            self.app_list.selected_list.addItem(item)

        self.app_list.available_list.sortItems()
        self.app_list.selected_list.sortItems()

    def save_appmenu_select_changes(self):
        new_whitelisted = [self.app_list.selected_list.item(i).whatsThis()
                           for i in range(self.app_list.selected_list.count())]

        if set(new_whitelisted) == set(self.whitelisted):
            return False

        try:
            self.vm.features['menu-items'] = " ".join(new_whitelisted)
        except exc.QubesException as ex:
            raise RuntimeError(QtCore.QCoreApplication.translate(
                "exception", 'Failed to set menu items')) from ex

        return True
