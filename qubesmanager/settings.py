#!/usr/bin/python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski-Górecki
#                       <marmarek@invisiblethingslab.com>
# Copyright (C) 2017  Wojtek Porczyk <woju@invisiblethingslab.com>
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


import collections
import os.path
import os
import re
import subprocess
import threading
import time
import traceback
import sys
from qubesadmin.tools import QubesArgumentParser
from qubesadmin import devices
import qubesadmin.exc

from . import utils
from . import multiselectwidget
from . import thread_monitor
from . import device_list

from .appmenu_select import AppmenuSelectManager
from . import firewall
from PyQt4 import QtCore, QtGui  # pylint: disable=import-error

from . import ui_settingsdlg  # pylint: disable=no-name-in-module


# pylint: disable=too-many-instance-attributes
class VMSettingsWindow(ui_settingsdlg.Ui_SettingsDialog, QtGui.QDialog):
    tabs_indices = collections.OrderedDict((
            ('basic', 0),
            ('advanced', 1),
            ('firewall', 2),
            ('devices', 3),
            ('applications', 4),
            ('services', 5),
        ))

    def __init__(self, vm, qapp, init_page="basic", parent=None):
        super(VMSettingsWindow, self).__init__(parent)

        self.vm = vm
        self.qapp = qapp
        try:
            self.source_vm = self.vm.template
        except AttributeError:
            self.source_vm = self.vm

        self.setupUi(self)
        self.setWindowTitle(self.tr("Settings: {vm}").format(vm=self.vm.name))
        if init_page in self.tabs_indices:
            idx = self.tabs_indices[init_page]
            assert idx in range(self.tabWidget.count())
            self.tabWidget.setCurrentIndex(idx)

        self.buttonBox.button(QtGui.QDialogButtonBox.Ok).clicked.connect(
            self.save_and_apply)
        self.buttonBox.button(QtGui.QDialogButtonBox.Cancel).clicked.connect(
            self.reject)
        self.buttonBox.button(QtGui.QDialogButtonBox.Apply).clicked.connect(
            self.apply)

        self.tabWidget.currentChanged.connect(self.current_tab_changed)

        ###### basic tab
        self.__init_basic_tab__()
        self.rename_vm_button.clicked.connect(self.rename_vm)
        self.delete_vm_button.clicked.connect(self.remove_vm)
        self.clone_vm_button.clicked.connect(self.clone_vm)

        ###### advanced tab
        self.__init_advanced_tab__()
        self.include_in_balancing.stateChanged.connect(
            self.include_in_balancing_changed)
        self.connect(self.init_mem,
                     QtCore.SIGNAL("editingFinished()"),
                     self.check_mem_changes)
        self.connect(self.max_mem_size,
                     QtCore.SIGNAL("editingFinished()"),
                     self.check_mem_changes)
        self.boot_from_device_button.clicked.connect(
            self.boot_from_cdrom_button_pressed)

        ###### firewall tab
        if self.tabWidget.isTabEnabled(self.tabs_indices['firewall']):
            model = firewall.QubesFirewallRulesModel()
            try:
                model.set_vm(vm)
                self.set_fw_model(model)
                self.firewall_modified_outside_label.setVisible(False)
            except firewall.FirewallModifiedOutsideError:
                self.disable_all_fw_conf()

            self.new_rule_button.clicked.connect(self.new_rule_button_pressed)
            self.edit_rule_button.clicked.connect(self.edit_rule_button_pressed)
            self.delete_rule_button.clicked.connect(
                self.delete_rule_button_pressed)
            self.policy_deny_radio_button.clicked.connect(self.policy_changed)
            self.policy_allow_radio_button.clicked.connect(self.policy_changed)
            if init_page == 'firewall':
                self.check_network_availability()

        ####### devices tab
        self.__init_devices_tab__()
        self.connect(self.dev_list,
                     QtCore.SIGNAL("selected_changed()"),
                     self.devices_selection_changed)
        self.no_strict_reset_button.clicked.connect(
            self.strict_reset_button_pressed)
        self.current_strict_reset_list = []
        self.new_strict_reset_list = []
        self.define_strict_reset_devices()

        ####### services tab
        self.__init_services_tab__()
        self.service_line_edit.returnPressed.connect(self.__add_service__)
        self.add_srv_button.clicked.connect(self.__add_service__)
        self.remove_srv_button.clicked.connect(self.__remove_service__)

        ####### apps tab
        if self.tabWidget.isTabEnabled(self.tabs_indices["applications"]):
            self.app_list = multiselectwidget.MultiSelectWidget(self)
            self.apps_layout.addWidget(self.app_list)
            self.app_list_manager = AppmenuSelectManager(self.vm, self.app_list)
            self.refresh_apps_button.clicked.connect(
                self.refresh_apps_button_pressed)

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        if event.key() == QtCore.Qt.Key_Enter \
                or event.key() == QtCore.Qt.Key_Return:
            return
        else:
            super(VMSettingsWindow, self).keyPressEvent(event)

    def reject(self):
        self.done(0)

    # needed not to close the dialog before applying changes
    def accept(self):
        pass

    def save_changes(self):
        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(target=self.__save_changes__,
                                  args=(t_monitor,))
        thread.daemon = True
        thread.start()

        progress = QtGui.QProgressDialog(
            self.tr("Applying settings to <b>{0}</b>...").format(self.vm.name),
            "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not t_monitor.is_finished():
            self.qapp.processEvents()
            time.sleep(0.1)

        progress.hide()

        if not t_monitor.success:
            QtGui.QMessageBox.warning(
                None,
                self.tr("Error while changing settings for {0}!"
                        ).format(self.vm.name),
                self.tr("ERROR: {0}").format(t_monitor.error_msg))

    def apply(self):
        self.save_changes()

    def save_and_apply(self):
        self.save_changes()
        self.done(0)

    def __save_changes__(self, t_monitor):

        ret = []
        try:
            ret_tmp = self.__apply_basic_tab__()
            if ret_tmp:
                ret += ["Basic tab:"] + ret_tmp
            ret_tmp = self.__apply_advanced_tab__()
            if ret_tmp:
                ret += ["Advanced tab:"] + ret_tmp
            ret_tmp = self.__apply_devices_tab__()
            if ret_tmp:
                ret += ["Devices tab:"] + ret_tmp
            ret_tmp = self.__apply_services_tab__()
            if ret_tmp:
                ret += ["Sevices tab:"] + ret_tmp
        except qubesadmin.exc.QubesException as qex:
            ret.append(self.tr('Error while saving changes: ') + str(qex))
        except Exception as ex:  # pylint: disable=broad-except
            ret.append(repr(ex))

        try:
            if self.policy_allow_radio_button.isEnabled():
                self.fw_model.apply_rules(
                    self.policy_allow_radio_button.isChecked(),
                    self.temp_full_access.isChecked(),
                    self.temp_full_access_time.value())
        except qubesadmin.exc.QubesException as qex:
            ret += [self.tr("Firewall tab:"), str(qex)]
        except Exception as ex:  # pylint: disable=broad-except
            ret += [self.tr("Firewall tab:"), repr(ex)]

        try:
            if self.tabWidget.isTabEnabled(self.tabs_indices["applications"]):
                self.app_list_manager.save_appmenu_select_changes()
        except qubesadmin.exc.QubesException as qex:
            ret += [self.tr("Applications tab:"), str(qex)]
        except Exception as ex:  # pylint: disable=broad-except
            ret += [self.tr("Applications tab:"), repr(ex)]

        if ret:
            t_monitor.set_error_msg('\n'.join(ret))

        utils.debug('\n'.join(ret))

        t_monitor.set_finished()

    def check_network_availability(self):
        netvm = self.vm.netvm
        self.no_netvm_label.setVisible(netvm is None)
        self.netvm_no_firewall_label.setVisible(
            netvm is not None and
            not netvm.features.check_with_template('qubes-firewall', False))
        if netvm is None:
            QtGui.QMessageBox.warning(
                None,
                self.tr("Qube configuration problem!"),
                self.tr('This qube has networking disabled '
                        '(Basic -> Networking) - network will be disabled. '
                        'If you want to use firewall, '
                        'please enable networking.')
            )
        if netvm is not None and \
                not netvm.features.check_with_template(
                    'qubes-firewall',
                    False):
            QtGui.QMessageBox.warning(
                None,
                self.tr("Qube configuration problem!"),
                self.tr("The '{vm}' qube is network connected to "
                        "'{netvm}', which does not support firewall!<br/>"
                        "You may edit the '{vm}' qube firewall rules, but "
                        "these will not take any effect until you connect it "
                        "to a working Firewall qube.").format(
                    vm=self.vm.name, netvm=netvm.name))

    def current_tab_changed(self, idx):
        if idx == self.tabs_indices["firewall"]:
            self.check_network_availability()

    ######### basic tab

    # TODO LISTENERS
    # - vm start/shutdown -> setEnabled on fields: template labels
    # - vm create/delete -> choices lists, whole window deactiv (if self.vm)
    # - property-set -> individual fields

    # TODO INTERACTIONS
    # netvm -> networking_groupbox
    # hvm -> include_in_balancing

    # TODO REMOVE
    # other_groupbox

    def __init_basic_tab__(self):
        self.vmname.setText(self.vm.name)
        self.vmname.setValidator(
            QtGui.QRegExpValidator(
                QtCore.QRegExp("[a-zA-Z0-9-]*",
                               QtCore.Qt.CaseInsensitive), None))
        self.vmname.setEnabled(False)
        self.rename_vm_button.setEnabled(not self.vm.is_running())
        self.delete_vm_button.setEnabled(not self.vm.is_running())

        if self.vm.is_running():
            self.delete_vm_button.setText(
                self.tr('Delete qube (cannot delete a running qube)'))

        if self.vm.qid == 0:
            self.vmlabel.setVisible(False)
        else:
            self.label_list, self.label_idx = utils.prepare_label_choice(
                self.vmlabel,
                self.vm, 'label',
                None,
                allow_default=False
                )
            self.vmlabel.setVisible(True)
            self.vmlabel.setEnabled(not self.vm.is_running())

        if self.vm.klass == 'AppVM':
            self.template_list, self.template_idx = utils.prepare_vm_choice(
                self.template_name,
                self.vm, 'template',
                self.vm.app.default_template,
                (lambda vm: vm.klass == 'TemplateVM'),
                allow_default=False, allow_none=False)
        else:
            self.template_name.setEnabled(False)
            self.template_idx = -1

        self.netvm_list, self.netvm_idx = utils.prepare_vm_choice(
            self.netVM,
            self.vm, 'netvm',
            self.vm.app.default_netvm,
            (lambda vm: vm.provides_network),
            allow_default=True, allow_none=True)

        self.include_in_backups.setChecked(self.vm.include_in_backups)

        try:
            self.run_in_debug_mode.setChecked(self.vm.debug)
            self.run_in_debug_mode.setVisible(True)
        except AttributeError:
            self.run_in_debug_mode.setVisible(False)

        try:
            self.autostart_vm.setChecked(self.vm.autostart)
            self.autostart_vm.setVisible(True)
        except AttributeError:
            self.autostart_vm.setVisible(False)

        # type
        self.type_label.setText(self.vm.klass)

        # installed by rpm
        self.rpm_label.setText('Yes' if self.vm.installed_by_rpm else 'No')

        # networking info
        if self.vm.netvm:
            self.networking_groupbox.setEnabled(True)
            self.ip_label.setText(self.vm.ip or "none")
            self.netmask_label.setText(self.vm.visible_netmask or "none")
            self.gateway_label.setText(self.vm.visible_gateway or "none")
        else:
            self.networking_groupbox.setEnabled(False)

        # max priv storage
        self.priv_img_size = self.vm.volumes['private'].size // 1024**2
        self.max_priv_storage.setMinimum(self.priv_img_size)
        self.max_priv_storage.setValue(self.priv_img_size)

        self.root_img_size = self.vm.volumes['root'].size // 1024**2
        self.root_resize.setValue(self.root_img_size)
        self.root_resize.setMinimum(self.root_img_size)
        self.root_resize.setEnabled(self.vm.volumes['root'].save_on_stop)
        self.root_resize_label.setEnabled(self.root_resize.isEnabled())

    def __apply_basic_tab__(self):
        msg = []

        # vm label changed
        try:
            if self.vmlabel.isVisible():
                if self.vmlabel.currentIndex() != self.label_idx:
                    label = self.label_list[self.vmlabel.currentIndex()]
                    self.vm.label = label
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # vm template changed
        try:
            if self.template_name.currentIndex() != self.template_idx:
                self.vm.template = \
                    self.template_list[self.template_name.currentIndex()]
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # vm netvm changed
        try:
            if self.netVM.currentIndex() != self.netvm_idx:
                self.vm.netvm = self.netvm_list[self.netVM.currentIndex()]
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # include in backups
        try:
            if self.vm.include_in_backups != \
                    self.include_in_backups.isChecked():
                self.vm.include_in_backups = self.include_in_backups.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # run_in_debug_mode
        try:
            if self.run_in_debug_mode.isVisible():
                if self.vm.debug != self.run_in_debug_mode.isChecked():
                    self.vm.debug = self.run_in_debug_mode.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # autostart_vm
        try:
            if self.autostart_vm.isVisible():
                if self.vm.autostart != self.autostart_vm.isChecked():
                    self.vm.autostart = self.autostart_vm.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # max priv storage
        priv_size = self.max_priv_storage.value()
        if self.priv_img_size != priv_size:
            try:
                self.vm.volumes['private'].resize(priv_size * 1024**2)
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        # max sys storage
        sys_size = self.root_resize.value()
        if self.root_img_size != sys_size:
            try:
                self.vm.volumes['root'].resize(sys_size * 1024**2)
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        return msg

    def check_mem_changes(self):
        if self.max_mem_size.value() < self.init_mem.value():
            QtGui.QMessageBox.warning(
                None,
                self.tr("Warning!"),
                self.tr("Max memory can not be less than initial memory.<br>"
                        "Setting max memory to equal initial memory."))
            self.max_mem_size.setValue(self.init_mem.value())
        # Linux specific limit: init memory must not be below
        # max_mem_size/10.79 in order to allow scaling up to
        # max_mem_size (or else "add_memory() failed: -17" problem)
        if self.init_mem.value() * 10 < self.max_mem_size.value():
            QtGui.QMessageBox.warning(
                None,
                self.tr("Warning!"),
                self.tr("Initial memory can not be less than one tenth "
                        "Max memory.<br>Setting initial memory to the minimum "
                        "allowed value."))
            self.init_mem.setValue(self.max_mem_size.value() / 10)

    def _run_in_thread(self, func, *args):
        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(target=func, args=(t_monitor, *args,))
        thread.daemon = True
        thread.start()

        while not t_monitor.is_finished():
            self.qapp.processEvents()
            time.sleep(0.1)

        if not t_monitor.success:
            QtGui.QMessageBox.warning(None,
                                      self.tr("Error!"),
                                      self.tr("ERROR: {}").format(
                                          t_monitor.error_msg))

    def _rename_vm(self, t_monitor, name):
        try:
            self.vm.app.clone_vm(self.vm, name)
            del self.vm.app.domains[self.vm.name]

        except qubesadmin.exc.QubesException as qex:
            t_monitor.set_error_msg(str(qex))
        except Exception as ex:  # pylint: disable=broad-except
            t_monitor.set_error_msg(repr(ex))

        t_monitor.set_finished()

    def rename_vm(self):

        new_vm_name, ok = QtGui.QInputDialog.getText(
            self,
            self.tr('Rename qube'),
            self.tr('New name: (WARNING: all other changes will be discarded)'))

        if ok:
            self._run_in_thread(self._rename_vm, new_vm_name)
            self.done(0)

    def _remove_vm(self, t_monitor):
        try:
            del self.vm.app.domains[self.vm.name]

        except qubesadmin.exc.QubesException as qex:
            t_monitor.set_error_msg(str(qex))
        except Exception as ex:  # pylint: disable=broad-except
            t_monitor.set_error_msg(repr(ex))

        t_monitor.set_finished()

    def remove_vm(self):

        answer, ok = QtGui.QInputDialog.getText(
            self,
            self.tr('Delete qube'),
            self.tr('Are you absolutely sure you want to delete this qube? '
                    '<br/> All qube settings and data will be irrevocably'
                    ' deleted. <br/> If you are sure, please enter this '
                    'qube\'s name below.'))

        if ok and answer == self.vm.name:
            self._run_in_thread(self._remove_vm)
            self.done(0)

        elif ok:
            QtGui.QMessageBox.warning(
                None,
                self.tr("Removal cancelled"),
                self.tr("The qube will not be removed."))

    def _clone_vm(self, t_monitor, name):
        try:
            self.vm.app.clone_vm(self.vm, name)

        except qubesadmin.exc.QubesException as qex:
            t_monitor.set_error_msg(str(qex))
        except Exception as ex:  # pylint: disable=broad-except
            t_monitor.set_error_msg(repr(ex))

        t_monitor.set_finished()

    def clone_vm(self):

        cloned_vm_name, ok = QtGui.QInputDialog.getText(
            self,
            self.tr('Clone qube'),
            self.tr('Name for the cloned qube:'))

        if ok:
            self._run_in_thread(self._clone_vm, cloned_vm_name)
            QtGui.QMessageBox.warning(
                None,
                self.tr("Success"),
                self.tr("The qube was cloned successfully."))

    ######### advanced tab

    def __init_advanced_tab__(self):

        # mem/cpu
#       qubes_memory = QubesHost().memory_total/1024

        self.init_mem.setValue(int(self.vm.memory))
#       self.init_mem.setMaximum(qubes_memory)

        self.max_mem_size.setValue(int(self.vm.maxmem))
#       self.max_mem_size.setMaximum(qubes_memory)

        self.vcpus.setMinimum(1)
#       self.vcpus.setMaximum(QubesHost().no_cpus)
        self.vcpus.setValue(int(self.vm.vcpus))

        self.include_in_balancing.setEnabled(True)
        self.include_in_balancing.setChecked(
            bool(self.vm.features.get('service.meminfo-writer', True)))
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())

        # in case VM is HVM
        if hasattr(self.vm, "kernel"):
            self.kernel_groupbox.setVisible(True)
            self.kernel_list, self.kernel_idx = utils.prepare_kernel_choice(
                self.kernel, self.vm, 'kernel',
                None,
                allow_default=True, allow_none=True)
            self.kernel.currentIndexChanged.connect(self.kernel_changed)
        else:
            self.kernel_groupbox.setVisible(False)

        self.other_groupbox.setVisible(False)

        if not hasattr(self.vm, 'default_dispvm'):
            self.other_groupbox.setVisible(False)
        else:
            self.other_groupbox.setVisible(True)
            self.default_dispvm_list, self.default_dispvm_idx = \
                utils.prepare_vm_choice(
                    self.default_dispvm,
                    self.vm, 'default_dispvm',
                    None,
                    (lambda vm: getattr(vm, 'template_for_dispvms', False)),
                    allow_default=True, allow_none=True)

        self.update_virt_mode_list()

    def __apply_advanced_tab__(self):
        msg = []

        # mem/cpu
        try:
            if self.init_mem.value() != int(self.vm.memory):
                self.vm.memory = self.init_mem.value()

            if self.max_mem_size.value() != int(self.vm.maxmem):
                self.vm.maxmem = self.max_mem_size.value()

            if self.vcpus.value() != int(self.vm.vcpus):
                self.vm.vcpus = self.vcpus.value()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # include_in_memory_balancing applied in services tab

        # in case VM is not Linux
        if hasattr(self.vm, "kernel") and self.kernel_groupbox.isVisible():
            try:
                if self.kernel.currentIndex() != self.kernel_idx:
                    self.vm.kernel = self.kernel_list[
                        self.kernel.currentIndex()]
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        # vm default_dispvm changed
        try:
            if self.default_dispvm.currentIndex() != self.default_dispvm_idx:
                self.vm.default_dispvm = \
                    self.default_dispvm_list[self.default_dispvm.currentIndex()]
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        try:
            if self.virt_mode.currentIndex() != self.virt_mode_idx:
                self.vm.virt_mode = self.selected_virt_mode()
        except Exception as ex:  # pylint: disable=broad-except
            msg.append(str(ex))

        return msg

    def boot_from_cdrom_button_pressed(self):
        self.save_and_apply()
        subprocess.check_call(['qubes-vm-boot-from-device', self.vm.name])

    def selected_virt_mode(self):
        return self.virt_mode_list[self.virt_mode.currentIndex()]

    def virt_mode_changed(self, new_idx):  # pylint: disable=unused-argument
        self.update_pv_warning()
        self.update_pvh_dont_support_devs()
        self.update_pvh_kernel_ver_warning()

    def update_pv_warning(self):
        if self.selected_virt_mode() == 'PV':
            self.pv_warning.show()
        else:
            self.pv_warning.hide()

    def update_virt_mode_list(self):
        choices = ['HVM', 'PV']

        if hasattr(self, 'dev_list'):
            devs_attached = self.dev_list.selected_list.count() != 0
        else:
            devs_attached = bool(list(self.vm.devices['pci'].persistent()))

        if devs_attached:
            self.pvh_mode_hidden.show()
        else:
            choices.insert(0, 'PVH')
            self.pvh_mode_hidden.hide()

        if hasattr(self, 'virt_mode_list'):
            old_mode = self.selected_virt_mode()
            self.virt_mode.currentIndexChanged.disconnect()
        else:
            old_mode = None

        self.virt_mode.clear()

        # pylint: disable=attribute-defined-outside-init
        self.virt_mode_list, self.virt_mode_idx = utils.prepare_choice(
                self.virt_mode, self.vm, 'virt_mode', choices, None,
                allow_default=True, transform=(lambda x: str(x).upper()))

        if old_mode is not None:
            self.virt_mode.setCurrentIndex(self.virt_mode_list.index(old_mode))

        self.virt_mode.currentIndexChanged.connect(self.virt_mode_changed)

        self.update_pv_warning()
        self.update_pvh_kernel_ver_warning()

    def update_pvh_kernel_ver_warning(self):
        if self.selected_virt_mode() != 'PVH':
            self.pvh_kernel_version_warning.hide()
            return

        kernel = self.kernel_list[self.kernel.currentIndex()]

        if self.pvh_kernel_version_ok(kernel):
            self.pvh_kernel_version_warning.hide()
        else:
            self.pvh_kernel_version_warning.show()

    def kernel_changed(self):
        self.update_pvh_kernel_ver_warning()

    def pvh_kernel_version_ok(self, name):
        # There are nearly no limitaions on kernel names (only file system and
        # general qvm-prefs rules). So we just look if we see something which
        # looks like a version number. It's just a warning to help the user
        # anyways.

        if name is None:
            return False

        if name is qubesadmin.DEFAULT:
            name = self.vm.app.default_kernel

        m = re.search(r'(\d+)\.(\d+)', name)

        if m is None:
            return False

        return (int(m.group(1)), int(m.group(2))) >= (4, 11)

    ######## devices tab
    def __init_devices_tab__(self):
        self.dev_list = multiselectwidget.MultiSelectWidget(self)
        self.dev_list.add_all_button.setVisible(False)
        self.devices_layout.addWidget(self.dev_list)

        devs = []
        lspci = subprocess.check_output(['/usr/sbin/lspci']).decode()
        for dev in lspci.splitlines():
            devs.append((dev.rstrip(), dev.split(' ')[0]))

        # pylint: disable=too-few-public-methods
        class DevListWidgetItem(QtGui.QListWidgetItem):
            def __init__(self, name, ident, parent=None):
                super(DevListWidgetItem, self).__init__(name, parent)
                self.ident = ident

        persistent = [ass.ident.replace('_', ':')
                      for ass in self.vm.devices['pci'].persistent()]

        for name, ident in devs:
            if ident in persistent:
                self.dev_list.selected_list.addItem(
                    DevListWidgetItem(name, ident))
            else:
                self.dev_list.available_list.addItem(
                    DevListWidgetItem(name, ident))

        if self.dev_list.selected_list.count() > 0\
                and self.include_in_balancing.isChecked():
            self.dmm_warning_adv.show()
            self.dmm_warning_dev.show()
        else:
            self.dmm_warning_adv.hide()
            self.dmm_warning_dev.hide()

        if self.vm.is_running():
            self.dev_list.setEnabled(False)
            self.turn_off_vm_to_modify_devs.setVisible(True)
            self.no_strict_reset_button.setEnabled(False)
        else:
            self.dev_list.setEnabled(True)
            self.turn_off_vm_to_modify_devs.setVisible(False)

        self.update_pvh_dont_support_devs()

    def __apply_devices_tab__(self):
        msg = []

        try:
            old = [ass.ident.replace('_', ':')
                   for ass in self.vm.devices['pci'].persistent()]

            new = [self.dev_list.selected_list.item(i).ident
                   for i in range(self.dev_list.selected_list.count())]
            for ident in new:
                if ident not in old:
                    options = {}
                    if ident in self.new_strict_reset_list:
                        options['no-strict-reset'] = True
                    ass = devices.DeviceAssignment(
                        self.vm.app.domains['dom0'],
                        ident.replace(':', '_'),
                        persistent=True, options=options)
                    self.vm.devices['pci'].attach(ass)
                elif (ident in self.current_strict_reset_list) != \
                        (ident in self.new_strict_reset_list):
                    current_assignment = None
                    for assignment in self.vm.devices['pci'].assignments(
                            persistent=True):
                        if assignment.ident.replace("_", ":") == ident:
                            current_assignment = assignment
                            break
                    if current_assignment is None:
                        # it would be very weird if this happened
                        msg.append(self.tr("Error re-assigning device ") +
                                   ident)
                        continue

                    self.vm.devices['pci'].detach(current_assignment)

                    current_assignment.options['no-strict-reset'] = \
                        (ident in self.new_strict_reset_list)

                    self.vm.devices['pci'].attach(current_assignment)

            for ass in self.vm.devices['pci'].assignments(persistent=True):
                if ass.ident.replace('_', ':') not in new:
                    self.vm.devices['pci'].detach(ass)

        except qubesadmin.exc.QubesException as ex:
            if utils.is_debug():
                traceback.print_exc()
            msg.append(str(ex))

        return msg

    def include_in_balancing_changed(self, state):
        for i in range(self.services_list.count()):
            item = self.services_list.item(i)
            if str(item.text()) == 'meminfo-writer':
                item.setCheckState(state)
                break

        if self.dev_list.selected_list.count() > 0:
            if state == ui_settingsdlg.QtCore.Qt.Checked:
                self.dmm_warning_adv.show()
                self.dmm_warning_dev.show()
            else:
                self.dmm_warning_adv.hide()
                self.dmm_warning_dev.hide()
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())

    def devices_selection_changed(self):
        if self.include_in_balancing.isChecked():
            if self.dev_list.selected_list.count() > 0:
                self.dmm_warning_adv.show()
                self.dmm_warning_dev.show()
            else:
                self.dmm_warning_adv.hide()
                self.dmm_warning_dev.hide()

        self.update_virt_mode_list()

    def update_pvh_dont_support_devs(self):
        if self.selected_virt_mode() == 'PVH':
            self.dev_list.setEnabled(False)
            self.pvh_dont_support_devs.setVisible(True)
        else:
            self.dev_list.setEnabled(True)
            self.pvh_dont_support_devs.setVisible(False)

    def define_strict_reset_devices(self):
        for assignment in self.vm.devices['pci'].assignments():
            if assignment.options.get('no-strict-reset', False):
                self.current_strict_reset_list.append(
                    assignment.ident.replace('_', ':'))
        self.new_strict_reset_list = self.current_strict_reset_list.copy()

    def strict_reset_button_pressed(self):
        device_list_window = device_list.PCIDeviceListWindow(
            self.vm, self.qapp, self.dev_list, self.new_strict_reset_list, self)
        device_list_window.exec()

    ######## applications tab

    def refresh_apps_in_vm(self, t_monitor):
        try:
            target_vm = self.vm.template
        except AttributeError:
            target_vm = self.vm

        if not target_vm.is_running():
            not_running = True
            target_vm.start()
        else:
            not_running = False

        subprocess.check_call(['qvm-sync-appmenus', target_vm.name])

        if not_running:
            target_vm.shutdown()

        t_monitor.set_finished()

    def refresh_apps_button_pressed(self):

        self.refresh_apps_button.setEnabled(False)
        self.refresh_apps_button.setText(self.tr('Refresh in progress...'))

        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(
            target=self.refresh_apps_in_vm,
            args=(t_monitor,))
        thread.daemon = True
        thread.start()

        while not t_monitor.is_finished():
            self.qapp.processEvents()
            time.sleep(0.1)

        self.app_list_manager = AppmenuSelectManager(self.vm, self.app_list)

        self.refresh_apps_button.setEnabled(True)
        self.refresh_apps_button.setText(self.tr('Refresh Applications'))

    ######## services tab

    def __init_services_tab__(self):
        self.new_srv_dict = {}
        for feature in self.vm.features:
            if not feature.startswith('service.'):
                continue
            service = feature[len('service.'):]
            item = QtGui.QListWidgetItem(service)
            item.setCheckState(ui_settingsdlg.QtCore.Qt.Checked
                               if self.vm.features[feature]
                               else ui_settingsdlg.QtCore.Qt.Unchecked)
            self.services_list.addItem(item)
            self.new_srv_dict[service] = self.vm.features[feature]

        self.connect(
            self.services_list,
            QtCore.SIGNAL("itemClicked(QListWidgetItem *)"),
            self.services_item_clicked)

    def __add_service__(self):
        srv = str(self.service_line_edit.text()).strip()
        if srv != "":
            if srv in self.new_srv_dict:
                QtGui.QMessageBox.information(
                    None,
                    '',
                    self.tr('Service already on the list!'))
            else:
                item = QtGui.QListWidgetItem(srv)
                item.setCheckState(ui_settingsdlg.QtCore.Qt.Checked)
                self.services_list.addItem(item)
                self.new_srv_dict[srv] = True

    def __remove_service__(self):
        item = self.services_list.currentItem()

        if not item:
            return
        if str(item.text()) == 'meminfo-writer':
            QtGui.QMessageBox.information(
                None,
                self.tr('Service can not be removed'),
                self.tr('Service meminfo-writer can not '
                        'be removed from the list.'))
            return

        row = self.services_list.currentRow()
        item = self.services_list.takeItem(row)
        del self.new_srv_dict[str(item.text())]

    def services_item_clicked(self, item):
        if str(item.text()) == 'meminfo-writer':
            if item.checkState() == ui_settingsdlg.QtCore.Qt.Checked:
                if not self.include_in_balancing.isChecked():
                    self.include_in_balancing.setChecked(True)
            elif item.checkState() == ui_settingsdlg.QtCore.Qt.Unchecked:
                if self.include_in_balancing.isChecked():
                    self.include_in_balancing.setChecked(False)

    def __apply_services_tab__(self):
        msg = []

        try:
            for i in range(self.services_list.count()):
                item = self.services_list.item(i)
                self.new_srv_dict[str(item.text())] = \
                    (item.checkState() == ui_settingsdlg.QtCore.Qt.Checked)

            balancing_was_checked = self.vm.features.get(
                'service.meminfo-writer', True)
            balancing_is_checked = self.include_in_balancing.isChecked()
            meminfo_writer_checked = self.new_srv_dict.get(
                'meminfo-writer', True)

            if balancing_is_checked != meminfo_writer_checked:
                if balancing_is_checked != balancing_was_checked:
                    self.new_srv_dict['meminfo-writer'] = balancing_is_checked

            for service, v in self.new_srv_dict.items():
                feature = 'service.' + service
                if v != self.vm.features.get(feature, object()):
                    self.vm.features[feature] = v

            for feature in self.vm.features:
                if not feature.startswith('service.'):
                    continue
                service = feature[len('service.'):]
                if service not in self.new_srv_dict:
                    del self.vm.features[feature]
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        return msg

    ######### firewall tab related
    def set_fw_model(self, model):
        self.fw_model = model
        self.rulesTreeView.setModel(model)
        self.rulesTreeView.header().setResizeMode(
            QtGui.QHeaderView.ResizeToContents)
        self.rulesTreeView.header().setResizeMode(0, QtGui.QHeaderView.Stretch)
        self.set_allow(model.allow)
        if model.temp_full_access_expire_time:
            self.temp_full_access.setChecked(True)
            self.temp_full_access_time.setValue(
                (model.temp_full_access_expire_time -
                 int(firewall.datetime.datetime.now().strftime("%s"))) / 60)

    def disable_all_fw_conf(self):
        self.firewall_modified_outside_label.setVisible(True)
        self.policy_allow_radio_button.setEnabled(False)
        self.policy_deny_radio_button.setEnabled(False)
        self.rulesTreeView.setEnabled(False)
        self.new_rule_button.setEnabled(False)
        self.edit_rule_button.setEnabled(False)
        self.delete_rule_button.setEnabled(False)
        self.firewal_rules_label.setEnabled(False)
        self.tempFullAccessWidget.setEnabled(False)

    def set_allow(self, allow):
        self.policy_allow_radio_button.setChecked(allow)
        self.policy_deny_radio_button.setChecked(not allow)
        self.policy_changed()

    def policy_changed(self):
        self.rulesTreeView.setEnabled(
            self.policy_deny_radio_button.isChecked())
        self.new_rule_button.setEnabled(
            self.policy_deny_radio_button.isChecked())
        self.edit_rule_button.setEnabled(
            self.policy_deny_radio_button.isChecked())
        self.delete_rule_button.setEnabled(
            self.policy_deny_radio_button.isChecked())
        self.firewal_rules_label.setEnabled(
            self.policy_deny_radio_button.isChecked())
        self.tempFullAccessWidget.setEnabled(
            self.policy_deny_radio_button.isChecked())

    def new_rule_button_pressed(self):
        dialog = firewall.NewFwRuleDlg()
        self.fw_model.run_rule_dialog(dialog)

    def edit_rule_button_pressed(self):

        selected = self.rulesTreeView.selectedIndexes()

        if selected:
            dialog = firewall.NewFwRuleDlg()
            dialog.set_ok_state(True)
            row = self.rulesTreeView.selectedIndexes().pop().row()
            self.fw_model.populate_edit_dialog(dialog, row)
            self.fw_model.run_rule_dialog(dialog, row)

    def delete_rule_button_pressed(self):
        for i in set([index.row() for index
                      in self.rulesTreeView.selectedIndexes()]):
            self.fw_model.remove_child(i)


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception(exc_type, exc_value, exc_traceback):

    filename, line, dummy, dummy = traceback.extract_tb(exc_traceback).pop()
    filename = os.path.basename(filename)
    error = "%s: %s" % (exc_type.__name__, exc_value)

    strace = ""
    stacktrace = traceback.extract_tb(exc_traceback)
    while stacktrace:
        (filename, line, func, txt) = stacktrace.pop()
        strace += "----\n"
        strace += "line: %s\n" % txt
        strace += "func: %s\n" % func
        strace += "line no.: %d\n" % line
        strace += "file: %s\n" % filename

    msg_box = QtGui.QMessageBox()
    msg_box.setDetailedText(strace)
    msg_box.setIcon(QtGui.QMessageBox.Critical)
    msg_box.setWindowTitle("Houston, we have a problem...")
    msg_box.setText("Whoops. A critical error has occured. "
                    "This is most likely a bug in Qubes Manager.<br><br>"
                    "<b><i>%s</i></b>" % error +
                    "<br/>at line <b>%d</b><br/>of file %s.<br/><br/>"
                    % (line, filename))

    msg_box.exec_()


parser = QubesArgumentParser(vmname_nargs=1)

parser.add_argument('--tab', metavar='TAB',
                    action='store',
                    choices=VMSettingsWindow.tabs_indices.keys())

parser.set_defaults(
    tab='basic',
)


def main(args=None):
    args = parser.parse_args(args)
    vm = args.domains.pop()

    qapp = QtGui.QApplication(sys.argv)
    qapp.setOrganizationName('Invisible Things Lab')
    qapp.setOrganizationDomain("https://www.qubes-os.org/")
    qapp.setApplicationName("Qube Settings")

    if not utils.is_debug():
        sys.excepthook = handle_exception

    settings_window = VMSettingsWindow(vm, qapp, args.tab)
    settings_window.show()

    qapp.exec_()
    qapp.exit()


if __name__ == "__main__":
    main()

# vim:sw=4:et:
