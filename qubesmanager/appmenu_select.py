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
import PyQt5.QtWidgets  # pylint: disable=import-error


# TODO description in tooltip
# TODO icon
# pylint: disable=too-few-public-methods
class AppListWidgetItem(PyQt5.QtWidgets.QListWidgetItem):
    def __init__(self, name, ident, tooltip=None, parent=None):
        super(AppListWidgetItem, self).__init__(name, parent)
        if tooltip:
            self.setToolTip(tooltip)
        self.ident = ident

    @classmethod
    def from_line(cls, line):
        ident, name, comment = line.split('|', maxsplit=3)
        return cls(name=name, ident=ident, tooltip=comment)


class AppmenuSelectManager:
    def __init__(self, vm, apps_multiselect):
        self.vm = vm
        self.app_list = apps_multiselect # this is a multiselect wiget
        self.whitelisted = None
        self.fill_apps_list()

    def fill_apps_list(self):
        self.whitelisted = [line for line in subprocess.check_output(
                ['qvm-appmenus', '--get-whitelist', self.vm.name]
            ).decode().strip().split('\n') if line]

        # Check if appmenu entry is really installed
        # whitelisted = [a for a in whitelisted
        #  if os.path.exists('%s/apps/%s-%s' %
        # (self.vm.dir_path, self.vm.name, a))]

        self.app_list.clear()

        available_appmenus = [AppListWidgetItem.from_line(line)
            for line in subprocess.check_output(
                ['qvm-appmenus', '--get-available',
                 '--i-understand-format-is-unstable', '--file-field',
                 'Comment', self.vm.name]).decode().splitlines()]

        for app in available_appmenus:
            if app.ident in self.whitelisted:
                self.app_list.selected_list.addItem(app)
            else:
                self.app_list.available_list.addItem(app)

        self.app_list.available_list.sortItems()
        self.app_list.selected_list.sortItems()

    def save_appmenu_select_changes(self):
        new_whitelisted = [self.app_list.selected_list.item(i).ident
                           for i in range(self.app_list.selected_list.count())]

        if set(new_whitelisted) == set(self.whitelisted):
            return False

        p = subprocess.Popen([
            'qvm-appmenus', '--set-whitelist', '-', '--update', self.vm.name],
            stdin=subprocess.PIPE)
        p.communicate('\n'.join(new_whitelisted).encode())
        if p.returncode != 0:
            raise RuntimeError('qvm-appmenus --set-whitelist failed')

        return True
