from PyQt4.QtCore import *
from PyQt4.QtGui import *
from .ui_multiselectwidget import *

class MultiSelectWidget(Ui_MultiSelectWidget, QWidget):

    __pyqtSignals__ = ("selected_changed()",)
    __pyqtSignals__ = ("items_added(PyQt_PyObject)",)
    __pyqtSignals__ = ("items_removed(PyQt_PyObject)",)

    def __init__(self, parent=None):
        super(MultiSelectWidget, self).__init__()
        self.setupUi(self)
        self.add_selected_button.clicked.connect(self.add_selected)
        self.add_all_button.clicked.connect(self.add_all)
        self.remove_selected_button.clicked.connect(self.remove_selected)
        self.remove_all_button.clicked.connect(self.remove_all)
        self.available_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def switch_selected(self, src, dst):
        selected = src.selectedItems()
        items = []

        for s in selected:
            row = src.indexFromItem(s).row()
            item = src.takeItem(row)
            dst.addItem(item)
            items.append(item)
        dst.sortItems()
        self.emit(SIGNAL("selected_changed()"))
        if src is self.selected_list:    
            self.emit(SIGNAL("items_removed(PyQt_PyObject)"), items)
        else:
            self.emit(SIGNAL("items_added(PyQt_PyObject)"), items)

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
        self.emit(SIGNAL("selected_changed()"))
        if src is self.selected_list:    
            self.emit(SIGNAL("items_removed(PyQt_PyObject)"), items)
        else:
            self.emit(SIGNAL("items_added(PyQt_PyObject)"), items)


    def add_all(self):
        self.move_all(self.available_list, self.selected_list)

    def remove_all(self):
        self.move_all(self.selected_list, self.available_list)

    def clear(self):
        self.available_list.clear()
        self.selected_list.clear()

