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

import qubesmanager.qrc_resources

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time
import threading
from operator import itemgetter

whitelisted_filename = 'whitelisted-appmenus.list'

class AppRowInTable(object):
    def __init__(self, filename, name, row_no, table):
        self.filename = filename
        self.row_no = row_no

        table.setRowHeight (row_no, AppmenuSelectWindow.row_height)

        self.name_widget = QTableWidgetItem(name)
        self.name_widget.setFlags (Qt.ItemIsSelectable | Qt.ItemIsEnabled )
        table.setItem(row_no, 0, self.name_widget)

        self.appvm_widget = QCheckBox()
        table.setCellWidget(row_no, 1, self.appvm_widget)

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

        self.table = QTableWidget(self)
        self.table.clear()
        self.table.setColumnCount(2)
        self.table.setColumnWidth (0, 200)
        self.table.setColumnWidth (1, 40)

        self.table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setResizeMode(1, QHeaderView.Fixed)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().show()
        self.table.setGridStyle(Qt.NoPen)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        self.gridLayout.addWidget(self.table, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.buttonBox, 1, 0, 1, 1)

        self.vm = vm
        if self.vm.template_vm:
            self.source_vm = self.vm.template_vm
        else:
            self.source_vm = self.vm
        self.setWindowTitle("Qubes Appmenus for %s" % vm.name)
        self.resize(250,500)

        self.fill_table()
        self.load_list_of_selected()

    def reject(self):
        self.done(0)

    def addActions(self, target, actions):
        for action in actions:
            if action is None:
                target.addSeparator()
            else:
                target.addAction(action)

    def createAction(self, text, slot=None, shortcut=None, icon=None,
                     tip=None, checkable=False, signal="triggered()"):
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(QIcon(":/%s.png" % icon))
        if shortcut is not None:
            action.setShortcut(shortcut)
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            self.connect(action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable(True)
        return action

    def fill_table(self):

        template_dir = self.source_vm.appmenus_templates_dir

        template_file_list = os.listdir(template_dir)

        self.table.clear()
        self.table.setHorizontalHeaderLabels(['Name', 'VM'])
        self.table.setRowCount(len(template_file_list))

        row_no = 0
        appmenus = []
        for template_file in template_file_list:
            desktop_template = open(template_dir + '/' + template_file, 'r')
            for line in desktop_template:
                if line.startswith("Name=%VMNAME%: "):
                    desktop_name = line.partition('Name=%VMNAME%: ')[2].strip()
                    row = AppRowInTable (template_file, desktop_name, row_no, self.table)
                    appmenus.append(row)
                    row_no += 1
                    break
            desktop_template.close()

        self.table.setRowCount(row_no)
        self.appmenus = appmenus
        self.table.sortItems(0)

    def load_list_of_selected(self):
        if not os.path.exists(self.vm.dir_path + '/' + whitelisted_filename):
            # select none
            for row in self.appmenus:
                row.appvm_widget.setCheckState(Qt.Unchecked)
            return

        f = open(self.vm.dir_path + '/' + whitelisted_filename, 'r')
        whitelisted = [item.strip() for item in f]
        f.close()
        for row in self.appmenus:
            if row.filename in whitelisted:
                row.appvm_widget.setCheckState(Qt.Checked)
            else:
                row.appvm_widget.setCheckState(Qt.Unchecked)

    def save_list_of_selected(self):
        whitelisted = open(self.vm.dir_path + '/' + whitelisted_filename, 'w')
        for row in self.appmenus:
            if row.appvm_widget.checkState() == Qt.Checked:
                whitelisted.write(row.filename + '\n')
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

