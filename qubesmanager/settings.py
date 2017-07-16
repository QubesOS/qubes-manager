#!/usr/bin/python2
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#


import collections
import copy
import os
import os.path
import subprocess
import sys
import threading
import time
import traceback

import qubesadmin
import qubesadmin.tools

from . import utils
from . import multiselectwidget
from . import thread_monitor

from .appmenu_select import AppmenuSelectManager
from .backup_utils import get_path_for_vm
from .firewall import *

from .ui_settingsdlg import *

class VMSettingsWindow(Ui_SettingsDialog, QDialog):
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
        if self.vm.template:
            self.source_vm = self.vm.template
        else:
            self.source_vm = self.vm

        self.setupUi(self)
        self.setWindowTitle(self.tr("Settings: {vm}").format(vm=self.vm.name))
        if init_page in self.tabs_indices:
            idx = self.tabs_indices[init_page]
            assert (idx in range(self.tabWidget.count()))
            self.tabWidget.setCurrentIndex(idx)

        self.connect(self.buttonBox, SIGNAL("accepted()"), self.save_and_apply)
        self.connect(self.buttonBox, SIGNAL("rejected()"), self.reject)

        self.tabWidget.currentChanged.connect(self.current_tab_changed)

#       self.tabWidget.setTabEnabled(self.tabs_indices["firewall"], vm.is_networked() and not vm.provides_network)

        ###### basic tab
        self.__init_basic_tab__()

        ###### advanced tab
        self.__init_advanced_tab__()
        self.include_in_balancing.stateChanged.connect(self.include_in_balancing_state_changed)
        self.connect(self.init_mem, SIGNAL("editingFinished()"), self.check_mem_changes)
        self.connect(self.max_mem_size, SIGNAL("editingFinished()"), self.check_mem_changes)
        self.drive_path_button.clicked.connect(self.drive_path_button_pressed)

        ###### firewall tab
        if self.tabWidget.isTabEnabled(self.tabs_indices['firewall']):
            model = QubesFirewallRulesModel()
            model.set_vm(vm)
            self.set_fw_model(model)

            self.newRuleButton.clicked.connect(self.new_rule_button_pressed)
            self.editRuleButton.clicked.connect(self.edit_rule_button_pressed)
            self.deleteRuleButton.clicked.connect(self.delete_rule_button_pressed)
            self.policyDenyRadioButton.clicked.connect(self.policy_changed)
            self.policyAllowRadioButton.clicked.connect(self.policy_changed)

        ####### devices tab
        self.__init_devices_tab__()
        self.connect(self.dev_list, SIGNAL("selected_changed()"), self.devices_selection_changed)

        ####### services tab
        self.__init_services_tab__()
        self.add_srv_button.clicked.connect(self.__add_service__)
        self.remove_srv_button.clicked.connect(self.__remove_service__)

        ####### apps tab
        if self.tabWidget.isTabEnabled(self.tabs_indices["applications"]):
            self.app_list = multiselectwidget.MultiSelectWidget(self)
            self.apps_layout.addWidget(self.app_list)
            self.AppListManager = AppmenuSelectManager(self.vm, self.app_list)

    def reject(self):
        self.done(0)

    #needed not to close the dialog before applying changes
    def accept(self):
        pass

    def save_and_apply(self):
        t_monitor = thread_monitor.ThreadMonitor()
        thread = threading.Thread(target=self.__save_changes__, args=(t_monitor,))
        thread.daemon = True
        thread.start()

        progress = QProgressDialog(
            self.tr("Applying settings to <b>{0}</b>...").format(self.vm.name), "", 0, 0)
        progress.setCancelButton(None)
        progress.setModal(True)
        progress.show()

        while not t_monitor.is_finished():
            self.qapp.processEvents()
            time.sleep (0.1)

        progress.hide()

        if not t_monitor.success:
            QMessageBox.warning(None,
                self.tr("Error while changing settings for {0}!").format(self.vm.name),
                    self.tr("ERROR: {0}").format(t_monitor.error_msg))

        self.done(0)

    def __save_changes__(self, t_monitor):

        self.anything_changed = False

        ret = []
        try:
            ret_tmp = self.__apply_basic_tab__()
            if len(ret_tmp) > 0:
                ret += ["Basic tab:"] + ret_tmp
            ret_tmp = self.__apply_advanced_tab__()
            if len(ret_tmp) > 0:
                ret += ["Advanced tab:"] + ret_tmp
            ret_tmp = self.__apply_devices_tab__()
            if len(ret_tmp) > 0:
                ret += ["Devices tab:"] + ret_tmp
            ret_tmp = self.__apply_services_tab__()
            if len(ret_tmp) > 0:
                ret += ["Sevices tab:"] + ret_tmp
        except Exception as ex:
            ret.append(self.tr('Error while saving changes: ') + str(ex))

        try:
            if self.tabWidget.isTabEnabled(self.tabs_indices["firewall"]):
                self.fw_model.apply_rules(self.policyAllowRadioButton.isChecked(),
                        self.dnsCheckBox.isChecked(),
                        self.icmpCheckBox.isChecked(),
                        self.yumproxyCheckBox.isChecked(),
                        self.tempFullAccess.isChecked(),
                        self.tempFullAccessTime.value())
                if self.fw_model.fw_changed:
                    # might modified vm.services
                    self.anything_changed = True
        except Exception as ex:
            ret += [self.tr("Firewall tab:"), str(ex)]

        try:
            if self.tabWidget.isTabEnabled(self.tabs_indices["applications"]):
                self.AppListManager.save_appmenu_select_changes()
        except Exception as ex:
            ret += [self.tr("Applications tab:"), str(ex)]

        if len(ret) > 0 :
            t_monitor.set_error_msg('\n'.join(ret))

        utils.debug('\n'.join(ret))

        t_monitor.set_finished()

    def current_tab_changed(self, idx):
        if idx == self.tabs_indices["firewall"]:
            netvm = self.vm.netvm
            if netvm is not None and \
                    not netvm.features.check_with_template('qubes-firewall', False):
                QMessageBox.warning(None,
                    self.tr("VM configuration problem!"),
                    self.tr("The '{vm}' AppVM is network connected to "
                        "'{netvm}', which does not support firewall!<br/>"
                        "You may edit the '{vm}' VM firewall rules, but these "
                        "will not take any effect until you connect it to "
                        "a working Firewall VM.").format(
                            vm=self.vm.name, netvm=netvm.name))


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
        self.vmname.setValidator(QRegExpValidator(QRegExp("[a-zA-Z0-9-]*", Qt.CaseInsensitive), None))
        self.vmname.setEnabled(False)

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

        if isinstance(self.vm, qubesadmin.vm.AppVM):
            self.template_list, self.template_idx = utils.prepare_vm_choice(
                self.template_name,
                self.vm, 'template',
                self.vm.app.default_template,
                (lambda vm: isinstance(vm, qubesadmin.vm.TemplateVM)),
                allow_default=True, allow_none=False)
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

        #type
        self.type_label.setText(type(self.vm).__name__)

        #installed by rpm
        self.rpm_label.setText('Yes' if self.vm.installed_by_rpm else 'No')

        #networking info
        if self.vm.netvm:
            self.networking_groupbox.setEnabled(True)
            self.ip_label.setText(self.vm.ip or "none")
            self.netmask_label.setText(self.vm.visible_netmask or "none")
            self.gateway_label.setText(self.vm.visible_gateway or "none")
        else:
            self.networking_groupbox.setEnabled(False)

        #max priv storage
        self.priv_img_size = self.vm.volumes['private'].size / 10**6
        self.max_priv_storage.setMinimum(self.priv_img_size)
        self.max_priv_storage.setValue(self.priv_img_size)

        self.root_img_size = self.vm.volumes['root'].size / 10**6
        self.root_resize.setValue(self.root_img_size)
        self.root_resize.setMinimum(self.root_img_size)
