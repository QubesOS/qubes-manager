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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#

import os
import subprocess
import sys
import time

from operator import itemgetter

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import qubesmanager.resources_rc

# TODO description in tooltip
# TODO icon
class AppListWidgetItem(QListWidgetItem):
    def __init__(self, name, ident, parent=None):
        super(AppListWidgetItem, self).__init__(name, parent)
#       self.setToolTip(command)
        self.ident = ident

    @classmethod
    def from_line(cls, line):
        ident, icon_name, name = line.strip().split(maxsplit=2)
        return cls(name=name, ident=ident)


class AppmenuSelectManager:
    def __init__(self, vm, apps_multiselect, parent=None):
        self.vm = vm
        self.app_list = apps_multiselect # this is a multiselect wiget
        self.fill_apps_list()

    def fill_apps_list(self):
        whitelisted = [line for line in subprocess.check_output(
                ['qvm-appmenus', '--get-whitelist', self.vm.name]
            ).decode().strip().split('\n') if line]

        # Check if appmenu entry is really installed
#       whitelisted = [a for a in whitelisted if os.path.exists('%s/apps/%s-%s' % (self.vm.dir_path, self.vm.name, a))]

        self.app_list.clear()

        available_appmenus = [AppListWidgetItem.from_line(line)
            for line in subprocess.check_output(['qvm-appmenus',
                    '--get-available', '--i-understand-format-is-unstable',
                    self.vm.name]).decode().split()]

        for a in available_appmenus:
            if a.ident in whitelisted:
                self.app_list.selected_list.addItem(a)
            else:
                self.app_list.available_list.addItem(a)

        self.app_list.available_list.sortItems()
        self.app_list.selected_list.sortItems()

    def save_list_of_selected(self):
        added = []

        new_whitelisted = [self.app_list.selected_list.item(i).ident
            for i in range(self.app_list.selected_list.count())]

        subprocess.check_call(
            'qvm-appmenus', '--set-whitelist', '-', self.vm.name,
            input='\n'.join(new_whitelisted))

        return True


    def save_appmenu_select_changes(self):
        if self.save_list_of_selected():
            self.vm.appmenus_recreate()
