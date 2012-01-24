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
import threading
from operator import itemgetter

from multiselectwidget import *

whitelisted_filename = 'whitelisted-appmenus.list'

class AppListWidgetItem(QListWidgetItem):
    def __init__(self, name, filename, parent = None):
        super(AppListWidgetItem, self).__init__(name, parent)
        self.filename = filename

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


class AppmenuSelectWindow(QDialog):
    row_height = 20

    def __init__(self, vm, parent=None):
        super(AppmenuSelectWindow, self).__init__(parent)

        self.gridLayout = QGridLayout(self)

        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.connect(self.buttonBox, SIGNAL("accepted()"), self.save_and_apply)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.reject)

        self.app_list = MultiSelectWidget(self)

        
        self.gridLayout.addWidget(self.app_list, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.buttonBox, 1, 0, 1, 1)

        self.vm = vm
        if self.vm.template_vm:
            self.source_vm = self.vm.template_vm
        else:
            self.source_vm = self.vm
        self.setWindowTitle("Qubes Appmenus for %s" % vm.name)
        self.resize(600,600)

        self.fill_apps_list()

    def reject(self):
        self.done(0)
 
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
 

    def save_and_apply(self):
        self.save_list_of_selected()
        subprocess.check_call([qubes_appmenu_remove_cmd, self.vm.name])
        subprocess.check_call([qubes_appmenu_create_cmd, self.source_vm.appmenus_templates_dir, self.vm.name])
        self.done(0)

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
                         "in Qubes Appmenu Select application.<br><br>"
                         "<b><i>%s</i></b>" % error +
                         "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
                         % ( line, filename ))

    #sys.exit(1)

def main():


    global qubes_host
    qubes_host = QubesHost()

    global app
    app = QApplication(sys.argv)
    app.setOrganizationName("The Qubes Project")
    app.setOrganizationDomain("http://qubes-os.org")
    app.setApplicationName("Qubes Appmenu Select")
    app.setWindowIcon(QIcon(":/qubes.png"))

    sys.excepthook = handle_exception

    qvm_collection = QubesVmCollection()
    qvm_collection.lock_db_for_reading()
    qvm_collection.load()
    qvm_collection.unlock_db()

    vm = None

    if len(sys.argv) > 1:
        vm = qvm_collection.get_vm_by_name(sys.argv[1])
        if vm is None or vm.qid not in qvm_collection:
            QMessageBox.critical(None, "Qubes Appmenu Select Error",
                    "A VM with the name '{0}' does not exist in the system.".format(sys.argv[1]))
            sys.exit(1)
    else:
        vms_list = [vm.name for vm in qvm_collection.values() if (vm.is_appvm() or vm.is_template())]
        vmname = QInputDialog.getItem(None, "Select VM", "Select VM:", vms_list, editable = False)
        if not vmname[1]:
            sys.exit(1)
        vm = qvm_collection.get_vm_by_name(vmname[0])

    global manager_window
    select_window = AppmenuSelectWindow(vm)

    select_window.show()

    app.exec_()
    app.exit()

