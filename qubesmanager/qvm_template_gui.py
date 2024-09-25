# -*- encoding: utf8 -*-
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2023 Marta Marczykowska-Górecka
#                               <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.

# disabling invalid name checking due to amount of Qt functions that
# need to be overwritten and have a camelCase name
# pylint: disable=invalid-name

import abc
import asyncio
import collections
import functools
import subprocess
import threading
from datetime import datetime
from datetime import UTC
import json
import os
import typing
import shlex

import PyQt6  # pylint: disable=import-error
import PyQt6.QtWidgets  # pylint: disable=import-error
import PyQt6.QtCore  # pylint: disable=import-error
import PyQt6.QtGui  # pylint: disable=import-error

from . import ui_templateinstallconfirmdlg  # pylint: disable=no-name-in-module
from . import ui_templateinstallprogressdlg  # pylint: disable=no-name-in-module
from . import ui_qvmtemplate # pylint: disable=no-name-in-module
from . import utils
from qui.utils import EOL_DATES, SUFFIXES # pylint: disable=import-error

# this is needed for icons to actually work
# pylint: disable=unused-import
from . import resources

BASE_CMD = ['qvm-template', '--yes']

# singleton for "no date"
ZERO_DATE = datetime.fromtimestamp(0, UTC)

tr = functools.partial(PyQt6.QtCore.QCoreApplication.translate, "Template GUI")

HELP_TEXT = tr("""
This tool can be used to manage templates on your system. \

Installed templates are the ones currently present in the system - you \
can update or remove them here. Caution: updating a template is different from \
updating its contents - in most cases you want to normally run the Qubes \
Update tool to update the packages withing your templates. However, \
if a template is for some reason malfunctioning, you can try to upgrade it \
here, replacing the existing template with a newer release, or reinstall it - \
but remember that both of those operations replace your template with a fresh \
copy and all of your changes will be lost.

Available templates are the templates available online - from official Qubes \
OS repositories and, if enabled, from community repositories. After installing \
a new template, you can switch your qubes to use it quickly using the \
Template Switcher tool. 

This tool only displays templates installed from repositories, not any cloned \
or manually-installed templates.
""")


class TreeItem(abc.ABC):
    COL_NAMES = [
        'Name',
        'Status',
        'Version',
        'Repository',
    ]

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Verbose description of the item"""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Item name"""

    @property
    def full_name(self) -> str:
        """Extended name, used as a parameter for template modification
        commands"""
        return self.name

    @property
    @abc.abstractmethod
    def children(self) -> typing.List['TreeItem']:
        """Item's children"""

    @property
    @abc.abstractmethod
    def parent(self) -> 'TreeItem':
        """Parent of this item"""

    def get_installable(self) -> bool:
        return False

    def get_reinstallable(self) -> bool:
        return False

    def get_uninstallable(self) -> bool:
        return False

    def get_upgradable(self) -> bool:
        return False

    def status(self, role):  # pylint: disable=unused-argument
        return None

    def version(self):
        return None

    def repository(self):
        return None


