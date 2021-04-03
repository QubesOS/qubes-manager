import asyncio
import collections
from datetime import datetime
import itertools
import json
import os
import typing

import PyQt5  # pylint: disable=import-error
import PyQt5.QtWidgets  # pylint: disable=import-error

from . import ui_qvmtemplate  # pylint: disable=no-name-in-module
from . import ui_templateinstallconfirmdlg  # pylint: disable=no-name-in-module
from . import ui_templateinstallprogressdlg  # pylint: disable=no-name-in-module
from . import utils

#pylint: disable=invalid-name

BASE_CMD = ['qvm-template', '--enablerepo=*', '--yes']

# singleton for "no date"
ZERO_DATE = datetime.utcfromtimestamp(0)

# pylint: disable=too-few-public-methods,inherit-non-class
class Template(typing.NamedTuple):
    status: str
    name: str
    evr: str
    reponame: str
    size: int
    buildtime: datetime
    installtime: typing.Optional[datetime]
    #licence: str
    #url: str
    #summary: str
    # ---- internal ----
    description: str
    default_status: str
    # ------------------

    COL_NAMES = [
        'Status',
        'Name',
        'Version',
        'Repository',
        'Download Size (MB)',
        'Build',
        'Install',
        #'License',
        #'URL',
        #'Summary'
    ]

    @staticmethod
    def build(status, entry):
        cli_format = '%Y-%m-%d %H:%M:%S'
        buildtime = datetime.strptime(entry['buildtime'], cli_format)
        if entry['installtime']:
            installtime = datetime.strptime(entry['installtime'], cli_format)
        else:
            installtime = ZERO_DATE
        return Template(
            status,
            entry['name'],
            '%s:%s-%s' % (entry['epoch'], entry['version'], entry['release']),
            entry['reponame'],
            int(entry['size']) // 1000000,
            buildtime,
            installtime,
            #entry['license'],
            #entry['url'],
            entry['description'],
            status
        )

class Action(typing.NamedTuple):
    op: str
    name: str
    evr: str

    TYPES = [str, str, str]
    COL_NAMES = ['Operation', 'Name', 'Version']

class TemplateStatusDelegate(PyQt5.QtWidgets.QStyledItemDelegate):
    OPS = [
        ['Installed', 'Reinstall', 'Remove'],
        ['Extra', 'Remove'],
        ['Upgradable', 'Upgrade', 'Remove'],
        ['Downgradable', 'Downgrade', 'Remove'],
        ['Available', 'Install']
    ]

    def createEditor(self, parent, option, index):
        _ = option # unused
        editor = PyQt5.QtWidgets.QComboBox(parent)
        # Otherwise the internalPointer can be overwritten with a QComboBox
        index = index.model().index(index.row(), index.column())
        kind = index.internalPointer().default_status
        for op_list in TemplateStatusDelegate.OPS:
            if op_list[0] == kind:
                for op in op_list:
                    editor.addItem(op)
                editor.currentIndexChanged.connect(self.currentIndexChanged)
                editor.showPopup()
                return editor
        return None

    def setEditorData(self, editor, index):
        #pylint: disable=no-self-use
        cur = index.data()
        idx = editor.findText(cur)
        if idx >= 0:
            editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        #pylint: disable=no-self-use
        model.setData(index, editor.currentText())

    def updateEditorGeometry(self, editor, option, index):
        #pylint: disable=no-self-use
        _ = index # unused
        editor.setGeometry(option.rect)

    @PyQt5.QtCore.pyqtSlot()
    def currentIndexChanged(self):
        self.commitData.emit(self.sender())

class TemplateModel(PyQt5.QtCore.QAbstractItemModel):
    def __init__(self):
        super().__init__()

        self.children = []

    def flags(self, index):
        if index.isValid() and index.column() == 0:
            return super().flags(index) | PyQt5.QtCore.Qt.ItemIsEditable
        return super().flags(index)

    def sort(self, idx, order):
        rev = (order == PyQt5.QtCore.Qt.AscendingOrder)
        self.children.sort(key=lambda x: x[idx], reverse=rev)

        self.dataChanged.emit(*self.row_index(0, self.rowCount() - 1))

    def index(self, row, column, parent=PyQt5.QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return PyQt5.QtCore.QModelIndex()

        return self.createIndex(row, column, self.children[row])

    def parent(self, child):
        #pylint: disable=no-self-use
        _ = child # unused
        return PyQt5.QtCore.QModelIndex()

    def rowCount(self, parent=PyQt5.QtCore.QModelIndex()):
        #pylint: disable=no-self-use
        _ = parent # unused
        return len(self.children)

    def columnCount(self, parent=PyQt5.QtCore.QModelIndex()):
        #pylint: disable=no-self-use
        _ = parent # unused
        return len(Template.COL_NAMES)

    def hasChildren(self, index=PyQt5.QtCore.QModelIndex()):
        #pylint: disable=no-self-use
        return index == PyQt5.QtCore.QModelIndex()

    def data(self, index, role=PyQt5.QtCore.Qt.DisplayRole):
        if index.isValid():
            data = self.children[index.row()][index.column()]
            if role == PyQt5.QtCore.Qt.DisplayRole:
                if data is ZERO_DATE:
                    return ''
                if isinstance(data, datetime):
                    return data.strftime('%d %b %Y')
                return data
            if role == PyQt5.QtCore.Qt.FontRole:
                font = PyQt5.QtGui.QFont()
                tpl = self.children[index.row()]
                font.setBold(tpl.status != tpl.default_status)
                return font
            if role == PyQt5.QtCore.Qt.TextAlignmentRole:
                if isinstance(data, int):
                    return PyQt5.QtCore.Qt.AlignRight
                return PyQt5.QtCore.Qt.AlignLeft
        return None

    def setData(self, index, value, role=PyQt5.QtCore.Qt.EditRole):
        if index.isValid() and role == PyQt5.QtCore.Qt.EditRole:
            old_list = list(self.children[index.row()])
            old_list[index.column()] = value
            new_tpl = Template(*old_list)
            self.children[index.row()] = new_tpl
            self.dataChanged.emit(index, index)
            return True
        return False

    def headerData(self, section, orientation,
            role=PyQt5.QtCore.Qt.DisplayRole):
        #pylint: disable=no-self-use
        if section < len(Template.COL_NAMES) \
                and orientation == PyQt5.QtCore.Qt.Horizontal \
                and role == PyQt5.QtCore.Qt.DisplayRole:
            return Template.COL_NAMES[section]
        return None

    def removeRows(self, row, count, parent=PyQt5.QtCore.QModelIndex()):
        _ = parent # unused
        self.beginRemoveRows(PyQt5.QtCore.QModelIndex(), row, row + count)
        del self.children[row:row+count]
        self.endRemoveRows()
        self.dataChanged.emit(*self.row_index(row, row + count))

    def row_index(self, low, high):
        return self.createIndex(low, 0), \
            self.createIndex(high, self.columnCount())

    def set_templates(self, templates):
        self.removeRows(0, self.rowCount())
        cnt = sum(len(g) for _, g in templates.items())
        self.beginInsertRows(PyQt5.QtCore.QModelIndex(), 0, cnt - 1)
        for status, grp in templates.items():
            for tpl in grp:
                self.children.append(Template.build(status, tpl))
        self.endInsertRows()
        self.dataChanged.emit(*self.row_index(0, self.rowCount() - 1))

    def get_actions(self):
        actions = []
        for tpl in self.children:
            if tpl.status != tpl.default_status:
                actions.append(Action(tpl.status, tpl.name, tpl.evr))
        return actions

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
        # Default type is dict as we're going to replace the lists with
        # dicts shortly after
        tpls = collections.defaultdict(dict, json.loads(output))
        # Remove duplicates
        # Should this be done in qvm-template?
        # TODO: Merge templates with same name?
        #       If so, we may need to have a separate UI to force versions.
        local_names = set(x['name'] for x in tpls['installed'])
        # Convert to dict for easier subtraction
        for key in tpls:
            tpls[key] = {
                (x['name'], x['epoch'], x['version'], x['release']): x
                for x in tpls[key]}
        tpls['installed'] = {
            k: v for k, v in tpls['installed'].items()
                if k not in tpls['extra'] and k not in tpls['upgradable']}
        tpls['available'] = {
            k: v for k, v in tpls['available'].items()
                if k not in tpls['installed']
                    and k not in tpls['upgradable']}
        # If the package name is installed but the specific version is
        # neither installed or an upgrade, then it must be a downgrade
        tpls['downgradable'] = {
            k: v for k, v in tpls['available'].items()
                if k[0] in local_names}
        tpls['available'] = {
            k: v for k, v in tpls['available'].items()
                if k not in tpls['downgradable']}
        # Convert back to list
        tpls = {k.title(): list(v.values()) for k, v in tpls.items()}
        self.set_templates(tpls)
        return True, None

class TemplateInstallConfirmDialog(
        ui_templateinstallconfirmdlg.Ui_TemplateInstallConfirmDlg,
        PyQt5.QtWidgets.QDialog):
    def __init__(self, actions):
        super().__init__()
        self.setupUi(self)

        model = PyQt5.QtGui.QStandardItemModel()
        model.setHorizontalHeaderLabels(Action.COL_NAMES)
        self.treeView.setModel(model)

        for act in actions:
            model.appendRow([PyQt5.QtGui.QStandardItem(x) for x in act])

class TemplateInstallProgressDialog(
        ui_templateinstallprogressdlg.Ui_TemplateInstallProgressDlg,
        PyQt5.QtWidgets.QDialog):
    def __init__(self, actions):
        super().__init__()
        self.setupUi(self)
        self.actions = actions
        self.buttonBox.hide()

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
            self.actions.sort()
            for oper, grp in itertools.groupby(self.actions, lambda x: x[0]):
                oper = oper.lower()
                # No need to specify versions for local operations
                if oper in ('remove', 'purge'):
                    specs = [x.name for x in grp]
                else:
                    specs = [x.name + '-' + x.evr for x in grp]
                # FIXME: (C)Python versions before 3.9 fully-buffers stderr in
                #        this context, cf. https://bugs.python.org/issue13601
                #        Forcing it to be unbuffered for the time being so that
                #        the messages can be displayed in time.
                envs = os.environ.copy()
                envs['PYTHONUNBUFFERED'] = '1'
                proc = await asyncio.create_subprocess_exec(
                    *(BASE_CMD + [oper, '--'] + specs),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=envs)
                #pylint: disable=cell-var-from-loop
                status_text = ''
                while True:
                    line = await proc.stdout.read(100)
                    if line == b'':
                        break
                    line = line.decode('UTF-8')
                    status_text = self._process_cr(status_text + line)
                    self.textEdit.setPlainText(status_text)
                if await proc.wait() != 0:
                    self.buttonBox.show()
                    self.progressBar.setMaximum(100)
                    self.progressBar.setValue(0)
                    return False
            self.progressBar.setMaximum(100)
            self.progressBar.setValue(100)
            self.buttonBox.show()
            return True
        asyncio.create_task(coro())

class QvmTemplateWindow(
        ui_qvmtemplate.Ui_QubesTemplateManager,
        PyQt5.QtWidgets.QMainWindow):
    def __init__(self, qt_app, qubes_app, dispatcher, parent=None):
        _ = parent # unused

        super().__init__()
        self.setupUi(self)

        self.qubes_app = qubes_app
        self.qt_app = qt_app
        self.dispatcher = dispatcher

        self.listing_model = TemplateModel()
        self.listing_delegate = TemplateStatusDelegate(self.listing)

        self.listing.setModel(self.listing_model)
        self.listing.setItemDelegateForColumn(0, self.listing_delegate)

        self.refresh(False)
        self.listing.setItemDelegateForColumn(0, self.listing_delegate)
        self.listing.selectionModel() \
            .selectionChanged.connect(self.update_info)

        self.actionRefresh.triggered.connect(lambda: self.refresh(True))
        self.actionInstall.triggered.connect(self.do_install)

    def update_info(self, selected):
        _ = selected # unused
        indices = [
            x
            for x in self.listing.selectionModel().selectedIndexes()
            if x.column() == 0]
        if len(indices) == 0:
            return
        self.infobox.clear()
        cursor = PyQt5.QtGui.QTextCursor(self.infobox.document())
        bold_fmt = PyQt5.QtGui.QTextCharFormat()
        bold_fmt.setFontWeight(PyQt5.QtGui.QFont.Bold)
        norm_fmt = PyQt5.QtGui.QTextCharFormat()
        if len(indices) > 1:
            cursor.insertText('Selected templates:\n', bold_fmt)
            for idx in indices:
                tpl = self.listing_model.children[idx.row()]
                cursor.insertText(tpl.name + '-' + tpl.evr + '\n', norm_fmt)
        else:
            idx = indices[0]
            tpl = self.listing_model.children[idx.row()]
            cursor.insertText('Name: ', bold_fmt)
            cursor.insertText(tpl.name + '\n', norm_fmt)
            cursor.insertText('Description:\n', bold_fmt)
            cursor.insertText(tpl.description + '\n', norm_fmt)

    def refresh(self, refresh=True):
        self.progressBar.show()
        async def coro():
            ok, stderr = await self.listing_model.refresh(refresh)
            self.infobox.clear()
            if not ok:
                cursor = PyQt5.QtGui.QTextCursor(self.infobox.document())
                fmt = PyQt5.QtGui.QTextCharFormat()
                fmt.setFontWeight(PyQt5.QtGui.QFont.Bold)
                cursor.insertText('Failed to fetch template list:\n', fmt)
                fmt.setFontWeight(PyQt5.QtGui.QFont.Normal)
                cursor.insertText(stderr, fmt)
            self.progressBar.hide()
        asyncio.create_task(coro())

    def do_install(self):
        actions = self.listing_model.get_actions()
        confirm = TemplateInstallConfirmDialog(actions)
        if confirm.exec_():
            progress = TemplateInstallProgressDialog(actions)
            progress.install()
            progress.exec_()
        self.refresh()

def main():
    utils.run_asynchronous(QvmTemplateWindow)

if __name__ == '__main__':
    main()
