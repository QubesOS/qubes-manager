#!/usr/bin/python2.6
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski <marmarek@mimuw.edu.pl>
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

from ui_settingsdlg import *
from multiselectwidget import *



class VMSettingsWindow(Ui_SettingsDialog, QDialog):

    def __init__(self, vm, init_page=0, parent=None):
        super(VMSettingsWindow, self).__init__(parent)

        self.setupUi(self)
        if init_page in range(self.tabWidget.count()):
            self.tabWidget.setCurrentIndex(init_page)

        self.connect(self.buttonBox, SIGNAL("accepted()"), self.save_and_apply)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.reject)

        self.app_list = MultiSelectWidget(self)
        self.dev_list = MultiSelectWidget(self)
        
        self.apps_layout.addWidget(self.app_list)
        self.devices_layout.addWidget(self.dev_list)

        self.vm = vm
        if self.vm.template_vm:
            self.source_vm = self.vm.template_vm
        else:
            self.source_vm = self.vm

        
        #self.fill_apps_list()
        #self.fill_devices_list()

    def reject(self):
        self.done(0)

    def save_and_apply(self):
        pass

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
                         "in Qubes VM Settings application.<br><br>"
                         "<b><i>%s</i></b>" % error +
                         "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
                         % ( line, filename ))




def main():

    global qubes_host
    qubes_host = QubesHost()

    global app
    app = QApplication(sys.argv)
    app.setOrganizationName("The Qubes Project")
    app.setOrganizationDomain("http://qubes-os.org")
    app.setApplicationName("Qubes VM Settings")

    sys.excepthook = handle_exception

    qvm_collection = QubesVmCollection()
    qvm_collection.lock_db_for_reading()
    qvm_collection.load()
    qvm_collection.unlock_db()

    vm = None

    if len(sys.argv) > 1:
        vm = qvm_collection.get_vm_by_name(sys.argv[1])
        if vm is None or vm.qid not in qvm_collection:
            QMessageBox.critical(None, "Qubes VM Settings Error",
                    "A VM with the name '{0}' does not exist in the system.".format(sys.argv[1]))
            sys.exit(1)
    else:
        vms_list = [vm.name for vm in qvm_collection.values() if (vm.is_appvm() or vm.is_template())]
        vmname = QInputDialog.getItem(None, "Select VM", "Select VM:", vms_list, editable = False)
        if not vmname[1]:
            sys.exit(1)
        vm = qvm_collection.get_vm_by_name(vmname[0])

    global settings_window
    settings_window = VMSettingsWindow(vm)

    settings_window.show()

    app.exec_()
    app.exit()



if __name__ == "__main__":
    main()
