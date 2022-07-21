#!/usr/bin/python3

# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only

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
import sys
import subprocess
import pkg_resources
from PyQt5 import QtWidgets, QtCore, QtGui  # pylint: disable=import-error

from qubesadmin.utils import parse_size
from qubesadmin import exc
from qubesmanager.releasenotes import ReleaseNotesDialog
from qubesmanager.informationnotes import InformationNotesDialog

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
    if p.returncode != 0:
        msg = QtCore.QCoreApplication.translate(
                "GlobalSettings",
                'qrexec call exited with non-zero return code')
        raise exc.QubesException(msg + ' (%s): %s',
                p.returncode, p.stderr.decode('utf-8'))
    if p.stderr:
        msg = QtCore.QCoreApplication.translate(
                "GlobalSettings",
                '%s qrexec call stderr was not empty (%s)')
        print(msg % (service, p.stderr.decode('utf-8')), file=sys.stderr)
    return p.stdout.decode('utf-8')


class GlobalSettingsWindow(ui_globalsettingsdlg.Ui_GlobalSettings,
                           QtWidgets.QDialog):

    def __init__(self, app, qubes_app, parent=None):
        super().__init__(parent)

        self.app: QtWidgets.QApplication = app
        self.qubes_app = qubes_app
        self.vm = self.qubes_app.domains[self.qubes_app.local_name]

        self.setupUi(self)

        self.buttonBox.accepted.connect(self.save_and_apply)
        self.buttonBox.rejected.connect(self.reject)

        self.__init_ux()

        self.__init_system_defaults__()
        self.__init_kernel_defaults__()
        self.__init_mem_defaults__()
        self.__init_updates__()
        self.__init_gui_defaults()

        self.errors = []

    def setup_application(self):
        self.app.setApplicationName(self.tr("Qubes Global Settings"))
        self.app.setWindowIcon(QtGui.QIcon.fromTheme("qubes-manager"))

    def __init_ux(self):
        icon = QtGui.QIcon.fromTheme('qubes-manager')
        pixmap = icon.pixmap(QtCore.QSize(128, 128))
        self.logo_label.setPixmap(pixmap)
        self.logo_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setStyleSheet(pkg_resources.resource_string(
            __name__, 'global_settings.css').decode())

        self.label_release.linkActivated.connect(self._link_activated)

        for button in self.buttonBox.buttons():
            button.setMinimumWidth(200)

        self.show()

        # The magical constants of 60 here are derived from margins set
        # in the .ui file
        req_width = self.scrollAreaWidgetContents_2.sizeHint().width() + 60
        avail_width = self.app.desktop().availableGeometry().width() * 0.95

        req_height = self.scrollAreaWidgetContents_2.sizeHint().height() + 60
        avail_height = self.app.desktop().availableGeometry().height() * 0.95

        self.resize(min(req_width, avail_width), min(req_height, avail_height))

    def _link_activated(self, link):
        if link == "version":
            dialog = InformationNotesDialog(self)
        elif link == "release":
            dialog = ReleaseNotesDialog(self)
        else:
            return

        dialog.exec_()

    def setup_widget_with_vms(self, widget, filter_function,
                              allow_none, holder, property_name):
        try:
            utils.initialize_widget_with_vms(
                widget=widget,
                qubes_app=self.qubes_app,
                filter_function=filter_function,
                allow_none=allow_none,
                holder=holder,
                property_name=property_name
            )
        except exc.QubesDaemonAccessError:
            widget.clear()
            widget.setCurrentText("unavailable")
            widget.setEnabled(False)

    def __init_system_defaults__(self):
        # set up updatevm choice
        self.setup_widget_with_vms(
            widget=self.update_vm_combo,
            filter_function=(lambda vm: vm.klass != 'TemplateVM'),
            allow_none=True,
            holder=self.qubes_app,
            property_name="updatevm")

        # set up clockvm choice
        self.setup_widget_with_vms(
            widget=self.clock_vm_combo,
            filter_function=(lambda vm: vm.klass != 'TemplateVM'),
            allow_none=True,
            holder=self.qubes_app,
            property_name="clockvm")

        # set up default netvm
        self.setup_widget_with_vms(
            widget=self.default_netvm_combo,
            filter_function=(lambda vm: getattr(
                vm, 'provides_network', False)),
            allow_none=True,
            holder=self.qubes_app,
            property_name="default_netvm")

        # default template
        self.setup_widget_with_vms(
            widget=self.default_template_combo,
            filter_function=(lambda vm: vm.klass == 'TemplateVM'),
            allow_none=True,
            holder=self.qubes_app,
            property_name="default_template"
        )

        # default dispvm
        self.setup_widget_with_vms(
            widget=self.default_dispvm_combo,
            filter_function=(lambda vm: getattr(
                vm, 'template_for_dispvms', False)),
            allow_none=True,
            holder=self.qubes_app,
            property_name="default_dispvm"
        )

    def __apply_system_defaults__(self):
        # updatevm
        if utils.did_widget_selection_change(self.update_vm_combo):
            try:
                self.qubes_app.updatevm = self.update_vm_combo.currentData()
            except exc.QubesException as ex:
                self.errors.append(
                    "Failed to set UpdateVM due to {}".format(str(ex)))

        # clockvm
        if utils.did_widget_selection_change(self.clock_vm_combo):
            try:
                self.qubes_app.clockvm = self.clock_vm_combo.currentData()
            except exc.QubesException as ex:
                self.errors.append(
                    "Failed to set ClockVM due to {}".format(str(ex)))

        # default netvm
        if utils.did_widget_selection_change(self.default_netvm_combo):
            new_default_netvm = self.default_netvm_combo.currentData()
            if new_default_netvm and \
                    new_default_netvm.property_is_default('netvm'):
                self.errors.append(
                    "Cannot set {} as the default net qube. Reason: {}'s net"
                    " qube is already set to 'default', and a qube cannot be "
                    "its own net qube. Please change {}'s net qube and try "
                    "again.".format(
                        str(new_default_netvm), str(new_default_netvm),
                        str(new_default_netvm)))
            else:
                try:
                    self.qubes_app.default_netvm = \
                        self.default_netvm_combo.currentData()
                except exc.QubesException as ex:
                    self.errors.append(
                        "Cannot set default net qube: {}".format(str(ex)))

        # default template
        if utils.did_widget_selection_change(self.default_template_combo):
            try:
                self.qubes_app.default_template = \
                    self.default_template_combo.currentData()
            except exc.QubesException as ex:
                self.errors.append(
                    "Failed to set Default Template due to {}".format(str(ex)))

        # default_dispvm
        if utils.did_widget_selection_change(self.default_dispvm_combo):
            try:
                self.qubes_app.default_dispvm = \
                    self.default_dispvm_combo.currentData()
            except exc.QubesException as ex:
                self.errors.append(
                    "Failed to set Default DispVM due to {}".format(str(ex)))

    def __init_kernel_defaults__(self):
        try:
            utils.initialize_widget_with_kernels(
                widget=self.default_kernel_combo,
                qubes_app=self.qubes_app,
                allow_none=True,
                holder=self.qubes_app,
                property_name='default_kernel')
        except exc.QubesDaemonAccessError:
            self.default_kernel_combo.clear()
            self.default_kernel_combo.setCurrentText("unavailable")
            self.default_kernel_combo.setEnabled(False)

    def __apply_kernel_defaults__(self):
        if utils.did_widget_selection_change(self.default_kernel_combo):
            try:
                self.qubes_app.default_kernel = \
                    self.default_kernel_combo.currentData()
            except exc.QubesException as ex:
                self.errors.append(
                    "Failed to set Default Kernel due to {}".format(str(ex)))

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
            selected_value=utils.get_feature(
                self.vm, 'gui-default-trayicon-mode', None))

        utils.initialize_widget(
            widget=self.securecopy,
            choices=[
                ('default (Ctrl+Shift+C)', None),
                ('Ctrl+Shift+C', 'Ctrl-Shift-c'),
                ('Ctrl+Win+C', 'Ctrl-Mod4-c'),
            ],
            selected_value=utils.get_feature(
                self.vm, 'gui-default-secure-copy-sequence', None))

        utils.initialize_widget(
            widget=self.securepaste,
            choices=[
                ('default (Ctrl+Shift+V)', None),
                ('Ctrl+Shift+V', 'Ctrl-Shift-V'),
                ('Ctrl+Win+V', 'Ctrl-Mod4-v'),
                ('Ctrl+Insert', 'Ctrl-Ins'),
            ],
            selected_value=utils.get_feature(
                self.vm, 'gui-default-secure-paste-sequence', None))

    def __apply_feature_change(self, widget, feature):
        if utils.did_widget_selection_change(widget):
            if widget.currentData() is None:
                try:
                    del self.vm.features[feature]
                except exc.QubesDaemonAccessError:
                    self.errors.append(
                        "Failed to set {} due to insufficient "
                        "permissions".format(feature))
            else:
                try:
                    self.vm.features[feature] = widget.currentData()
                except exc.QubesDaemonAccessError:
                    self.errors.append(
                        "Failed to set {} due to insufficient "
                        "permissions".format(feature))

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
        try:
            self.qmemman_config = ConfigParser()
            self.vm_min_mem_val = '200MiB'  # str(qmemman_algo.MIN_PREFMEM)
            # str(qmemman_algo.DOM0_MEM_BOOST)
            self.dom0_mem_boost_val = '350MiB'

            self.qmemman_config.read(qmemman_config_path)
            if self.qmemman_config.has_section('global'):
                self.vm_min_mem_val = \
                    self.qmemman_config.get('global', 'vm-min-mem')
                self.dom0_mem_boost_val = \
                    self.qmemman_config.get('global', 'dom0-mem-boost')

            self.vm_min_mem_val = parse_size(self.vm_min_mem_val)
            self.dom0_mem_boost_val = parse_size(self.dom0_mem_boost_val)

            self.min_vm_mem.setValue(
                int(self.vm_min_mem_val / 1024 / 1024))
            self.dom0_mem_boost.setValue(
                int(self.dom0_mem_boost_val / 1024 / 1024))
        except exc.QubesException:
            self.min_vm_mem.setEnabled(False)
            self.dom0_mem_boost.setEnabled(False)

    def __apply_mem_defaults__(self):

        if not self.min_vm_mem.isEnabled() or \
                not self.dom0_mem_boost.isEnabled():
            return

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

                try:
                    with open(qmemman_config_path, 'a', encoding='utf-8') \
                            as qmemman_config_file:
                        self.qmemman_config.write(qmemman_config_file)
                except Exception as ex:  # pylint: disable=broad-except
                    self.errors.append(
                        "Failed to set memory settings due to {}".format(
                            str(ex)))

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

                try:
                    with open(qmemman_config_path, 'r', encoding='utf-8') \
                            as qmemman_config_file:
                        for line in qmemman_config_file:
                            if line.strip().startswith('vm-min-mem'):
                                config_lines.append(lines_to_add['vm-min-mem'])
                                del lines_to_add['vm-min-mem']
                            elif line.strip().startswith('dom0-mem-boost'):
                                config_lines.append(
                                        lines_to_add['dom0-mem-boost'])
                                del lines_to_add['dom0-mem-boost']
                            else:
                                config_lines.append(line)
                except Exception as ex:  # pylint: disable=broad-except
                    self.errors.append(
                        "Failed to set memory settings due to {}".format(
                            str(ex)))
                    return

                for line in lines_to_add:
                    config_lines.append(line)

                try:
                    with open(qmemman_config_path, 'w', encoding='utf-8') \
                            as qmemman_config_file:
                        qmemman_config_file.writelines(config_lines)
                except Exception as ex:  # pylint: disable=broad-except
                    self.errors.append(
                        "Failed to set memory settings due to {}".format(
                            str(ex)))
                    return

    def __init_updates__(self):
        self.updates_dom0_val = bool(
            utils.get_feature(self.qubes_app.domains['dom0'],
                              'service.qubes-update-check',
                              True))

        self.updates_dom0.setChecked(self.updates_dom0_val)

        try:
            self.updates_vm.setChecked(self.qubes_app.check_updates_vm)
        except exc.QubesDaemonAccessError:
            self.updates_vm.isEnabled(False)

        self.enable_updates_all.clicked.connect(self.__enable_updates_all)
        self.disable_updates_all.clicked.connect(self.__disable_updates_all)

        self.repos = repos = {}
        try:
            for i in _run_qrexec_repo('qubes.repos.List').split('\n'):
                lst = i.split('\0')
                # Keyed by repo name
                dct = repos[lst[0]] = {}
                dct['prettyname'] = lst[1]
                dct['enabled'] = lst[2] == 'enabled'
        except exc.QubesException:
            self.dom0_updates_repo.setEnabled(False)
            self.itl_tmpl_updates_repo.setEnabled(False)
            self.comm_tmpl_updates_repo.setEnabled(False)

        if repos.get('qubes-dom0-unstable', {}).get('enabled', None):
            self.dom0_updates_repo.setCurrentIndex(3)
        elif repos.get('qubes-dom0-current-testing', {}).get('enabled', None):
            self.dom0_updates_repo.setCurrentIndex(2)
        elif repos.get('qubes-dom0-security-testing', {}).get('enabled', None):
            self.dom0_updates_repo.setCurrentIndex(1)
        elif repos.get('qubes-dom0-current', {}).get('enabled', None):
            self.dom0_updates_repo.setCurrentIndex(0)
        else:
            raise Exception(
                self.tr('Cannot detect enabled dom0 update repositories'))

        if repos.get('qubes-templates-itl-testing', {}).get('enabled', None):
            self.itl_tmpl_updates_repo.setCurrentIndex(1)
        elif repos.get('qubes-templates-itl', {}).get('enabled', None):
            self.itl_tmpl_updates_repo.setCurrentIndex(0)
        else:
            raise Exception(self.tr('Cannot detect enabled ITL template update '
                                    'repositories'))

        if repos.get(
                'qubes-templates-community-testing', {}).get('enabled', None):
            self.comm_tmpl_updates_repo.setCurrentIndex(2)
        elif repos.get('qubes-templates-community', {}).get('enabled', None):
            self.comm_tmpl_updates_repo.setCurrentIndex(1)
        else:
            self.comm_tmpl_updates_repo.setCurrentIndex(0)

    def __enable_updates_all(self):
        reply = QtWidgets.QMessageBox.question(
            self, self.tr("Change state of all qubes"),
            self.tr("Are you sure you want to set all qubes to check "
                    "for updates? This will override current qube settings."),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
        if reply == QtWidgets.QMessageBox.Cancel:
            return

        self.__set_updates_all(True)

    def __disable_updates_all(self):
        reply = QtWidgets.QMessageBox.question(
            self, self.tr("Change state of all qubes"),
            self.tr("Are you sure you want to set all qubes to not check "
                    "for updates? This will override current qube settings."),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel)
        if reply == QtWidgets.QMessageBox.Cancel:
            return

        self.__set_updates_all(False)

    def __set_updates_all(self, state):
        errors = []
        for vm in self.qubes_app.domains:
            if vm.klass != "AdminVM":
                try:
                    vm.features['service.qubes-update-check'] = state
                except exc.QubesDaemonAccessError:
                    errors.append(vm.name)

        if errors:
            QtWidgets.QMessageBox.warning(
                self, "Error!",
                "Failed to set state for some qubes: {}".format(
                    ", ".join(errors)))

    def __apply_updates__(self):
        if self.updates_dom0.isEnabled() and \
                self.updates_dom0.isChecked() != self.updates_dom0_val:
            try:
                self.qubes_app.domains['dom0'].features[
                    'service.qubes-update-check'] = \
                    self.updates_dom0.isChecked()
            except exc.QubesDaemonAccessError:
                self.errors.append("Failed to change dom0 update value due "
                                   "to insufficient permissions.")

        if self.updates_vm.isEnabled() and \
                self.qubes_app.check_updates_vm != self.updates_vm.isChecked():
            try:
                self.qubes_app.check_updates_vm = self.updates_vm.isChecked()
            except exc.QubesDaemonAccessError:
                self.errors.append("Failed to set qube update checking due "
                                   "to insufficient permissions.")

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
        if self.dom0_updates_repo.isEnabled():
            self._handle_dom0_updates_combobox(
                self.dom0_updates_repo.currentIndex())
        if self.itl_tmpl_updates_repo.isEnabled():
            self._handle_itl_tmpl_updates_combobox(
                self.itl_tmpl_updates_repo.currentIndex())
        if self.comm_tmpl_updates_repo.isEnabled():
            self._handle_comm_tmpl_updates_combobox(
                self.comm_tmpl_updates_repo.currentIndex())

    def reject(self):
        self.done(0)

    def save_and_apply(self):
        self.errors = []

        self.__apply_system_defaults__()
        self.__apply_kernel_defaults__()
        self.__apply_mem_defaults__()
        self.__apply_updates__()
        self.__apply_repos__()
        self.__apply_gui_defaults()

        if self.errors:
            err_msg = "Failed to apply some settings:\n" + "\n".join(
                self.errors)
            QtWidgets.QMessageBox.warning(self, "Error", err_msg)


def main():
    utils.run_synchronous(GlobalSettingsWindow)


if __name__ == "__main__":
    main()
