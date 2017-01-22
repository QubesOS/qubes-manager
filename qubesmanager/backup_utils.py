#!/usr/bin/python2
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
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
import re
import sys
import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *

import subprocess
import time
from qubes.qubes import QubesException

from thread_monitor import *

from datetime import datetime
from string import replace

path_re = re.compile(r"[a-zA-Z0-9/:.,_+=() -]*")
path_max_len = 512

def fill_appvms_list(dialog):
    dialog.appvm_combobox.clear()
    dialog.appvm_combobox.addItem("dom0")

    dialog.appvm_combobox.setCurrentIndex(0) #current selected is null ""

    for vm in dialog.qvm_collection.values():
        if vm.is_appvm() and vm.internal:
            continue
        if vm.is_template() and vm.installed_by_rpm:
            continue

        if vm.is_running() and vm.qid != 0:
            dialog.appvm_combobox.addItem(vm.name)

def enable_dir_line_edit(dialog, boolean):
    dialog.dir_line_edit.setEnabled(boolean)
    dialog.select_path_button.setEnabled(boolean)

def get_path_for_vm(vm, service_name):
    if not vm:
        return None
    proc = vm.run("QUBESRPC %s dom0" % service_name, passio_popen=True)
    proc.stdin.close()
    untrusted_path = proc.stdout.readline(path_max_len)
    if len(untrusted_path) == 0:
        return None
    if path_re.match(untrusted_path):
        assert '../' not in untrusted_path
        assert '\0' not in untrusted_path
        return untrusted_path.strip()
    else:
        return None

def select_path_button_clicked(dialog, select_file = False):
    backup_location = str(dialog.dir_line_edit.text())
    file_dialog = QFileDialog()
    file_dialog.setReadOnly(True)

    if select_file:
        file_dialog_function = file_dialog.getOpenFileName
    else:
        file_dialog_function = file_dialog.getExistingDirectory

    new_appvm = None
    new_path = None
    if dialog.appvm_combobox.currentIndex() != 0:   #An existing appvm chosen
        new_appvm = str(dialog.appvm_combobox.currentText())
        vm = dialog.qvm_collection.get_vm_by_name(new_appvm)
        if vm:
            new_path = get_path_for_vm(vm, "qubes.SelectFile" if select_file
                    else "qubes.SelectDirectory")
    else:
        new_path = file_dialog_function(dialog,
            dialog.tr("Select backup location."),
            backup_location if backup_location else '/')

    if new_path != None:
        new_path = unicode(new_path)
        if os.path.basename(new_path) == 'qubes.xml':
            backup_location = os.path.dirname(new_path)
        else:
            backup_location = new_path
        dialog.dir_line_edit.setText(backup_location)

    if (new_path or new_appvm) and len(backup_location) > 0:
        dialog.select_dir_page.emit(SIGNAL("completeChanged()"))

def simulate_long_lasting_proces(period, progress_callback):
    for i in range(period):
        progress_callback((i*100)/period)
        time.sleep(1)

    progress_callback(100)
    return 0