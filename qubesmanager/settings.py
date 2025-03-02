#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski-Górecki
#                       <marmarek@invisiblethingslab.com>
# Copyright (C) 2017  Wojtek Porczyk <woju@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#


import collections
import functools
import re
import subprocess
import sys
import traceback
import datetime
from qubesadmin.tools import QubesArgumentParser
from qubesadmin import device_protocol
from qubesadmin import utils as admin_utils
from qubesadmin.tools import qvm_start
import qubesadmin.exc

from . import bootfromdevice
from . import utils
from . import multiselectwidget
from . import common_threads
from . import device_list
from . import clone_vm

from .appmenu_select import AppmenuSelectManager
from . import firewall
from PyQt6 import QtCore, QtWidgets, QtGui  # pylint: disable=import-error

from . import ui_settingsdlg  # pylint: disable=no-name-in-module

# this is needed for icons to actually work
# pylint: disable=unused-import, no-name-in-module
from . import resources

SERVICE_PREFIX = "service."
SUPPORTED_SERVICE_PREFIX = "supported-service."

IDLE_SUPPORTED_SERVICE = f"{SUPPORTED_SERVICE_PREFIX}shutdown-idle"
IDLE_SERVICE = f"{SERVICE_PREFIX}shutdown-idle"

INTERNAL_SERVICE_FEATURES = [IDLE_SERVICE]
INTERNAL_SUPPORTED_FEATURES = [IDLE_SUPPORTED_SERVICE]


def get_default_bootmode_name(vm, bootmode):
    if bootmode == "default":
        return vm.features.check_with_template(
            "boot-mode.name.default", ""
        )
    return vm.features.check_with_template(
        f"boot-mode.name.{bootmode}", bootmode
    )


# pylint: disable=too-few-public-methods
class RenameVMThread(common_threads.QubesThread):
    def __init__(self, vm, new_vm_name, dependencies):
        super().__init__(vm)
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
                                    ).format(self.vm.name, self.new_vm_name,
                                             self.vm.name) + list_text)

        except qubesadmin.exc.QubesException as ex:
            self.msg = (self.tr("Rename error!"), str(ex))
        except Exception as ex:  # pylint: disable=broad-except
            self.msg = (self.tr("Rename error!"), repr(ex))


