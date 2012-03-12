#!/usr/bin/python2.6
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

import sys
import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesException
from qubes.qubes import qubes_appmenu_create_cmd
from qubes.qubes import qubes_appmenu_remove_cmd
from qubes.qubes import QubesDaemonPidfile
from qubes.qubes import QubesHost
from qubes.qubes import qrexec_client_path

import qubesmanager.resources_rc

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time

from operator import itemgetter

from thread_monitor import *
from multiselectwidget import *

whitelisted_filename = 'whitelisted-appmenus.list'

class AppListWidgetItem(QListWidgetItem):
    def __init__(self, name, filename, parent = None):
        super(AppListWidgetItem, self).__init__(name, parent)
        self.filename = filename



class AppmenuSelectManager:
    def __init__(self, vm, apps_multiselect, parent=None):

        self.app_list = apps_multiselect # this is a multiselect wiget
        
        self.vm = vm
        if self.vm.template:
            self.source_vm = self.vm.template
        else:
            self.source_vm = self.vm

        self.fill_apps_list()

    def fill_apps_list(self):

        template_dir = self.source_vm.appmenus_templates_dir

        template_file_list = os.listdir(template_dir)

        whitelisted = []
        if os.path.exists(self.vm.dir_path + '/' + whitelisted_filename):
            f = open(self.vm.dir_path + '/' + whitelisted_filename, 'r')
            whitelisted = [item.strip() for item in f]
            f.close()

        self.app_list.clear()


        available_appmenus = []
        for template_file in template_file_list:
            desktop_template = open(template_dir + '/' + template_file, 'r')
            for line in desktop_template:
                if line.startswith("Name=%VMNAME%: "):
                    desktop_name = line.partition('Name=%VMNAME%: ')[2].strip()
                    available_appmenus.append( (template_file, desktop_name) )
                    break
            desktop_template.close()

        whitelisted_appmenus = [a for a in available_appmenus if a[0] in whitelisted]
        available_appmenus = [a for a in available_appmenus if a[0] not in whitelisted]
                
        for a in available_appmenus:
            self.app_list.available_list.addItem( AppListWidgetItem(a[1], a[0]))

        for a in whitelisted_appmenus:
            self.app_list.selected_list.addItem( AppListWidgetItem(a[1], a[0]))
   
        self.app_list.available_list.sortItems()
        self.app_list.selected_list.sortItems()

    def save_list_of_selected(self):
        whitelisted = open(self.vm.dir_path + '/' + whitelisted_filename, 'w')
        for i in range(self.app_list.selected_list.count()):
            item = self.app_list.selected_list.item(i)
            whitelisted.write(item.filename + '\n')
        whitelisted.close()        
 

    def save_appmenu_select_changes(self):
        self.save_list_of_selected()
        subprocess.check_call([qubes_appmenu_remove_cmd, self.vm.name])
        subprocess.check_call([qubes_appmenu_create_cmd, self.source_vm.appmenus_templates_dir, self.vm.name])