class Template(TreeItem):
    def __init__(self, entry: dict):
        self.template_status: str = entry['status']
        self.template_name: str = entry['name']

        cli_format = '%Y-%m-%d %H:%M:%S'

        self.build_time = datetime.strptime(entry['buildtime'], cli_format)

        self.install_time: typing.Optional[str] = None
        if entry['installtime']:
            self.install_time = datetime.strptime(entry['installtime'],
                                                  cli_format)
        else:
            self.install_time = None

        self.version_release: str = '%s:%s-%s' % (entry['epoch'],
                                                  entry['version'],
                                                  entry['release'])
        self.repository_name: str = entry['reponame']
        self.size: int = int(entry['size']) // 1000000
        self.license = entry['license']
        # install_size
        self._description = entry['description']
        self._parent = None

        self.system_eol_date = None
        self.newest_available_version = entry.get('upgraded_version',
                                                  self.version_release)

    @property
    def description(self) -> str:
        text = tr("<b>Template name:</b> ") + self.template_name + '<br>'
        text += tr("<b>Version:</b> ") + self.version_release + '<br>'
        text += tr("<b>Repository:</b> ") + self.repository_name + '<br>'
        text += tr("<b>License:</b> ") + self.license + "<br><br>"

        if self.installed:
            status = tr("yes")
        else:
            status = tr("no")
        if self.template_status == "extra":
            status += tr(" (local template, not available from repositories)")

        text += tr("<b>Installed:</b> ") + status + '<br>'
        if self.installed:
            text += tr("<b>Template upgrade available: </b>")
            if self.template_status == 'upgradable':
                text += tr("yes, newest available version: " +
                           self.newest_available_version + "<br>")
            else:
                text += tr("no <br>")

        if self.obsolete():
            text += tr("<b>THIS TEMPLATE IS NO LONGER SUPPORTED AND WILL "
                       "NOT RECEIVE SECURITY UPDATES</b><br>")

        text += '<br>'
        if self.size > 1000:
            size_txt = str(self.size / 1000) + " GB"
        else:
            size_txt = str(self.size) + " MB"
        text += tr("<b>Download size:</b> ") + size_txt + "<br>"
        text += tr("<b>Build time:</b> ") + self.build_time.strftime(
            "%Y-%m-%d %H:%M") + "<br>"
        if self.install_time:
            text += tr("<b>Install time:</b> ") + self.install_time.strftime(
                "%Y-%m-%d %H:%M") + "<br>"
        text += "<br>"
        text += self._description
        return text

    @property
    def name(self) -> str:
        return self.template_name

    @property
    def full_name(self) -> str:
        return self.template_name + "-" + self.version_release

    @property
    def children(self) -> typing.List['TreeItem']:
        """Children of this item"""
        return []

    def set_parent(self, parent: TreeItem):
        self._parent = parent

    @property
    def parent(self) -> 'TreeItem':
        """Parent of this item"""
        return self._parent

    @property
    def installed(self) -> bool:
        return self.template_status != 'available'

    def get_installable(self) -> bool:
        return self.template_status == 'available'

    def get_reinstallable(self) -> bool:
        return self.template_status in ["installed", "downgrade"]

    def get_uninstallable(self) -> bool:
        return self.template_status in ["installed", "extra", "upgradable",
                                        "downgrade"]

    def get_upgradable(self) -> bool:
        return self.template_status == 'upgradable'

    def status(self, role):
        # pylint: disable=too-many-return-statements
        if self.obsolete():
            if role == PyQt6.QtCore.Qt.ItemDataRole.ToolTipRole:
                return tr("This template is obsolete and no longer receives "
                          "updates")
            if role == PyQt6.QtCore.Qt.ItemDataRole.DecorationRole:
                return ":/obsolete.svg"
        if self.template_status == 'extra':
            if role == PyQt6.QtCore.Qt.ItemDataRole.ToolTipRole:
                return tr("This template is a local template, not installed "
                          "from a repository")
            if role == PyQt6.QtCore.Qt.ItemDataRole.DecorationRole:
                return ':/checkmark-with-plus.svg'
        if self.template_status in ['installed', 'upgradable']:
            if role == PyQt6.QtCore.Qt.ItemDataRole.ToolTipRole:
                return tr("This template is installed")
            if role == PyQt6.QtCore.Qt.ItemDataRole.DecorationRole:
                return ':/checkmark.svg'
        return None

    def version(self):
        return self.version_release

    def repository(self):
        return self.repository_name

    def obsolete(self) -> bool:
        name = self.template_name
        if self.system_eol_date:
            return self.system_eol_date < datetime.now()
        for suffix in SUFFIXES:
            name = name.removesuffix(suffix)
        eol_string = EOL_DATES.get(name, None)
        if not eol_string:
            return False
        eol = datetime.strptime(eol_string, '%Y-%m-%d')
        return eol < datetime.now()


class DescriptiveItem(TreeItem):
    NAMES = {
        tr("Installed"): tr("Installed templates"),
        tr("Available"): tr("Available templates"),
        tr("Downgradable"): tr("Template downgrades")
    }
    DESCRIPTIONS = {
        tr("Installed"):
            tr("Templates in this group are currently installed in your "
               "system. Templates may come from official or unofficial "
               "repositories (the default and recommended way of installing "
               "templates), but you might also encounter templates installed "
               "from RPM packages, especially if some of your templates are "
               "restored from older Qubes OS versions."),
        tr("Available"):
            tr("Templates in this group are available from repositories "
               "online. Templates that come from ITL repository are "
               "officially supported by the Qubes OS team, while templates "
               "from the Community repository are maintained by the members "
               "of the community. You can adjust which repositories to use in "
               "Global Settings - Update - Template Repository Settings."),
        tr("Downgradable"):
            tr("Templates in this group are old versions of templates you "
               "already have installed. It is not recommended to install them.")
    }

    def __init__(self, name):
        self._name = name
        self._children: typing.List[TreeItem] = []
        self._parent = PyQt6.QtCore.QModelIndex()

    @property
    def name(self) -> str:
        return self.NAMES.get(self._name, self._name)

    @property
    def description(self) -> str:
        return self.DESCRIPTIONS.get(self._name, self._name)

    @property
    def children(self) -> typing.List[TreeItem]:
        return self._children

    @property
    def parent(self) -> TreeItem:
        return self._parent


class TemplateModel(PyQt6.QtCore.QAbstractItemModel):
    def __init__(self, qubes_app):
        super().__init__()
        self.qubes_app = qubes_app
        self.children = []

    def index(self, row, column, parent=PyQt6.QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return PyQt6.QtCore.QModelIndex()
        if not parent.isValid():
            child_item = self.children[row]
        else:
            child_item = parent.internalPointer().children[row]
        return self.createIndex(row, column, child_item)

    def parent(self, child_index: PyQt6.QtCore.QModelIndex):
        node = PyQt6.QtCore.QModelIndex()
        if child_index.isValid():
            own_object = child_index.internalPointer()
            if own_object is not None:
                parent = own_object.parent
                if not parent:
                    return node
                if parent != node:
                    # thankfully we have only one level of depth
                    row = self.children.index(parent)
                    node = self.createIndex(row, 0, parent)
        return node

    def rowCount(self, parent=PyQt6.QtCore.QModelIndex()):
        if parent.internalPointer():
            return len(parent.internalPointer().children)
        return len(self.children)

    def columnCount(self, _parent=PyQt6.QtCore.QModelIndex()):
        return len(Template.COL_NAMES)

    def data(self, index, role=PyQt6.QtCore.Qt.ItemDataRole.DisplayRole):
        # pylint: disable=too-many-return-statements
        if index.isValid():
            data = index.internalPointer()
            if role == PyQt6.QtCore.Qt.ItemDataRole:
                return data.description
            if role == PyQt6.QtCore.Qt.ItemDataRole.DisplayRole:
                if index.column() == 0:
                    return data.name
                if index.column() == 1:
                    return None
                if index.column() == 2:
                    return data.version()
                if index.column() == 3:
                    return data.repository()
                return data.name
            if role == PyQt6.QtCore.Qt.ItemDataRole.ToolTipRole:
                if index.column() == 0:
                    return "Template name"
                if index.column() == 1:
                    return data.status(role)
                if index.column() == 2:
                    return "Template version"
                if index.column() == 3:
                    return "Repository"
            if role == PyQt6.QtCore.Qt.ItemDataRole.TextAlignmentRole:
                if isinstance(data, int):
                    return PyQt6.QtCore.Qt.AlignmentFlag.AlignRight
                return PyQt6.QtCore.Qt.AlignmentFlag.AlignLeft
            if role == PyQt6.QtCore.Qt.ItemDataRole.DecorationRole:
                if index.column() == 1:
                    icon_name = data.status(role)
                    if icon_name:
                        return PyQt6.QtGui.QIcon(icon_name)
            if role == PyQt6.QtCore.Qt.ItemDataRole.UserRole:
                return data
        return None

    def headerData(self, section, orientation,
                   role=PyQt6.QtCore.Qt.ItemDataRole.DisplayRole):
        if section < len(Template.COL_NAMES) \
                and orientation == PyQt6.QtCore.Qt.Orientation.Horizontal \
                and role == PyQt6.QtCore.Qt.ItemDataRole.DisplayRole:
            return Template.COL_NAMES[section]
        return None

    def removeRows(self, row, count, _parent=PyQt6.QtCore.QModelIndex()):
        self.beginRemoveRows(PyQt6.QtCore.QModelIndex(), row, row + count)
        del self.children[row:row+count]
        self.endRemoveRows()
        self.dataChanged.emit(*self.row_index(row, row + count))

    def row_index(self, low, high):
        return self.createIndex(low, 0), \
            self.createIndex(high, self.columnCount())

    async def refresh(self, refresh=True):
        cmd = BASE_CMD[:]
        if refresh:
            # Force refresh if triggered by button press
            cmd.append('--refresh')
        cmd.extend(['info', '--machine-readable-json', '--installed',
                    '--available', '--upgrades', '--extras'])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)
        output, stderr = await proc.communicate()
        output = output.decode('ASCII')
        if proc.returncode != 0:
            stderr = stderr.decode('ASCII')
            return False, stderr
        # remove old rows
        rows_to_remove = len(self.children)
        self.beginRemoveRows(PyQt6.QtCore.QModelIndex(), 0,
                             rows_to_remove)
        self.children = []
        self.endRemoveRows()
        self.dataChanged.emit(*self.row_index(0, rows_to_remove))

        # Default type is dict as we're going to replace the lists with
        # dicts shortly after
        tpls = collections.defaultdict(dict, json.loads(output))
        # TODO: Merge templates with same name?
        #       If so, we may need to have a separate UI to force versions.

        local_names = set(x['name'] for x in tpls['installed'])

        # Convert to dict for easier subtraction
        for key in tpls:
            tpls[key] = {
                (x['name']): x for x in tpls[key]}
            for x in tpls[key].values():
                x['status'] = key  # add status info to templates
        # if a template is 'extra' or 'upgradable', adjust the status
        # accordingly

        for k in tpls['extra'].keys():
            if k in tpls['installed']:
                tpls['installed'][k]['status'] = 'extra'
        for k, v in tpls['upgradable'].items():
            if k in tpls['installed']:
                tpls['installed'][k]['status'] = 'upgradable'
                tpls['installed'][k]['upgraded_version'] = (
                        '%s:%s-%s' % (v['epoch'], v['version'], v['release']))

        # create available list
        tpls['available'] = {
            k: v for k, v in tpls['available'].items()
                if k not in tpls['installed']
                    and k not in tpls['upgradable']}

        # If the package name is installed but the specific version is
        # neither installed or an upgrade, then it must be a downgrade

        tpls['downgradable'] = {
            k: v for k, v in tpls['available'].items()
            if k in local_names}
        tpls['available'] = {
            k: v for k, v in tpls['available'].items()
            if k not in tpls['downgradable']}
        # remove obsolete keys
        del tpls['upgradable']
        del tpls['extra']

        eol_dates = {}
        # collect eol dates
        for vm in self.qubes_app.domains:
            os_eol = vm.features.get('os-eol', None)
            tpl_name = vm.features.get('template-name', None)
            if os_eol and tpl_name:
                eol_dates[tpl_name] = datetime.strptime(os_eol, '%Y-%m-%d')

        # Convert back to list
        tpls = {k.title(): list(v.values()) for k, v in tpls.items()}
        self.beginInsertRows(PyQt6.QtCore.QModelIndex(), 0, len(tpls) - 1)
        for template_type, template_list in tpls.items():
            if not template_list:
                continue
            itm = DescriptiveItem(template_type)
            self.children.append(itm)
            for template in template_list:
                template_item = Template(template)
                if template_item.template_name in eol_dates:
                    template_item.system_eol_date = eol_dates[
                        template_item.template_name]
                template_item.set_parent(itm)
                itm.children.append(template_item)
        self.dataChanged.emit(*self.row_index(0, self.rowCount() - 1))
        self.endInsertRows()
        return True, None


class TemplateInstallConfirmDialog(
        ui_templateinstallconfirmdlg.Ui_TemplateInstallConfirmDlg,
        PyQt6.QtWidgets.QDialog):
    # pylint: disable=too-few-public-methods
    def __init__(self, question: str, operation_name: str,
                 palette: PyQt6.QtGui.QPalette, enable_warn: bool = False):
        super().__init__()
        self.setupUi(self)

        self.desc_label.setText(question)
        self.warn_label.setVisible(enable_warn)

        ok_button = self.button_box.addButton(
            operation_name,
            PyQt6.QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        ok_button.setPalette(palette)

        self.button_box.addButton(
            "Cancel",
            PyQt6.QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)


class TemplateInstallProgressDialog(
        ui_templateinstallprogressdlg.Ui_TemplateInstallProgressDlg,
        PyQt6.QtWidgets.QDialog):
    def __init__(self, command: typing.List[str],
                 palette: PyQt6.QtGui.QPalette,
                 window_title: typing.Optional[str] = None):
        """
        :param command: a list of strings containing the command to be used
        by this process
        """
        super().__init__()
        self.setupUi(self)
        self.command = command
        self.qubes_palette = palette
        self.window().setWindowTitle(window_title)

        # currently this button does nothing
        # self.cancel_button = self.button_box.addButton(
        #     "Abort",
        #     PyQt6.QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)

    def add_ok_button(self, error: bool = False):
        """Replace the "Cancel" button with OK or "Close" button"""
        # self.button_box.removeButton(self.cancel_button)
        ok_button: PyQt6.QtWidgets.QPushButton = self.button_box.addButton(
            "Close" if error else "OK",
            PyQt6.QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        if not error:
            ok_button.setPalette(self.qubes_palette)

    @staticmethod
    def _process_cr(text):
        """Reduce lines replaced using CR character (\r)"""
        while '\r' in text:
            prefix, suffix = text.rsplit('\r', 1)
            if '\n' in prefix:
                prefix = prefix.rsplit('\n', 1)[0]
                prefix += '\n'
            else:
                prefix = ''
            text = prefix + suffix
        return text

    def install(self):
        async def coro():
            # FIXME: (C)Python versions before 3.9 fully-buffers stderr in
            #        this context, cf. https://bugs.python.org/issue13601
            #        Forcing it to be unbuffered for the time being so that
            #        the messages can be displayed in time.
            envs = os.environ.copy()
            envs['PYTHONUNBUFFERED'] = '1'
            proc = await asyncio.create_subprocess_exec(
                *self.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=envs)
            status_text = ''
            while True:
                line = await proc.stdout.read(100)
                if line == b'':
                    break
                line = line.decode('UTF-8')
                status_text = self._process_cr(status_text + line)
                self.textEdit.setPlainText(status_text)
            result = await proc.wait() == 0
            if not result:
                self.textEdit.setHtml(
                    status_text.replace("\n", "<br />") +
                    "<br /><font color='red'>ERROR PERFORMING OPERATION</font>")
            self.add_ok_button(error=not result)
            self.progressBar.setMaximum(100)
            self.progressBar.setValue(100 if result else 0)
            return result
        asyncio.create_task(coro())


class QvmTemplateWindow(
        ui_qvmtemplate.Ui_MainWindow,
        PyQt6.QtWidgets.QMainWindow):
    def __init__(self, qt_app, qubes_app, dispatcher, _parent=None):
        super().__init__()
        self.setupUi(self)
        self.template_tree.header().setSectionResizeMode(
            PyQt6.QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

        self.qubes_app = qubes_app
        self.qt_app: PyQt6.QtWidgets.QApplication = qt_app
        self.qt_app.setWindowIcon(PyQt6.QtGui.QIcon.fromTheme("qubes-manager"))
        self.dispatcher = dispatcher

        self.template_model = TemplateModel(self.qubes_app)
        self.template_tree.setModel(self.template_model)

        self.template_tree.selectionModel() \
            .selectionChanged.connect(self.template_selected)

        self.template_info.setText(HELP_TEXT)
        self.install_button.setVisible(False)
        self.uninstall_button.setVisible(False)
        self.reinstall_button.setVisible(False)
        self.upgrade_button.setVisible(False)

        self.install_button.pressed.connect(self.do_install)
        self.uninstall_button.pressed.connect(self.do_uninstall)
        self.reinstall_button.pressed.connect(self.do_reinstall)
        self.upgrade_button.pressed.connect(self.do_upgrade)

        self.refresh(False)

        self.actionRefreshRepositoryData.triggered.connect(
            lambda: self.refresh(True))
        self.actionHelp.triggered.connect(self.show_help)
        self.actionTemplate_switcher.triggered.connect(
            lambda: self.run_in_background("qubes-template-manager"))
        self.actionRepository_settings.triggered.connect(
            self.open_global_config)

        self.qubes_palette = self.initialize_styles()

    def initialize_styles(self):
        qubes_style_buttons = [self.upgrade_button, self.install_button,
                               self.reinstall_button, self.uninstall_button]
        palette = self.qt_app.palette()
        palette.setColor(PyQt6.QtGui.QPalette.ColorRole.Button,
                         PyQt6.QtGui.QColor("#4180c9"))
        palette.setColor(PyQt6.QtGui.QPalette.ColorRole.ButtonText,
                         PyQt6.QtGui.QColor("#ffffff"))

        for button in qubes_style_buttons:
            button.setPalette(palette)

        return palette

    def show_help(self):
        """Action on pressing Help button"""
        self.template_tree.selectionModel().clearSelection()
        self._show_help()

    def _show_help(self):
        self.template_info.setText(HELP_TEXT)
        self.install_button.setVisible(False)
        self.uninstall_button.setVisible(False)
        self.reinstall_button.setVisible(False)
        self.upgrade_button.setVisible(False)

    def run_in_background(self, command):
        """
        Run a given process in background (non-blocking)
        """
        if isinstance(command, str):
            command = shlex.split(command)
        # pylint: disable=consider-using-with
        p = subprocess.Popen(command)
        threading.Thread(target=p.wait, daemon=True).start()

    def open_global_config(self, *_args):
        """
        Run global config in foreground (blocking)
        """
        subprocess.call('qubes-global-config')
        self.refresh()

    def _get_selected_item(self) -> typing.Optional[TreeItem]:
        selected_indexes = self.template_tree.selectionModel().selectedIndexes()
        if not selected_indexes:
            return None
        # we just grab the first item, because we don't care about details
        # and the selection model is single-row
        selected_item = selected_indexes[0]
        item = self.template_model.data(selected_item,
                                        PyQt6.QtCore.Qt.ItemDataRole.UserRole)
        return item

    def template_selected(self, _selected: PyQt6.QtCore.QItemSelection):
        item = self._get_selected_item()
        if not item:
            self._show_help()
            return
        self.template_info.setText(item.description)

        self.install_button.setVisible(item.get_installable())
        self.reinstall_button.setVisible(item.get_reinstallable())
        self.uninstall_button.setVisible(item.get_uninstallable())
        self.upgrade_button.setVisible(item.get_upgradable())

    def _do_action(self, command: typing.List[str], operation_name: str,
                   question: str, enable_warn: bool = False, window_title:
                   typing.Optional[str] = None):
        """
        :param command: a list of strings representing the operation to perform
        :operation name: what should be on the confirmation button
        :param question: what should we ask the user in confirmation dialog?
        :param enable_warn: should the confirm dialog warn about discarding
        local changes?
        """
        confirm = TemplateInstallConfirmDialog(question, operation_name,
                                               self.qubes_palette,
                                               enable_warn)
        if confirm.exec():
            progress = TemplateInstallProgressDialog(command,
                                                     self.qubes_palette,
                                                     window_title)
            progress.install()
            progress.exec()
            self.refresh()

    def do_uninstall(self):
        item = self._get_selected_item()
        command = BASE_CMD + ['remove', '--'] + [item.name]
        question = (self.tr("Are you sure you want to remove template <b>{"
                    "}</b>?")).format(item.name)
        self._do_action(command, self.tr("Uninstall ") + item.name,
                        question, True,
                        self.tr("Uninstalling template..."))

    def do_install(self):
        item = self._get_selected_item()
        command = BASE_CMD + ['install', '--'] + [item.full_name]
        question = (self.tr("Are you sure you want to install template <b>{"
                    "}</b>?")).format(item.name)
        self._do_action(command, self.tr("Install ") + item.name,
                        question, False)

    def do_reinstall(self):
        item = self._get_selected_item()
        command = BASE_CMD + ['reinstall', '--'] + [item.full_name]
        question = (self.tr("Are you sure you want to reinstall template <b>{"
                    "}</b>?")).format(item.name)
        self._do_action(command, self.tr("Reinstall ") + item.name ,
                        question,True)

    def do_upgrade(self):
        item = self._get_selected_item()
        command = BASE_CMD + ['upgrade', '--'] + [item.name]
        question = (self.tr("Are you sure you want to reinstall and upgrade "
                            "template <b>{"
                    "}</b>?")).format(item.name)
        self._do_action(command, self.tr("Reinstall and upgrade ") + item.name,
                        question, True)

    def refresh(self, refresh=True):
        self.label_loading.setVisible(True)
        self.info_frame.setVisible(False)
        self.template_tree.setVisible(False)

        # deselect whatever is selected
        self.template_tree.selectionModel().clearSelection()

        async def coro():
            ok, stderr = await self.template_model.refresh(refresh)
            if not ok:
                PyQt6.QtWidgets.QMessageBox.warning(
                    self,
                    self.tr('Failed to fetch template list!'),
                    self.tr('Failed to fetch template list: \n') + stderr
                )
            self.label_loading.setVisible(False)
            self.info_frame.setVisible(True)
            self.template_tree.setVisible(True)
            self.template_tree.expandAll()
            self.template_tree.resizeColumnToContents(0)
            self.template_tree.resizeColumnToContents(1)

        asyncio.create_task(coro())


def main():
    utils.run_asynchronous(QvmTemplateWindow)


if __name__ == '__main__':
    main()
