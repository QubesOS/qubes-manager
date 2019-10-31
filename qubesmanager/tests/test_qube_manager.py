#!/usr/bin/python3
#
# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2016 Marta Marczykowska-Górecka
#                                       <marmarta@invisiblethingslab.com>
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
import asyncio
import contextlib
import logging.handlers
import sys
import unittest
import unittest.mock

import gc
import subprocess
import datetime
import time

import quamash
from PyQt4 import QtGui, QtTest, QtCore
from qubesadmin import Qubes, events, exc
import qubesmanager.qube_manager as qube_manager


class QubeManagerTest(unittest.TestCase):
    def setUp(self):
        super(QubeManagerTest, self).setUp()

        self.mock_qprogress = unittest.mock.patch('PyQt4.QtGui.QProgressDialog')
        self.mock_qprogress.start()

        self.addCleanup(self.mock_qprogress.stop)

        self.qapp = Qubes()
        self.qtapp = QtGui.QApplication(["test", "-style", "cleanlooks"])
        self.dispatcher = events.EventsDispatcher(self.qapp)

        self.loop = quamash.QEventLoop(self.qtapp)

        self.dialog = qube_manager.VmManagerWindow(
            self.qtapp, self.qapp, self.dispatcher)

    def tearDown(self):
        # process any pending events before destroying the object
        self.qtapp.processEvents()

        # queue destroying the QApplication object, do that for any other QT
        # related objects here too
        self.qtapp.deleteLater()
        self.dialog.deleteLater()

        # process any pending events (other than just queued destroy),
        # just in case
        self.qtapp.processEvents()

        # execute main loop, which will process all events, _
        # including just queued destroy_
        self.loop.run_until_complete(asyncio.sleep(0))

        # at this point it QT objects are destroyed, cleanup all remaining
        # references;
        # del other QT object here too
        self.loop.close()
        del self.dialog
        del self.qtapp
        del self.loop
        gc.collect()
        super(QubeManagerTest, self).tearDown()

    def test_000_window_loads(self):
        self.assertTrue(self.dialog.table is not None, "Window did not load")

    def test_001_correct_vms_listed(self):
        vms_in_table = []

        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm
            self.assertIsNotNone(vm)
            vms_in_table.append(vm.name)

            # check that name is listed correctly
            name_item = self._get_table_item(row, "Name")
            self.assertEqual(name_item.text(), vm.name,
                             "Incorrect VM name for {}".format(vm.name))

        actual_vms = [vm.name for vm in self.qapp.domains]

        self.assertEqual(len(vms_in_table), len(actual_vms),
                         "Incorrect number of VMs loaded")
        self.assertListEqual(sorted(vms_in_table), sorted(actual_vms),
                             "Incorrect VMs loaded")

    def test_002_correct_template_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm
            # check that template is listed correctly
            template_item = self._get_table_item(row, "Template")
            if getattr(vm, "template", None):
                self.assertEqual(vm.template,
                                 template_item.text(),
                                 "Incorrect template for {}".format(vm.name))
            else:
                self.assertEqual(vm.klass, template_item.text(),
                                 "Incorrect class for {}".format(vm.name))

    def test_003_correct_netvm_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            # check that netvm is listed correctly
            netvm_item = self._get_table_item(row, "NetVM")
            netvm_value = getattr(vm, "netvm", None)
            netvm_value = "n/a" if not netvm_value else netvm_value
            if netvm_value and hasattr(vm, "netvm") \
                    and vm.property_is_default("netvm"):
                netvm_value = "default ({})".format(netvm_value)

            self.assertEqual(netvm_value,
                             netvm_item.text(),
                             "Incorrect netvm for {}".format(vm.name))

    def test_004_correct_disk_usage_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            size_item = self._get_table_item(row, "Size")
            if vm.klass == 'AdminVM':
                size_value = "n/a"
            else:
                size_value = round(vm.get_disk_utilization() / (1024 * 1024), 2)
                size_value = str(size_value) + " MiB"

            self.assertEqual(size_value,
                             size_item.text(),
                             "Incorrect size for {}".format(vm.name))

    def test_005_correct_internal_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            internal_item = self._get_table_item(row, "Internal")
            internal_value = "Yes" if vm.features.get('internal', False) else ""

            self.assertEqual(internal_item.text(), internal_value,
                             "Incorrect internal value for {}".format(vm.name))

    def test_006_correct_ip_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            ip_item = self._get_table_item(row, "IP")
            if hasattr(vm, 'ip'):
                ip_value = getattr(vm, 'ip')
                ip_value = "" if ip_value is None else ip_value
            else:
                ip_value = "n/a"

            self.assertEqual(ip_value, ip_item.text(),
                             "Incorrect ip value for {}".format(vm.name))

    def test_007_incl_in_backups_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            incl_backups_item = self._get_table_item(row, "Include in backups")
            incl_backups_value = getattr(vm, 'include_in_backups', False)
            incl_backups_value = "Yes" if incl_backups_value else ""

            self.assertEqual(
                incl_backups_value, incl_backups_item.text(),
                "Incorrect include in backups value for {}".format(vm.name))

    def test_008_last_backup_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            last_backup_item = self._get_table_item(row, "Last backup")
            last_backup_value = getattr(vm, 'backup_timestamp', None)

            if last_backup_value:
                last_backup_value = str(
                    datetime.datetime.fromtimestamp(last_backup_value))
            else:
                last_backup_value = ""

            self.assertEqual(
                last_backup_value, last_backup_item.text(),
                "Incorrect last backup value for {}".format(vm.name))

    def test_009_def_dispvm_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            def_dispvm_item = self._get_table_item(row, "Default DispVM")
            if vm.property_is_default("default_dispvm"):
                def_dispvm_value = "default ({})".format(
                    self.qapp.default_dispvm)
            else:
                def_dispvm_value = getattr(vm, "default_dispvm", None)

            self.assertEqual(
                str(def_dispvm_value), def_dispvm_item.text(),
                "Incorrect default dispvm value for {}".format(vm.name))

    def test_010_is_dvm_template_listed(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            is_dvm_template_item = self._get_table_item(row, "Is DVM Template")
            is_dvm_template_value = "Yes" if \
                getattr(vm, "template_for_dispvms", False) else ""

            self.assertEqual(
                is_dvm_template_value, is_dvm_template_item.text(),
                "Incorrect is DVM template value for {}".format(vm.name))

    def test_011_is_label_correct(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            label_item = self._get_table_item(row, "Label")

            self.assertEqual(label_item.icon_path, vm.label.icon)

    def test_012_is_state_correct(self):
        for row in range(self.dialog.table.rowCount()):
            vm = self._get_table_item(row, "Name").vm

            state_item = self._get_table_item(row, "State")

            # this should not be done like that in table_widgets
            displayed_power_state = state_item.on_icon.status

            if vm.is_running():
                correct_power_state = 3
            else:
                correct_power_state = 0

            self.assertEqual(
                displayed_power_state, correct_power_state,
                "Wrong power state displayed for {}".format(vm.name))

    def test_013_incorrect_settings_file(self):
        mock_settings = unittest.mock.MagicMock(spec=QtCore.QSettings)

        settings_result_dict = {"view/sort_column": "Cthulhu",
                                "view/sort_order": "Fhtagn",
                                "view/menubar_visible": "R'lyeh"
                                }

        mock_settings.side_effect = (
            lambda x, *args, **kwargs: settings_result_dict.get(x))

        with unittest.mock.patch('PyQt4.QtCore.QSettings.value', mock_settings),\
                unittest.mock.patch('PyQt4.QtGui.QMessageBox.warning')\
                as mock_warning:
            self.dialog = qube_manager.VmManagerWindow(
                self.qtapp, self.qapp, self.dispatcher)
            self.assertEqual(mock_warning.call_count, 1)

    def test_100_sorting(self):

        self.dialog.table.sortByColumn(self.dialog.columns_indices["Template"])
        self.__check_sorting("Template")

        self.dialog.table.sortByColumn(self.dialog.columns_indices["Name"])
        self.__check_sorting("Name")

    @unittest.mock.patch('qubesmanager.qube_manager.QtCore.QSettings.setValue')
    @unittest.mock.patch('qubesmanager.qube_manager.QtCore.QSettings.sync')
    def test_101_hide_column(self, mock_sync, mock_settings):
        self.dialog.action_is_dvm_template.trigger()
        mock_settings.assert_called_with('columns/Is DVM Template', False)
        self.assertEqual(mock_sync.call_count, 1, "Hidden column not synced")

        self.dialog.action_is_dvm_template.trigger()
        mock_settings.assert_called_with('columns/Is DVM Template', True)
        self.assertEqual(mock_sync.call_count, 2, "Hidden column not synced")

    @unittest.mock.patch('qubesmanager.settings.VMSettingsWindow')
    def test_200_vm_open_settings(self, mock_window):
        selected_vm = self._select_non_admin_vm()
        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")
        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_settings)
        QtTest.QTest.mouseClick(widget,
                                QtCore.Qt.LeftButton)
        mock_window.assert_called_once_with(
            selected_vm, self.qtapp, "basic")

    def test_201_vm_open_settings_admin(self):
        self._select_admin_vm()

        self.assertFalse(self.dialog.action_settings.isEnabled(),
                         "Settings not disabled for admin VM")
        self.assertFalse(self.dialog.action_editfwrules.isEnabled(),
                         "Settings not disabled for admin VM")
        self.assertFalse(self.dialog.action_appmenus.isEnabled(),
                         "Settings not disabled for admin VM")

    @unittest.mock.patch('qubesmanager.settings.VMSettingsWindow')
    def test_202_vm_open_firewall(self, mock_window):
        selected_vm = self._select_non_admin_vm()
        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")
        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_editfwrules)
        QtTest.QTest.mouseClick(widget,
                                QtCore.Qt.LeftButton)
        mock_window.assert_called_once_with(
            selected_vm, self.qtapp, "firewall")

    @unittest.mock.patch('qubesmanager.settings.VMSettingsWindow')
    def test_203_vm_open_apps(self, mock_window):
        selected_vm = self._select_non_admin_vm()
        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")
        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_appmenus)
        QtTest.QTest.mouseClick(widget,
                                QtCore.Qt.LeftButton)
        mock_window.assert_called_once_with(
            selected_vm, self.qtapp, "applications")

    def test_204_vm_keyboard(self):
        selected_vm = self._select_non_admin_vm(running=True)
        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")
        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_set_keyboard_layout)
        with unittest.mock.patch.object(selected_vm, 'run') as mock_run:
            QtTest.QTest.mouseClick(widget,
                                    QtCore.Qt.LeftButton)
            mock_run.assert_called_once_with("qubes-change-keyboard-layout")

    def test_205_vm_keyboard_not_running(self):
        selected_vm = self._select_non_admin_vm(running=False)
        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")
        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_set_keyboard_layout)
        with unittest.mock.patch.object(selected_vm, 'run') as mock_run:
            QtTest.QTest.mouseClick(widget,
                                    QtCore.Qt.LeftButton)
            self.assertEqual(mock_run.call_count, 0,
                             "Keyboard change called on a halted VM")

    def test_206_dom0_keyboard(self):
        self._select_admin_vm()

        self.assertFalse(self.dialog.action_set_keyboard_layout.isEnabled())

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    def test_207_update_vm_not_running(self, _):
        selected_vm = self._select_templatevm(running=False)
        self.assertIsNotNone(selected_vm, "No valid template VM found")

        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_updatevm)

        with unittest.mock.patch('qubesmanager.qube_manager.UpdateVMThread') \
                as mock_update:
            QtTest.QTest.mouseClick(widget,
                                    QtCore.Qt.LeftButton)
            mock_update.assert_called_once_with(selected_vm)
            mock_update().start.assert_called_once_with()

    def test_208_update_vm_admin(self):
        selected_vm = self._select_admin_vm()
        self.assertIsNotNone(selected_vm, "No valid admin VM found")

        widget = self.dialog.toolbar.widgetForAction(
            self.dialog.action_updatevm)

        with unittest.mock.patch('qubesmanager.qube_manager.UpdateVMThread') \
                as mock_update:
            QtTest.QTest.mouseClick(widget,
                                    QtCore.Qt.LeftButton)
            mock_update.assert_called_once_with(selected_vm)
            mock_update().start.assert_called_once_with()

    @unittest.mock.patch("PyQt4.QtGui.QInputDialog.getText",
                         return_value=("command to run", True))
    def test_209_run_command_in_vm(self, _):
        selected_vm = self._select_non_admin_vm()

        self.assertIsNotNone(selected_vm, "No valid non-admin VM found")

        with unittest.mock.patch('qubesmanager.qube_manager.RunCommandThread') \
                as mock_thread:
            self.dialog.action_run_command_in_vm.trigger()
            mock_thread.assert_called_once_with(selected_vm, "command to run")
            mock_thread().finished.connect.assert_called_once_with(
                self.dialog.clear_threads)
            mock_thread().start.assert_called_once_with()

    def test_210_run_command_in_adminvm(self):
        self._select_admin_vm()

        self.assertFalse(self.dialog.action_run_command_in_vm.isEnabled(),
                         "Should not be able to run commands for dom0")

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.warning")
    def test_211_pausevm(self, mock_warn):
        selected_vm = self._select_non_admin_vm(running=True)

        self.assertTrue(self.dialog.action_pausevm.isEnabled(),
                        "Pause not enabled for a running VM")

        with unittest.mock.patch.object(selected_vm, 'pause') as mock_pause:
            self.dialog.action_pausevm.trigger()
            mock_pause.assert_called_once_with()

            mock_pause.side_effect = exc.QubesException('Error')
            self.dialog.action_pausevm.trigger()
            self.assertEqual(mock_warn.call_count, 1)

    def test_212_resumevm(self):
        selected_vm = self._select_non_admin_vm(running=False)

        with unittest.mock.patch.object(selected_vm, 'get_power_state')\
                as mock_state, \
                unittest.mock.patch.object(selected_vm, 'unpause')\
                as mock_unpause:
            mock_state.return_value = 'Paused'
            self.dialog.action_resumevm.trigger()
            mock_unpause.assert_called_once_with()

        with unittest.mock.patch('qubesmanager.qube_manager.StartVMThread') \
                as mock_thread:
            self.dialog.action_resumevm.trigger()
            mock_thread.assert_called_once_with(selected_vm)
            mock_thread().finished.connect.assert_called_once_with(
                self.dialog.clear_threads)
            mock_thread().start.assert_called_once_with()

    def test_213_resume_running_vm(self):
        self._select_non_admin_vm(running=True)
        self.assertFalse(self.dialog.action_resumevm.isEnabled())

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    @unittest.mock.patch('PyQt4.QtCore.QTimer.singleShot')
    @unittest.mock.patch('qubesmanager.qube_manager.VmShutdownMonitor')
    def test_214_shutdownvm(self, mock_monitor, mock_timer, _):
        selected_vm = self._select_non_admin_vm(running=True)

        with unittest.mock.patch.object(selected_vm, 'shutdown')\
                as mock_shutdown:
            self.dialog.action_shutdownvm.trigger()
            mock_shutdown.assert_called_once_with()
            mock_monitor.assert_called_once_with(
                selected_vm,
                unittest.mock.ANY, unittest.mock.ANY,
                unittest.mock.ANY, unittest.mock.ANY)
            mock_timer.assert_called_once_with(unittest.mock.ANY,
                                               unittest.mock.ANY)

    def test_215_shutdown_halted_vm(self):
        self._select_non_admin_vm(running=False)

        self.assertFalse(self.dialog.action_shutdownvm.isEnabled())

    @unittest.mock.patch('qubesmanager.create_new_vm.NewVmDlg')
    def test_216_create_vm(self, mock_new_vm):
        action = self.dialog.action_createvm
        self.assertTrue(action.isEnabled())

        action.trigger()

        self.assertEqual(mock_new_vm.call_count, 1,
                         "Create New VM window did not appear")

    def test_217_remove_admin_vm(self):
        self._select_admin_vm()

        self.assertFalse(self.dialog.action_removevm.isEnabled())

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox")
    @unittest.mock.patch('qubesadmin.utils.vm_dependencies')
    def test_218_remove_vm_dependencies(self, mock_dependencies, mock_msgbox):
        action = self.dialog.action_removevm

        mock_vm = unittest.mock.Mock(spec=['name'],
                                     **{'name.return_value': 'testvm'})
        mock_dependencies.return_value = [(mock_vm, "test_prop")]

        action.trigger()
        mock_msgbox().show.assert_called_with()

    @unittest.mock.patch('PyQt4.QtGui.QMessageBox.warning')
    @unittest.mock.patch("PyQt4.QtGui.QInputDialog.getText")
    @unittest.mock.patch('qubesadmin.utils.vm_dependencies')
    def test_219_remove_vm_no_depencies(
            self, mock_dependencies, mock_input, mock_warning):
        action = self.dialog.action_removevm
        selected_vm = self._select_non_admin_vm(running=False)

        # test with no dependencies
        mock_dependencies.return_value = None

        with unittest.mock.patch('qubesmanager.common_threads.RemoveVMThread')\
                as mock_thread:
            mock_input.return_value = (selected_vm.name, False)
            action.trigger()
            self.assertEqual(mock_thread.call_count, 0,
                             "VM removed despite user clicking 'cancel")

            mock_input.return_value = ("wrong_name", True)
            action.trigger()
            self.assertEqual(mock_warning.call_count, 1)
            self.assertEqual(mock_thread.call_count, 0,
                             "VM removed despite user not confirming the name")

            mock_input.return_value = (selected_vm.name, True)
            action.trigger()
            mock_thread.assert_called_once_with(selected_vm)
            mock_thread().finished.connect.assert_called_once_with(
                self.dialog.clear_threads)
            mock_thread().start.assert_called_once_with()

    def test_220_restartvm_halted_vm(self):
        self._select_non_admin_vm(running=False)
        self.assertFalse(self.dialog.action_restartvm.isEnabled())

    @unittest.mock.patch('PyQt4.QtCore.QTimer.singleShot')
    @unittest.mock.patch('qubesmanager.qube_manager.VmShutdownMonitor')
    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    def test_221_restartvm_running_vm(self, _msgbox, mock_monitor, _qtimer):
        selected_vm = self._select_non_admin_vm(running=True)

        action = self.dialog.action_restartvm

        # currently the VM is running
        with unittest.mock.patch.object(selected_vm, 'shutdown')\
                as mock_shutdown:
            action.trigger()
            mock_shutdown.assert_called_once_with()
            mock_monitor.assert_called_once_with(
                selected_vm, unittest.mock.ANY,
                unittest.mock.ANY, True, unittest.mock.ANY)

    @unittest.mock.patch('qubesmanager.qube_manager.StartVMThread')
    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    def test_222_restartvm_shutdown_meantime(self, _, mock_thread):
        selected_vm = self._select_non_admin_vm(running=True)

        action = self.dialog.action_restartvm

        # it was shutdown in the meantime
        with unittest.mock.patch.object(
                selected_vm, 'is_running', **{'return_value': False}):
            action.trigger()
            mock_thread.assert_called_once_with(selected_vm)
            mock_thread().finished.connect.assert_called_once_with(
                self.dialog.clear_threads)
            mock_thread().start.assert_called_once_with()

    @unittest.mock.patch('qubesmanager.qube_manager.UpdateVMThread')
    def test_223_updatevm_running(self, mock_thread):
        selected_vm = self._select_non_admin_vm(running=True)

        self.dialog.action_updatevm.trigger()

        mock_thread.assert_called_once_with(selected_vm)
        mock_thread().finished.connect.assert_called_once_with(
            self.dialog.clear_threads)
        mock_thread().start.assert_called_once_with()

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    @unittest.mock.patch('qubesmanager.qube_manager.UpdateVMThread')
    def test_224_updatevm_halted(self, mock_thread, _):
        selected_vm = self._select_non_admin_vm(running=False)

        self.dialog.action_updatevm.trigger()

        mock_thread.assert_called_once_with(selected_vm)
        mock_thread().finished.connect.assert_called_once_with(
            self.dialog.clear_threads)
        mock_thread().start.assert_called_once_with()

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Yes)
    def test_224_killvm(self, _):
        selected_vm = self._select_non_admin_vm(running=True)
        action = self.dialog.action_killvm

        with unittest.mock.patch.object(selected_vm, 'kill') as mock_kill:
            action.trigger()
            mock_kill.assert_called_once_with()

    @unittest.mock.patch("PyQt4.QtGui.QMessageBox.question",
                         return_value=QtGui.QMessageBox.Cancel)
    def test_225_killvm_cancel(self, _):
        selected_vm = self._select_non_admin_vm(running=True)
        action = self.dialog.action_killvm

        with unittest.mock.patch.object(selected_vm, 'kill') as mock_kill:
            action.trigger()
            self.assertEqual(mock_kill.call_count, 0,
                             "Ignored Cancel on kill VM")

    @unittest.mock.patch('qubesmanager.global_settings.GlobalSettingsWindow')
    def test_226_global_settings(self, mock_settings):
        self._select_non_admin_vm()
        self.dialog.action_global_settings.trigger()
        self.assertEqual(mock_settings.call_count, 1,
                         "Global Settings not opened")

        self._select_admin_vm()
        self.dialog.action_global_settings.trigger()
        self.assertEqual(mock_settings.call_count, 2,
                         "Global Settings not opened for the second time")

    @unittest.mock.patch('qubesmanager.backup.BackupVMsWindow')
    def test_227_backup(self, mock_backup):
        self.dialog.action_backup.trigger()
        self.assertTrue(self.dialog.action_backup.isEnabled())
        self.assertEqual(mock_backup.call_count, 1,
                         "Backup window does not appear")

    @unittest.mock.patch('qubesmanager.restore.RestoreVMsWindow')
    def test_228_restore(self, mock_restore):
        self.dialog.action_restore.trigger()
        self.assertTrue(self.dialog.action_restore.isEnabled())
        self.assertEqual(mock_restore.call_count, 1,
                         "Backup window does not appear")

    @unittest.mock.patch('qubesmanager.qube_manager.AboutDialog')
    def test_229_about_qubes(self, mock_about):
        self.assertTrue(self.dialog.action_about_qubes.isEnabled())
        self.dialog.action_about_qubes.trigger()

        self.assertEqual(
            mock_about.call_count, 1, "About window does not appear")

    def test_230_exit_action(self):
        self.assertTrue(self.dialog.action_exit.isEnabled())
        with unittest.mock.patch.object(self.dialog, 'close') as mock_close:
            self.dialog.action_exit.trigger()
            mock_close.assert_called_once_with()

    @unittest.mock.patch('subprocess.check_call')
    def test_231_template_manager(self, mock_subprocess):
        self.assertTrue(self.dialog.action_manage_templates.isEnabled())

        self.dialog.action_manage_templates.trigger()
        mock_subprocess.assert_called_once_with('qubes-template-manager')

    @unittest.mock.patch('qubesmanager.common_threads.CloneVMThread')
    @unittest.mock.patch('PyQt4.QtGui.QInputDialog.getText')
    def test_232_clonevm(self, mock_input, mock_thread):
        action = self.dialog.action_clonevm

        self._select_admin_vm()
        self.assertFalse(action.isEnabled())

        selected_vm = self._select_non_admin_vm()
        self.assertTrue(action.isEnabled())

        mock_input.return_value = (selected_vm.name + "clone1", False)
        action.trigger()
        self.assertEqual(mock_thread.call_count, 0,
                         "Ignores cancelling clone VM")

        mock_input.return_value = (selected_vm.name + "clone1", True)
        action.trigger()
        mock_thread.assert_called_once_with(selected_vm,
                                            selected_vm.name + "clone1")
        mock_thread().finished.connect.assert_called_once_with(
            self.dialog.clear_threads)
        mock_thread().start.assert_called_once_with()

    def test_233_search_action(self):
        self.qtapp.setActiveWindow(self.dialog.searchbox)
        self.dialog.action_search.trigger()
        self.assertTrue(self.dialog.searchbox.hasFocus())

        # input text
        self.dialog.searchbox.setText("sys")
        # click outside the widget
        QtTest.QTest.mouseClick(self.dialog.table, QtCore.Qt.LeftButton)
        # click the widget, check if it is correctly activated and the whole
        # text was selected
        QtTest.QTest.mouseClick(self.dialog.searchbox, QtCore.Qt.LeftButton)
        self.assertTrue(self.dialog.searchbox.hasFocus())
        self.assertEqual(self.dialog.searchbox.selectedText(), "sys")

    def test_234_searchbox(self):
        # look for sys
        self.dialog.searchbox.setText("sys")
        expected_number = \
            len([vm for vm in self.qapp.domains if "sys" in vm.name])
        actual_number = self._count_visible_table_rows()
        self.assertEqual(expected_number, actual_number,
                         "Incorrect number of vms shown for 'sys'")

        # clear search
        self.dialog.searchbox.setText("")
        expected_number = len([vm for vm in self.qapp.domains])
        actual_number = self._count_visible_table_rows()
        self.assertEqual(expected_number, actual_number,
                         "Incorrect number of vms shown for cleared search box")

    def test_235_hide_show_toolbars(self):
        with unittest.mock.patch('PyQt4.QtCore.QSettings.setValue')\
                as mock_setvalue:
            self.dialog.action_menubar.trigger()
            mock_setvalue.assert_called_with('view/menubar_visible', False)
            self.dialog.action_toolbar.trigger()
            mock_setvalue.assert_called_with('view/toolbar_visible', False)

            self.assertFalse(self.dialog.menubar.isVisible(),
                             "Menubar not hidden correctly")
            self.assertFalse(self.dialog.toolbar.isVisible(),
                             "Toolbar not hidden correctly")

    def test_236_clear_searchbox(self):
        self.dialog.searchbox.setText("text")

        self.assertEqual(self.dialog.searchbox.text(), "text")

        QtTest.QTest.keyPress(self.dialog, QtCore.Qt.Key_Escape)

        self.assertEqual(self.dialog.searchbox.text(), "",
                         "Escape failed to clear searchbox")

        expected_number = len([vm for vm in self.qapp.domains])
        actual_number = self._count_visible_table_rows()
        self.assertEqual(expected_number, actual_number,
                         "Incorrect number of vms shown for cleared search box")

    @unittest.mock.patch('PyQt4.QtGui.QMessageBox.information')
    @unittest.mock.patch('PyQt4.QtGui.QMessageBox.warning')
    def test_300_clear_threads(self, mock_warning, mock_info):
        mock_thread_finished_ok = unittest.mock.Mock(
            spec=['isFinished', 'msg', 'msg_is_success'],
            msg=None, msg_is_success=False,
            **{'isFinished.return_value': True})
        mock_thread_not_finished = unittest.mock.Mock(
            spec=['isFinished', 'msg', 'msg_is_success'],
            msg=None, msg_is_success=False,
            **{'isFinished.return_value': False})
        mock_thread_finished_error = unittest.mock.Mock(
            spec=['isFinished', 'msg', 'msg_is_success'],
            msg=("Error", "Error"), msg_is_success=False,
            **{'isFinished.return_value': True})
        mock_thread_fin_error_success = unittest.mock.Mock(
            spec=['isFinished', 'msg', 'msg_is_success'],
            msg=("Done", "Done"), msg_is_success=True,
            **{'isFinished.return_value': True})

        # single finished thread
        self.dialog.threads_list = [mock_thread_not_finished,
                                    mock_thread_finished_ok]
        self.dialog.clear_threads()
        self.assertEqual(mock_warning.call_count, 0)
        self.assertEqual(mock_info.call_count, 0)
        self.assertEqual(len(self.dialog.threads_list), 1)

        # an error thread and some in-progress ones
        self.dialog.threads_list = [mock_thread_not_finished,
                                    mock_thread_not_finished,
                                    mock_thread_finished_error]
        self.dialog.clear_threads()
        self.assertEqual(mock_warning.call_count, 1)
        self.assertEqual(mock_info.call_count, 0)
        self.assertEqual(len(self.dialog.threads_list), 2)

        # an error-success thread and some in-progress ones
        self.dialog.threads_list = [mock_thread_not_finished,
                                    mock_thread_not_finished,
                                    mock_thread_fin_error_success,
                                    mock_thread_finished_error]
        self.dialog.clear_threads()
        self.assertEqual(mock_warning.call_count, 1)
        self.assertEqual(mock_info.call_count, 1)
        self.assertEqual(len(self.dialog.threads_list), 3)

    def test_400_event_domain_added(self):
        number_of_vms = self.dialog.table.rowCount()

        self.addCleanup(subprocess.call, ["qvm-remove", "-f", "testvm"])

        self._run_command_and_process_events(
            ["qvm-create", "--label", "red", "testvm"])

        # a single row was added to the table
        self.assertEqual(self.dialog.table.rowCount(), number_of_vms + 1)

        # table contains the correct vms
        vms_in_table = self._create_set_of_current_vms()

        vms_in_system = set([vm.name for vm in self.qapp.domains])

        self.assertEqual(vms_in_table, vms_in_system, "Table not updated "
                                                      "correctly after add")

        # check if sorting works
        self.dialog.table.sortItems(self.dialog.columns_indices["Name"],
                                    QtCore.Qt.AscendingOrder)
        self.__check_sorting("Name")

        # try opening settings for the added vm
        for row in range(self.dialog.table.rowCount()):
            name = self._get_table_item(row, "Name")
            if name.text() == "testvm":
                self.dialog.table.setCurrentItem(name)
                break
        with unittest.mock.patch('qubesmanager.settings.VMSettingsWindow')\
                as mock_settings:
            self.dialog.action_settings.trigger()
            mock_settings.assert_called_once_with(
                self.qapp.domains["testvm"], self.qtapp, "basic")

    def test_401_event_domain_removed(self):
        initial_vms = self._create_set_of_current_vms()

        self._run_command_and_process_events(
            ["qvm-create", "--label", "red", "testvm"])

        current_vms = self._create_set_of_current_vms()
        self.assertEqual(len(initial_vms) + 1, len(current_vms))

        self._run_command_and_process_events(
            ["qvm-remove", "--force", "testvm"])
        current_vms = self._create_set_of_current_vms()
        self.assertEqual(initial_vms, current_vms)

        # check if sorting works
        self.dialog.table.sortItems(self.dialog.columns_indices["Name"],
                                    QtCore.Qt.AscendingOrder)
        self.__check_sorting("Name")

    def test_403_event_dispvm_added(self):
        initial_vms = self._create_set_of_current_vms()

        dispvm_template = None

        for vm in self.qapp.domains:
            if getattr(vm, "template_for_dispvms", False):
                dispvm_template = vm.name
                break
        self.assertIsNotNone(dispvm_template,
                             "Cannot find a template for dispVMs")

        # this requires very long timeout, because it takes time for the
        # dispvm to vanish
        self._run_command_and_process_events(
            ["qvm-run", "--dispvm", dispvm_template, "true"], timeout=60)

        final_vms = self._create_set_of_current_vms()

        self.assertEqual(initial_vms, final_vms,
                         "Failed handling of a created-and-removed dispvm")

    def test_404_crashing_dispvm(self):
        initial_vms = self._create_set_of_current_vms()

        dispvm_template = None

        for vm in self.qapp.domains:
            if getattr(vm, "template_for_dispvms", False):
                dispvm_template = vm.name
                break

        self.assertIsNotNone(dispvm_template,
                             "Cannot find a template for dispVMs")

        current_memory = getattr(self.qapp.domains[dispvm_template], "memory")
        self.addCleanup(
            subprocess.call,
            ["qvm-prefs", dispvm_template, "memory", str(current_memory)])
        subprocess.check_call(
            ["qvm-prefs", dispvm_template, "memory", "600000"])

        self._run_command_and_process_events(
            ["qvm-run", "--dispvm", dispvm_template, "true"], timeout=30)

        final_vms = self._create_set_of_current_vms()

        self.assertEqual(initial_vms, final_vms,
                         "Failed handling of dispvm that crashed on start")

    def test_405_prop_change_label(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        current_label_path = self._get_table_item(vm_row, "Label").icon_path

        self.addCleanup(
            subprocess.call, ["qvm-prefs", target_vm_name, "label", "blue"])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "label", "red"])

        new_label_path = self._get_table_item(vm_row, "Label").icon_path

        self.assertNotEqual(current_label_path, new_label_path,
                            "Label path did not change")
        self.assertEqual(
            new_label_path,
            self.qapp.domains[target_vm_name].label.icon,
            "Incorrect label")

    def test_406_prop_change_template(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        old_template = self._get_table_item(vm_row, "Template").text()
        new_template = None
        for vm in self.qapp.domains:
            if vm.klass == 'TemplateVM' and vm.name != old_template:
                new_template = vm.name
                break

        self.addCleanup(
            subprocess.call,
            ["qvm-prefs", target_vm_name, "template", old_template])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "template", new_template])

        self.assertNotEqual(old_template,
                            self._get_table_item(vm_row, "Template").text(),
                            "Template did not change")
        self.assertEqual(
            self._get_table_item(vm_row, "Template").text(),
            self.qapp.domains[target_vm_name].template.name,
            "Incorrect template")

    def test_407_prop_change_netvm(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        old_netvm = self._get_table_item(vm_row, "NetVM").text()
        new_netvm = None
        for vm in self.qapp.domains:
            if getattr(vm, "provides_network", False) and vm.name != old_netvm:
                new_netvm = vm.name
                break

        self.addCleanup(
            subprocess.call, ["qvm-prefs", target_vm_name, "netvm", old_netvm])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "netvm", new_netvm])

        self.assertNotEqual(old_netvm,
                            self._get_table_item(vm_row, "NetVM").text(),
                            "NetVM did not change")
        self.assertEqual(
            self._get_table_item(vm_row, "NetVM").text(),
            self.qapp.domains[target_vm_name].netvm.name,
            "Incorrect NetVM")

    @unittest.expectedFailure
    def test_408_prop_change_internal(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        self.addCleanup(subprocess.call,
                        ["qvm-features", "--unset", "work", "interal"])
        self._run_command_and_process_events(
            ["qvm-features", "work", "interal", "1"])

        self.assertEqual(
            self._get_table_item(vm_row, "Internal").text(),
            "Yes",
            "Incorrect value for internal VM")

        self._run_command_and_process_events(
            ["qvm-features", "--unset", "work", "interal"])

        self.assertEqual(
            self._get_table_item(vm_row, "Internal").text(),
            "",
            "Incorrect value for non-internal VM")

    def test_409_prop_change_ip(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        old_ip = self._get_table_item(vm_row, "IP").text()
        new_ip = old_ip.replace(".0.", ".5.")

        self.addCleanup(
            subprocess.call, ["qvm-prefs", target_vm_name, "ip", old_ip])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "ip", new_ip])

        self.assertNotEqual(old_ip,
                            self._get_table_item(vm_row, "IP").text(),
                            "IP did not change")
        self.assertEqual(
            self._get_table_item(vm_row, "IP").text(),
            self.qapp.domains[target_vm_name].ip,
            "Incorrect IP")

    def test_410_prop_change_in_backups(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        old_value = self.qapp.domains[target_vm_name].include_in_backups
        new_value = not old_value

        self.addCleanup(
            subprocess.call,
            ["qvm-prefs", target_vm_name, "include_in_backups", str(old_value)])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "include_in_backups", str(new_value)])

        self.assertEqual(
            self._get_table_item(vm_row, "Internal").text(),
            "Yes" if new_value else "",
            "Incorrect value for include_in_backups")

    def test_411_prop_change_last_backup(self):
        target_vm_name = "work"
        target_timestamp = "2015-01-01 17:00:00"
        vm_row = self._find_vm_row(target_vm_name)

        old_value = self._get_table_item(vm_row, "Last backup").text()
        new_value = datetime.datetime.strptime(
            target_timestamp, "%Y-%m-%d %H:%M:%S")

        self.addCleanup(
            subprocess.call,
            ["qvm-prefs", '-D', target_vm_name, "backup_timestamp"])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "backup_timestamp",
             str(int(new_value.timestamp()))])

        self.assertNotEqual(old_value,
                            self._get_table_item(vm_row, "Last backup").text(),
                            "Last backup date did not change")
        self.assertEqual(
            self._get_table_item(vm_row, "Last backup").text(),
            target_timestamp,
            "Incorrect Last backup date")

    def test_412_prop_change_defdispvm(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        old_default_dispvm =\
            self._get_table_item(vm_row, "Default DispVM").text()
        new_default_dispvm = None
        for vm in self.qapp.domains:
            if getattr(vm, "template_for_dispvms", False) and vm.name !=\
                    old_default_dispvm:
                new_default_dispvm = vm.name
                break

        self.addCleanup(
            subprocess.call,
            ["qvm-prefs", target_vm_name, "default_dispvm", old_default_dispvm])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "default_dispvm", new_default_dispvm])

        self.assertNotEqual(
            old_default_dispvm,
            self._get_table_item(vm_row, "Default DispVM").text(),
            "Default DispVM did not change")

        self.assertEqual(
            self._get_table_item(vm_row, "Default DispVM").text(),
            self.qapp.domains[target_vm_name].default_dispvm.name,
            "Incorrect Default DispVM")

    def test_413_prop_change_templ_disp(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        self.addCleanup(
            subprocess.call,
            ["qvm-prefs", "--default", target_vm_name, "template_for_dispvms"])
        self._run_command_and_process_events(
            ["qvm-prefs", target_vm_name, "template_for_dispvms", "True"])

        self.assertEqual(
            self._get_table_item(vm_row, "Is DVM Template").text(),
            "Yes",
            "Incorrect value for DVM Template")

        self._run_command_and_process_events(
            ["qvm-prefs", "--default", target_vm_name, "template_for_dispvms"])

        self.assertEqual(
            self._get_table_item(vm_row, "Is DVM Template").text(),
            "",
            "Incorrect value for not DVM Template")

    def test_414_vm_state_change(self):
        target_vm_name = "work"
        vm_row = self._find_vm_row(target_vm_name)

        self.assertFalse(self.qapp.domains[target_vm_name].is_running())

        self.addCleanup(
            subprocess.call,
            ["qvm-shutdown", target_vm_name])
        self._run_command_and_process_events(
            ["qvm-start", target_vm_name], timeout=20)

        status_item = self._get_table_item(vm_row, "State")

        displayed_power_state = status_item.on_icon.status

        self.assertEqual(displayed_power_state, 3,
                         "Power state failed to update on start")

        self._run_command_and_process_events(
            ["qvm-shutdown", target_vm_name], timeout=20)

        displayed_power_state = status_item.on_icon.status

        self.assertEqual(displayed_power_state, 0,
                         "Power state failed to update on shutdown")

    def test_415_template_vm_started(self):
        # check whether changing state of a template_vm causes all other
        # vms depending on it to check theirs
        target_vm_name = None
        for vm in self.qapp.domains:
            if vm.klass == 'TemplateVM':
                for vm2 in self.qapp.domains:
                    if getattr(vm2, 'template', None) == vm.name:
                        target_vm_name = vm.name
                        break
            if target_vm_name:
                break

        for i in range(self.dialog.table.rowCount()):
            self._get_table_item(i, "State").update_vm_state =\
                unittest.mock.Mock()

        self.addCleanup(
            subprocess.call,
            ["qvm-shutdown", target_vm_name])
        self._run_command_and_process_events(
            ["qvm-start", target_vm_name], timeout=20)

        for i in range(self.dialog.table.rowCount()):
            call_count = self._get_table_item(
                i, "State").update_vm_state.call_count
            if self._get_table_item(i, "Template").text() == target_vm_name:
                self.assertGreater(call_count, 0)
            elif self._get_table_item(i, "Name").text() == target_vm_name:
                self.assertGreater(call_count, 0)
            else:
                self.assertEqual(call_count, 0)

    def test_500_logs(self):
        self._select_admin_vm()

        self.assertTrue(self.dialog.logs_menu.isEnabled())

        dom0_logs = set()
        for c in self.dialog.logs_menu.actions():
            dom0_logs.add(c.text())
            self.assertIsNotNone(
                c.data(), "Empty log file found: {}".format(c.text()))
            self.assertIn("hypervisor", c.text(),
                          "Log for dom0 does not contain 'hypervisor'")

        selected_vm = self._select_non_admin_vm().name

        self.assertTrue(self.dialog.logs_menu.isEnabled())

        vm_logs = set()
        for c in self.dialog.logs_menu.actions():
            vm_logs.add(c.text())
            self.assertIsNotNone(
                c.data(),
                "Empty log file found: {}".format(c.text()))
            self.assertIn(
                selected_vm,
                c.text(),
                "Log for {} does not contain its name".format(selected_vm))

        self.assertNotEqual(dom0_logs, vm_logs,
                            "Same logs found for dom0 and non-adminVM")

    def _find_vm_row(self, vm_name):
        for row in range(self.dialog.table.rowCount()):
            name = self._get_table_item(row, "Name")
            if name.text() == vm_name:
                return row
        return None

    def _count_visible_table_rows(self):
        result = 0
        for i in range(self.dialog.table.rowCount()):
            if not self.dialog.table.isRowHidden(i):
                result += 1
        return result

    def _run_command_and_process_events(self, command, timeout=5):
        """
        helper function to run a given command and process eventsDispatcher
        events
        :param command: list of strings, containing the command and all its
        parameters
        :param timeout: default 20 seconds
        :return:
        """
        asyncio.set_event_loop(self.loop)

        future1 = asyncio.ensure_future(self.dispatcher.listen_for_events())
        future2 = asyncio.create_subprocess_exec(*command,
                                                 stdout=subprocess.DEVNULL,
                                                 stderr=subprocess.DEVNULL)

        (done, pending) = self.loop.run_until_complete(
            asyncio.wait({future1, future2}, timeout=timeout))

        for task in pending:
            with contextlib.suppress(asyncio.CancelledError):
                task.cancel()

        self.loop.call_soon(self.loop.stop)
        self.loop.run_forever()

    def _create_set_of_current_vms(self):
        result = set()
        for i in range(self.dialog.table.rowCount()):
            result.add(self._get_table_item(i, "Name").vm.name)
        return result

    def _select_admin_vm(self):
        for row in range(self.dialog.table.rowCount()):
            template = self.dialog.table.item(
                row, self.dialog.columns_indices["Template"])
            if template.text() == 'AdminVM':
                self.dialog.table.setCurrentItem(template)
                return template.vm
        return None

    def _select_non_admin_vm(self, running=None):
        for row in range(self.dialog.table.rowCount()):
            template = self.dialog.table.item(
                row, self.dialog.columns_indices["Template"])
            status = self.dialog.table.item(
                row, self.dialog.columns_indices["State"])
            if template.text() != 'AdminVM' and \
                    (running is None
                     or (running and status.on_icon.status == 3)
                     or (not running and status.on_icon.status != 3)):
                self.dialog.table.setCurrentItem(template)
                return template.vm
        return None

    def _select_templatevm(self, running=None):
        for row in range(self.dialog.table.rowCount()):
            template = self.dialog.table.item(
                row, self.dialog.columns_indices["Template"])
            status = self.dialog.table.item(
                row, self.dialog.columns_indices["State"])
            if template.text() == 'TemplateVM' and \
                    (running is None
                     or (running and status.on_icon.status == 3)
                     or (not running and status.on_icon.status != 3)):
                self.dialog.table.setCurrentItem(template)
                return template.vm
        return None

    def __check_sorting(self, column_name):
        last_text = None
        last_vm = None
        for row in range(self.dialog.table.rowCount()):

            vm = self._get_table_item(row, "Name").vm.name
            text = self._get_table_item(row, column_name).text().lower()

            if row == 0:
                self.assertEqual(vm, "dom0", "dom0 is not sorted first")
            elif last_text is None:
                last_text = text
                last_vm = vm
            else:
                if last_text == text:
                    self.assertGreater(
                        vm, last_vm,
                        "Incorrect sorting for {}".format(column_name))
                else:
                    self.assertGreater(
                        text, last_text,
                        "Incorrect sorting for {}".format(column_name))
                last_text = text
                last_vm = vm

    def _get_table_item(self, row, column_name):
        value = self.dialog.table.cellWidget(
            row, self.dialog.columns_indices[column_name])
        if not value:
            value = self.dialog.table.item(
                row, self.dialog.columns_indices[column_name])

        return value


class QubeManagerThreadTest(unittest.TestCase):
    def test_01_startvm_thread(self):
        vm = unittest.mock.Mock(spec=['start'])

        thread = qube_manager.StartVMThread(vm)
        thread.run()

        vm.start.assert_called_once_with()

    def test_02_startvm_thread_error(self):
        vm = unittest.mock.Mock(
            spec=['start'],
            **{'start.side_effect': exc.QubesException('Error')})

        thread = qube_manager.StartVMThread(vm)
        thread.run()

        self.assertIsNotNone(thread.msg)

    def test_10_run_command_thread(self):
        vm = unittest.mock.Mock(spec=['run'])

        thread = qube_manager.RunCommandThread(vm, "test_command")
        thread.run()

        vm.run.assert_called_once_with("test_command")

    def test_11_run_command_thread_error(self):
        vm = unittest.mock.Mock(spec=['run'],
                                **{'run.side_effect': ChildProcessError})

        thread = qube_manager.RunCommandThread(vm, "test_command")
        thread.run()

        self.assertIsNotNone(thread.msg)

    @unittest.mock.patch('subprocess.check_call')
    def test_20_update_vm_thread_dom0(self, check_call):
        vm = unittest.mock.Mock(spec=['qid'])
        vm.qid = 0
        thread = qube_manager.UpdateVMThread(vm)
        thread.run()

        check_call.assert_called_once_with(
            ["/usr/bin/qubes-dom0-update", "--clean", "--gui"])

    @unittest.mock.patch('builtins.open')
    @unittest.mock.patch('subprocess.call')
    def test_21_update_vm_thread_running(self, mock_call, mock_open):
        vm = unittest.mock.Mock(
            spec=['qid', 'is_running', 'run_service_for_stdio', 'run_service'],
            **{'is_running.return_value': True})

        vm.qid = 1
        vm.run_service_for_stdio.return_value = (b'changed=no\n', None)

        thread = qube_manager.UpdateVMThread(vm)

        thread.run()

        mock_open.assert_called_with(
            '/usr/libexec/qubes-manager/dsa-4371-update', 'rb')

        vm.run_service_for_stdio.assert_called_once_with(
            "qubes.VMShell", user='root', input=unittest.mock.ANY)

        vm.run_service.assert_called_once_with(
            "qubes.InstallUpdatesGUI", user="root", wait=False)

        self.assertEqual(mock_call.call_count, 0)

    @unittest.mock.patch('builtins.open')
    @unittest.mock.patch('subprocess.call')
    def test_22_update_vm_thread_not_running(self, mock_call, mock_open):
        vm = unittest.mock.Mock(
            spec=['qid', 'is_running', 'run_service_for_stdio',
                  'run_service', 'start', 'name'],
            **{'is_running.return_value': False})

        vm.qid = 1
        vm.run_service_for_stdio.return_value = (b'changed=yes\n', None)

        thread = qube_manager.UpdateVMThread(vm)
        thread.run()

        mock_open.assert_called_with(
            '/usr/libexec/qubes-manager/dsa-4371-update', 'rb')

        vm.start.assert_called_once_with()

        vm.run_service_for_stdio.assert_called_once_with(
            "qubes.VMShell", user='root', input=unittest.mock.ANY)

        vm.run_service.assert_called_once_with(
            "qubes.InstallUpdatesGUI", user="root", wait=False)

        self.assertEqual(mock_call.call_count, 1)

    @unittest.mock.patch('builtins.open')
    @unittest.mock.patch('subprocess.check_call')
    def test_23_update_vm_thread_error(self, *_args):
        vm = unittest.mock.Mock(
            spec=['qid', 'is_running'],
            **{'is_running.side_effect': ChildProcessError})

        vm.qid = 1

        thread = qube_manager.UpdateVMThread(vm)
        thread.run()

        self.assertIsNotNone(thread.msg)


class VMShutdownMonitorTest(unittest.TestCase):
    @unittest.mock.patch('PyQt4.QtGui.QMessageBox.question')
    @unittest.mock.patch('PyQt4.QtCore.QTimer')
    def test_01_vm_shutdown_correct(self, mock_timer, mock_question):
        mock_vm = unittest.mock.Mock()
        mock_vm.is_running.return_value = False

        monitor = qube_manager.VmShutdownMonitor(mock_vm)
        monitor.restart_vm_if_needed = unittest.mock.Mock()

        monitor.check_if_vm_has_shutdown()

        self.assertEqual(mock_question.call_count, 0)
        self.assertEqual(mock_timer.call_count, 0)
        monitor.restart_vm_if_needed.assert_called_once_with()

    @unittest.mock.patch('PyQt4.QtGui.QMessageBox.question',
                         return_value=1)
    @unittest.mock.patch('PyQt4.QtCore.QTimer.singleShot')
    def test_02_vm_not_shutdown_wait(self, mock_timer, mock_question):
        mock_vm = unittest.mock.Mock()
        mock_vm.is_running.return_value = True
        mock_vm.start_time = datetime.datetime.now().timestamp() - 3000

        monitor = qube_manager.VmShutdownMonitor(mock_vm, shutdown_time=1)
        time.sleep(3)

        monitor.check_if_vm_has_shutdown()

        self.assertEqual(mock_question.call_count, 1)
        self.assertEqual(mock_timer.call_count, 1)

    @unittest.mock.patch('PyQt4.QtGui.QMessageBox.question',
                         return_value=0)
    @unittest.mock.patch('PyQt4.QtCore.QTimer.singleShot')
    def test_03_vm_kill(self, mock_timer, mock_question):
        mock_vm = unittest.mock.Mock()
        mock_vm.is_running.return_value = True
        mock_vm.start_time = datetime.datetime.now().timestamp() - 3000

        monitor = qube_manager.VmShutdownMonitor(mock_vm, shutdown_time=1)
        time.sleep(3)
        monitor.restart_vm_if_needed = unittest.mock.Mock()

        monitor.check_if_vm_has_shutdown()

        self.assertEqual(mock_question.call_count, 1)
        self.assertEqual(mock_timer.call_count, 0)
        mock_vm.kill.assert_called_once_with()
        monitor.restart_vm_if_needed.assert_called_once_with()

    @unittest.mock.patch('PyQt4.QtGui.QMessageBox.question',
                         return_value=0)
    @unittest.mock.patch('PyQt4.QtCore.QTimer.singleShot')
    def test_04_check_later(self, mock_timer, mock_question):
        mock_vm = unittest.mock.Mock()
        mock_vm.is_running.return_value = True
        mock_vm.start_time = datetime.datetime.now().timestamp() - 3000

        monitor = qube_manager.VmShutdownMonitor(mock_vm, shutdown_time=3000)
        time.sleep(1)

        monitor.check_if_vm_has_shutdown()

        self.assertEqual(mock_question.call_count, 0)
        self.assertEqual(mock_timer.call_count, 1)


if __name__ == "__main__":
    ha_syslog = logging.handlers.SysLogHandler('/dev/log')
    ha_syslog.setFormatter(
        logging.Formatter('%(name)s[%(process)d]: %(message)s'))
    logging.root.addHandler(ha_syslog)
    unittest.main()
