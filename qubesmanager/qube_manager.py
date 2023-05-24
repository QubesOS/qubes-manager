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
import subprocess
from datetime import datetime, timedelta
from functools import partial
from os import path

from qubesadmin import exc
from qubesadmin import utils
from qubesadmin.tools import qvm_start

# pylint: disable=import-error
from PyQt5.QtCore import (Qt, QAbstractTableModel, QObject, pyqtSlot, QEvent,
    QSettings, QRegExp, QSortFilterProxyModel, QSize, QPoint, QTimer)

# pylint: disable=import-error
from PyQt5.QtWidgets import (QLineEdit, QStyledItemDelegate, QToolTip,
    QMenu, QInputDialog, QMainWindow, QProgressDialog, QStyleOptionViewItem,
    QMessageBox, QShortcut)

# pylint: disable=import-error
from PyQt5.QtGui import (QIcon, QPixmap, QRegExpValidator, QFont, QColor,
                         QKeySequence)

from qubesmanager.about import AboutDialog

from . import ui_qubemanager  # pylint: disable=no-name-in-module
from . import settings
from . import global_settings
from . import restore
from . import backup
from . import create_new_vm
from . import log_dialog
from . import utils as manager_utils
from . import common_threads
from . import clone_vm


class SearchBox(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.focusing = False

    def focusInEvent(self, e):  # pylint: disable=invalid-name
        super().focusInEvent(e)
        self.selectAll()
        self.focusing = True

    def mousePressEvent(self, e):  # pylint: disable=invalid-name
        super().mousePressEvent(e)
        if self.focusing:
            self.selectAll()
            self.focusing = False

icon_size = QSize(22, 22)

# pylint: disable=invalid-name
class StateIconDelegate(QStyledItemDelegate):
    lastIndex = None
    def __init__(self):
        super().__init__()
        self.stateIcons = {
                "Running" : QIcon(":/on.png"),
                "Paused" : QIcon(":/paused.png"),
                "Suspended" : QIcon(":/paused.png"),
                "Transient" : QIcon(":/transient.png"),
                "Halting" : QIcon(":/transient.png"),
                "Dying" : QIcon(":/transient.png"),
                "Halted" : QIcon(":/off.png")
                }
        self.outdatedIcons = {
                "update" : QIcon(":/update-recommended.png"),
                "outdated" : QIcon(":/outdated.png"),
                "to-be-outdated" : QIcon(":/to-be-outdated.png"),
                }
        self.outdatedTooltips = {
                "update" : self.tr("Updates pending!"),
                "outdated" : self.tr(
                    "The qube must be restarted for its filesystem to reflect"
                    " the template's recent committed changes."),
                "to-be-outdated" : self.tr(
                    "The Template must be stopped before changes from its "
                    "current session can be picked up by this qube."),
                }

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        option = QStyleOptionViewItem(option)
        option.features |= option.HasDecoration
        widget = option.widget
        style = widget.style()
        iconRect = style.subElementRect(style.SE_ItemViewItemDecoration,
            option, widget)
        width = iconRect.width() * 3 # Nº of possible icons
        hint.setWidth(width)
        return hint

    def paint(self, qp, option, index):
        # create a new QStyleOption (*never* use the one given in arguments)
        option = QStyleOptionViewItem(option)

        widget = option.widget
        style = widget.style()

        # paint the base item (borders, gradients, selection colors, etc)
        style.drawControl(style.CE_ItemViewItem, option, qp, widget)

        # "lie" about the decoration, to get a valid icon rectangle (even if we
        # don't have any "real" icon set for the item)
        option.features |= option.HasDecoration
        iconRect = style.subElementRect(style.SE_ItemViewItemDecoration,
            option, widget)
        iconSize = iconRect.size()
        margin = iconRect.left() - option.rect.left()

        qp.save()
        # ensure that we do not draw outside the item rectangle (and add some
        # fancy margin on the right
        qp.setClipRect(option.rect.adjusted(0, 0, -margin, 0))

        # draw the main state icon, assuming all items have one
        qp.drawPixmap(iconRect,
            self.stateIcons[index.data()['power']].pixmap(iconSize))

        left = delta = margin + iconRect.width()
        if index.data()['outdated']:
            qp.drawPixmap(iconRect.translated(left, 0),
                    self.outdatedIcons[index.data()['outdated']]\
                           .pixmap(iconSize))
            left += delta

        qp.restore()

    def helpEvent(self, event, view, option, index):
        if event.type() != QEvent.ToolTip:
            return super().helpEvent(event, view,
                    option, index)
        option = QStyleOptionViewItem(option)
        widget = option.widget
        style = widget.style()
        option.features |= option.HasDecoration

        iconRect = style.subElementRect(style.SE_ItemViewItemDecoration,
            option, widget)
        iconRect.setTop(option.rect.y())
        iconRect.setHeight(option.rect.height())

        # similar to what we do in the paint() method
        if event.pos() in iconRect:
            # (*) clear any existing tooltip; a single space is better , as
            # sometimes it's not enough to use an empty string
            if index != self.lastIndex:
                QToolTip.showText(QPoint(), ' ')
            QToolTip.showText(event.globalPos(),
                index.data()['power'], view)
        else:
            margin = iconRect.left() - option.rect.left()
            left = delta = margin + iconRect.width()

            if index.data()['outdated']:
                if event.pos() in iconRect.translated(left, 0):
                    # see above (*)
                    if index != self.lastIndex:
                        QToolTip.showText(QPoint(), ' ')
                    QToolTip.showText(event.globalPos(),
                            self.outdatedTooltips[index.data()['outdated']],
                            view)
                # shift the left *only* if the role is True, otherwise we
                # can assume that that icon doesn't exist at all
            left += delta
        self.lastIndex = index
        return True


# pylint: disable=too-many-instance-attributes
# pylint: disable=too-few-public-methods
class VmInfo():
    def __init__(self, vm):
        self.vm = vm
        self.qid = vm.qid
        self.name = self.vm.name

        self.label = getattr(self.vm, 'label', None)
        self.klass = getattr(self.vm, 'klass', None)
        self.icon = getattr(vm, 'icon', 'appvm-black')

        self.state = {'power': "", 'outdated': ""}
        self.updateable = getattr(vm, 'updateable', False)
        self.update(True)

    def update_power_state(self):
        try:
            self.state['power'] = self.vm.get_power_state()
        except exc.QubesDaemonAccessError:
            self.state['power'] = ""

        self.state['outdated'] = ""
        try:
            if manager_utils.is_running(self.vm, False):
                if hasattr(self.vm, 'template') and \
                        manager_utils.is_running(self.vm.template, False):
                    self.state['outdated'] = "to-be-outdated"
                else:
                    try:
                        if any(vol.is_outdated()
                               for vol in self.vm.volumes.values()):
                            self.state['outdated'] = "outdated"
                    except exc.QubesDaemonAccessError:
                        pass

            if self.vm.klass in {'TemplateVM', 'StandaloneVM'} and \
                    manager_utils.get_feature(
                        self.vm, 'updates-available', False):
                self.state['outdated'] = 'update'
        except exc.QubesDaemonAccessError:
            pass

    def update(self, update_size_on_disk=False, event=None):
        """
        Update VmInfo
        :param update_size_on_disk: should disk utilization be updated?
        :param event: name of the event that caused the update, to avoid
        updating unnecessary properties; if event is none, update everything
        :return: None
        """
        self.update_power_state()

        if not event or event.endswith(':label'):
            self.label = getattr(self.vm, 'label', None)
            self.icon = getattr(self.vm, 'icon', 'appvm-black')

        if not event or event.endswith(':template'):
            try:
                self.template = self.vm.template.name
            except AttributeError:
                self.template = None

        if not event or event.endswith(':netvm'):
            self.netvm = getattr(self.vm, 'netvm', None)
            if self.netvm:
                self.netvm = str(self.netvm)
            else:
                self.netvm = "n/a"
            try:
                if hasattr(self.vm, 'netvm') \
                        and self.vm.property_is_default("netvm"):
                    self.netvm = "default (" + self.netvm + ")"
            except exc.QubesDaemonAccessError:
                pass

        if not event or event.endswith(':internal'):
            self.internal = manager_utils.get_boolean_feature(
                self.vm, 'internal')

        if not event or event.endswith(':ip'):
            self.ip = getattr(self.vm, 'ip', "n/a")

        if not event or event.endswith(':include_in_backups'):
            self.inc_backup = getattr(self.vm, 'include_in_backups', None)

        if not event or event.endswith(':backup_timestamp'):
            self.last_backup = getattr(self.vm, 'backup_timestamp', None)
            if self.last_backup:
                self.last_backup = str(datetime.fromtimestamp(self.last_backup))

        if not event or event.endswith(':default_dispvm'):
            self.dvm = getattr(self.vm, 'default_dispvm', None)
            try:
                if self.vm.property_is_default("default_dispvm"):
                    self.dvm = "default (" + str(self.dvm) + ")"
                elif self.dvm is not None:
                    self.dvm = str(self.dvm)
            except exc.QubesDaemonAccessError:
                if self.dvm is not None:
                    self.dvm = str(self.dvm)

        if not event or event.endswith(':template_for_dispvms'):
            self.dvm_template = getattr(self.vm, 'template_for_dispvms', None)

        if self.vm.klass != 'AdminVM' and update_size_on_disk:
            try:
                self.disk_float = float(self.vm.get_disk_utilization())
                self.disk = str(round(self.disk_float/(1024*1024), 2)) + " MiB"
            except exc.QubesDaemonAccessError:
                self.disk_float = None
                self.disk = None

        if self.vm.klass != 'AdminVM':
            self.virt_mode = getattr(self.vm, 'virt_mode', None)
        else:
            self.virt_mode = None
            self.disk = "n/a"


class QubesCache(QAbstractTableModel):
    def __init__(self, qubes_app):
        QAbstractTableModel.__init__(self)
        self._qubes_app = qubes_app
        self._info_list = []
        self._info_by_id = {}

    def add_vm(self, vm):
        vm_info = VmInfo(vm)
        self._info_list.append(vm_info)
        self._info_by_id[vm.qid] = vm_info

    def remove_vm(self, name):
        vm_info = self.get_vm(name=name)
        self._info_list.remove(vm_info)
        del self._info_by_id[vm_info.qid]

    def get_vm(self, row=None, qid=None, name=None):
        if row is not None:
            return self._info_list[row]
        if qid is not None:
            return self._info_by_id[qid]
        return next(x for x in self._info_list if x.name == name)

    def update_model_data(self, *args, **kwargs):
        # pylint: disable=unused-argument
        for vm_info in self._info_list:
            # FIXME: add helper maybe?
            # pylint: disable=protected-access
            vm_info.vm._power_state_cache = None
            vm_info.update()

    def __len__(self):
        return len(self._info_list)

    def __iter__(self):
        return iter(self._info_list)


class QubesTableModel(QAbstractTableModel):
    def __init__(self, qubes_cache):
        QAbstractTableModel.__init__(self)
        self.qubes_cache = qubes_cache
        self.template = {}
        self.klass_pixmap = {}
        self.label_pixmap = {}
        self.columns_indices = [
                "Type",
                "Label",
                "Name",
                "State",
                "Template",
                "NetVM",
                "Disk Usage",
                "Internal",
                "IP",
                "Backup",
                "Last backup",
                "Default DispVM",
                "Is DVM Template",
                "Virt Mode"
                ]

    # pylint: disable=invalid-name
    def rowCount(self, _):
        return len(self.qubes_cache)

    # pylint: disable=invalid-name
    def columnCount(self, _):
        return len(self.columns_indices)

    # pylint: disable=too-many-return-statements
    def data(self, index, role):
        if not index.isValid():
            return  None

        col = index.column()
        row = index.row()

        col_name = self.columns_indices[col]
        vm = self.qubes_cache.get_vm(row)

        if role == Qt.DisplayRole:
            if col in [0, 1]:
                return None
            if col_name == "Name":
                return vm.name
            if col_name == "State":
                return vm.state
            if col_name == "Template":
                if vm.template is None:
                    return vm.klass
                return vm.template
            if col_name == "NetVM":
                return vm.netvm
            if col_name == "Disk Usage":
                return vm.disk
            if col_name == "Internal":
                return "Yes" if vm.internal else ""
            if col_name == "IP":
                return vm.ip
            if col_name == "Last backup":
                return vm.last_backup
            if col_name == "Default DispVM":
                return vm.dvm
            if col_name == "Is DVM Template":
                return "Yes" if vm.dvm_template else ""
            if col_name == "Virt Mode":
                return vm.virt_mode
        if role == Qt.DecorationRole:
            if col_name == "Type":
                try:
                    return self.klass_pixmap[vm.klass]
                except KeyError:
                    pixmap = QPixmap()
                    icon_name = ":/"+vm.klass.lower()+".png"
                    icon_name = icon_name.replace("adminvm", "dom0")
                    icon_name = icon_name.replace("dispvm", "appvm")
                    pixmap.load(icon_name)
                    self.klass_pixmap[vm.klass] = pixmap.scaled(icon_size)
                    return self.klass_pixmap[vm.klass]
                except exc.QubesDaemonAccessError:
                    return None
            if col_name == "Label":
                try:
                    return self.label_pixmap[vm.icon]
                except (KeyError, AttributeError):
                    icon = QIcon.fromTheme(vm.icon)
                    self.label_pixmap[vm.icon] = icon.pixmap(icon_size)
                    return self.label_pixmap[vm.icon]
        if role == Qt.CheckStateRole:
            if col_name == "Backup":
                return Qt.Checked if vm.inc_backup else Qt.Unchecked
        if role == Qt.FontRole:
            if col_name == "Template":
                if vm.template is None:
                    font = QFont()
                    font.setItalic(True)
                    return font
        if role == Qt.ForegroundRole:
            if col_name == "Template":
                if vm.template is None:
                    return QColor("gray")
        # Used for get VM Object
        if role == Qt.UserRole:
            return vm
        # Used for sorting
        if role == Qt.UserRole + 1:
            if vm.klass == 'AdminVM':
                return ""
            if col_name == "Type":
                return vm.klass
            if col_name == "Label":
                vmtype, vmcolor = vm.icon.split("-")
                try:
                    processed_color = str(vm.label.index)
                except ValueError:
                    processed_color = vmcolor
                return vmtype + processed_color
            if col_name == "State":
                # sorting order is based on a logical order (from running to
                # progressively less running) and update state
                state = vm.state.get('power', '')
                try:
                    ordered_state = str(
                        ["Running", "Transient", "Halting", "Paused",
                         "Suspended", "Dying", "Crashed",
                         "Halted", "NA"].index(state))
                except ValueError:
                    ordered_state = state
                updated = vm.state.get('outdated', '')
                return ordered_state + updated
            if col_name == "Disk Usage":
                return vm.disk_float
            if col_name == "Backup":
                # sort True before False, hence the not
                return not vm.inc_backup
            return self.data(index, Qt.DisplayRole)

    # pylint: disable=invalid-name
    def headerData(self, col, orientation, role):
        if col < 2:
            return None
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.columns_indices[col]
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False

        if role == Qt.CheckStateRole:
            col_name = self.columns_indices[index.column()]
            if col_name == "Backup":
                vm = self.qubes_cache.get_vm(index.row())
                vm.vm.include_in_backups = value == Qt.Checked
                vm.inc_backup = value == Qt.Checked
                return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        def_flags = QAbstractTableModel.flags(self, index)
        if self.columns_indices[index.column()] == "Backup":
            return  def_flags | Qt.ItemIsUserCheckable
        return def_flags

vm_restart_check_timeout = 1000  # in msec


class VmShutdownMonitor(QObject):
    def __init__(self, vm, check_time=vm_restart_check_timeout,
                 and_restart=False, caller=None):
        QObject.__init__(self)
        self.vm = vm
        self.shutdown_timeout = vm.shutdown_timeout
        self.check_time = check_time
        self.and_restart = and_restart
        self.shutdown_started = datetime.now()
        self.caller = caller

    def restart_vm_if_needed(self):
        if self.and_restart and self.caller:
            self.caller.start_vm(self.vm)

    def check_again_later(self):
        # noinspection PyTypeChecker,PyCallByClass
        QTimer.singleShot(self.check_time, self.check_if_vm_has_shutdown)

    def timeout_reached(self):
        actual = datetime.now() - self.shutdown_started
        allowed = timedelta(seconds=self.shutdown_timeout)

        return actual > allowed

    def check_if_vm_has_shutdown(self):
        vm = self.vm
        vm_is_running = manager_utils.is_running(vm, False)
        try:
            vm_start_time = datetime.fromtimestamp(float(vm.start_time))
        except (AttributeError, TypeError, ValueError):
            vm_start_time = None

        if vm_is_running and vm_start_time \
                and vm_start_time < self.shutdown_started:
            if self.timeout_reached():

                msgbox = QMessageBox(self.caller)
                msgbox.setIcon(QMessageBox.Question)
                msgbox.setWindowTitle(self.tr("Qube Shutdown"))
                msgbox.setText(self.tr(
                        "The Qube <b>'{0}'</b> hasn't shutdown within the last "
                        "{1} seconds, do you want to kill it?<br>").format(
                            vm.name, self.shutdown_timeout))
                kill_button = msgbox.addButton(
                    self.tr("Kill it!"), QMessageBox.YesRole)
                wait_button = msgbox.addButton(
                    self.tr("Wait another {0} seconds...").format(
                        self.shutdown_timeout),
                    QMessageBox.NoRole)
                ignore_button = msgbox.addButton(self.tr("Don't ask again"),
                                                 QMessageBox.RejectRole)
                msgbox.setDefaultButton(wait_button)
                msgbox.setEscapeButton(ignore_button)
                msgbox.setWindowFlags(
                    msgbox.windowFlags() | Qt.CustomizeWindowHint)
                msgbox.setWindowFlags(
                    msgbox.windowFlags() & ~Qt.WindowCloseButtonHint)
                msgbox.exec_()
                msgbox.deleteLater()

                if msgbox.clickedButton() is kill_button:
                    try:
                        vm.kill()
                    except exc.QubesVMNotStartedError:
                        # the VM shut down while the user was thinking about
                        # shutting it down
                        pass
                    self.restart_vm_if_needed()
                elif msgbox.clickedButton() is ignore_button:
                    return
                else:
                    self.shutdown_started = datetime.now()
                    self.check_again_later()
            else:
                self.check_again_later()
        else:
            if vm_is_running:
                # Due to unknown reasons, Xen sometimes reports that a domain
                # is running even though its start-up timestamp is not valid.
                # Make sure that "restart_vm_if_needed" is not called until
                # the domain has been completely shut down according to Xen.
                self.check_again_later()
                return

            self.restart_vm_if_needed()


# pylint: disable=too-few-public-methods
class StartVMThread(common_threads.QubesThread):
    def run(self):
        try:
            self.vm.start()
        except exc.QubesException as ex:
            self.msg = ("Error starting Qube!", str(ex))


# pylint: disable=too-few-public-methods
class UpdateVMThread(common_threads.QubesThread):
    def run(self):
        try:
            if self.vm.klass == 'AdminVM':
                subprocess.check_call(
                    ["/usr/bin/qubes-dom0-update", "--clean", "--gui"])
            else:
                if not manager_utils.is_running(self.vm, False):
                    try:
                        self.vm.start()
                    except exc.QubesDaemonAccessError:
                        # permission denied, let us hope for the best
                        pass
                self.vm.run_service("qubes.InstallUpdatesGUI",
                                    user="root", wait=False)
        except (OSError, subprocess.SubprocessError,
                exc.QubesException) as ex:
            self.msg = (self.tr("Error on qube update!"), str(ex))


# pylint: disable=too-few-public-methods
class RunCommandThread(common_threads.QubesThread):
    def __init__(self, vm, command_to_run):
        super().__init__(vm)
        self.command_to_run = command_to_run

    def run(self):
        try:
            self.vm.run(self.command_to_run)
        except (ChildProcessError, subprocess.CalledProcessError,
                exc.QubesException) as ex:
            self.msg = (self.tr("Error while running command!"), str(ex))

class QubesProxyModel(QSortFilterProxyModel):
    def __init__(self, window):
        super().__init__()
        self.window = window

    def lessThan(self, left, right):
        if left.data(self.sortRole()) != right.data(self.sortRole()):
            return super().lessThan(left, right)

        left_vm = left.data(Qt.UserRole)
        right_vm = right.data(Qt.UserRole)

        return left_vm.name.lower() < right_vm.name.lower()

    # pylint: disable=too-many-return-statements
    def filterAcceptsRow(self, sourceRow, sourceParent):
        index = self.sourceModel().index(sourceRow, 0, sourceParent)
        vm = self.sourceModel().data(index, Qt.UserRole)

        # if hide internal is true, ignore all other filters
        if not self.window.show_internal_action.isChecked() and vm.internal:
            return False
        if self.window.show_all.isChecked():
            return super().filterAcceptsRow(sourceRow, sourceParent)

        if self.window.show_running.isChecked() and \
                vm.state['power'] != 'Halted':
            return super().filterAcceptsRow(sourceRow, sourceParent)
        if self.window.show_halted.isChecked() and \
                vm.state['power'] == 'Halted':
            return super().filterAcceptsRow(sourceRow, sourceParent)
        if self.window.show_network.isChecked() and \
                getattr(vm.vm, 'provides_network', False):
            return super().filterAcceptsRow(sourceRow, sourceParent)
        if self.window.show_templates.isChecked() and vm.klass == 'TemplateVM':
            return super().filterAcceptsRow(sourceRow, sourceParent)
        if self.window.show_standalone.isChecked() \
                and vm.klass == 'StandaloneVM':
            return super().filterAcceptsRow(sourceRow, sourceParent)

        return False


class VmManagerWindow(ui_qubemanager.Ui_VmManagerWindow, QMainWindow):
    # suppress saving settings while initializing widgets
    settings_loaded = False

    def __init__(self, qt_app, qubes_app, dispatcher, _parent=None):
        super().__init__()
        self.setupUi(self)

        self.manager_settings = QSettings(self)

        self.qubes_app = qubes_app
        self.qt_app = qt_app

        self.searchbox = SearchBox()
        self.searchbox.setValidator(QRegExpValidator(
            QRegExp("[a-zA-Z0-9_-]*", Qt.CaseInsensitive), None))
        self.searchbox.textChanged.connect(self.do_search)
        self.searchContainer.insertWidget(1, self.searchbox)

        self.search_shortcut = QShortcut(QKeySequence('Ctrl+F'), self)
        self.search_shortcut.activated.connect(self.searchbox.setFocus)

        self.settings_windows = {}

        self.frame_width = 0
        self.frame_height = 0

        self.init_template_menu()
        self.init_network_menu()
        self.__init_context_menu()

        self.tools_context_menu = QMenu(self)
        self.tools_context_menu.addAction(self.action_toolbar)
        self.tools_context_menu.addAction(self.action_menubar)

        self.menubar.customContextMenuRequested.connect(
                lambda pos: self.open_tools_context_menu(self.menubar, pos))
        self.toolbar.customContextMenuRequested.connect(
                lambda pos: self.open_tools_context_menu(self.toolbar, pos))
        self.action_menubar.toggled.connect(self.showhide_menubar)
        self.action_toolbar.toggled.connect(self.showhide_toolbar)
        self.action_show_logs.triggered.connect(self.show_log)
        self.action_compact_view.toggled.connect(self.set_compactview)

        self.table.resizeColumnsToContents()

        self.update_size_on_disk = False
        self.shutdown_monitor = {}

        self.qubes_cache = QubesCache(qubes_app)
        self.fill_cache()
        self.qubes_model = QubesTableModel(self.qubes_cache)

        self.show_running.stateChanged.connect(self.invalidate)
        self.show_halted.stateChanged.connect(self.invalidate)
        self.show_network.stateChanged.connect(self.invalidate)
        self.show_templates.stateChanged.connect(self.invalidate)
        self.show_standalone.stateChanged.connect(self.invalidate)
        self.show_all.stateChanged.connect(self.invalidate)

        # Create view menu
        for col_no, column in enumerate(self.qubes_model.columns_indices):
            action = self.menu_view.addAction(column)
            action.setData(column)
            action.setCheckable(True)
            action.toggled.connect(partial(self.showhide_column, col_no))

        self.menu_view.addSeparator()
        self.show_internal_action = self.menu_view.addAction(
            self.tr('Show internal qubes'))
        self.show_internal_action.setCheckable(True)
        self.show_internal_action.toggled.connect(self.invalidate)

        self.menu_view.addSeparator()
        self.menu_view.addAction(self.action_toolbar)
        self.menu_view.addAction(self.action_menubar)

        self.menu_view.addSeparator()
        self.menu_view.addAction(self.action_compact_view)

        self.proxy = QubesProxyModel(self)
        self.proxy.setSourceModel(self.qubes_model)
        self.proxy.setSortRole(Qt.UserRole + 1)
        self.proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(2)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.layoutChanged.connect(self.save_sorting)
        self.proxy.layoutChanged.connect(self.update_template_menu)
        self.proxy.layoutChanged.connect(self.update_network_menu)

        self.table.setModel(self.proxy)
        self.table.setItemDelegateForColumn(3, StateIconDelegate())
        self.table.resizeColumnsToContents()
        selection_model = self.table.selectionModel()
        selection_model.selectionChanged.connect(self.table_selection_changed)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

        try:
            self.load_manager_settings()
        except Exception as ex:  # pylint: disable=broad-except
            QMessageBox.warning(
                self,
                self.tr("Manager settings unreadable"),
                self.tr("Qube Manager settings cannot be parsed. Previously "
                        "saved display settings may not be restored "
                        "correctly.\nError: {}".format(str(ex))))

        self.settings_loaded = True

        # Connect events
        self.dispatcher = dispatcher
        dispatcher.add_handler('connection-established',
                               self.qubes_cache.update_model_data)
        dispatcher.add_handler('domain-pre-start',
                               self.on_domain_status_changed)
        dispatcher.add_handler('domain-start', self.on_domain_status_changed)
        dispatcher.add_handler('domain-start-failed',
                               self.on_domain_status_changed)
        dispatcher.add_handler('domain-stopped', self.on_domain_status_changed)
        dispatcher.add_handler('domain-pre-shutdown',
                               self.on_domain_status_changed)
        dispatcher.add_handler('domain-shutdown', self.on_domain_status_changed)
        dispatcher.add_handler('domain-paused', self.on_domain_status_changed)
        dispatcher.add_handler('domain-unpaused', self.on_domain_status_changed)

        dispatcher.add_handler('domain-add', self.on_domain_added)
        dispatcher.add_handler('domain-delete', self.on_domain_removed)

        dispatcher.add_handler('property-set:*',
                               self.on_domain_changed)
        dispatcher.add_handler('property-del:*',
                               self.on_domain_changed)
        dispatcher.add_handler('property-load',
                               self.on_domain_changed)
        dispatcher.add_handler('domain-feature-set:internal',
                               self.on_domain_changed)
        dispatcher.add_handler('domain-feature-delete:internal',
                               self.on_domain_changed)

        dispatcher.add_handler('domain-feature-set:updates-available',
                               self.on_domain_updates_available)
        dispatcher.add_handler('domain-feature-delete:updates-available',
                               self.on_domain_updates_available)

        # It needs to store threads until they finish
        self.threads_list = []
        self.progress = None

        self.check_updates()

    def change_template(self, template):
        selected_vms = self.get_selected_vms()
        reply = QMessageBox.question(
            self, self.tr("Template Change Confirmation"),
            self.tr("Do you want to change '{0}'<br>"
                "to Template <b>'{1}'</b>?").format(
                ', '.join(vm.name for vm in selected_vms), template),
            QMessageBox.Yes | QMessageBox.Cancel)

        if reply == QMessageBox.Yes:
            errors = []
            for info in selected_vms:
                try:
                    info.vm.template = template
                except exc.QubesException as ex:
                    errors.append((info.name, str(ex)))

            for error in errors:
                QMessageBox.warning(self, self.tr("{0} template change failed!")
                        .format(error[0]), error[1])


    def change_network(self, netvm_name):
        selected_vms = self.get_selected_vms()
        reply = QMessageBox.question(
            self, self.tr("Network Change Confirmation"),
            self.tr("Do you want to change '{0}'<br>"
                "to Network <b>'{1}'</b>?").format(
                ', '.join(vm.name for vm in selected_vms), netvm_name),
            QMessageBox.Yes | QMessageBox.Cancel)

        if reply != QMessageBox.Yes:
            return

        if netvm_name not in [None, 'default']:
            check_power = any(info.state['power'] == 'Running' for info
                    in self.get_selected_vms())
            netvm = self.qubes_cache.get_vm(name=netvm_name)
            if check_power and netvm.state['power'] != 'Running':
                reply = QMessageBox.question(
                    self, self.tr("Qube Start Confirmation"),
                    self.tr("<br>Can not change netvm to a halted Qube.<br>"
                        "Do you want to start the Qube <b>'{0}'</b>?").format(
                        netvm_name),
                    QMessageBox.Yes | QMessageBox.Cancel)

                if reply == QMessageBox.Yes:
                    self.start_vm(netvm.vm, True)
                else:
                    return

        errors = []
        for info in self.get_selected_vms():
            try:
                if netvm_name == 'default':
                    delattr(info.vm, 'netvm')
                else:
                    info.vm.netvm = netvm_name
            except exc.QubesValueError as ex:
                errors.append((info.name, str(ex)))

        for error in errors:
            QMessageBox.warning(self, self.tr("{0} network change failed!")
                    .format(error[0]), error[1])


    def __init_context_menu(self):
        self.context_menu = QMenu(self)
        self.context_menu.addAction(self.action_settings)
        self.context_menu.addAction(self.template_menu.menuAction())
        self.context_menu.addAction(self.network_menu.menuAction())
        self.context_menu.addAction(self.action_editfwrules)
        self.context_menu.addAction(self.action_appmenus)
        self.context_menu.addAction(self.action_set_keyboard_layout)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.action_updatevm)
        self.context_menu.addAction(self.action_run_command_in_vm)
        self.context_menu.addAction(self.action_open_console)
        self.context_menu.addAction(self.action_resumevm)
        self.context_menu.addAction(self.action_startvm_tools_install)
        self.context_menu.addAction(self.action_pausevm)
        self.context_menu.addAction(self.action_shutdownvm)
        self.context_menu.addAction(self.action_restartvm)
        self.context_menu.addAction(self.action_killvm)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.action_clonevm)
        self.context_menu.addAction(self.action_removevm)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.action_show_logs)

    def save_showing(self):
        self.manager_settings.setValue('show/running',
                self.show_running.isChecked())
        self.manager_settings.setValue('show/halted',
                self.show_halted.isChecked())
        self.manager_settings.setValue('show/network',
                self.show_network.isChecked())
        self.manager_settings.setValue('show/templates',
                self.show_templates.isChecked())
        self.manager_settings.setValue('show/standalone',
                self.show_standalone.isChecked())
        self.manager_settings.setValue('show/internal',
                self.show_internal_action.isChecked())
        self.manager_settings.setValue('show/all', self.show_all.isChecked())

    def save_sorting(self):
        self.manager_settings.setValue('view/sort_column',
                self.proxy.sortColumn())
        self.manager_settings.setValue('view/sort_order',
                self.proxy.sortOrder())

    def invalidate(self):
        self.proxy.invalidate()
        self.table.resizeColumnsToContents()

    def fill_cache(self):
        progress = QProgressDialog(
            self.tr(
                "Loading Qube Manager..."), "", 0,
                len(self.qubes_app.domains.keys()))
        progress.setWindowTitle(self.tr("Qube Manager"))
        progress.setMinimumDuration(1000)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)

        row_no = 0
        for vm in self.qubes_app.domains:
            progress.setValue(row_no)
            self.qubes_cache.add_vm(vm)
            row_no += 1

        progress.setValue(row_no)

    def init_template_menu(self):
        self.template_menu.clear()
        for vm in self.qubes_app.domains:
            if vm.klass == 'TemplateVM':
                action = self.template_menu.addAction(vm.name)
                action.setData(vm.name)
                action.triggered.connect(partial(self.change_template, vm.name))

    def _get_default_netvm(self):
        for vm in self.qubes_app.domains:
            if vm.klass == 'AppVM':
                return vm.property_get_default('netvm')

    def init_network_menu(self):
        default = self._get_default_netvm()
        self.network_menu.clear()
        action = self.network_menu.addAction("None")
        action.triggered.connect(partial(self.change_network, None))
        action = self.network_menu.addAction("default ({0})".format(default))
        action.triggered.connect(partial(self.change_network, 'default'))

        for vm in self.qubes_app.domains:
            if vm.qid != 0 and vm.provides_network:
                action = self.network_menu.addAction(vm.name)
                action.setData(vm.name)
                action.triggered.connect(partial(self.change_network, vm.name))

    def setup_application(self):
        self.qt_app.setApplicationName(self.tr("Qube Manager"))
        self.qt_app.setWindowIcon(QIcon.fromTheme("qubes-manager"))

    def keyPressEvent(self, event):  # pylint: disable=invalid-name
        if event.key() == Qt.Key_Escape:
            self.searchbox.clear()
        super().keyPressEvent(event)

    def clear_threads(self):
        for thread in self.threads_list:
            if thread.isFinished():
                if self.progress:
                    self.progress.hide()
                    self.progress = None

                if thread.msg:
                    (title, msg) = thread.msg
                    if thread.msg_is_success:
                        QMessageBox.information(
                            self,
                            title,
                            msg)
                    else:
                        QMessageBox.warning(
                            self,
                            title,
                            msg)

                self.threads_list.remove(thread)
                return

        raise RuntimeError(self.tr('No finished thread found'))

    # pylint: disable=invalid-name
    def resizeEvent(self, event):
        self.manager_settings.setValue("window_size", event.size())

    def check_updates(self, info=None):
        if info is None:
            for info_iter in self.qubes_cache:
                self.check_updates(info_iter)
            return

        try:
            if info.vm.klass in {'TemplateVM', 'StandaloneVM'} and \
                    manager_utils.get_feature(
                        info.vm, 'updates-available', False):
                info.state['outdated'] = 'update'
        except exc.QubesDaemonAccessError:
            return

    def on_domain_added(self, _submitter, _event, vm, **_kwargs):
        try:
            domain = self.qubes_app.domains[vm]
            self.qubes_cache.add_vm(domain)
            self.proxy.invalidate()
            if domain.klass == 'TemplateVM':
                self.init_template_menu()
        except (exc.QubesException, KeyError):
            pass

    def on_domain_removed(self, _submitter, _event, **kwargs):
        self.qubes_cache.remove_vm(name=kwargs['vm'])
        self.proxy.invalidate()
        self.init_template_menu()
        self.init_network_menu()

    def on_domain_status_changed(self, vm, event, **_kwargs):
        try:
            self.qubes_cache.get_vm(qid=vm.qid).update(event=event)
            if vm.klass in {'TemplateVM'}:
                for appvm in vm.appvms:
                    self.qubes_cache.get_vm(qid=appvm.qid).\
                            update(event="outdated")
            self.proxy.invalidate()
            self.table_selection_changed()
        except (exc.QubesDaemonAccessError, exc.QubesVMNotFoundError):
            return  # the VM was deleted before its status could be updated
        except KeyError:  # adding the VM failed for some reason
            self.on_domain_added(None, None, vm)

    def on_domain_updates_available(self, vm, _event, **_kwargs):
        self.check_updates(self.qubes_cache.get_vm(qid=vm.qid))

    def on_domain_changed(self, vm, event, **_kwargs):
        if not vm:  # change of global properties occured
            if event.endswith(':default_netvm'):
                for vm_info in self.qubes_cache:
                    vm_info.update(event='property-set:netvm')
            if event.endswith(':default_dispvm'):
                for vm_info in self.qubes_cache:
                    vm_info.update(event='property-set:default_dispvm')
            return

        try:
            if event.endswith(':provides_network'):
                self.init_network_menu()
            self.qubes_cache.get_vm(qid=vm.qid).update(event=event)
            self.proxy.invalidate()
        except exc.QubesDaemonAccessError:
            return  # the VM was deleted before its status could be updated

    def load_manager_settings(self):
        # Load view menu settings
        # QSettings stores True as 'true' string and False as 'false' string
        for action in self.menu_view.actions():
            column = action.data()
            if column is not None:
                col_no = self.qubes_model.columns_indices.index(column)
                if column == 'Name':
                    # 'Name' column should be always visible
                    action.setChecked(True)
                else:
                    visible = self.manager_settings.value('columns/%s' % column,
                        defaultValue="true")
                    action.setChecked(visible == "true")
                    self.showhide_column(col_no, visible == "true")

        # Restore sorting
        sort_column = int(self.manager_settings.value("view/sort_column",
                                 defaultValue=2))
        order = Qt.SortOrder(self.manager_settings.value("view/sort_order",
                                 defaultValue=Qt.AscendingOrder))

        if not sort_column: # Default sort by name
            self.table.sortByColumn(2, Qt.AscendingOrder)
        else:
            self.table.sortByColumn(sort_column, order)

        if self.manager_settings.value("view/menubar_visible") == 'false':
            self.action_menubar.setChecked(False)
            self.menubar.setVisible(False)
        if self.manager_settings.value("view/toolbar_visible") == 'false':
            self.action_toolbar.setChecked(False)
            self.toolbar.setVisible(False)
        if self.manager_settings.value("view/compactview",
                                           defaultValue="false") != "false":
            self.action_compact_view.setChecked(True)

        # Restore show checkboxes
        self.show_running.setChecked(self.manager_settings.value(
            'show/running', "true") == "true")
        self.show_halted.setChecked(self.manager_settings.value(
            'show/halted', "true") == "true")
        self.show_network.setChecked(self.manager_settings.value(
            'show/network', "true") == "true")
        self.show_templates.setChecked(self.manager_settings.value(
            'show/templates', "true") == "true")
        self.show_standalone.setChecked(self.manager_settings.value(
            'show/standalone', "true") == "true")
        self.show_all.setChecked(self.manager_settings.value(
            'show/all', "true") == "true")

        self.show_internal_action.setChecked(self.manager_settings.value(
            'show/internal', "false") == "true")
        # load last window size
        self.resize(self.manager_settings.value("window_size",
                                                QSize(1100, 600)))

    @pyqtSlot(str)
    def do_search(self, search):
        self.proxy.setFilterFixedString(search)

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_search_triggered')
    def action_search_triggered(self):
        self.searchbox.setFocus()

    def get_selected_vms(self):
        vms = []

        selection = self.table.selectionModel().selection()
        indexes = self.proxy.mapSelectionToSource(selection).indexes()

        for index in indexes:
            if index.column() != 0:
                continue
            vms.append(index.data(Qt.UserRole))

        return vms

    def table_selection_changed(self):
        # Since selection could have multiple domains
        # enable all first and then filter them
        self.template_menu.setEnabled(True)
        self.network_menu.setEnabled(True)
        for action in self.toolbar.actions() + self.context_menu.actions():
            action.setEnabled(True)

        for vm in self.get_selected_vms():
            #  TODO: add boot from device to menu and add windows tools there
            # Update available actions:
            if vm.state['power'] in \
                    ['Running', 'Transient', 'Halting', 'Dying']:
                self.action_resumevm.setEnabled(False)
                self.action_removevm.setEnabled(False)
                self.template_menu.setEnabled(False)
            elif vm.state['power'] == 'Paused':
                self.action_removevm.setEnabled(False)
                self.action_pausevm.setEnabled(False)
                self.action_set_keyboard_layout.setEnabled(False)
                self.action_restartvm.setEnabled(False)
                self.action_open_console.setEnabled(False)
                self.template_menu.setEnabled(False)
            elif vm.state['power'] == 'Suspend':
                self.action_set_keyboard_layout.setEnabled(False)
                self.action_removevm.setEnabled(False)
                self.action_pausevm.setEnabled(False)
                self.action_open_console.setEnabled(False)
                self.template_menu.setEnabled(False)
            elif vm.state['power'] == 'Halted':
                self.action_set_keyboard_layout.setEnabled(False)
                self.action_pausevm.setEnabled(False)
                self.action_shutdownvm.setEnabled(False)
                self.action_restartvm.setEnabled(False)
                self.action_killvm.setEnabled(False)
                self.action_open_console.setEnabled(False)

            if vm.klass == 'AdminVM':
                self.action_open_console.setEnabled(False)
                self.action_settings.setEnabled(False)
                self.action_resumevm.setEnabled(False)
                self.action_removevm.setEnabled(False)
                self.action_clonevm.setEnabled(False)
                self.action_pausevm.setEnabled(False)
                self.action_restartvm.setEnabled(False)
                self.action_killvm.setEnabled(False)
                self.action_shutdownvm.setEnabled(False)
                self.action_appmenus.setEnabled(False)
                self.action_editfwrules.setEnabled(False)
                self.action_set_keyboard_layout.setEnabled(False)
                self.action_run_command_in_vm.setEnabled(False)
                self.template_menu.setEnabled(False)
                self.network_menu.setEnabled(False)
            elif vm.klass == 'DispVM':
                self.action_appmenus.setEnabled(False)
                self.action_restartvm.setEnabled(False)
                self.template_menu.setEnabled(False)
            elif vm.klass == 'TemplateVM':
                self.template_menu.setEnabled(False)
                self.network_menu.setEnabled(False)

            if vm.vm.features.get('internal', False):
                self.action_appmenus.setEnabled(False)

            if not vm.updateable and vm.klass != 'AdminVM':
                self.action_updatevm.setEnabled(False)

        self.update_template_menu()
        self.update_network_menu()

    def update_template_menu(self):
        if not self.template_menu.isEnabled():
            return

        for entry in self.template_menu.actions():
            entry.setIcon(QIcon())

        vms = self.get_selected_vms()
        for vm in vms:
            for entry in self.template_menu.actions():
                if entry.data() == vm.template:
                    if len(vms) == 1:
                        entry.setIcon(QIcon(":/on.png"))
                    else:
                        entry.setIcon(QIcon(":/transient.png"))

    def update_network_menu(self):
        if not self.network_menu.isEnabled():
            return

        for entry in self.network_menu.actions():
            entry.setIcon(QIcon())

        if len(self.get_selected_vms()) == 1:
            icon = QIcon(":/on.png")
        else:
            icon = QIcon(":/transient.png")

        for vm in self.get_selected_vms():
            if vm.netvm == "n/a":
                self.network_menu.actions()[0].setIcon(QIcon(icon))
            elif vm.vm.property_is_default("netvm"):
                self.network_menu.actions()[1].setIcon(QIcon(icon))
            else:
                for entry in self.network_menu.actions():
                    if entry.data() == vm.netvm:
                        entry.setIcon(icon)

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_createvm_triggered')
    def action_createvm_triggered(self):
        with common_threads.busy_cursor():
            create_window = create_new_vm.NewVmDlg(
                    self.qt_app, self.qubes_app, self)
        create_window.exec_()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_removevm_triggered')
    def action_removevm_triggered(self):
        remove_vms = []

        for vm_info in self.get_selected_vms():
            vm = vm_info.vm

            dependencies = utils.vm_dependencies(self.qubes_app, vm)

            if dependencies:
                list_deps = manager_utils.format_dependencies_list(dependencies)
                list_text = "<br>" + list_deps + "<br>"

                info_dialog = QMessageBox(self)
                info_dialog.setWindowTitle(self.tr("Warning!"))
                info_dialog.setText(
                    self.tr("This qube cannot be removed. It is used as: <br> "
                            "{} <small>If you want to  remove this qube, you "
                            "should remove or change settings of each qube or "
                            "setting that uses it.</small>").format(list_text))
                info_dialog.setModal(False)
                info_dialog.show()

                return

            (requested_name, ok) = QInputDialog.getText(
                self, self.tr("Qube Removal Confirmation"),
                self.tr("Are you sure you want to remove the Qube <b>'{0}'</b>"
                        "?<br> All data on this Qube's private storage will be "
                        "lost!<br><br>Type the name of the Qube (<b>{1}</b>) be"
                        "low to confirm:").format(vm.name, vm.name))

            if not ok:
                # user clicked cancel
                continue

            if requested_name == vm.name:
                remove_vms.append(vm)
            else:
                # name did not match
                QMessageBox.warning(
                    self,
                    self.tr("Qube removal confirmation failed"),
                    self.tr(
                        "Entered name did not match! Not removing "
                        "{0}.").format(vm.name))

        # remove the VMs
        for vm in remove_vms:
            thread = common_threads.RemoveVMThread(vm)
            self.threads_list.append(thread)
            thread.finished.connect(self.clear_threads)
            thread.start()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_clonevm_triggered')
    def action_clonevm_triggered(self):
        for vm_info in self.get_selected_vms():
            vm = vm_info.vm
            with common_threads.busy_cursor():
                clone_window = clone_vm.CloneVMDlg(
                    self.qt_app, self.qubes_app, src_vm=vm)
            clone_window.exec_()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_resumevm_triggered')
    def action_resumevm_triggered(self):
        for vm_info in self.get_selected_vms():
            vm = vm_info.vm
            try:
                if vm.get_power_state() in ["Paused", "Suspended"]:
                    vm.unpause()
            except exc.QubesException as ex:
                QMessageBox.warning(
                    self, self.tr("Error unpausing Qube!"),
                    self.tr("ERROR: {0}").format(ex))
                return

            self.start_vm(vm)

    def start_vm(self, vm, wait=False):
        if manager_utils.is_running(vm, False):
            return

        thread = StartVMThread(vm)
        self.threads_list.append(thread)
        thread.finished.connect(self.clear_threads)
        thread.start()

        if wait:
            with common_threads.busy_cursor():
                thread.wait()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_startvm_tools_install_triggered')
    # TODO: unhardcode path
    def action_startvm_tools_install_triggered(self):
        # pylint: disable=invalid-name
        if not path.exists(r'/usr/lib/qubes/qubes-windows-tools.iso'):
            QMessageBox.warning(
                    self,
                    self.tr("QWT not found"),
                    self.tr("'qubes-windows-tools' is not installed in dom0."))
        for vm_info in self.get_selected_vms():
            vm = vm_info.vm
            qvm_start.main(['--cdrom',
                'dom0:/usr/lib/qubes/qubes-windows-tools.iso', vm.name])

    @pyqtSlot(name='on_action_pausevm_triggered')
    def action_pausevm_triggered(self):
        for vm_info in self.get_selected_vms():
            try:
                vm_info.vm.pause()
            except exc.QubesException as ex:
                QMessageBox.warning(
                    self,
                    self.tr("Error pausing Qube!"),
                    self.tr("ERROR: {0}").format(ex))
                return

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_shutdownvm_triggered')
    def action_shutdownvm_triggered(self):
        for vm_info in self.get_selected_vms():
            vm = vm_info.vm
            reply = QMessageBox.question(
                self, self.tr("Qube Shutdown Confirmation"),
                self.tr("Are you sure you want to power down the Qube <b>'{0}'"
                        "</b>?<br><small>This will shutdown all the running"
                        " applications within this Qube.</small>").format(
                         vm.name),
                QMessageBox.Yes | QMessageBox.Cancel)

            if reply == QMessageBox.Yes:
                self.shutdown_vm(vm)

    def get_connected_vms(self, vm, connected_vms):
        for connected_vm in vm.connected_vms:
            if connected_vm.is_running():
                connected_vms.append(connected_vm)
                self.get_connected_vms(connected_vm, connected_vms)

    def shutdown_vm(self, vm, force=False, check_time=vm_restart_check_timeout,
                    and_restart=False):
        try:
            connected_vms = []

            if not and_restart:
                self.get_connected_vms(vm, connected_vms)

            if len(connected_vms) > 0:
                reply = QMessageBox.question(
                    self, self.tr("Qube Shutdown Confirmation"),
                    self.tr("There are some qubes connected to <b>'{0}'</b>!"
                        "<br><small>Do you want to shutdown: </small>"
                        "<b>'{1}'</b>?").format(vm.name,
                            ", ".join([x.name for x in connected_vms])),
                    QMessageBox.Yes | QMessageBox.Cancel)

                if reply != QMessageBox.Yes:
                    return False

                force = True
                for connected_vm in connected_vms:
                    connected_vm.shutdown(force=force)

            vm.shutdown(force=force)
        except exc.QubesException as ex:
            QMessageBox.warning(
                self,
                self.tr("Error shutting down Qube!"),
                self.tr("ERROR: {0}").format(ex))
            return False

        self.shutdown_monitor[vm.qid] = VmShutdownMonitor(vm, check_time,
                                                          and_restart, self)
        # noinspection PyCallByClass,PyTypeChecker
        QTimer.singleShot(check_time, self.shutdown_monitor[
            vm.qid].check_if_vm_has_shutdown)

        return True

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_restartvm_triggered')
    def action_restartvm_triggered(self):
        for vm_info in self.get_selected_vms():
            vm = vm_info.vm
            reply = QMessageBox.question(
                self, self.tr("Qube Restart Confirmation"),
                self.tr("Are you sure you want to restart the Qube <b>'{0}'</b>"
                        "?<br><small>This will shutdown all the running applica"
                        "tions within this Qube.</small>").format(vm.name),
                QMessageBox.Yes | QMessageBox.Cancel)

            if reply == QMessageBox.Yes:
                # in case the user shut down the VM in the meantime
                try:
                    if manager_utils.is_running(vm, False):
                        self.shutdown_vm(vm, force=True, and_restart=True)
                    else:
                        self.start_vm(vm)
                except exc.QubesException as ex:
                    QMessageBox.warning(
                        self,
                        self.tr("Error restarting Qube!"),
                        self.tr("ERROR: {0}").format(ex))

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_killvm_triggered')
    def action_killvm_triggered(self):
        for vm_info in self.get_selected_vms():
            vm = vm_info.vm

            try:
                vm_not_running = not (vm.is_running() or vm.is_paused())
            except exc.QubesDaemonAccessError:
                vm_not_running = False

            if vm_not_running:
                info = self.tr("Qube <b>'{0}'</b> is not running. Are you "
                               "absolutely sure you want to try to kill it?<br>"
                               "<small>This will end <b>(not shutdown!)</b> "
                               "all the running applications within this "
                               "Qube.</small>").format(vm.name)
            else:
                info = self.tr("Are you sure you want to kill the Qube "
                               "<b>'{0}'</b>?<br><small>This will end <b>(not "
                               "shutdown!)</b> all the running applications "
                               "within this Qube.</small>").format(vm.name)

            reply = QMessageBox.question(
                self, self.tr("Qube Kill Confirmation"), info,
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel)

            if reply == QMessageBox.Yes:
                try:
                    vm.kill()
                except exc.QubesException as ex:
                    QMessageBox.critical(
                        self, self.tr("Error while killing Qube!"),
                        self.tr(
                            "<b>An exception occurred while killing {0}.</b>"
                            "<br>ERROR: {1}").format(vm.name, ex))
                    return

    def open_settings(self, vm, tab='basic'):
        try:
            with common_threads.busy_cursor():
                settings_window = settings.VMSettingsWindow(
                    vm, tab, self.qt_app, self.qubes_app, self)
            settings_window.show()
            self.settings_windows[vm.name] = settings_window
        except exc.QubesException as ex:
            QMessageBox.warning(
                self,
                self.tr("Qube settings unavailable"),
                self.tr(
                    "Qube settings cannot be opened. The qube might have "
                    "been removed or unavailable due to policy settings."
                    "\nError: {}".format(str(ex))))
            return

    def closeEvent(self, _):
        self.save_showing()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_settings_triggered')
    def action_settings_triggered(self):
        for vm_info in self.get_selected_vms():
            self.open_settings(vm_info.vm, "basic")

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_appmenus_triggered')
    def action_appmenus_triggered(self):
        for vm_info in self.get_selected_vms():
            self.open_settings(vm_info.vm, "applications")

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_updatevm_triggered')
    def action_updatevm_triggered(self):
        for vm_info in self.get_selected_vms():
            vm = vm_info.vm
            if not manager_utils.is_running(vm, True):
                reply = QMessageBox.question(
                    self, self.tr("Qube Update Confirmation"),
                    self.tr(
                        "<b>{0}</b>"
                        "<br>The Qube has to be running to be updated."
                        "<br>Do you want to start it?<br>").format(vm.name),
                    QMessageBox.Yes | QMessageBox.Cancel)
                if reply != QMessageBox.Yes:
                    return

            thread = UpdateVMThread(vm)
            self.threads_list.append(thread)
            thread.finished.connect(self.clear_threads)
            thread.start()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_run_command_in_vm_triggered')
    def action_run_command_in_vm_triggered(self):
        # pylint: disable=invalid-name
        for vm_info in self.get_selected_vms():
            (command_to_run, ok) = QInputDialog.getText(
                self, self.tr('Qubes command entry'),
                self.tr('Run command in <b>{}</b>:').format(vm_info.name))
            if not ok or command_to_run == "":
                return

            thread = RunCommandThread(vm_info.vm, command_to_run)
            self.threads_list.append(thread)
            thread.finished.connect(self.clear_threads)
            thread.start()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_open_console_triggered')
    def action_open_console_triggered(self):
        # pylint: disable=invalid-name
        for vm in self.get_selected_vms():
            # pylint: disable=consider-using-with
            subprocess.Popen(['qvm-console-dispvm', vm.name],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_set_keyboard_layout_triggered')
    def action_set_keyboard_layout_triggered(self):
        # pylint: disable=invalid-name
        for vm_info in self.get_selected_vms():
            if vm_info.vm.features.check_with_template(
                    "supported-feature.keyboard-layout", False):
                vm_info.vm.run('qubes-change-keyboard-layout')
            else:
                QMessageBox.warning(
                    self,
                    self.tr("Keyboard layout change unsupported"),
                    self.tr(
                        "Please update the qube {} or its template to the "
                        "newest version of Qubes tools.").format(
                        str(vm_info.vm)))

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_editfwrules_triggered')
    def action_editfwrules_triggered(self):
        for vm_info in self.get_selected_vms():
            self.open_settings(vm_info.vm, "firewall")

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_global_settings_triggered')
    def action_global_settings_triggered(self):  # pylint: disable=invalid-name
        with common_threads.busy_cursor():
            global_settings_window = global_settings.GlobalSettingsWindow(
                self.qt_app,
                self.qubes_app,
                self)
        global_settings_window.show()
        self.settings_windows['global_settings_window'] = global_settings_window

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_manage_templates_triggered')
    def action_manage_templates_triggered(self):
        subprocess.check_call('qubes-template-manager')

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_show_network_triggered')
    def action_show_network_triggered(self):
        pass
        # TODO: revive for 4.1
        # network_notes_dialog = NetworkNotesDialog()
        # network_notes_dialog.exec_()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_restore_triggered')
    def action_restore_triggered(self):
        with common_threads.busy_cursor():
            restore_window = restore.RestoreVMsWindow(self.qt_app,
                                                      self.qubes_app, self)
        restore_window.exec_()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_backup_triggered')
    def action_backup_triggered(self):
        with common_threads.busy_cursor():
            backup_window = backup.BackupVMsWindow(
                self.qt_app, self.qubes_app, self.dispatcher, self)
        backup_window.show()

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_exit_triggered')
    def action_exit_triggered(self):
        self.close()

    def set_compactview(self, checked):
        if checked:
            self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        else:
            self.toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if self.settings_loaded:
            self.manager_settings.setValue('view/compactview', checked)

    def showhide_menubar(self, checked):
        self.menubar.setVisible(checked)
        if not checked:
            self.context_menu.addAction(self.action_menubar)
        else:
            self.context_menu.removeAction(self.action_menubar)
        if self.settings_loaded:
            self.manager_settings.setValue('view/menubar_visible', checked)

    def showhide_toolbar(self, checked):
        self.toolbar.setVisible(checked)
        if not checked:
            self.context_menu.addAction(self.action_toolbar)
        else:
            self.context_menu.removeAction(self.action_toolbar)
        if self.settings_loaded:
            self.manager_settings.setValue('view/toolbar_visible', checked)

    def showhide_column(self, col_num, show):
        self.table.setColumnHidden(col_num, not show)
        col_name = self.qubes_model.columns_indices[col_num]
        self.manager_settings.setValue('columns/%s' % col_name, show)

    # noinspection PyArgumentList
    @pyqtSlot(name='on_action_about_qubes_triggered')
    def action_about_qubes_triggered(self):
        about = AboutDialog(self)
        about.exec_()

    def createPopupMenu(self):  # pylint: disable=invalid-name
        menu = QMenu()
        menu.addAction(self.action_toolbar)
        menu.addAction(self.action_menubar)
        return menu

    def open_tools_context_menu(self, widget, point):
        self.tools_context_menu.exec_(widget.mapToGlobal(point))

    @pyqtSlot('const QPoint&')
    def open_context_menu(self, point):
        self.context_menu.exec_(self.table.mapToGlobal(
            point + QPoint(10, 0)))

    def show_log(self):
        logfiles = []

        try:
            for vm_info in self.get_selected_vms():
                vm = vm_info.vm

                if vm.klass == 'AdminVM':
                    logfiles.append("/var/log/xen/console/hypervisor.log")
                else:
                    logfiles.extend([
                        "/var/log/xen/console/guest-" + vm.name + ".log",
                        "/var/log/xen/console/guest-" + vm.name + "-dm.log",
                        "/var/log/qubes/guid." + vm.name + ".log",
                        "/var/log/qubes/qrexec." + vm.name + ".log",
                    ])

            logfiles = [x for x in logfiles if path.exists(x)]

            if len(logfiles) > 0:
                log_dlg = log_dialog.LogDialog(self.qt_app, logfiles)
                log_dlg.exec_()
            else:
                QMessageBox.warning(
                    self,
                    self.tr("Error"),
                    self.tr(
                        "No log files were found for the selected qubes."))

        except exc.QubesDaemonAccessError:
            pass

def main():
    manager_utils.run_asynchronous(VmManagerWindow)


if __name__ == "__main__":
    main()
