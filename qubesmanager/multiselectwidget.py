# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only



from PyQt5 import QtCore, QtWidgets  # pylint: disable=import-error
from . import ui_multiselectwidget  # pylint: disable=no-name-in-module


class MultiSelectWidget(
        ui_multiselectwidget.Ui_MultiSelectWidget, QtWidgets.QWidget):

    selectedChanged = QtCore.pyqtSignal()
    itemsAdded = QtCore.pyqtSignal(list)
    itemsRemoved = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)
        self.add_selected_button.clicked.connect(self.add_selected)
        self.add_all_button.clicked.connect(self.add_all)
        self.remove_selected_button.clicked.connect(self.remove_selected)
        self.remove_all_button.clicked.connect(self.remove_all)
        self.available_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        self.selected_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)

    def switch_selected(self, src, dst):
        selected = src.selectedItems()
        items = []

        for selected_item in selected:
            row = src.indexFromItem(selected_item).row()
            item = src.takeItem(row)
            dst.addItem(item)
            items.append(item)
        dst.sortItems()
        self.selectedChanged.emit()
        if src is self.selected_list:
            self.itemsRemoved.emit(items)
        else:
            self.itemsAdded.emit(items)

    def add_selected(self):
        self.switch_selected(self.available_list, self.selected_list)

    def remove_selected(self):
        self.switch_selected(self.selected_list, self.available_list)

    def move_all(self, src, dst):
        items = []
        while src.count() > 0:
            item = src.takeItem(0)
            dst.addItem(item)
            items.append(item)
        dst.sortItems()
        self.selectedChanged.emit()
        if src is self.selected_list:
            self.itemsRemoved.emit(items)
        else:
            self.itemsAdded.emit(items)

    def add_all(self):
        self.move_all(self.available_list, self.selected_list)

    def remove_all(self):
        self.move_all(self.selected_list, self.available_list)

    def clear(self):
        self.available_list.clear()
        self.selected_list.clear()