# pylint: disable=too-few-public-methods
class RefreshAppsVMThread(common_threads.QubesThread):
    def __init__(self, vm, button):
        super().__init__(vm)
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
                if not utils.is_running(vm, True):
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

    # pylint: disable=too-many-positional-arguments
    def __init__(self, vm_name, init_page="basic", qapp=None, qubesapp=None,
                 parent=None):
        super().__init__(parent)

        self.vm = qubesapp.domains[vm_name]
        self.qapp = qapp
        self.qubesapp = qubesapp
        self.threads_list = []
        self.progress = None
        self.thread_closes = False

        self.setupUi(self)
        self.setWindowTitle(self.tr("Settings: {vm}").format(vm=self.vm.name))
        self.setWindowFlags(self.windowFlags() |
                            QtCore.Qt.WindowType.WindowMaximizeButtonHint |
                            QtCore.Qt.WindowType.WindowMinimizeButtonHint)
        if init_page in self.tabs_indices:
            idx = self.tabs_indices[init_page]
            assert idx in range(self.tabWidget.count())
            self.tabWidget.setCurrentIndex(idx)

        self.buttonBox.button(
            QtWidgets.QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply)

        self.tabWidget.currentChanged.connect(self.current_tab_changed)

        # Initialize several auxillary variables for pylint's sake
        self.root_img_size = None
        self.priv_img_size = None

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
        self.check_mem_changes()
        self.boot_from_device_button.clicked.connect(
            self.boot_from_cdrom_button_pressed)

        ###### firewall tab
        if self.tabWidget.isTabEnabled(self.tabs_indices['firewall']):
            model = firewall.QubesFirewallRulesModel()
            try:
                model.set_vm(self.vm)
                self.set_fw_model(model)
                self.firewall_modified_outside_label.setVisible(False)
            except firewall.FirewallModifiedOutsideError:
                self.disable_all_fw_conf()
            except qubesadmin.exc.QubesException:
                self.tabWidget.setTabEnabled(
                    self.tabs_indices['firewall'], False)

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
            self.app_list.change_labels(
                available="All available applications",
                selected="Applications shown in App Menu")
            self.apps_layout.addWidget(self.app_list)
            self.app_list_manager = AppmenuSelectManager(self.vm, self.app_list)
            self.refresh_apps_button.clicked.connect(
                self.refresh_apps_button_pressed)

            # Enable Drag & Drop between between two panels
            # ToDo: Disable D&D between multiple instances of qubes-vm-settings
            # - by overriding QListWidget.dragMoveEvent event
            self.app_list.available_list.setDragEnabled(True)
            self.app_list.available_list.setAcceptDrops(True)
            self.app_list.available_list.setDragDropMode(
                QtWidgets.QListWidget.DragDropMode.DragDrop)
            self.app_list.available_list.setDefaultDropAction(
                QtCore.Qt.DropAction.MoveAction)
            self.app_list.selected_list.setDragEnabled(True)
            self.app_list.selected_list.setAcceptDrops(True)
            self.app_list.selected_list.setDragDropMode(
                QtWidgets.QListWidget.DragDropMode.DragDrop)
            self.app_list.selected_list.setDefaultDropAction(
                QtCore.Qt.DropAction.MoveAction)

            # template change
            if self.template_name.isEnabled():
                self.template_name.currentIndexChanged.connect(
                    self.template_apps_change)
            self.warn_template_missing_apps.setVisible(
                self.app_list_manager.has_missing)

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
        if event.key() == QtCore.Qt.Key.Key_Enter \
                or event.key() == QtCore.Qt.Key.Key_Return:
            return
        super().keyPressEvent(event)

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

        self.vm.clear_cache()

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
            if self.tabWidget.isTabEnabled(self.tabs_indices['firewall']) and \
                    self.policy_allow_radio_button.isEnabled():
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
        # this should attempt to use whatever is currently selected, not VM
        # settings
        if self.netVM.currentData() == qubesadmin.DEFAULT:
            netvm = self.vm.property_get_default('netvm')
        else:
            netvm = self.netVM.currentData()
        provides_network = self.provides_network_checkbox.isChecked()

        self.no_netvm_label.setVisible(netvm is None and not provides_network)

        try:
            no_firewall_state = \
                netvm is not None and \
                not netvm.features.check_with_template('qubes-firewall', False)
        except qubesadmin.exc.QubesDaemonAccessError:
            no_firewall_state = False

        self.netvm_no_firewall_label.setVisible(no_firewall_state)
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

    def __init_basic_tab__(self):
        self.vmname.setText(self.vm.name)
        self.vmname.setValidator(
            QtGui.QRegularExpressionValidator(
                QtCore.QRegularExpression(
                    "[a-zA-Z0-9_-]*",
                    QtCore.QRegularExpression.
                    PatternOption.CaseInsensitiveOption), None))
        self.vmname.setEnabled(False)
        self.rename_vm_button.setEnabled(not self.vm.is_running())
        self.delete_vm_button.setEnabled(not self.vm.is_running())

        if utils.is_running(self.vm, False):
            self.delete_vm_button.setText(
                self.tr('Delete qube (cannot delete a running qube)'))

        if self.vm.klass == 'AdminVM':
            self.vmlabel.setVisible(False)
        else:
            try:
                utils.initialize_widget_with_labels(
                    widget=self.vmlabel,
                    qubes_app=self.qubesapp,
                    holder=self.vm)
                self.vmlabel.setVisible(True)
                self.vmlabel.setEnabled(not utils.is_running(self.vm, False))
            except qubesadmin.exc.QubesDaemonAccessError:
                self.vmlabel.setEnabled(False)

        if self.vm.klass == 'AppVM':
            try:
                utils.initialize_widget_with_vms(
                    widget=self.template_name,
                    qubes_app=self.qubesapp,
                    filter_function=(lambda vm: vm.klass == 'TemplateVM'),
                    holder=self.vm,
                    property_name='template')
            except qubesadmin.exc.QubesDaemonAccessError:
                self.template_name.setCurrentIndex(-1)
                self.template_name.setEnabled(False)

        elif self.vm.klass == 'DispVM':
            try:
                utils.initialize_widget_with_vms(
                    widget=self.template_name,
                    qubes_app=self.qubesapp,
                    filter_function=(
                        lambda vm: getattr(vm, 'template_for_dispvms', False)),
                    holder=self.vm,
                    property_name='template')
            except qubesadmin.exc.QubesDaemonAccessError:
                self.template_name.setCurrentIndex(-1)
                self.template_name.setEnabled(False)

        else:
            self.template_name.setEnabled(False)

        if utils.is_running(self.vm, False):
            self.template_name.setEnabled(False)

        try:
            utils.initialize_widget_with_vms(
                widget=self.netVM,
                qubes_app=self.qubesapp,
                filter_function=(lambda vm:
                                 getattr(vm, 'provides_network', False)),
                holder=self.vm,
                property_name='netvm',
                allow_default=True,
                allow_none=True)
        except qubesadmin.exc.QubesDaemonAccessError:
            self.netVM.setEnabled(False)
            self.netVM.setCurrentIndex(-1)

        self.netVM.currentIndexChanged.connect(self.check_warn_dispvmnetvm)
        self.netVM.currentIndexChanged.connect(self.check_warn_templatenetvm)
        self.netVM.currentIndexChanged.connect(self.check_network_availability)

        try:
            self.include_in_backups.setChecked(self.vm.include_in_backups)
        except qubesadmin.exc.QubesDaemonAccessError:
            self.include_in_backups.setEnabled(False)

        try:
            has_shutdown_idle = self.vm.features.check_with_template(
                IDLE_SUPPORTED_SERVICE, False)
            if has_shutdown_idle:
                self.idle_shutdown_checkbox.setChecked(
                    bool(self.vm.features.get(IDLE_SERVICE, False)))
            else:
                text = "Shut down when idle "
                if getattr(self.vm, 'template', None):
                    additional_text = "(unavailable: package " \
                                      "qubes-app-shutdown-idle missing " \
                                      "in the template)"
                else:
                    additional_text = "(unavailable: package " \
                                      "qubes-app-shutdown-idle missing " \
                                      "in the qube)"
                self.idle_shutdown_checkbox.setText(text + additional_text)
                self.idle_shutdown_checkbox.setEnabled(False)
        except qubesadmin.exc.QubesDaemonCommunicationError:
            self.idle_shutdown_checkbox.setText(
                self.idle_shutdown_checkbox.text() +
                " (unavailable: permission denied)")
            self.idle_shutdown_checkbox.setEnabled(False)

        try:
            self.autostart_vm.setChecked(self.vm.autostart)
            self.autostart_vm.setVisible(True)
        except qubesadmin.exc.QubesDaemonAccessError:
            self.autostart_vm.setEnabled(False)
        except AttributeError:
            self.autostart_vm.setEnabled(False)
            self.autostart_vm.setVisible(False)

        # type
        self.type_label.setText(self.vm.klass)

        # installed by rpm
        self.rpm_label.setText(
            'Yes' if getattr(self.vm, 'installed_by_rpm', False) else 'No')

        # networking info
        if getattr(self.vm, 'netvm', None):
            self.networking_groupbox.setEnabled(True)
            self.ip_label.setText(getattr(self.vm, 'ip', None) or "none")
            self.netmask_label.setText(
                getattr(self.vm, 'visible_netmask', None) or "none")
            self.gateway_label.setText(
                getattr(self.vm, 'visible_gateway', None) or "none")
            dns_list = getattr(self.vm, 'dns', '10.139.1.1 10.139.1.2')
            self.dns_label.setText(dns_list.replace(' ', ', '))
        else:
            self.networking_groupbox.setEnabled(False)

        # max priv storage
        try:
            self.priv_img_size = self.vm.volumes['private'].size // 1024**2
            self.max_priv_storage.setMinimum(self.priv_img_size)
            self.max_priv_storage.setValue(self.priv_img_size)
            self.max_priv_storage.setMaximum(
                max(self.priv_img_size,
                    self.qubesapp.pools[self.vm.volumes['private'].pool].size
                    // 1024**2))
        except qubesadmin.exc.QubesException:
            self.max_priv_storage.setEnabled(False)

        try:
            self.root_img_size = self.vm.volumes['root'].size // 1024**2
            self.root_resize.setValue(self.root_img_size)
            self.root_resize.setMinimum(self.root_img_size)
            self.root_resize.setMaximum(
                max(self.root_img_size,
                    self.qubesapp.pools[self.vm.volumes['root'].pool].size
                    // 1024**2))
            self.root_resize.setEnabled(self.vm.volumes['root'].save_on_stop)
            if not self.root_resize.isEnabled():
                self.root_resize.setToolTip(
                    self.tr("To change system storage size, change properties "
                            "of the underlying template."))
            self.root_resize_label.setEnabled(self.root_resize.isEnabled())
        except qubesadmin.exc.QubesException:
            self.root_resize.setEnabled(False)

        self.warn_template_missing_apps.setVisible(False)

    def __apply_basic_tab__(self):
        msg = []
        # vm label changed
        try:
            if utils.did_widget_selection_change(self.vmlabel):
                self.vm.label = self.vmlabel.currentData()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # vm template changed
        try:
            if utils.did_widget_selection_change(self.template_name):
                self.vm.template = self.template_name.currentData()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # vm netvm changed
        try:
            if utils.did_widget_selection_change(self.netVM):
                if self.netVM.currentData() == qubesadmin.DEFAULT:
                    netvm = self.vm.property_get_default('netvm')
                else:
                    netvm = self.netVM.currentData()
                if self.vm.get_power_state() == 'Running' and netvm and \
                        netvm.get_power_state() != 'Running':
                    reply = QtWidgets.QMessageBox.question(
                        self, self.tr("Qube Start Confirmation"),
                        self.tr("<br>Can not change netvm of a running qube"
                                "to a halted Qube.<br>"
                                "Do you want to start the Qube"
                                " <b>'{0}'</b>?").format(netvm.name),
                        QtWidgets.QMessageBox.StandardButton.Yes |
                        QtWidgets.QMessageBox.StandardButton.Cancel)

                    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                        netvm.start()
                        self.vm.netvm = self.netVM.currentData()
                else:
                    self.vm.netvm = self.netVM.currentData()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # include in backups
        try:
            if self.include_in_backups.isEnabled() and\
                    self.vm.include_in_backups != \
                    self.include_in_backups.isChecked():
                self.vm.include_in_backups = self.include_in_backups.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # autostart_vm
        try:
            if self.autostart_vm.isEnabled():
                if self.vm.autostart != self.autostart_vm.isChecked():
                    self.vm.autostart = self.autostart_vm.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # shutdown-idle
        try:
            current_idle = self.vm.features.get(IDLE_SERVICE, False)
            if self.idle_shutdown_checkbox.isEnabled() and \
                    self.idle_shutdown_checkbox.isChecked() != current_idle:
                self.vm.features[IDLE_SERVICE] = \
                    self.idle_shutdown_checkbox.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # max priv storage
        if self.max_priv_storage.isEnabled():
            priv_size = self.max_priv_storage.value()
            if self.priv_img_size != priv_size:
                try:
                    self.vm.volumes['private'].resize(priv_size * 1024**2)
                    self.priv_img_size = priv_size
                except qubesadmin.exc.QubesException as ex:
                    msg.append(str(ex))

        # max sys storage
        if self.root_resize.isEnabled():
            sys_size = self.root_resize.value()
            if self.root_img_size != sys_size:
                try:
                    self.vm.volumes['root'].resize(sys_size * 1024**2)
                    self.root_img_size = sys_size
                except qubesadmin.exc.QubesException as ex:
                    msg.append(str(ex))

        return msg

    def check_mem_changes(self):
        self.warn_too_much_mem_label.setVisible(False)
        if not self.include_in_balancing.isChecked():
            # do not interfere with settings if the VM is not included in memory
            # balancing
            return
        if not self.max_mem_size.isEnabled() or not self.init_mem.isEnabled():
            # do not interfere with settings if they are unavailable
            return
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
        try:
            is_linux = self.vm.features.check_with_template('os', None) == \
                       'Linux'
        except qubesadmin.exc.QubesException:
            is_linux = False

        if is_linux and \
                self.init_mem.value() * 10 < self.max_mem_size.value():
            self.warn_too_much_mem_label.setVisible(True)

    def check_warn_templatenetvm(self):
        if self.vm.klass != 'TemplateVM':
            return

        current_netvm = self.netVM.currentData()
        if current_netvm is None:
            return

        if current_netvm != qubesadmin.DEFAULT:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Warning!"),
                self.tr(
                    "Connecting a TemplateVM directly to a network is highly"
                    " discouraged! <br> <small>You are breaking a basic part "
                    "of Qubes security and there is probably no real need"
                    " to do so. Continue at your own risk.</small>"))

    def check_warn_dispvmnetvm(self):
        if not hasattr(self.vm, 'default_dispvm'):
            self.warn_netvm_dispvm.setVisible(False)
            return
        dispvm = self.default_dispvm.currentData()
        own_netvm = self.netVM.currentData()

        if dispvm == qubesadmin.DEFAULT:
            try:
                dispvm = self.vm.property_get_default('default_dispvm')
            except qubesadmin.exc.QubesDaemonAccessError:
                pass

        if dispvm == self.vm:
            self.warn_netvm_dispvm.setVisible(False)
            return

        dispvm_netvm = getattr(dispvm, 'netvm', None)

        if own_netvm == qubesadmin.DEFAULT:
            try:
                own_netvm = self.vm.property_get_default('netvm')
            except qubesadmin.exc.QubesDaemonAccessError:
                # no point in warning if we don't know what we're warning about
                self.warn_netvm_dispvm.setVisible(False)
                return

        if dispvm_netvm and dispvm_netvm != own_netvm:
            self.warn_netvm_dispvm.setVisible(True)
        else:
            self.warn_netvm_dispvm.setVisible(False)

    def rename_vm(self):

        dependencies = admin_utils.vm_dependencies(self.vm.app, self.vm)

        running_dependencies = [vm.name for (vm, prop) in dependencies
                                if vm and prop == 'template'
                                and utils.is_running(vm, False)]

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
        with common_threads.busy_cursor():
            clone_window = clone_vm.CloneVMDlg(
                self.qapp, self.qubesapp, src_vm=self.vm)
        clone_window.exec()

    ######### advanced tab

    def __init_advanced_tab__(self):

        vm_memory = getattr(self.vm, 'memory', None)
        vm_maxmem = getattr(self.vm, 'maxmem', None)

        if vm_memory is None:
            self.init_mem.setEnabled(False)
        else:
            self.init_mem.setValue(int(vm_memory))

        if vm_maxmem is None:
            self.max_mem_size.setEnabled(False)
        elif vm_maxmem > 0:
            self.max_mem_size.setValue(int(vm_maxmem))
        else:
            try:
                maxmem = self.vm.property_get_default('maxmem')
            except qubesadmin.exc.QubesDaemonAccessError:
                maxmem = 0
            if maxmem == 0:
                maxmem = vm_memory
            self.max_mem_size.setValue(
                int(utils.get_feature(
                    self.vm, 'qubesmanager.maxmem_value', maxmem)))

        self.vcpus.setMinimum(1)
        self.vcpus.setValue(int(getattr(self.vm, 'vcpus', 1)))

        self.include_in_balancing.setEnabled(True)
        self.include_in_balancing.setChecked(
            int(getattr(self.vm, 'maxmem', 0)) > 0)
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())

        # in case VM is HVM
        if hasattr(self.vm, "kernel"):
            self.kernel_groupbox.setVisible(True)
            try:
                utils.initialize_widget_with_kernels(
                    widget=self.kernel,
                    qubes_app=self.qubesapp,
                    allow_none=True,
                    allow_default=True,
                    holder=self.vm,
                    property_name='kernel')
                self.kernel.currentIndexChanged.connect(self.kernel_changed)
                self.kernel_opts.setText(getattr(self.vm, 'kernelopts', '-'))
                # load bootmode information from features
                if hasattr(self.vm, "appvm_default_bootmode"):
                    self.appvm_default_bootmode_desc.setVisible(True)
                    self.appvm_default_bootmode.setVisible(True)
                else:
                    self.appvm_default_bootmode_desc.setVisible(False)
                    self.appvm_default_bootmode.setVisible(False)
                self.bootmode_ids = [
                    x.split('.')[2] for x in self.vm.features \
                        if x.startswith("boot-mode.kernelopts.")
                ]
                subject = self.vm
                while hasattr(subject, "template"):
                    self.bootmode_ids.extend([
                        x.split('.')[2] for x in subject.template.features \
                            if x.startswith("boot-mode.kernelopts.")
                    ])
                    subject = subject.template
                self.bootmode_names = [
                    self.vm.features.check_with_template(
                        f"boot-mode.name.{x}", x
                    ) for x in self.bootmode_ids
                ]
                bootmode_widget_data = list(zip(
                    self.bootmode_names, self.bootmode_ids
                ))
                bootmode_widget_data.sort()
                utils.initialize_widget_for_property(
                    widget=self.bootmode,
                    choices=bootmode_widget_data,
                    property_name="bootmode",
                    holder=self.vm,
                    allow_default=True,
                    default_text_provider=get_default_bootmode_name
                )
                if hasattr(self.vm, "appvm_default_bootmode"):
                    # We need to recreate the bootmode_widget_data list,
                    # because utils.initialize_widget_for_property adds a
                    # default item to the list as a side-effect, and we'd end
                    # up with duplicate "default" entries if we didn't
                    # reinitialize it. Modifying
                    # initialize_widget_for_property to operate on a list deep
                    # copy breaks the virtualization mode combo box, making
                    # the default mode appear as
                    # `<object object at 0xaddress>`.
                    bootmode_widget_data = list(zip(
                        self.bootmode_names, self.bootmode_ids
                    ))
                    bootmode_widget_data.sort()
                    utils.initialize_widget_for_property(
                        widget=self.appvm_default_bootmode,
                        choices=bootmode_widget_data,
                        property_name="appvm_default_bootmode",
                        holder=self.vm,
                        allow_default=True,
                        default_text_provider=get_default_bootmode_name
                    )
                self.bootmode_kernel_opts.setText(
                    self.vm.features.check_with_template(
                        f"boot-mode.kernelopts.{self.vm.bootmode}",
                        ""
                    )
                )
            except qubesadmin.exc.QubesDaemonAccessError:
                self.kernel_groupbox.setVisible(False)
                self.kernel.setEnabled(False)
        else:
            self.kernel.setEnabled(False)
            self.kernel_groupbox.setVisible(False)

        if not hasattr(self.vm, 'default_dispvm'):
            self.other_groupbox.setVisible(False)
        else:
            try:
                self.other_groupbox.setVisible(True)
                utils.initialize_widget_with_vms(
                    widget=self.default_dispvm,
                    qubes_app=self.qubesapp,
                    filter_function=(lambda vm:
                                     getattr(
                                         vm, 'template_for_dispvms', False)),
                    allow_none=True,
                    allow_default=True,
                    holder=self.vm,
                    property_name='default_dispvm'
                )
                self.default_dispvm.currentIndexChanged.connect(
                    self.check_warn_dispvmnetvm)
            except qubesadmin.exc.QubesDaemonAccessError:
                self.other_groupbox.setVisible(False)

        self.check_warn_dispvmnetvm()
        self.update_virt_mode_list()

        try:
            windows_running = \
                self.vm.features.check_with_template('os', None) == 'Windows' \
                and self.vm.is_running()
        except qubesadmin.exc.QubesException:
            windows_running = False

        self.seamless_on_button.setEnabled(windows_running)
        self.seamless_off_button.setEnabled(windows_running)

        self.seamless_on_button.clicked.connect(self.enable_seamless)
        self.seamless_off_button.clicked.connect(self.disable_seamless)

        self.dvm_template_checkbox.setChecked(
            getattr(self.vm, 'template_for_dispvms', False))

        if not hasattr(self.vm, 'template_for_dispvms'):
            self.dvm_template_checkbox.setEnabled(False)

        self.provides_network_checkbox.setChecked(
            getattr(self.vm, 'provides_network', False))
        if self.provides_network_checkbox.isChecked():
            domains_using = [vm.name for vm
                             in getattr(self.vm, 'connected_vms', [])]
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
            self.run_in_debug_mode.setEnabled(False)

        utils.initialize_widget(
            widget=self.allow_fullscreen,
            choices=[
                ('(use system default)', None),
                ('allow', True),
                ('disallow', False)
            ],
            selected_value=utils.get_boolean_feature(self.vm,
                                                     'gui-allow-fullscreen'))
        self.allow_fullscreen_initial = self.allow_fullscreen.currentIndex()
        utils.initialize_widget(
            widget=self.allow_utf8,
            choices=[
                ('(use system default)', None),
                ('allow', True),
                ('disallow', False)
            ],
            selected_value=utils.get_boolean_feature(self.vm,
                                                     'gui-allow-utf8-titles'))
        self.allow_utf8_initial = self.allow_utf8.currentIndex()

    def enable_seamless(self):
        try:
            self.vm.run_service_for_stdio("qubes.SetGuiMode", input=b'SEAMLESS')
        except (qubesadmin.exc.QubesException,
                subprocess.CalledProcessError) as ex:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Failed to set seamless mode"),
                self.tr("Error occurred: {}".format(str(ex))))

    def disable_seamless(self):
        try:
            self.vm.run_service_for_stdio("qubes.SetGuiMode",
                                          input=b'FULLSCREEN')
        except (qubesadmin.exc.QubesException,
                subprocess.CalledProcessError) as ex:
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Failed to set fullscreen mode"),
                self.tr("Error occurred: {}".format(str(ex))))

    def __apply_advanced_tab__(self):
        msg = []

        # mem/cpu
        try:
            if self.init_mem.isEnabled() and \
                    self.init_mem.value() != int(self.vm.memory):
                self.vm.memory = self.init_mem.value()

            curr_maxmem = int(getattr(self.vm, 'maxmem', 0))

            if not self.include_in_balancing.isChecked():
                maxmem = 0
            else:
                maxmem = self.max_mem_size.value()

            if maxmem != curr_maxmem:
                if curr_maxmem > 0:
                    self.vm.features['qubesmanager.maxmem_value'] = curr_maxmem
                if maxmem == 0 or self.max_mem_size.isEnabled():
                    self.vm.maxmem = maxmem

            if self.vcpus.isEnabled() and \
                    self.vcpus.value() != int(self.vm.vcpus):
                self.vm.vcpus = self.vcpus.value()

        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        # in case VM is not Linux
        if hasattr(self.vm, "kernel"):
            try:
                if utils.did_widget_selection_change(self.kernel):
                    self.vm.kernel = self.kernel.currentData()
                if utils.did_widget_selection_change(self.bootmode):
                    self.vm.bootmode = self.bootmode.currentData()
                if hasattr(self.vm, "appvm_default_bootmode"):
                    if utils.did_widget_selection_change(
                        self.appvm_default_bootmode):
                        self.vm.appvm_default_bootmode \
                            = self.appvm_default_bootmode.currentData()
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        # vm default_dispvm changed
        try:
            if utils.did_widget_selection_change(self.default_dispvm):
                self.vm.default_dispvm = self.default_dispvm.currentData()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))
        try:
            if utils.did_widget_selection_change(self.virt_mode):
                self.vm.virt_mode = self.virt_mode.currentData()
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
            if self.run_in_debug_mode.isEnabled():
                if self.vm.debug != self.run_in_debug_mode.isChecked():
                    self.vm.debug = self.run_in_debug_mode.isChecked()
        except qubesadmin.exc.QubesException as ex:
            msg.append(str(ex))

        if self.allow_fullscreen_initial !=\
                self.allow_fullscreen.currentIndex():
            try:
                if self.allow_fullscreen.currentData() is None:
                    del self.vm.features['gui-allow-fullscreen']
                else:
                    self.vm.features['gui-allow-fullscreen'] = \
                        self.allow_fullscreen.currentData()
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        if self.allow_utf8_initial !=\
                self.allow_utf8.currentIndex():
            try:
                if self.allow_utf8.currentData() is None:
                    del self.vm.features['gui-allow-utf8-titles']
                else:
                    self.vm.features['gui-allow-utf8-titles'] = \
                        self.allow_utf8.currentData()
            except qubesadmin.exc.QubesException as ex:
                msg.append(str(ex))

        return msg

    def include_in_balancing_changed(self, state):
        if self.dev_list.selected_list.count() > 0:
            if state == ui_settingsdlg.QtCore.Qt.CheckState.Checked:
                self.dmm_warning_adv.show()
                self.dmm_warning_dev.show()
            else:
                self.dmm_warning_adv.hide()
                self.dmm_warning_dev.hide()
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())
        if self.include_in_balancing.isChecked():
            self.check_mem_changes()

    def boot_from_cdrom_button_pressed(self):
        boot_dialog = bootfromdevice.VMBootFromDeviceWindow(
                vm=self.vm.name, qapp=self.qapp, qubesapp=self.qubesapp,
                parent=self)
        if boot_dialog.exec():
            self.save_and_apply()
            qvm_start.main(
                    ['--cdrom', boot_dialog.cdrom_location, self.vm.name])

    def virt_mode_changed(self, new_idx):  # pylint: disable=unused-argument
        self.update_pv_warning()
        self.update_pvh_dont_support_devs()
        self.update_pvh_kernel_ver_warning()

    def update_pv_warning(self):
        if self.virt_mode.currentData() == 'pv':
            self.pv_warning.show()
        else:
            self.pv_warning.hide()

    def update_virt_mode_list(self):
        choices = [('HVM', 'hvm'),
                   ('PV', 'pv')]

        if hasattr(self, "dev_list"):
            devs_attached = self.dev_list.selected_list.count() != 0
        else:
            try:
                devs_attached = bool(list(
                    self.vm.devices['pci'].get_assigned_devices(
                        required_only=True))
                )
            except qubesadmin.exc.QubesException:
                devs_attached = False

        if devs_attached:
            self.pvh_mode_hidden.show()
        else:
            choices.insert(0, ('PVH', 'pvh'))
            self.pvh_mode_hidden.hide()

        old_mode = self.virt_mode.currentData()
        if old_mode:
            self.virt_mode.currentIndexChanged.disconnect()

        # due to how virtualization mode has uniquely different displayed and
        # actual name of the default value, I will add it manually
        try:
            choices.insert(0, (
                "default ({})".format(
                    self.vm.property_get_default('virt_mode').upper()),
                qubesadmin.DEFAULT))
        except qubesadmin.exc.QubesException:
            choices.insert(0,
                           ("default ({SYSTEM DEFAULT})", qubesadmin.DEFAULT))

        try:
            utils.initialize_widget_for_property(
                widget=self.virt_mode,
                choices=choices,
                holder=self.vm,
                property_name='virt_mode')
        except qubesadmin.exc.QubesDaemonAccessError:
            self.virt_mode.setEnabled(False)

        if self.virt_mode.isEnabled() and old_mode is not None:
            self.virt_mode.setCurrentIndex(self.virt_mode.findData(old_mode))

        self.virt_mode.currentIndexChanged.connect(self.virt_mode_changed)

        self.update_pv_warning()
        self.update_pvh_kernel_ver_warning()

    def update_pvh_kernel_ver_warning(self):
        if self.virt_mode.currentData() != 'pvh':
            self.pvh_kernel_version_warning.hide()
            return

        kernel = self.kernel.currentData()

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
            name = getattr(self.vm.app, 'default_kernel', None)

        m = re.search(r'(\d+)\.(\d+)', name)

        if m is None:
            return False

        return (int(m.group(1)), int(m.group(2))) >= (4, 11)

    ######## devices tab
    def __init_devices_tab__(self):
        self.dev_list = multiselectwidget.MultiSelectWidget(self)
        self.dev_list.change_labels(
            available="Available devices",
            selected="Devices always connected to this qube")
        self.dev_list.add_all_button.setVisible(False)
        self.devices_layout.addWidget(self.dev_list)

        try:
            dom0_devs = \
                list(self.vm.app.domains['dom0'].
                     devices['pci'].get_exposed_devices())
            attached = list(
                self.vm.devices['pci'].get_assigned_devices(required_only=True))
        except qubesadmin.exc.QubesException:
            # no permission to access devices
            self.tabWidget.setTabEnabled(self.tabs_indices['devices'], False)
            return

        # pylint: disable=too-few-public-methods
        class DevListWidgetItem(QtWidgets.QListWidgetItem):
            def __init__(self, dev, unknown=False, parent=None):
                super().__init__(parent)
                name = dev.port_id.replace('_', ":") + ' ' + dev.description
                if unknown:
                    name += ' (unknown)'
                self.setText(name)
                self.dev = dev

        for dev in dom0_devs:
            if any(attached_dev.matches(dev) for attached_dev in attached):
                self.dev_list.selected_list.addItem(DevListWidgetItem(dev))
            else:
                self.dev_list.available_list.addItem(DevListWidgetItem(dev))
        for ass in attached:
            if not any(ass.matches(dev) for dev in dom0_devs):
                self.dev_list.selected_list.addItem(
                    DevListWidgetItem(ass.device, unknown=True))

        if self.dev_list.selected_list.count() > 0\
                and self.include_in_balancing.isChecked():
            self.dmm_warning_adv.show()
            self.dmm_warning_dev.show()
        else:
            self.dmm_warning_adv.hide()
            self.dmm_warning_dev.hide()

        if utils.is_running(self.vm, False):
            self.dev_list.setEnabled(False)
            self.turn_off_vm_to_modify_devs.setVisible(True)
            self.no_strict_reset_button.setEnabled(False)
        else:
            self.dev_list.setEnabled(True)
            self.turn_off_vm_to_modify_devs.setVisible(False)

        self.update_pvh_dont_support_devs()

        self.dev_list.setEnabled(not utils.is_running(self.vm, False))

    def __apply_devices_tab__(self):
        msg = []

        if not self.tabWidget.isTabEnabled(self.tabs_indices['devices']):
            return msg

        try:
            old_devs = list(
                self.vm.devices['pci'].get_assigned_devices(required_only=True))

            new_devs = [self.dev_list.selected_list.item(i).dev
                        for i in range(self.dev_list.selected_list.count())]

            for dev in new_devs:
                old_assignments = [old for old in old_devs
                                   if old.matches(dev)]
                if not old_assignments:
                    options = {}
                    if dev.port_id in self.new_strict_reset_list:
                        options['no-strict-reset'] = True
                    ass = device_protocol.DeviceAssignment.new(
                        backend_domain=self.vm.app.domains['dom0'],
                        port_id=dev.port_id,
                        devclass='pci',
                        mode='required',
                        options=options,
                    )
                    self.vm.devices['pci'].assign(ass)
                elif (dev.port_id in self.current_strict_reset_list) != \
                        (dev.port_id in self.new_strict_reset_list):
                    current_assignment = old_assignments[0]
                    self.vm.devices['pci'].unassign(current_assignment)

                    current_assignment.options['no-strict-reset'] = \
                        dev.port_id in self.new_strict_reset_list

                    self.vm.devices['pci'].assign(current_assignment)

            for ass in self.vm.devices['pci'].get_assigned_devices(
                    required_only=True):
                if ass.device not in new_devs:
                    self.vm.devices['pci'].unassign(ass)

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
        # this is the easiest way to check for both normal 'PVH' and
        # default (PVH) options
        if 'PVH' in self.virt_mode.currentText().upper():
            self.dev_list.setEnabled(False)
            self.pvh_dont_support_devs.setVisible(True)
        else:
            self.dev_list.setEnabled(True)
            self.pvh_dont_support_devs.setVisible(False)

    def define_strict_reset_devices(self):
        for assignment in self.vm.devices['pci'].get_assigned_devices(
                required_only=True):
            if assignment.options.get('no-strict-reset', False):
                self.current_strict_reset_list.append(
                    assignment.port_id.replace('_', ':'))
        self.new_strict_reset_list = self.current_strict_reset_list.copy()

    def strict_reset_button_pressed(self):
        device_list_window = device_list.PCIDeviceListWindow(
            vm=self.vm, qapp=self.qapp, dev_list=self.dev_list,
            no_strict_reset_list=self.new_strict_reset_list, parent=self)
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
        self.refresh_apps_button.setText(self.tr('Refresh applications'))

    def template_apps_change(self):
        if self.tabWidget.isTabEnabled(self.tabs_indices["applications"]):
            self.app_list_manager.fill_apps_list(
                template=self.template_name.currentData())
            # add a label to show
            self.warn_template_missing_apps.setVisible(
                self.app_list_manager.has_missing)

    ######## services tab

    def __init_services_tab__(self):
        self.new_srv_dict = {}
        try:
            for feature in self.vm.features:
                if not feature.startswith(SERVICE_PREFIX) or \
                        feature in INTERNAL_SERVICE_FEATURES:
                    continue
                service = feature[len(SERVICE_PREFIX):]
                item = QtWidgets.QListWidgetItem(service)
                item.setCheckState(
                    ui_settingsdlg.QtCore.Qt.CheckState.Checked
                    if self.vm.features[feature]
                    else ui_settingsdlg.QtCore.Qt.CheckState.Unchecked)
                self.services_list.addItem(item)
                self.new_srv_dict[service] = self.vm.features[feature]
        except qubesadmin.exc.QubesDaemonAccessError:
            self.tabWidget.setTabEnabled(self.tabs_indices["services"], False)
            return

        self.service_line_edit.addItem("")

        supported_services = set()

        for feature in self.vm.features:
            if feature.startswith(SUPPORTED_SERVICE_PREFIX) and \
                    feature not in INTERNAL_SUPPORTED_FEATURES:
                supported_services.add(feature[len(SUPPORTED_SERVICE_PREFIX):])
        if getattr(self.vm, "template", None):
            try:
                for feature in self.vm.template.features:
                    if feature.startswith(SUPPORTED_SERVICE_PREFIX) and \
                            feature not in INTERNAL_SUPPORTED_FEATURES:
                        supported_services.add(
                            feature[len(SUPPORTED_SERVICE_PREFIX):])
            except qubesadmin.exc.QubesDaemonAccessError:
                pass

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
            item.setCheckState(ui_settingsdlg.QtCore.Qt.CheckState.Checked)
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

        if not self.tabWidget.isTabEnabled(self.tabs_indices['services']):
            return msg

        try:
            for i in range(self.services_list.count()):
                item = self.services_list.item(i)
                self.new_srv_dict[str(item.text())] = \
                    (item.checkState() ==
                     QtCore.Qt.CheckState.Checked)

            for service, v in self.new_srv_dict.items():
                feature = SERVICE_PREFIX + service
                val = '1' if v else ''
                if val != self.vm.features.get(feature, object()):
                    self.vm.features[feature] = val

            for feature in self.vm.features:
                if not feature.startswith(SERVICE_PREFIX) or \
                        feature in INTERNAL_SERVICE_FEATURES:
                    continue
                service = feature[len(SERVICE_PREFIX):]
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
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.rulesTreeView.header().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.set_allow(model.allow)
        if model.temp_full_access_expire_time:
            self.temp_full_access.setChecked(True)
            expire_time = model.temp_full_access_expire_time - \
                datetime.datetime.now().timestamp()
            self.temp_full_access_time.setValue(int(expire_time / 60))

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
        dialog = firewall.NewFwRuleDlg(parent=self)
        self.fw_model.run_rule_dialog(dialog)

    def edit_rule_button_pressed(self):

        selected = self.rulesTreeView.selectedIndexes()

        if selected:
            dialog = firewall.NewFwRuleDlg(parent=self)
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
    if vm.klass == 'AdminVM':
        print("This tool cannot be used to change properties of an "
              f"AdminVM ({vm.name}).")
        print("You can use command-line tools such as qvm-prefs "
              "and qvm-features to change properties of an AdminVM")
        return 1

    utils.run_synchronous(functools.partial(VMSettingsWindow, vm.name,
                                            args.tab))


if __name__ == "__main__":
    sys.exit(main())

# vim:sw=4:et:
