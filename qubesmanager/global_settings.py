#!/usr/bin/python2
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
from qubes.qubes import QubesDaemonPidfile
from qubes.qubes import QubesHost
from qubes.qubes import system_path

import qubesmanager.resources_rc

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import time
import threading
from operator import itemgetter

from ui_globalsettingsdlg import *

from ConfigParser import SafeConfigParser
from qubes.qubesutils import parse_size
from qubes.qubesutils import updates_dom0_toggle,updates_vms_toggle,\
    updates_dom0_status,updates_vms_status
from qubes import qmemman_algo

dont_keep_dvm_in_memory_path = '/var/lib/qubes/dvmdata/dont-use-shm'
qmemman_config_path = '/etc/qubes/qmemman.conf'


class GlobalSettingsWindow(Ui_GlobalSettings, QDialog):

    def __init__(self, app, qvm_collection, parent=None):
        super(GlobalSettingsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection

        self.setupUi(self)
 
        self.connect(self.buttonBox, SIGNAL("accepted()"), self.save_and_apply)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.reject)
       
        self.__init_system_defaults__()
        self.__init_kernel_defaults__()
        self.__init_mem_defaults__()
        self.__init_updates__()


    def __init_system_defaults__(self):
        #updatevm and clockvm
        all_vms = [vm for vm in self.qvm_collection.values() if not vm.internal]
        self.updatevm_idx = -1

        current_update_vm = self.qvm_collection.get_updatevm_vm()
        for (i, vm) in enumerate(all_vms):
            text = vm.name
            if vm is current_update_vm:
                self.updatevm_idx = i
                text += " (current)"
            self.update_vm_combo.insertItem(i, text)
        self.update_vm_combo.insertItem(len(all_vms), "none")
        if current_update_vm is None:
            self.updatevm_idx = len(all_vms)
        self.update_vm_combo.setCurrentIndex(self.updatevm_idx)

        #clockvm 
        self.clockvm_idx = -1

        current_clock_vm = self.qvm_collection.get_clockvm_vm()
        for (i, vm) in enumerate(all_vms):
            text = vm.name
            if vm is current_clock_vm:
                self.clockvm_idx = i
                text += " (current)"
            self.clock_vm_combo.insertItem(i, text)
        self.clock_vm_combo.insertItem(len(all_vms), "none")
        if current_clock_vm is None:
            self.clockvm_idx = len(all_vms)
        self.clock_vm_combo.setCurrentIndex(self.clockvm_idx)

        #default netvm
        netvms = [vm for vm in all_vms if vm.is_netvm() and vm.qid != 0]
        self.netvm_idx = -1

        current_netvm = self.qvm_collection.get_default_netvm()
        for (i, vm) in enumerate(netvms):
            text = vm.name
            if vm is current_netvm:
                self.netvm_idx = i
                text += " (current)"
            self.default_netvm_combo.insertItem(i, text)
        if current_netvm is not None:
            self.default_netvm_combo.setCurrentIndex(self.netvm_idx)

        #default template
        templates = [vm for vm in all_vms if vm.is_template()]
        self.template_idx = -1

        current_template = self.qvm_collection.get_default_template()
        for (i, vm) in enumerate(templates):
            text = vm.name
            if vm is current_template:
                self.template_idx = i
                text += " (current)"
            self.default_template_combo.insertItem(i, text)
        if current_template is not None:
            self.default_template_combo.setCurrentIndex(self.template_idx)

    def __apply_system_defaults__(self):
        #upatevm
        if self.update_vm_combo.currentIndex() != self.updatevm_idx:
            updatevm_name = str(self.update_vm_combo.currentText())
            updatevm_name = updatevm_name.split(' ')[0]
            updatevm = self.qvm_collection.get_vm_by_name(updatevm_name)
            
            self.qvm_collection.set_updatevm_vm(updatevm)
            self.anything_changed = True

        #clockvm
        if self.clock_vm_combo.currentIndex() != self.clockvm_idx:
            clockvm_name = str(self.clock_vm_combo.currentText())
            clockvm_name = clockvm_name.split(' ')[0]
            clockvm = self.qvm_collection.get_vm_by_name(clockvm_name)
            
            self.qvm_collection.set_clockvm_vm(clockvm)
            self.anything_changed = True

        #default netvm
        if self.default_netvm_combo.currentIndex() != self.netvm_idx:
            name = str(self.default_netvm_combo.currentText())
            name = name.split(' ')[0]
            vm = self.qvm_collection.get_vm_by_name(name)
            
            self.qvm_collection.set_default_netvm(vm)
            self.anything_changed = True

        #default template
        if self.default_template_combo.currentIndex() != self.template_idx:
            name = str(self.default_template_combo.currentText())
            name = name.split(' ')[0]
            vm = self.qvm_collection.get_vm_by_name(name)
            
            self.qvm_collection.set_default_template(vm)
            self.anything_changed = True


    def __init_kernel_defaults__(self):
        kernel_list = []
        for k in os.listdir(system_path["qubes_kernels_base_dir"]):
            kernel_list.append(k)

        self.kernel_idx = 0

        for (i, k) in enumerate(kernel_list):
            text = k
            if k == self.qvm_collection.get_default_kernel():
                text += " (current)"
                self.kernel_idx = i
            self.default_kernel_combo.insertItem(i,text)
        self.default_kernel_combo.setCurrentIndex(self.kernel_idx)

    def __apply_kernel_defaults__(self):
        if self.default_kernel_combo.currentIndex() != self.kernel_idx:
            kernel = str(self.default_kernel_combo.currentText())
            kernel = kernel.split(' ')[0]
            
            self.qvm_collection.set_default_kernel(kernel)
            self.anything_changed = True

        
    def __init_mem_defaults__(self):

        #qmemman settings
        self.qmemman_config = SafeConfigParser()
        self.vm_min_mem_val =  str(qmemman_algo.MIN_PREFMEM)
        self.dom0_mem_boost_val = str(qmemman_algo.DOM0_MEM_BOOST)
        
        self.qmemman_config.read(qmemman_config_path)
        if self.qmemman_config.has_section('global'):
            self.vm_min_mem_val = self.qmemman_config.get('global', 'vm-min-mem')
            self.dom0_mem_boost_val = self.qmemman_config.get('global', 'dom0-mem-boost')

        self.vm_min_mem_val = parse_size(self.vm_min_mem_val)
        self.dom0_mem_boost_val = parse_size(self.dom0_mem_boost_val)

        self.min_vm_mem.setValue(self.vm_min_mem_val/1024/1024)
        self.dom0_mem_boost.setValue(self.dom0_mem_boost_val/1024/1024)

        #keep dispvm in memory
        exists = os.path.exists(dont_keep_dvm_in_memory_path)
        self.dispvm_in_memory.setChecked( not exists)

    
    def __apply_mem_defaults__(self):

        #qmemman settings
        current_min_vm_mem = self.min_vm_mem.value()
        current_dom0_mem_boost = self.dom0_mem_boost.value()

        if current_min_vm_mem*1024*1024 != self.vm_min_mem_val or current_dom0_mem_boost*1024*1024 != self.dom0_mem_boost_val:

            current_min_vm_mem = str(current_min_vm_mem)+'M'
            current_dom0_mem_boost = str(current_dom0_mem_boost)+'M'

            if not self.qmemman_config.has_section('global'):
                #add the whole section
                self.qmemman_config.add_section('global')
                self.qmemman_config.set('global', 'vm-min-mem', current_min_vm_mem)
                self.qmemman_config.set('global', 'dom0-mem-boost', current_dom0_mem_boost)
                self.qmemman_config.set('global', 'cache-margin-factor', str(qmemman_algo.CACHE_FACTOR))

                qmemman_config_file = open(qmemman_config_path, 'a')
                self.qmemman_config.write(qmemman_config_file)
                qmemman_config_file.close()

            else:
                #If there already is a 'global' section, we don't use SafeConfigParser.write() - it would get rid of all the comments...
                
                lines_to_add = {}
                lines_to_add['vm-min-mem'] = "vm-min-mem = " + current_min_vm_mem + "\n"
                lines_to_add['dom0-mem-boost'] = "dom0-mem-boost = " + current_dom0_mem_boost +"\n"

                config_lines = []

                qmemman_config_file = open(qmemman_config_path, 'r')
                for l in qmemman_config_file:
                    if l.strip().startswith('vm-min-mem'):
                        config_lines.append(lines_to_add['vm-min-mem'])
                        del lines_to_add['vm-min-mem']
                    elif l.strip().startswith('dom0-mem-boost'):
                        config_lines.append(lines_to_add['dom0-mem-boost'])
                        del lines_to_add['dom0-mem-boost']
                    else:
                        config_lines.append(l)
                
                qmemman_config_file.close()

                for l in lines_to_add:
                    config_lines.append(l)

                qmemman_config_file = open(qmemman_config_path, 'w')
                qmemman_config_file.writelines(config_lines)
                qmemman_config_file.close()

            self.anything_changed = True
        
        #keep dispvm in memory
        was_checked = not os.path.exists(dont_keep_dvm_in_memory_path)
        if was_checked != self.dispvm_in_memory.isChecked():
            if was_checked:
                #touch file
                open(dont_keep_dvm_in_memory_path, 'w').close()
            else:
                #rm file
                os.remove(dont_keep_dvm_in_memory_path)
            self.anything_changed = True

    def __init_updates__(self):
        self.updates_val = False
        self.updates_dom0_val = updates_dom0_status(self.qvm_collection)
        self.updates_dom0.setChecked(self.updates_dom0_val)
        updates_vms = updates_vms_status(self.qvm_collection)
        if updates_vms is None:
            self.updates_vm.setCheckState(Qt.PartiallyChecked)
        else:
            self.updates_vm.setCheckState(updates_vms)

    def __apply_updates__(self):
        if self.updates_dom0.isChecked() != self.updates_dom0_val:
            updates_dom0_toggle(self.qvm_collection, self.updates_dom0.isChecked())
        if self.updates_vm.checkState() != Qt.PartiallyChecked:
            self.anything_changed = True
            updates_vms_toggle(self.qvm_collection, self.updates_vm
                               .isChecked())

    def reject(self):
        self.done(0)

    def save_and_apply(self):
        self.qvm_collection.lock_db_for_writing()
    
        self.anything_changed = False
        self.__apply_system_defaults__()        
        self.__apply_kernel_defaults__()
        self.__apply_mem_defaults__()
        self.__apply_updates__()

        if self.anything_changed == True:
            self.qvm_collection.save()
        self.qvm_collection.unlock_db()

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
                         "in Qubes Global Settings application.<br><br>"
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
    app.setApplicationName("Qubes Global Settings")

    sys.excepthook = handle_exception

    qvm_collection = QubesVmCollection()
    qvm_collection.lock_db_for_reading()
    qvm_collection.load()
    qvm_collection.unlock_db()

    global global_window
    global_window = GlobalSettingsWindow()

    global_window.show()

    app.exec_()
    app.exit()



if __name__ == "__main__":
    main()