#       self.root_resize.setEnabled(hasattr(self.vm, 'resize_root_img') and
#           not self.vm.template)
        self.root_resize_label.setEnabled(self.root_resize.isEnabled())

    def __apply_basic_tab__(self):
        msg = []

        #vm label changed
        try:
            if self.vmlabel.isVisible():
                if self.vmlabel.currentIndex() != self.label_idx:
                    label = self.label_list[self.vmlabel.currentIndex()]
                    self.vm.label = label
                    self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        #vm template changed
        try:
            if self.template_name.currentIndex() != self.template_idx:
                self.vm.template = \
                    self.template_list[self.template_name.currentIndex()]
                self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        #vm netvm changed
        try:
            if self.netVM.currentIndex() != self.netvm_idx:
                self.vm.netvm = self.netvm_list[self.netVM.currentIndex()]
                self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        #include in backups
        try:
            if self.vm.include_in_backups != self.include_in_backups.isChecked():
                self.vm.include_in_backups = self.include_in_backups.isChecked()
                self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        #run_in_debug_mode
        try:
            if self.run_in_debug_mode.isVisible():
                if self.vm.debug != self.run_in_debug_mode.isChecked():
                    self.vm.debug = self.run_in_debug_mode.isChecked()
                    self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        #autostart_vm
        try:
            if self.autostart_vm.isVisible():
                if self.vm.autostart != self.autostart_vm.isChecked():
                    self.vm.autostart = self.autostart_vm.isChecked()
                    self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        #max priv storage
        priv_size = self.max_priv_storage.value()
        if self.priv_img_size != priv_size:
            try:
                self.vm.volumes['private'].resize(priv_size * 10**6)
                self.anything_changed = True
            except Exception as ex:
                msg.append(str(ex))

        #max sys storage
        sys_size = self.root_resize.value()
        if self.root_img_size != sys_size:
            try:
                self.vm.volumes['root'].resize(priv_size * 10**6)
                self.anything_changed = True
            except Exception as ex:
                msg.append(str(ex))

        return msg


    def check_mem_changes(self):
        if self.max_mem_size.value() < self.init_mem.value():
            QMessageBox.warning(None,
                self.tr("Warning!"),
                self.tr("Max memory can not be less than initial memory.<br>"
                        "Setting max memory to equal initial memory."))
            self.max_mem_size.setValue(self.init_mem.value())
        # Linux specific limit: init memory must not be below max_mem_size/10.79 in order to allow scaling up to max_mem_size (or else "add_memory() failed: -17" problem)
        if self.init_mem.value() * 10 < self.max_mem_size.value():
            QMessageBox.warning(None,
                self.tr("Warning!"),
                self.tr("Initial memory can not be less than one tenth "
                        "Max memory.<br>Setting initial memory to the minimum "
                        "allowed value."))
            self.init_mem.setValue(self.max_mem_size.value() / 10)



    ######### advanced tab

    def __init_advanced_tab__(self):

        #mem/cpu
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
            self.vm.features.get('services.meminfo-writer', True))
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())

        try:
            self.root_img_path.setText('{volume.pool}:{volume.vid}'.format(
                volume=self.vm.volumes['root']))
        except AttributeError:
            self.root_img_path.setText("n/a")
        try:
            self.volatile_img_path.setText('{volume.pool}:{volume.vid}'.format(
                volume=self.vm.volumes['volatile']))
        except AttributeError:
            self.volatile_img_path.setText('n/a')
        self.private_img_path.setText('{volume.pool}:{volume.vid}'.format(
            volume=self.vm.volumes['private']))


        #kernel

        #in case VM is HVM
        if hasattr(self.vm, "kernel"):
            self.kernel_groupbox.setVisible(True)
            self.kernel_list, self.kernel_idx = utils.prepare_kernel_choice(
                self.kernel, self.vm, 'kernel',
                self.vm.app.default_kernel,
                allow_default=True, allow_none=True)
        else:
            self.kernel_groupbox.setVisible(False)

        if not hasattr(self.vm, "drive"):
            self.drive_groupbox.setVisible(False)
        else:
            self.drive_groupbox.setVisible(True)
            self.drive_groupbox.setChecked(self.vm.drive is not None)
            self.drive_running_warning.setVisible(self.vm.is_running())
            self.drive_type.addItems(["hd", "cdrom"])
            self.drive_type.setCurrentIndex(0)
            vm_list = [vm for vm in self.app.values() if not vm
                    .internal and vm.qid != self.vm.qid]
            # default to dom0 (in case of nonexisting vm already set...)
            self.drive_domain_idx = 0
            for (i, vm) in enumerate(sorted(vm_list, key=lambda v: v.name)):
                if vm.qid == 0:
                    self.drive_domain_idx = i
                self.drive_domain.insertItem(i, vm.name)

            if self.vm.drive is not None:
                (drv_type, drv_domain, drv_path) = self.vm.drive.split(":")
                if drv_type == "cdrom":
                    self.drive_type.setCurrentIndex(1)
                else:
                    self.drive_type.setCurrentIndex(0)

                for i in xrange(self.drive_domain.count()):
                    if drv_domain == self.drive_domain.itemText(i):
                        self.drive_domain_idx = i

                self.drive_path.setText(drv_path)
            self.drive_domain.setCurrentIndex(self.drive_domain_idx)

        self.other_groupbox.setVisible(False)

        if not hasattr(self.vm, 'default_dispvm'):
            self.other_groupbox.setVisible(False)
        else:
            self.other_groupbox.setVisible(True)
            self.default_dispvm_list, self.default_dispvm_idx = \
                utils.prepare_vm_choice(
                    self.default_dispvm,
                    self.vm, 'default_dispvm',
                    self.vm.app.default_dispvm,
                    (lambda vm: isinstance(vm, qubesadmin.vm.DispVM)),
                    allow_default=True, allow_none=True)

    def __apply_advanced_tab__(self):
        msg = []

        #mem/cpu
        try:
            if self.init_mem.value() != int(self.vm.memory):
                self.vm.memory = self.init_mem.value()
                self.anything_changed = True

            if self.max_mem_size.value() != int(self.vm.maxmem):
                self.vm.maxmem = self.max_mem_size.value()
                self.anything_changed = True

            if self.vcpus.value() != int(self.vm.vcpus):
                self.vm.vcpus = self.vcpus.value()
                self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        #include_in_memory_balancing applied in services tab

        #in case VM is not Linux
        if hasattr(self.vm, "kernel") and self.kernel_groupbox.isVisible():
            try:
                if self.kernel.currentIndex() != self.kernel_idx:
                    new_kernel = str(self.kernel.currentText())
                    new_kernel = new_kernel.split(' ')[0]
                    uses_default_kernel = False

                    if new_kernel == "default":
                        kernel = self.app.get_default_kernel()
                        uses_default_kernel = True
                    elif new_kernel == "none":
                        kernel = None
                    else:
                        kernel = new_kernel

                    self.vm.kernel = kernel
                    # Set self.vm.uses_default_kernel after self.vm.kernel to ensure that
                    # the correct value persists after QubesVm.kernel resets self.vm.uses_default_kernel
                    # to False.
                    self.vm.uses_default_kernel = uses_default_kernel
                    self.anything_changed = True
            except Exception as ex:
                msg.append(str(ex))

        #vm default_dispvm changed
        try:
            if self.default_dispvm.currentIndex() != self.default_dispvm_idx:
                self.vm.default_dispvm = \
                    self.default_dispvm_list[self.default_dispvm.currentIndex()]
                self.anything_changed = True
        except Exception as ex:
            msg.append(str(ex))

        return msg

    def drive_path_button_pressed(self):
        if str(self.drive_domain.currentText()) in ["dom0", "dom0 (current)"]:
            file_dialog = QFileDialog()
            file_dialog.setReadOnly(True)
            new_path = file_dialog.getOpenFileName(self, "Select drive image",
                                                   str(self.drive_path.text()))
        else:
            drv_domain = str(self.drive_domain.currentText())
            if drv_domain.count("(current)") > 0:
                drv_domain = drv_domain.split(' ')[0]
            backend_vm = self.app.get_vm_by_name(drv_domain)
            if backend_vm:
                new_path = get_path_for_vm(backend_vm, "qubes.SelectFile")
        if new_path:
            self.drive_path.setText(new_path)

    ######## devices tab
    def __init_devices_tab__(self):
        self.dev_list = multiselectwidget.MultiSelectWidget(self)
        self.dev_list.add_all_button.setVisible(False)
        self.devices_layout.addWidget(self.dev_list)

        devs = []
        lspci = subprocess.check_output(['/usr/sbin/lspci']).decode()
        for dev in lspci.splitlines():
            devs.append((dev.rstrip(), dev.split(' ')[0]))

        class DevListWidgetItem(QListWidgetItem):
            def __init__(self, name, ident, parent = None):
                super(DevListWidgetItem, self).__init__(name, parent)
                self.ident = ident
                self.Type

        persistent = [ass.ident.replace('_', ':')
            for ass in self.vm.devices['pci'].persistent()]

        for name, ident in devs:
            if ident in persistent:
                self.dev_list.selected_list.addItem(
                    DevListWidgetItem(name, ident))
            else:
                self.dev_list.available_list.addItem(
                    DevListWidgetItem(name, ident))

        if self.dev_list.selected_list.count() > 0 and self.include_in_balancing.isChecked():
            self.dmm_warning_adv.show()
            self.dmm_warning_dev.show()
        else:
            self.dmm_warning_adv.hide()
            self.dmm_warning_dev.hide()

        if self.vm.is_running():
            self.dev_list.setEnabled(False)
            self.turn_off_vm_to_modify_devs.setVisible(True)
        else:
            self.dev_list.setEnabled(True)
            self.turn_off_vm_to_modify_devs.setVisible(False)


    def __apply_devices_tab__(self):
        msg = []

        try:
            old = [ass.ident.replace('_', ':')
                for ass in self.vm.devices['pci'].persistent()]

            new = [self.dev_list.selected_list.item(i).ident
                    for i in range(self.dev_list.selected_list.count())]
            for ident in new:
                if ident not in old:
                    ass = qubesadmin.devices.DeviceAssignment(
                        self.vm.app.domains['dom0'],
                        ident.replace(':', '_'),
                        persistent=True)
                    self.vm.devices['pci'].attach(ass)
            for ass in self.vm.devices['pci'].assignments(persistent=True):
                if ass.ident.replace('_', ':') not in new:
                    self.vm.devices['pci'].detach(ass)

            self.anything_changed = True

        except Exception as ex:
            if utils.is_debug():
                traceback.print_exc()
            msg.append(str(ex))

        return msg

    def include_in_balancing_state_changed(self, state):
        for r in range (self.services_list.count()):
            item = self.services_list.item(r)
            if str(item.text()) == 'meminfo-writer':
                item.setCheckState(state)
                break

        if self.dev_list.selected_list.count() > 0:
            if state == QtCore.Qt.Checked:
                self.dmm_warning_adv.show()
                self.dmm_warning_dev.show()
            else:
                self.dmm_warning_adv.hide()
                self.dmm_warning_dev.hide()
        self.max_mem_size.setEnabled(self.include_in_balancing.isChecked())

    def devices_selection_changed(self):
        if self.include_in_balancing.isChecked():
            if self.dev_list.selected_list.count() > 0 :
                self.dmm_warning_adv.show()
                self.dmm_warning_dev.show()
            else:
                self.dmm_warning_adv.hide()
                self.dmm_warning_dev.hide()

    ######## services tab

    def __init_services_tab__(self):
        self.new_srv_dict = {}
        for feature in self.vm.features:
            if not feature.startswith('service.'):
                continue
            service = feature[len('service.'):]
            item = QListWidgetItem(service)
            item.setCheckState(QtCore.Qt.Checked
                if self.vm.features[feature] else QtCore.Qt.Unchecked)
            self.services_list.addItem(item)
            self.new_srv_dict[service] = self.vm.features[feature]

        self.connect(self.services_list, SIGNAL("itemClicked(QListWidgetItem *)"), self.services_item_clicked)

    def __add_service__(self):
        srv = str(self.service_line_edit.text()).strip()
        if srv != "":
            if srv in self.new_srv_dict:
                QMessageBox.information(None, '',
                    self.tr('Service already on the list!'))
            else:
                item = QListWidgetItem(srv)
                item.setCheckState(QtCore.Qt.Checked)
                self.services_list.addItem(item)
                self.new_srv_dict[srv] = True

    def __remove_service__(self):
        item = self.services_list.currentItem()

        if not item:
            return
        if str(item.text()) == 'meminfo-writer':
            QMessageBox.information(None,
                self.tr('Service can not be removed'),
                self.tr('Service meminfo-writer can not be removed from the list.'))
            return

        row = self.services_list.currentRow()
        item = self.services_list.takeItem(row)
        del self.new_srv_dict[str(item.text())]


    def services_item_clicked(self, item):
        if str(item.text()) == 'meminfo-writer':
            if item.checkState() == QtCore.Qt.Checked:
                if not self.include_in_balancing.isChecked():
                    self.include_in_balancing.setChecked(True)
            elif item.checkState() == QtCore.Qt.Unchecked:
                if self.include_in_balancing.isChecked():
                    self.include_in_balancing.setChecked(False)


    def __apply_services_tab__(self):
        msg = []

        try:
            for r in range(self.services_list.count()):
                item = self.services_list.item(r)
                self.new_srv_dict[str(item.text())] = (item.checkState() == QtCore.Qt.Checked)

            balancing_was_checked = self.vm.features.get('service.meminfo-writer', True)
            balancing_is_checked = self.include_in_balancing.isChecked()
            meminfo_writer_checked = self.new_srv_dict.get('meminfo-writer', True)

            if balancing_is_checked != meminfo_writer_checked:
                if balancing_is_checked != balancing_was_checked:
                    self.new_srv_dict['meminfo-writer'] = balancing_is_checked

            for service, v in self.new_srv_dict.items():
                feature = 'service.' + service
                if v != self.vm.features.get(feature, object()):
                    self.vm.features[feature] = v
                    self.anything_changed = True

            for feature in self.vm.features:
                if not feature.startswith('service.'):
                    continue
                service = feature[len('service.'):]
                if service not in self.new_srv_dict:
                    del self.vm.features[feature]
        except Exception as ex:
            msg.append(str(ex))

        return msg


    ######### firewall tab related

    def set_fw_model(self, model):
        self.fw_model = model
        self.rulesTreeView.setModel(model)
        self.rulesTreeView.header().setResizeMode(QHeaderView.ResizeToContents)
        self.rulesTreeView.header().setResizeMode(0, QHeaderView.Stretch)
        self.set_allow(model.allow)
        self.dnsCheckBox.setChecked(model.allowDns)
        self.icmpCheckBox.setChecked(model.allowIcmp)
        self.yumproxyCheckBox.setChecked(model.allowYumProxy)
        if model.tempFullAccessExpireTime:
            self.tempFullAccess.setChecked(True)
            self.tempFullAccessTime.setValue(
                (model.tempFullAccessExpireTime -
                int(datetime.datetime.now().strftime("%s")))/60)

    def set_allow(self, allow):
        self.policyAllowRadioButton.setChecked(allow)
        self.policyDenyRadioButton.setChecked(not allow)
        self.policy_changed(allow)

    def policy_changed(self, checked):
        self.tempFullAccessWidget.setEnabled(self.policyDenyRadioButton.isChecked())

    def new_rule_button_pressed(self):
        dialog = NewFwRuleDlg()
        self.run_rule_dialog(dialog)

    def edit_rule_button_pressed(self):
        dialog = NewFwRuleDlg()
        dialog.set_ok_enabled(True)
        selected = self.rulesTreeView.selectedIndexes()
        if len(selected) > 0:
            row = self.rulesTreeView.selectedIndexes().pop().row()
            address = self.fw_model.get_column_string(0, row).replace(' ', '')
            dialog.addressComboBox.setItemText(0, address)
            dialog.addressComboBox.setCurrentIndex(0)
            service = self.fw_model.get_column_string(1, row)
            if service == "any":
                service = ""
            dialog.serviceComboBox.setItemText(0, service)
            dialog.serviceComboBox.setCurrentIndex(0)
            protocol = self.fw_model.get_column_string(2, row)
            if protocol == "tcp":
                dialog.tcp_radio.setChecked(True)
            elif protocol == "udp":
                dialog.udp_radio.setChecked(True)
            else:
                dialog.any_radio.setChecked(True)

            self.run_rule_dialog(dialog, row)

    def delete_rule_button_pressed(self):
        for i in set([index.row() for index in self.rulesTreeView.selectedIndexes()]):
            self.fw_model.removeChild(i)

    def run_rule_dialog(self, dialog, row = None):
        if dialog.exec_():
            address = str(dialog.addressComboBox.currentText())
            service = str(dialog.serviceComboBox.currentText())
            port = None
            port2 = None

            unmask = address.split("/", 1)
            if len(unmask) == 2:
                address = unmask[0]
                netmask = int(unmask[1])
            else:
                netmask = 32

            if address == "*":
                address = "0.0.0.0"
                netmask = 0

            if dialog.any_radio.isChecked():
                protocol = "any"
                port = 0
            else:
                if dialog.tcp_radio.isChecked():
                    protocol = "tcp"
                elif dialog.udp_radio.isChecked():
                    protocol = "udp"
                else:
                    protocol = "any"

                try:
                    range = service.split("-", 1)
                    if len(range) == 2:
                        port = int(range[0])
                        port2 = int(range[1])
                    else:
                        port = int(service)
                except (TypeError, ValueError) as ex:
                    port = self.fw_model.get_service_port(service)

            if port is not None:
                if port2 is not None and port2 <= port:
                    QMessageBox.warning(None, self.tr("Invalid service ports range"),
                        self.tr("Port {0} is lower than port {1}.").format(
                            port2, port))
                else:
                    item = {"address": address,
                            "netmask": netmask,
                            "portBegin": port,
                            "portEnd": port2,
                            "proto": protocol,
                    }
                    if row is not None:
                        self.fw_model.setChild(row, item)
                    else:
                        self.fw_model.appendChild(item)
            else:
                QMessageBox.warning(None, self.tr("Invalid service name"),
                    self.tr("Service '{0}' is unknown.").format(service))


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception(exc_type, exc_value, exc_traceback):

    filename, line, dummy, dummy = traceback.extract_tb(exc_traceback).pop()
    filename = os.path.basename(filename)
    error = "%s: %s" % (exc_type.__name__, exc_value)

    strace = ""
    stacktrace = traceback.extract_tb(exc_traceback)
    while len(stacktrace) > 0:
        (filename, line, func, txt) = stacktrace.pop()
        strace += "----\n"
        strace += "line: %s\n" %txt
        strace += "func: %s\n" %func
        strace += "line no.: %d\n" %line
        strace += "file: %s\n" %filename

    msg_box = QMessageBox()
    msg_box.setDetailedText(strace)
    msg_box.setIcon(QMessageBox.Critical)
    msg_box.setWindowTitle("Houston, we have a problem...")
    msg_box.setText("Whoops. A critical error has occured. This is most likely a bug "
                    "in Qubes Manager.<br><br>"
                    "<b><i>%s</i></b>" % error +
                    "<br/>at line <b>%d</b><br/>of file %s.<br/><br/>"
                    % ( line, filename ))

    msg_box.exec_()


parser = qubesadmin.tools.QubesArgumentParser(vmname_nargs=1)

parser.add_argument('--tab', metavar='TAB',
    action='store',
    choices=VMSettingsWindow.tabs_indices.keys())

parser.set_defaults(
    tab='basic',
)

def main(args=None):
    global settings_window

    args = parser.parse_args(args)
    vm = args.domains.pop()

    qapp = QApplication(sys.argv)
    qapp.setOrganizationName('Invisible Things Lab')
    qapp.setOrganizationDomain("https://www.qubes-os.org/")
    qapp.setApplicationName("Qubes VM Settings")

    if not utils.is_debug():
        sys.excepthook = handle_exception

    settings_window = VMSettingsWindow(vm, qapp, args.tab)
    settings_window.show()

    qapp.exec_()
    qapp.exit()


if __name__ == "__main__":
    main()

# vim:sw=4:et:
