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
import functools
import re
import subprocess
import traceback
from qubesadmin.tools import QubesArgumentParser
from qubesadmin import devices
from qubesadmin import utils as admin_utils
import qubesadmin.exc

from . import utils
from . import multiselectwidget
from . import common_threads
from . import device_list

from .appmenu_select import AppmenuSelectManager
from . import firewall
from PyQt5 import QtCore, QtWidgets, QtGui  # pylint: disable=import-error

from . import ui_settingsdlg  # pylint: disable=no-name-in-module


# pylint: disable=too-few-public-methods
class RenameVMThread(common_threads.QubesThread):
    def __init__(self, vm, new_vm_name, dependencies):
        super(RenameVMThread, self).__init__(vm)
        self.new_vm_name = new_vm_name
        self.dependencies = dependencies

    def run(self):
        try:
            new_vm = self.vm.app.clone_vm(self.vm, self.new_vm_name)

            failed_props = []

            for (holder, prop) in self.dependencies:
                try:
                    if holder is None:
                        setattr(self.vm.app, prop, new_vm)
                    else:
                        setattr(holder, prop, new_vm)
                except qubesadmin.exc.QubesException:
                    failed_props += [(holder, prop)]
            if not failed_props:
                del self.vm.app.domains[self.vm.name]
            else:
                list_text = utils.format_dependencies_list(failed_props)
                self.msg = (self.tr("Warning: rename partially unsuccessful!"),
                            self.tr("Some properties could not be changed to "
                                    "the new name. The system has now both {} "
                                    "and {} qubes. To resolve this, please "
                                    "check and change the following properties "
                                    "and remove the qube {} manually.<br>"
                                    ).format(self.vm.name, self.vm.name,
                                             self.vm.name) + list_text)

        except qubesadmin.exc.QubesException as ex:
            self.msg = (self.tr("Rename error!"), str(ex))
        except Exception as ex:  # pylint: disable=broad-except
            self.msg = (self.tr("Rename error!"), repr(ex))


# pylint: disable=too-few-public-methods
class RefreshAppsVMThread(common_threads.QubesThread):
    def __init__(self, vm, button):
        super(RefreshAppsVMThread, self).__init__(vm)
        self.button = button

    def run(self):
        vms_to_refresh = [self.vm]
        template = getattr(self.vm, 'template', None)
        if template:
            vms_to_refresh.append(template)

        for vm in vms_to_refresh:
            self.button.setText(
                self.tr('Refresh in progress (refreshing applications '
                        'from {})').format(vm.name))
            try:
                if not vm.is_running():
                    not_running = True
                    vm.start()
                else:
                    not_running = False

                subprocess.check_call(['qvm-sync-appmenus', vm.name])

                if not_running:
                    vm.shutdown()
            except Exception as ex:  # pylint: disable=broad-except
                self.msg = (self.tr("Refresh failed!"), str(ex))


# pylint: disable=too-many-instance-attributes
class VMSettingsWindow(ui_settingsdlg.Ui_SettingsDialog, QtWidgets.QDialog):
    tabs_indices = collections.OrderedDict((
        ('basic', 0),
        ('advanced', 1),
        ('firewall', 2),
        ('devices', 3),
        ('applications', 4),
        ('services', 5),
        ))

    def __init__(self, vm, init_page="basic", qapp=None, qubesapp=None,
                 parent=None):
        super(VMSettingsWindow, self).__init__(parent)

        self.vm = vm
        self.qapp = qapp
        self.qubesapp = qubesapp
        self.threads_list = []
        self.progress = None
        self.thread_closes = False
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

        self.buttonBox.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(
            self.apply)

        self.tabWidget.currentChanged.connect(self.current_tab_changed)

        # Initialize several auxillary variables for pylint's sake
        self.netvm_idx = None
        self.kernel_idx = None
        self.label_idx = None
        self.template_idx = None
        self.root_img_size = None
        self.priv_img_size = None
        self.default_dispvm_idx = None
        self.virt_mode_idx = None
        self.virt_mode_list = None

        ###### basic tab
        self.__init_basic_tab__()
        self.rename_vm_button.clicked.connect(self.rename_vm)
        self.delete_vm_button.clicked.connect(self.remove_vm)
        self.clone_vm_button.clicked.connect(self.clone_vm)

        ###### advanced tab
        self.__init_advanced_tab__()
        self.include_in_balancing.stateChanged.connect(
            self.include_in_balancing_changed)
        self.init_mem.editingFinished.connect(self.check_mem_changes)
        self.max_mem_size.editingFinished.connect(self.check_mem_changes)
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
        self.dev_list.selectedChanged.connect(self.devices_selection_changed)
        self.no_strict_reset_button.clicked.connect(
            self.strict_reset_button_pressed)
        self.current_strict_reset_list = []
        self.new_strict_reset_list = []
        self.define_strict_reset_devices()

        ####### services tab
        self.__init_services_tab__()
        self.add_srv_button.clicked.connect(self.__add_service__)
        self.remove_srv_button.clicked.connect(self.__remove_service__)

        ####### apps tab
        if self.tabWidget.isTabEnabled(self.tabs_indices["applications"]):
            self.app_list = multiselectwidget.MultiSelectWidget(self)
            self.apps_layout.addWidget(self.app_list)
            self.app_list_manager = AppmenuSelectManager(self.vm, self.app_list)
            self.refresh_apps_button.clicked.connect(
                self.refresh_apps_button_pressed)

    def setup_application(self):
        self.qapp.setApplicationName(self.tr("Qube Settings"))
        self.qapp.setWindowIcon(QtGui.QIcon.fromTheme("qubes-manager"))

    def clear_threads(self):
        for thread in self.threads_list:
            if thread.isFinished():
                if self.progress:
                    self.progress.hide()
                    self.progress = None

                if thread.msg:
                    (title, msg) = thread.msg
                    QtWidgets.QMessageBox.warning(
                        self,
                        title,
                        msg)

                self.threads_list.remove(thread)

                if self.thread_closes:
                    self.done(0)

                return

        raise RuntimeError(self.tr('No finished thread found'))

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        if event.key() == QtCore.Qt.Key_Enter \
                or event.key() == QtCore.Qt.Key_Return:
            return
        super(VMSettingsWindow, self).keyPressEvent(event)

    def accept(self):
        self.save_and_apply()

    def save_changes(self):
        with common_threads.busy_cursor():
            error = self.__save_changes__()

        if error:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Error while changing settings for {0}!"
                        ).format(self.vm.name),
                self.tr("ERROR: {0}").format('\n'.join(error)))

    def apply(self):
        self.save_changes()

        # these signals must be disconnected to avoid unintended behavior
        # on refreshing the drop-downs
        self.netVM.currentIndexChanged.disconnect()
        self.kernel.currentIndexChanged.disconnect()
        self.default_dispvm.currentIndexChanged.disconnect()

        self.__init_basic_tab__()
        self.__init_advanced_tab__()

    def save_and_apply(self):
        self.save_changes()
        self.done(0)

    def __save_changes__(self):
        ret = []

        try:
            ret_tmp = self.__apply_basic_tab__()
            if ret_tmp:
                ret += [self.tr("Basic tab:")] + ret_tmp
            ret_tmp = self.__apply_advanced_tab__()
            if ret_tmp:
                ret += [self.tr("Advanced tab:")] + ret_tmp
            ret_tmp = self.__apply_devices_tab__()
            if ret_tmp:
                ret += [self.tr("Devices tab:")] + ret_tmp
            ret_tmp = self.__apply_services_tab__()
            if ret_tmp:
                ret += [self.tr("Sevices tab:")] + ret_tmp
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

        utils.debug('\n'.join(ret))
        return ret

    def check_network_availability(self):
        netvm = self.vm.netvm
        try:
            provides_network = self.vm.provides_network
        except AttributeError:
            provides_network = False
        self.no_netvm_label.setVisible(netvm is None and not provides_network)
        self.netvm_no_firewall_label.setVisible(
            netvm is not None and
            not netvm.features.check_with_template('qubes-firewall', False))
        self.sysnet_warning_label.setVisible(netvm is None and provides_network)

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
                QtCore.QRegExp("[a-zA-Z0-9_-]*",
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
        elif self.vm.klass == 'DispVM':
            self.template_list, self.template_idx = utils.prepare_vm_choice(
                self.template_name,
                self.vm, 'template',
                self.vm.app.default_dispvm,
                (lambda vm: getattr(vm, 'template_for_dispvms', False)),
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

        self.netVM.currentIndexChanged.connect(self.check_warn_dispvmnetvm)

        self.include_in_backups.setChecked(self.vm.include_in_backups)

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
            dns_list = getattr(self.vm, 'dns', ['10.139.1.1', '10.139.1.2'])
            self.dns_label.setText(", ".join(dns_list))
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
        if not self.root_resize.isEnabled():
            self.root_resize.setToolTip(
                self.tr("To change system storage size, change properties "
                        "of the underlying template."))
        self.root_resize_label.setEnabled(self.root_resize.isEnabled())

    def __apply_basic_tab__(self):
        msg = []

        # vm label changed
        try:
            if self.vmlabel.isVisible():
                if self.vmlabel.currentIndex() != self.label_idx:
                    label = self.label_list[self.vmlabel.currentIndex()]
                    self.vm.label = label
                    self.label_idx = self.vmlabel.currentIndex()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # vm template changed
        try:
            if self.template_name.currentIndex() != self.template_idx:
                self.vm.template = \
                    self.template_list[self.template_name.currentIndex()]
                self.template_idx = self.template_name.currentIndex()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # vm netvm changed
        try:
            if self.netVM.currentIndex() != self.netvm_idx:
                self.vm.netvm = self.netvm_list[self.netVM.currentIndex()]
                self.netvm_idx = self.netVM.currentIndex()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # include in backups
        try:
            if self.vm.include_in_backups != \
                    self.include_in_backups.isChecked():
                self.vm.include_in_backups = self.include_in_backups.isChecked()
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
                self.priv_img_size = priv_size
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        # max sys storage
        sys_size = self.root_resize.value()
        if self.root_img_size != sys_size:
            try:
                self.vm.volumes['root'].resize(sys_size * 1024**2)
                self.root_img_size = sys_size
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        return msg

    def check_mem_changes(self):
        if self.max_mem_size.value() < self.init_mem.value():
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Warning!"),
                self.tr("Max memory can not be less than initial memory.<br>"
                        "Setting max memory to equal initial memory."))
            self.max_mem_size.setValue(self.init_mem.value())
        # Linux specific limit: init memory must not be below
        # max_mem_size/10.79 in order to allow scaling up to
        # max_mem_size (or else "add_memory() failed: -17" problem)
        if self.vm.features.check_with_template('os', None) == 'Linux' and \
                self.init_mem.value() * 10 < self.max_mem_size.value():
            self.init_mem.setValue((self.max_mem_size.value() + 9) // 10)
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Warning!"),
                self.tr("For Linux qubes, Initial memory can not be less than "
                        "one tenth Max memory.<br>Setting initial memory "
                        "to the minimum allowed value."))

    def check_warn_dispvmnetvm(self):
        if not hasattr(self.vm, 'default_dispvm'):
            self.warn_netvm_dispvm.setVisible(False)
            return
        dispvm = self.default_dispvm_list[
            self.default_dispvm.currentIndex()]
        own_netvm = self.netvm_list[self.netVM.currentIndex()]

        if dispvm == qubesadmin.DEFAULT:
            dispvm = self.vm.property_get_default('default_dispvm')

        if dispvm == self.vm:
            self.warn_netvm_dispvm.setVisible(False)
            return

        dispvm_netvm = getattr(dispvm, 'netvm', None)

        if own_netvm == qubesadmin.DEFAULT:
            own_netvm = self.vm.property_get_default('netvm')

        if dispvm_netvm and dispvm_netvm != own_netvm:
            self.warn_netvm_dispvm.setVisible(True)
        else:
            self.warn_netvm_dispvm.setVisible(False)

    def rename_vm(self):

        dependencies = admin_utils.vm_dependencies(self.vm.app, self.vm)

        running_dependencies = [vm.name for (vm, prop) in dependencies
                                if vm and prop == 'template'
                                and vm.is_running()]

        if running_dependencies:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Qube cannot be renamed!"),
                self.tr(
                    "The following qubes using this qube as a template are "
                    "running: <br> {}. <br> In order to rename this qube, you "
                    "must first shut them down.").format(
                        ", ".join(running_dependencies)))
            return

        new_vm_name, ok = QtWidgets.QInputDialog.getText(
            self,
            self.tr('Rename qube'),
            self.tr('New name: (WARNING: all other changes will be discarded)'),
            text=self.vm.name)

        if ok:
            thread = RenameVMThread(self.vm, new_vm_name, dependencies)
            self.threads_list.append(thread)
            thread.finished.connect(self.clear_threads)

            self.progress = QtWidgets.QProgressDialog(
                self.tr("Renaming Qube..."), "", 0, 0)
            self.progress.setCancelButton(None)
            self.progress.setModal(True)
            self.thread_closes = True
            self.progress.show()

            thread.start()

    def remove_vm(self):

        dependencies = admin_utils.vm_dependencies(self.vm.app, self.vm)

        if dependencies:
            list_text = utils.format_dependencies_list(dependencies)
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Qube cannot be removed!"),
                self.tr("This qube cannot be removed. It is used as:"
                        " <br> {} <small>If you want to  remove this qube, "
                        "you should remove or change settings of each qube "
                        "or setting that uses it.</small>").format(list_text))

            return

        answer, ok = QtWidgets.QInputDialog.getText(
            self,
            self.tr('Delete qube'),
            self.tr('Are you absolutely sure you want to delete this qube? '
                    '<br/> All qube settings and data will be irrevocably'
                    ' deleted. <br/> If you are sure, please enter this '
                    'qube\'s name below.'))

        if ok and answer == self.vm.name:
            thread = common_threads.RemoveVMThread(self.vm)
            thread.finished.connect(self.clear_threads)
            self.threads_list.append(thread)

            self.progress = QtWidgets.QProgressDialog(
                self.tr("Deleting Qube..."), "", 0, 0)
            self.progress.setCancelButton(None)
            self.progress.setModal(True)
            self.thread_closes = True
            self.progress.show()

            thread.start()

        elif ok:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Removal cancelled"),
                self.tr("The qube will not be removed."))

    def clone_vm(self):

        cloned_vm_name, ok = QtWidgets.QInputDialog.getText(
            self,
            self.tr('Clone qube'),
            self.tr('Name for the cloned qube:'))

        if ok:
            thread = common_threads.CloneVMThread(self.vm, cloned_vm_name)
            thread.finished.connect(self.clear_threads)
            self.threads_list.append(thread)

            self.progress = QtWidgets.QProgressDialog(
                self.tr("Cloning Qube..."), "", 0, 0)
            self.progress.setCancelButton(None)
            self.progress.setModal(True)
            self.thread_closes = True
            self.progress.show()

            thread.start()

    ######### advanced tab

    def __init_advanced_tab__(self):

        self.init_mem.setValue(int(self.vm.memory))

        if self.vm.maxmem > 0:
            self.max_mem_size.setValue(int(self.vm.maxmem))
        else:
            maxmem = self.vm.property_get_default('maxmem')
            if maxmem == 0:
                maxmem = self.vm.memory
            self.max_mem_size.setValue(int(
                self.vm.features.get('qubesmanager.maxmem_value', maxmem)))

        self.vcpus.setMinimum(1)
        self.vcpus.setValue(int(self.vm.vcpus))

        self.include_in_balancing.setEnabled(True)
        self.include_in_balancing.setChecked(int(self.vm.maxmem) > 0)
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())

        # in case VM is HVM
        if hasattr(self.vm, "kernel"):
            self.kernel_groupbox.setVisible(True)
            self.kernel_list, self.kernel_idx = utils.prepare_kernel_choice(
                self.kernel, self.vm, 'kernel',
                None,
                allow_default=True, allow_none=True)
            self.kernel.currentIndexChanged.connect(self.kernel_changed)
            self.kernel_opts.setText(getattr(self.vm, 'kernelopts', '-'))
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
            self.default_dispvm.currentIndexChanged.connect(
                self.check_warn_dispvmnetvm)

        self.check_warn_dispvmnetvm()
        self.update_virt_mode_list()

        windows_running = \
            self.vm.features.check_with_template('os', None) == 'Windows' \
            and self.vm.is_running()

        self.seamless_on_button.setEnabled(windows_running)
        self.seamless_off_button.setEnabled(windows_running)

        self.seamless_on_button.clicked.connect(self.enable_seamless)
        self.seamless_off_button.clicked.connect(self.disable_seamless)

        if hasattr(self.vm, "template_for_dispvms"):
            self.dvm_template_checkbox.setChecked(self.vm.template_for_dispvms)
        else:
            self.dvm_template_checkbox.setVisible(False)

        self.provides_network_checkbox.setChecked(
            getattr(self.vm, 'provides_network', False))
        if self.provides_network_checkbox.isChecked():
            domains_using = [vm.name for vm in self.vm.connected_vms]
            if domains_using:
                self.provides_network_checkbox.setEnabled(False)
                self.provides_network_checkbox.setToolTip(self.tr(
                    "Cannot change this setting while this qube is used as a "
                    "NetVM by the following qubes:\n") +
                    "\n".join(domains_using))

        try:
            self.run_in_debug_mode.setChecked(self.vm.debug)
            self.run_in_debug_mode.setVisible(True)
        except AttributeError:
            self.run_in_debug_mode.setVisible(False)

    def enable_seamless(self):
        self.vm.run_service_for_stdio("qubes.SetGuiMode", input=b'SEAMLESS')

    def disable_seamless(self):
        self.vm.run_service_for_stdio("qubes.SetGuiMode", input=b'FULLSCREEN')

    def __apply_advanced_tab__(self):
        msg = []

        # mem/cpu
        try:
            if self.init_mem.value() != int(self.vm.memory):
                self.vm.memory = self.init_mem.value()

            curr_maxmem = int(self.vm.maxmem)

            if not self.include_in_balancing.isChecked():
                maxmem = 0
            else:
                maxmem = self.max_mem_size.value()

            if maxmem != curr_maxmem:
                if curr_maxmem > 0:
                    self.vm.features['qubesmanager.maxmem_value'] = curr_maxmem
                self.vm.maxmem = maxmem

            if self.vcpus.value() != int(self.vm.vcpus):
                self.vm.vcpus = self.vcpus.value()

        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # in case VM is not Linux
        if hasattr(self.vm, "kernel") and self.kernel_groupbox.isVisible():
            try:
                if self.kernel.currentIndex() != self.kernel_idx:
                    self.vm.kernel = self.kernel_list[
                        self.kernel.currentIndex()]
                    self.kernel_idx = self.kernel.currentIndex()
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        # vm default_dispvm changed
        try:
            if self.default_dispvm.currentIndex() != self.default_dispvm_idx:
                self.vm.default_dispvm = \
                    self.default_dispvm_list[self.default_dispvm.currentIndex()]
                self.default_dispvm_idx = self.default_dispvm.currentIndex()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        try:
            if self.virt_mode.currentIndex() != self.virt_mode_idx:
                self.vm.virt_mode = self.selected_virt_mode()
                self.virt_mode_idx = self.virt_mode.currentIndex()
        except Exception as ex:  # pylint: disable=broad-except
            msg.append(str(ex))

        if getattr(self.vm, "template_for_dispvms", False) != \
                self.dvm_template_checkbox.isChecked():
            try:
                self.vm.template_for_dispvms = \
                    self.dvm_template_checkbox.isChecked()
                if self.dvm_template_checkbox.isChecked():
                    self.vm.features["appmenus-dispvm"] = True
                else:
                    del self.vm.features["appmenus-dispvm"]
            except Exception as ex:  # pylint: disable=broad-except
                msg.append(str(ex))

        if getattr(self.vm, 'provides_network', False) != \
                self.provides_network_checkbox.isChecked():
            try:
                self.vm.provides_network = \
                    self.provides_network_checkbox.isChecked()
            except Exception as ex:  # pylint: disable=broad-except
                msg.append(str(ex))

        # run_in_debug_mode
        try:
            if self.run_in_debug_mode.isVisible():
                if self.vm.debug != self.run_in_debug_mode.isChecked():
                    self.vm.debug = self.run_in_debug_mode.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        return msg

    def include_in_balancing_changed(self, state):
        if self.dev_list.selected_list.count() > 0:
            if state == ui_settingsdlg.QtCore.Qt.Checked:
                self.dmm_warning_adv.show()
                self.dmm_warning_dev.show()
            else:
                self.dmm_warning_adv.hide()
                self.dmm_warning_dev.hide()
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())

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

        if hasattr(self, "dev_list"):
            devs_attached = self.dev_list.selected_list.count() != 0
        else:
            devs_attached = bool(list(self.vm.devices['pci'].persistent()))

        if devs_attached:
            self.pvh_mode_hidden.show()
        else:
            choices.insert(0, 'PVH')
            self.pvh_mode_hidden.hide()

        if self.virt_mode_list:
            old_mode = self.selected_virt_mode()
            self.virt_mode.currentIndexChanged.disconnect()
        else:
            old_mode = None

        self.virt_mode.clear()

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

        dom0_devs = list(self.vm.app.domains['dom0'].devices['pci'].available())

        attached_devs = list(self.vm.devices['pci'].persistent())

        # pylint: disable=too-few-public-methods
        class DevListWidgetItem(QtWidgets.QListWidgetItem):
            def __init__(self, dev, unknown=False, parent=None):
                super(DevListWidgetItem, self).__init__(parent)
                name = dev.ident.replace('_', ":") + ' ' + dev.description
                if unknown:
                    name += ' (unknown)'
                self.setText(name)
                self.dev = dev

        for dev in dom0_devs:
            if dev in attached_devs:
                self.dev_list.selected_list.addItem(DevListWidgetItem(dev))
            else:
                self.dev_list.available_list.addItem(DevListWidgetItem(dev))
        for dev in attached_devs:
            if dev not in dom0_devs:
                self.dev_list.selected_list.addItem(
                    DevListWidgetItem(dev, unknown=True))

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

        self.dev_list.setEnabled(not self.vm.is_running())

    def __apply_devices_tab__(self):
        msg = []

        try:
            old_devs = list(self.vm.devices['pci'].persistent())

            new_devs = [self.dev_list.selected_list.item(i).dev
                        for i in range(self.dev_list.selected_list.count())]

            for dev in new_devs:
                if dev not in old_devs:
                    options = {}
                    if dev.ident in self.new_strict_reset_list:
                        options['no-strict-reset'] = True
                    ass = devices.DeviceAssignment(
                        self.vm.app.domains['dom0'],
                        dev.ident, persistent=True, options=options)
                    self.vm.devices['pci'].attach(ass)
                elif (dev.ident in self.current_strict_reset_list) != \
                        (dev.ident in self.new_strict_reset_list):
                    current_assignment = None
                    for assignment in self.vm.devices['pci'].assignments(
                            persistent=True):
                        if assignment.ident == dev.ident:
                            current_assignment = assignment
                            break
                    if current_assignment is None:
                        # it would be very weird if this happened
                        msg.append(self.tr("Error re-assigning device ") +
                                   dev.ident)
                        continue

                    self.vm.devices['pci'].detach(current_assignment)

                    current_assignment.options['no-strict-reset'] = \
                        (dev.ident in self.new_strict_reset_list)

                    self.vm.devices['pci'].attach(current_assignment)

            for ass in self.vm.devices['pci'].assignments(persistent=True):
                if ass.device not in new_devs:
                    self.vm.devices['pci'].detach(ass)

        except qubesadmin.exc.QubesException as ex:
            if utils.is_debug():
                traceback.print_exc()
            msg.append(str(ex))

        return msg

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

    def refresh_apps_button_pressed(self):

        self.refresh_apps_button.setEnabled(False)
        self.refresh_apps_button.setText(self.tr('Refresh in progress...'))

        thread = RefreshAppsVMThread(self.vm, self.refresh_apps_button)
        thread.finished.connect(self.clear_threads)
        thread.finished.connect(self.refresh_finished)
        self.threads_list.append(thread)
        thread.start()

    def refresh_finished(self):
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
            item = QtWidgets.QListWidgetItem(service)
            item.setCheckState(ui_settingsdlg.QtCore.Qt.Checked
                               if self.vm.features[feature]
                               else ui_settingsdlg.QtCore.Qt.Unchecked)
            self.services_list.addItem(item)
            self.new_srv_dict[service] = self.vm.features[feature]

        self.service_line_edit.addItem("")

        supported_services = set()
        service_prefix = "supported-service."

        for feature in self.vm.features:
            if feature.startswith(service_prefix):
                supported_services.add(feature[len(service_prefix):])
        if getattr(self.vm, "template", None):
            for feature in self.vm.template.features:
                if feature.startswith(service_prefix):
                    supported_services.add(feature[len(service_prefix):])

        for service in sorted(supported_services):
            self.service_line_edit.addItem(service)

        self.service_line_edit.addItem(self.tr('(custom...)'))
        self.service_line_edit.setEditText("")

    def __add_service__(self):
        srv = str(self.service_line_edit.currentText()).strip()

        if srv != "":
            if self.service_line_edit.currentIndex() == \
                    len(self.service_line_edit) - 1:
                (custom_name, ok) = QtWidgets.QInputDialog.getText(
                    self, self.tr("Custom service name"),
                    self.tr(
                        "Name of the service:"))
                if ok:
                    srv = custom_name.strip()
                else:
                    return
            if srv in self.new_srv_dict:
                QtWidgets.QMessageBox.information(
                    self,
                    '',
                    self.tr('Service already on the list!'))
                return
            item = QtWidgets.QListWidgetItem(srv)
            item.setCheckState(ui_settingsdlg.QtCore.Qt.Checked)
            self.services_list.addItem(item)
            self.new_srv_dict[srv] = True

    def __remove_service__(self):
        item = self.services_list.currentItem()

        if not item:
            return

        row = self.services_list.currentRow()
        item = self.services_list.takeItem(row)
        del self.new_srv_dict[str(item.text())]

    def __apply_services_tab__(self):
        msg = []

        try:
            for i in range(self.services_list.count()):
                item = self.services_list.item(i)
                self.new_srv_dict[str(item.text())] = \
                    (item.checkState() == ui_settingsdlg.QtCore.Qt.Checked)

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
        self.rulesTreeView.header().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents)
        self.rulesTreeView.header().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
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
        for i in {index.row() for index
                  in self.rulesTreeView.selectedIndexes()}:
            self.fw_model.remove_child(i)


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

    utils.run_synchronous(functools.partial(VMSettingsWindow, vm, args.tab))


if __name__ == "__main__":
    main()

# vim:sw=4:et:
