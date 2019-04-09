#!/usr/bin/python3
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
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
#
#

import sys
import os
import os.path
import traceback
import subprocess
from PyQt4 import QtCore, QtGui  # pylint: disable=import-error

from qubesadmin import Qubes
from qubesadmin.utils import parse_size

from . import ui_globalsettingsdlg  # pylint: disable=no-name-in-module
from . import utils

from configparser import ConfigParser

qmemman_config_path = '/etc/qubes/qmemman.conf'

def _run_qrexec_repo(service, arg=''):
    # Fake up a "qrexec call" to dom0 because dom0 can't qrexec to itself yet
    cmd = '/etc/qubes-rpc/' + service
    p = subprocess.run(
        ['sudo', cmd, arg],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    assert not p.stderr
    assert p.returncode == 0
    return p.stdout.decode('utf-8')

def _manage_repos(repolist, action):
    for i in repolist:
        result = _run_qrexec_repo('qubes.repos.' + action, i)
        assert result == 'ok\n'

def _handle_dom0_updates_combobox(idx):
    idx += 1
    repolist = ['qubes-dom0-current', 'qubes-dom0-security-testing',
         'qubes-dom0-current-testing', 'qubes-dom0-unstable']
    enable = repolist[:idx]
    disable = repolist[idx:]
    _manage_repos(enable, 'Enable')
    _manage_repos(disable, 'Disable')

# pylint: disable=invalid-name
def _handle_itl_tmpl_updates_combobox(idx):
    idx += 1
    repolist = ['qubes-templates-itl', 'qubes-templates-itl-testing']
    enable = repolist[:idx]
    disable = repolist[idx:]
    _manage_repos(enable, 'Enable')
    _manage_repos(disable, 'Disable')

# pylint: disable=invalid-name
def _handle_comm_tmpl_updates_combobox(idx):
    # We don't increment idx by 1 because this is the only combobox that
    # has an explicit "disable this repository entirely" option
    repolist = ['qubes-templates-community',
                'qubes-templates-community-testing']
    enable = repolist[:idx]
    disable = repolist[idx:]
    _manage_repos(enable, 'Enable')
    _manage_repos(disable, 'Disable')

# pylint: disable=too-many-instance-attributes
class GlobalSettingsWindow(ui_globalsettingsdlg.Ui_GlobalSettings,
                           QtGui.QDialog):

    def __init__(self, app, qvm_collection, parent=None):
        super(GlobalSettingsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection

        self.setupUi(self)

        self.connect(
            self.buttonBox,
            QtCore.SIGNAL("accepted()"),
            self.save_and_apply)
        self.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), self.reject)

        self.__init_system_defaults__()
        self.__init_kernel_defaults__()
        self.__init_mem_defaults__()
        self.__init_updates__()

    def __init_system_defaults__(self):
        # set up updatevm choice
        self.update_vm_vmlist, self.update_vm_idx = utils.prepare_vm_choice(
            self.update_vm_combo, self.qvm_collection, 'updatevm',
            None, allow_none=True,
            filter_function=(lambda vm: vm.klass != 'TemplateVM')
        )

        # set up clockvm choice
        self.clock_vm_vmlist, self.clock_vm_idx = utils.prepare_vm_choice(
            self.clock_vm_combo, self.qvm_collection, 'clockvm',
            None, allow_none=True,
            filter_function=(lambda vm: vm.klass != 'TemplateVM')
        )

        # set up default netvm
        self.default_netvm_vmlist, self.default_netvm_idx = \
            utils.prepare_vm_choice(
                self.default_netvm_combo,
                self.qvm_collection, 'default_netvm',
                None,
                filter_function=(lambda vm: vm.provides_network),
                allow_none=True)

        # default template
        self.default_template_vmlist, self.default_template_idx = \
            utils.prepare_vm_choice(
                self.default_template_combo,
                self.qvm_collection, 'default_template',
                None,
                filter_function=(lambda vm: vm.klass == 'TemplateVM'),
                allow_none=True
            )

        # default dispvm
        self.default_dispvm_vmlist, self.default_dispvm_idx = \
            utils.prepare_vm_choice(
                self.default_dispvm_combo,
                self.qvm_collection, 'default_dispvm',
                None,
                (lambda vm: getattr(vm, 'template_for_dispvms', False)),
                allow_none=True
            )

    def __apply_system_defaults__(self):
        # updatevm
        if self.qvm_collection.updatevm != \
                self.update_vm_vmlist[self.update_vm_combo.currentIndex()]:
            self.qvm_collection.updatevm = \
                self.update_vm_vmlist[self.update_vm_combo.currentIndex()]

        # clockvm
        if self.qvm_collection.clockvm !=\
                self.clock_vm_vmlist[self.clock_vm_combo.currentIndex()]:
            self.qvm_collection.clockvm = \
                self.clock_vm_vmlist[self.clock_vm_combo.currentIndex()]

        # default netvm
        if self.qvm_collection.default_netvm !=\
                self.default_netvm_vmlist[
                    self.default_netvm_combo.currentIndex()]:
            self.qvm_collection.default_netvm = \
                self.default_netvm_vmlist[
                    self.default_netvm_combo.currentIndex()]

        # default template
        if self.qvm_collection.default_template != \
                self.default_template_vmlist[
                    self.default_template_combo.currentIndex()]:
            self.qvm_collection.default_template = \
                self.default_template_vmlist[
                    self.default_template_combo.currentIndex()]

        # default_dispvm
        if self.qvm_collection.default_dispvm != \
                self.default_dispvm_vmlist[
                    self.default_dispvm_combo.currentIndex()]:
            self.qvm_collection.default_dispvm = \
                self.default_dispvm_vmlist[
                    self.default_dispvm_combo.currentIndex()]

    def __init_kernel_defaults__(self):
        self.kernels_list, self.kernels_idx = utils.prepare_kernel_choice(
            self.default_kernel_combo, self.qvm_collection, 'default_kernel',
            None,
            allow_none=True
        )

    def __apply_kernel_defaults__(self):
        if self.qvm_collection.default_kernel != \
                self.kernels_list[self.default_kernel_combo.currentIndex()]:
            self.qvm_collection.default_kernel = \
                self.kernels_list[self.default_kernel_combo.currentIndex()]

    def __init_mem_defaults__(self):
        #qmemman settings
        self.qmemman_config = ConfigParser()
        self.vm_min_mem_val = '200MiB'  #str(qmemman_algo.MIN_PREFMEM)
        self.dom0_mem_boost_val = '350MiB' #str(qmemman_algo.DOM0_MEM_BOOST)

        self.qmemman_config.read(qmemman_config_path)
        if self.qmemman_config.has_section('global'):
            self.vm_min_mem_val = \
                self.qmemman_config.get('global', 'vm-min-mem')
            self.dom0_mem_boost_val = \
                self.qmemman_config.get('global', 'dom0-mem-boost')

        self.vm_min_mem_val = parse_size(self.vm_min_mem_val)
        self.dom0_mem_boost_val = parse_size(self.dom0_mem_boost_val)

        self.min_vm_mem.setValue(self.vm_min_mem_val/1024/1024)
        self.dom0_mem_boost.setValue(self.dom0_mem_boost_val/1024/1024)


    def __apply_mem_defaults__(self):

        #qmemman settings
        current_min_vm_mem = self.min_vm_mem.value()
        current_dom0_mem_boost = self.dom0_mem_boost.value()

        if current_min_vm_mem*1024*1024 != self.vm_min_mem_val \
                or current_dom0_mem_boost*1024*1024 != self.dom0_mem_boost_val:

            current_min_vm_mem = str(current_min_vm_mem)+'MiB'
            current_dom0_mem_boost = str(current_dom0_mem_boost)+'MiB'

            if not self.qmemman_config.has_section('global'):
                #add the whole section
                self.qmemman_config.add_section('global')
                self.qmemman_config.set(
                    'global', 'vm-min-mem', current_min_vm_mem)
                self.qmemman_config.set(
                    'global', 'dom0-mem-boost', current_dom0_mem_boost)
                self.qmemman_config.set(
                    'global', 'cache-margin-factor', str(1.3))
                # removed qmemman_algo.CACHE_FACTOR

                qmemman_config_file = open(qmemman_config_path, 'a')
                self.qmemman_config.write(qmemman_config_file)
                qmemman_config_file.close()

            else:
                #If there already is a 'global' section, we don't use
                # SafeConfigParser.write() - it would get rid of
                # all the comments...

                lines_to_add = {}
                lines_to_add['vm-min-mem'] = \
                    "vm-min-mem = " + current_min_vm_mem + "\n"
                lines_to_add['dom0-mem-boost'] = \
                    "dom0-mem-boost = " + current_dom0_mem_boost +"\n"

                config_lines = []

                qmemman_config_file = open(qmemman_config_path, 'r')
                for line in qmemman_config_file:
                    if line.strip().startswith('vm-min-mem'):
                        config_lines.append(lines_to_add['vm-min-mem'])
                        del lines_to_add['vm-min-mem']
                    elif line.strip().startswith('dom0-mem-boost'):
                        config_lines.append(lines_to_add['dom0-mem-boost'])
                        del lines_to_add['dom0-mem-boost']
                    else:
                        config_lines.append(line)

                qmemman_config_file.close()

                for line in lines_to_add:
                    config_lines.append(line)

                qmemman_config_file = open(qmemman_config_path, 'w')
                qmemman_config_file.writelines(config_lines)
                qmemman_config_file.close()

    def __init_updates__(self):
        # TODO: remove workaround when it is no longer needed
        self.dom0_updates_file_path = '/var/lib/qubes/updates/disable-updates'

        try:
            self.updates_dom0_val = bool(self.qvm_collection.domains[
                'dom0'].features['service.qubes-update-check'])
        except KeyError:
            self.updates_dom0_val =\
                not os.path.isfile(self.dom0_updates_file_path)

        self.updates_dom0.setChecked(self.updates_dom0_val)

        self.updates_vm.setChecked(self.qvm_collection.check_updates_vm)
        self.enable_updates_all.clicked.connect(self.__enable_updates_all)
        self.disable_updates_all.clicked.connect(self.__disable_updates_all)

        repos = dict()
        for i in _run_qrexec_repo('qubes.repos.List').split('\n'):
            l = i.split('\0')
            # Keyed by repo name
            d = repos[l[0]] = dict()
            d['prettyname'] = l[1]
            d['enabled'] = l[2] == 'enabled'

        if repos['qubes-dom0-unstable']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(3)
        elif repos['qubes-dom0-current-testing']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(2)
        elif repos['qubes-dom0-security-testing']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(1)
        elif repos['qubes-dom0-current']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(0)
        else:
            raise Exception('Cannot detect enabled dom0 update repositories')

        if repos['qubes-templates-itl-testing']['enabled']:
            self.itl_tmpl_updates_repo.setCurrentIndex(1)
        elif repos['qubes-templates-itl']['enabled']:
            self.itl_tmpl_updates_repo.setCurrentIndex(0)
        else:
            raise Exception('Cannot detect enabled ITL template update '
                            'repositories')

        if repos['qubes-templates-community-testing']['enabled']:
            self.comm_tmpl_updates_repo.setCurrentIndex(2)
        elif repos['qubes-templates-community']['enabled']:
            self.comm_tmpl_updates_repo.setCurrentIndex(1)
        else:
            self.comm_tmpl_updates_repo.setCurrentIndex(0)

        self.dom0_updates_repo.currentIndexChanged.connect(
            _handle_dom0_updates_combobox
        )
        self.itl_tmpl_updates_repo.currentIndexChanged.connect(
            _handle_itl_tmpl_updates_combobox
        )
        self.comm_tmpl_updates_repo.currentIndexChanged.connect(
            _handle_comm_tmpl_updates_combobox
        )

    def __enable_updates_all(self):
        reply = QtGui.QMessageBox.question(
            self, self.tr("Change state of all qubes"),
            self.tr("Are you sure you want to set all qubes to check "
                    "for updates?"),
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel)
        if reply == QtGui.QMessageBox.Cancel:
            return

        self.__set_updates_all(True)

    def __disable_updates_all(self):
        reply = QtGui.QMessageBox.question(
            self, self.tr("Change state of all qubes"),
            self.tr("Are you sure you want to set all qubes to not check "
                    "for updates?"),
            QtGui.QMessageBox.Yes | QtGui.QMessageBox.Cancel)
        if reply == QtGui.QMessageBox.Cancel:
            return

        self.__set_updates_all(False)

    def __set_updates_all(self, state):
        for vm in self.qvm_collection.domains:
            if vm.klass != "AdminVM":
                vm.features['service.qubes-update-check'] = state

    def __apply_updates__(self):
        if self.updates_dom0.isChecked() != self.updates_dom0_val:
            self.qvm_collection.domains['dom0'].features[
                'service.qubes-update-check'] = \
                self.updates_dom0.isChecked()

        if self.qvm_collection.check_updates_vm != self.updates_vm.isChecked():
            self.qvm_collection.check_updates_vm = self.updates_vm.isChecked()

    def reject(self):
        self.done(0)

    def save_and_apply(self):

        self.__apply_system_defaults__()
        self.__apply_kernel_defaults__()
        self.__apply_mem_defaults__()
        self.__apply_updates__()



# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception(exc_type, exc_value, exc_traceback):
    filename, line, dummy, dummy = traceback.extract_tb(exc_traceback).pop()
    filename = os.path.basename(filename)
    error = "%s: %s" % (exc_type.__name__, exc_value)

    QtGui.QMessageBox.critical(
        None,
        "Houston, we have a problem...",
        "Whoops. A critical error has occured. This is most likely a bug "
        "in Qubes Global Settings application.<br><br><b><i>%s</i></b>" %
        error + "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
        % (line, filename))


def main():
    qtapp = QtGui.QApplication(sys.argv)
    qtapp.setOrganizationName("The Qubes Project")
    qtapp.setOrganizationDomain("http://qubes-os.org")
    qtapp.setApplicationName("Qubes Global Settings")

    sys.excepthook = handle_exception

    app = Qubes()

    global_window = GlobalSettingsWindow(qtapp, app)

    global_window.show()

    qtapp.exec_()
    qtapp.exit()

if __name__ == "__main__":
    main()
