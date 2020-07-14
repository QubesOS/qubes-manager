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

import os
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui  # pylint: disable=import-error

from qubesadmin.utils import parse_size

from . import ui_globalsettingsdlg  # pylint: disable=no-name-in-module
from . import utils

from configparser import ConfigParser

qmemman_config_path = '/etc/qubes/qmemman.conf'


def _run_qrexec_repo(service, arg=''):
    # Set default locale to C in order to prevent error msg
    # in subprocess call related to falling back to C locale
    env = os.environ.copy()
    env['LC_ALL'] = 'C'
    # Fake up a "qrexec call" to dom0 because dom0 can't qrexec to itself yet
    cmd = '/etc/qubes-rpc/' + service
    p = subprocess.run(
        ['sudo', cmd, arg],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env
    )
    if p.stderr:
        raise RuntimeError(
            QtCore.QCoreApplication.translate(
                "GlobalSettings", 'qrexec call stderr was not empty'),
            {'stderr': p.stderr.decode('utf-8')})
    if p.returncode != 0:
        raise RuntimeError(
            QtCore.QCoreApplication.translate(
                "GlobalSettings",
                'qrexec call exited with non-zero return code'),
            {'returncode': p.returncode})
    return p.stdout.decode('utf-8')


class GlobalSettingsWindow(ui_globalsettingsdlg.Ui_GlobalSettings,
                           QtWidgets.QDialog):

    def __init__(self, app, qubes_app, parent=None):
        super(GlobalSettingsWindow, self).__init__(parent)

        self.app = app
        self.qubes_app = qubes_app
        self.vm = self.qubes_app.domains[self.qubes_app.local_name]

        self.setupUi(self)

        self.buttonBox.accepted.connect(self.save_and_apply)
        self.buttonBox.rejected.connect(self.reject)

        self.__init_system_defaults__()
        self.__init_kernel_defaults__()
        self.__init_mem_defaults__()
        self.__init_updates__()
        self.__init_gui_defaults()

    def setup_application(self):
        self.app.setApplicationName(self.tr("Qubes Global Settings"))
        self.app.setWindowIcon(QtGui.QIcon.fromTheme("qubes-manager"))

    def __init_system_defaults__(self):
        # set up updatevm choice
        utils.initialize_widget_with_vms(
            widget=self.update_vm_combo,
            qubes_app=self.qubes_app,
            filter_function=(lambda vm: vm.klass != 'TemplateVM'),
            allow_none=True,
            holder=self.qubes_app,
            property_name="updatevm"
        )

        # set up clockvm choice
        utils.initialize_widget_with_vms(
            widget=self.clock_vm_combo,
            qubes_app=self.qubes_app,
            filter_function=(lambda vm: vm.klass != 'TemplateVM'),
            allow_none=True,
            holder=self.qubes_app,
            property_name="clockvm"
        )

        # set up default netvm
        utils.initialize_widget_with_vms(
            widget=self.default_netvm_combo,
            qubes_app=self.qubes_app,
            filter_function=(lambda vm: vm.provides_network),
            allow_none=True,
            holder=self.qubes_app,
            property_name="default_netvm"
        )

        # default template
        utils.initialize_widget_with_vms(
            widget=self.default_template_combo,
            qubes_app=self.qubes_app,
            filter_function=(lambda vm: vm.klass == 'TemplateVM'),
            allow_none=True,
            holder=self.qubes_app,
            property_name="default_template"
        )

        # default dispvm
        utils.initialize_widget_with_vms(
            widget=self.default_dispvm_combo,
            qubes_app=self.qubes_app,
            filter_function=(lambda vm: getattr(
                vm, 'template_for_dispvms', False)),
            allow_none=True,
            holder=self.qubes_app,
            property_name="default_dispvm"
        )

    def __apply_system_defaults__(self):
        # updatevm
        if utils.did_widget_selection_change(self.update_vm_combo):
            self.qubes_app.updatevm = self.update_vm_combo.currentData()

        # clockvm
        if utils.did_widget_selection_change(self.clock_vm_combo):
            self.qubes_app.clockvm = self.clock_vm_combo.currentData()

        # default netvm
        if utils.did_widget_selection_change(self.default_netvm_combo):
            self.qubes_app.default_netvm = \
                self.default_netvm_combo.currentData()

        # default template
        if utils.did_widget_selection_change(self.default_template_combo):
            self.qubes_app.default_template = \
                self.default_template_combo.currentData()

        # default_dispvm
        if utils.did_widget_selection_change(self.default_dispvm_combo):
            self.qubes_app.default_dispvm = \
                self.default_dispvm_combo.currentData()

    def __init_kernel_defaults__(self):
        utils.initialize_widget_with_kernels(
            widget=self.default_kernel_combo,
            qubes_app=self.qubes_app,
            allow_none=True,
            holder=self.qubes_app,
            property_name='default_kernel')

    def __apply_kernel_defaults__(self):
        if utils.did_widget_selection_change(self.default_kernel_combo):
            self.qubes_app.default_kernel = \
                self.default_kernel_combo.currentData()

    def __init_gui_defaults(self):
        utils.initialize_widget(
            widget=self.allow_fullscreen,
            choices=[
                ('default (disallow)', None),
                ('allow', True),
                ('disallow', False)
            ],
            selected_value=utils.get_boolean_feature(
                self.vm,
                'gui-default-allow-fullscreen'))

        utils.initialize_widget(
            widget=self.allow_utf8,
            choices=[
                ('default (disallow)', None),
                ('allow', True),
                ('disallow', False)
            ],
            selected_value=utils.get_boolean_feature(
                self.vm,
                'gui-default-allow-utf8-titles'))

        utils.initialize_widget(
            widget=self.trayicon,
            choices=[
                ('default (thin border)', None),
                ('full background', 'bg'),
                ('thin border', 'border1'),
                ('thick border', 'border2'),
                ('tinted icon', 'tint'),
                ('tinted icon with modified white', 'tint+whitehack'),
                ('tinted icon with 50% saturation', 'tint+saturation50')
            ],
            selected_value=self.vm.features.get('gui-default-trayicon-mode',
                                                None))

        utils.initialize_widget(
            widget=self.securecopy,
            choices=[
                ('default (Ctrl+Shift+C)', None),
                ('Ctrl+Shift+C', 'Ctrl-Shift-c'),
                ('Ctrl+Win+C', 'Ctrl-Mod4-c'),
            ],
            selected_value=self.vm.features.get(
                'gui-default-secure-copy-sequence', None))

        utils.initialize_widget(
            widget=self.securepaste,
            choices=[
                ('default (Ctrl+Shift+V)', None),
                ('Ctrl+Shift+V', 'Ctrl-Shift-V'),
                ('Ctrl+Win+V', 'Ctrl-Mod4-v'),
                ('Ctrl+Insert', 'Ctrl-Ins'),
            ],
            selected_value=self.vm.features.get(
                'gui-default-secure-paste-sequence', None))

    def __apply_feature_change(self, widget, feature):
        if utils.did_widget_selection_change(widget):
            if widget.currentData() is None:
                del self.vm.features[feature]
            else:
                self.vm.features[feature] = widget.currentData()

    def __apply_gui_defaults(self):
        self.__apply_feature_change(widget=self.allow_fullscreen,
                                    feature='gui-default-allow-fullscreen')
        self.__apply_feature_change(widget=self.allow_utf8,
                                    feature='gui-default-allow-utf8-titles')
        self.__apply_feature_change(widget=self.trayicon,
                                    feature='gui-default-trayicon-mode')
        self.__apply_feature_change(widget=self.securecopy,
                                    feature='gui-default-secure-copy-sequence')
        self.__apply_feature_change(widget=self.securepaste,
                                    feature='gui-default-secure-paste-sequence')

    def __init_mem_defaults__(self):
        # qmemman settings
        self.qmemman_config = ConfigParser()
        self.vm_min_mem_val = '200MiB'  # str(qmemman_algo.MIN_PREFMEM)
        self.dom0_mem_boost_val = '350MiB'  # str(qmemman_algo.DOM0_MEM_BOOST)

        self.qmemman_config.read(qmemman_config_path)
        if self.qmemman_config.has_section('global'):
            self.vm_min_mem_val = \
                self.qmemman_config.get('global', 'vm-min-mem')
            self.dom0_mem_boost_val = \
                self.qmemman_config.get('global', 'dom0-mem-boost')

        self.vm_min_mem_val = parse_size(self.vm_min_mem_val)
        self.dom0_mem_boost_val = parse_size(self.dom0_mem_boost_val)

        self.min_vm_mem.setValue(int(self.vm_min_mem_val / 1024 / 1024))
        self.dom0_mem_boost.setValue(int(self.dom0_mem_boost_val / 1024 / 1024))

    def __apply_mem_defaults__(self):

        # qmemman settings
        current_min_vm_mem = self.min_vm_mem.value()
        current_dom0_mem_boost = self.dom0_mem_boost.value()

        if current_min_vm_mem * 1024 * 1024 != self.vm_min_mem_val or \
                current_dom0_mem_boost * 1024 * 1024 != self.dom0_mem_boost_val:

            current_min_vm_mem = str(current_min_vm_mem) + 'MiB'
            current_dom0_mem_boost = str(current_dom0_mem_boost) + 'MiB'

            if not self.qmemman_config.has_section('global'):
                # add the whole section
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
                # If there already is a 'global' section, we don't use
                # SafeConfigParser.write() - it would get rid of
                # all the comments...

                lines_to_add = {}
                lines_to_add['vm-min-mem'] = \
                    "vm-min-mem = " + current_min_vm_mem + "\n"
                lines_to_add['dom0-mem-boost'] = \
                    "dom0-mem-boost = " + current_dom0_mem_boost + "\n"

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
        self.updates_dom0_val = bool(
            self.qubes_app.domains['dom0'].features.get(
                'service.qubes-update-check', True))

        self.updates_dom0.setChecked(self.updates_dom0_val)

        self.updates_vm.setChecked(self.qubes_app.check_updates_vm)
        self.enable_updates_all.clicked.connect(self.__enable_updates_all)
        self.disable_updates_all.clicked.connect(self.__disable_updates_all)

        self.repos = repos = dict()
        for i in _run_qrexec_repo('qubes.repos.List').split('\n'):
            lst = i.split('\0')
            # Keyed by repo name
            dct = repos[lst[0]] = dict()
            dct['prettyname'] = lst[1]
            dct['enabled'] = lst[2] == 'enabled'

        if repos['qubes-dom0-unstable']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(3)
        elif repos['qubes-dom0-current-testing']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(2)
        elif repos['qubes-dom0-security-testing']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(1)
        elif repos['qubes-dom0-current']['enabled']:
            self.dom0_updates_repo.setCurrentIndex(0)
        else:
            raise Exception(
                self.tr('Cannot detect enabled dom0 update repositories'))

        if repos['qubes-templates-itl-testing']['enabled']:
            self.itl_tmpl_updates_repo.setCurrentIndex(1)
        elif repos['qubes-templates-itl']['enabled']:
            self.itl_tmpl_updates_repo.setCurrentIndex(0)
        else:
            raise Exception(self.tr('Cannot detect enabled ITL template update '
                                    'repositories'))

        if repos['qubes-templates-community-testing']['enabled']:
            self.comm_tmpl_updates_repo.setCurrentIndex(2)
        elif repos['qubes-templates-community']['enabled']:
            self.comm_tmpl_updates_repo.setCurrentIndex(1)
        else:
            self.comm_tmpl_updates_repo.setCurrentIndex(0)

    def __enable_updates_all(self):
        reply = QtWidgets.QMessageBox.question(
            self, self.tr("Change state of all qubes"),
            self.tr("Are you sure you want to set all qubes to check "
                    "for updates?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
        if reply == QtWidgets.QMessageBox.Cancel:
            return

        self.__set_updates_all(True)

    def __disable_updates_all(self):
        reply = QtWidgets.QMessageBox.question(
            self, self.tr("Change state of all qubes"),
            self.tr("Are you sure you want to set all qubes to not check "
                    "for updates?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
        if reply == QtWidgets.QMessageBox.Cancel:
            return

        self.__set_updates_all(False)

    def __set_updates_all(self, state):
        for vm in self.qubes_app.domains:
            if vm.klass != "AdminVM":
                vm.features['service.qubes-update-check'] = state

    def __apply_updates__(self):
        if self.updates_dom0.isChecked() != self.updates_dom0_val:
            self.qubes_app.domains['dom0'].features[
                'service.qubes-update-check'] = \
                self.updates_dom0.isChecked()

        if self.qubes_app.check_updates_vm != self.updates_vm.isChecked():
            self.qubes_app.check_updates_vm = self.updates_vm.isChecked()

    def _manage_repos(self, repolist, action):
        for name in repolist:
            if self.repos[name]['enabled'] and action == 'Enable' or \
                    not self.repos[name]['enabled'] and action == 'Disable':
                continue

            try:
                result = _run_qrexec_repo('qubes.repos.' + action, name)
                if result != 'ok\n':
                    raise RuntimeError(
                        self.tr('qrexec call stdout did not contain "ok"'
                                ' as expected'),
                        {'stdout': result})
            except RuntimeError as ex:
                msg = '{desc}; {args}'.format(desc=ex.args[0], args=', '.join(
                    # This is kind of hard to mentally parse but really all
                    # it does is pretty-print args[1], which is a dictionary
                    ['{key}: {val}'.format(key=i[0], val=i[1]) for i in
                     ex.args[1].items()]
                ))
                QtWidgets.QMessageBox.warning(
                    None,
                    self.tr("ERROR!"),
                    self.tr("Error managing {repo} repository settings:"
                            " {msg}".format(repo=name, msg=msg)))

    def _handle_dom0_updates_combobox(self, idx):
        idx += 1
        repolist = ['qubes-dom0-current', 'qubes-dom0-security-testing',
                    'qubes-dom0-current-testing', 'qubes-dom0-unstable']
        enable = repolist[:idx]
        disable = repolist[idx:]
        self._manage_repos(enable, 'Enable')
        self._manage_repos(disable, 'Disable')

    # pylint: disable=invalid-name
    def _handle_itl_tmpl_updates_combobox(self, idx):
        idx += 1
        repolist = ['qubes-templates-itl', 'qubes-templates-itl-testing']
        enable = repolist[:idx]
        disable = repolist[idx:]
        self._manage_repos(enable, 'Enable')
        self._manage_repos(disable, 'Disable')

    # pylint: disable=invalid-name
    def _handle_comm_tmpl_updates_combobox(self, idx):
        # We don't increment idx by 1 because this is the only combobox that
        # has an explicit "disable this repository entirely" option
        repolist = ['qubes-templates-community',
                    'qubes-templates-community-testing']
        enable = repolist[:idx]
        disable = repolist[idx:]
        self._manage_repos(enable, 'Enable')
        self._manage_repos(disable, 'Disable')

    def __apply_repos__(self):
        self._handle_dom0_updates_combobox(
            self.dom0_updates_repo.currentIndex())
        self._handle_itl_tmpl_updates_combobox(
            self.itl_tmpl_updates_repo.currentIndex())
        self._handle_comm_tmpl_updates_combobox(
            self.comm_tmpl_updates_repo.currentIndex())

    def reject(self):
        self.done(0)

    def save_and_apply(self):

        self.__apply_system_defaults__()
        self.__apply_kernel_defaults__()
        self.__apply_mem_defaults__()
        self.__apply_updates__()
        self.__apply_repos__()
        self.__apply_gui_defaults()


def main():
    utils.run_synchronous(GlobalSettingsWindow)


if __name__ == "__main__":
    main()
