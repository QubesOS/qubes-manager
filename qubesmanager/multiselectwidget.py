import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from ui_multiselectwidget import *

class MultiSelectWidget(Ui_MultiSelectWidget, QWidget):

    def __init__(self, parent=None):
        super(MultiSelectWidget, self).__init__()
        self.setupUi(self);
        self.add_selected_button.clicked.connect(self.add_selected)
        self.add_all_button.clicked.connect(self.add_all)
        self.remove_selected_button.clicked.connect(self.remove_selected)
        self.remove_all_button.clicked.connect(self.remove_all)
        self.available_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def switch_selected(self, src, dst):
        selected = src.selectedItems()

        for s in selected:
            row = src.indexFromItem(s).row()
            item = src.takeItem(row)
            dst.addItem(item)
        dst.sortItems()

    def add_selected(self):
        self.switch_selected(self.available_list, self.selected_list)

    def remove_selected(self):
        self.switch_selected(self.selected_list, self.available_list)        

    def move_all(self, src, dst):
        while src.count() > 0:
            item = src.takeItem(0)
            dst.addItem(item)
        dst.sortItems()

    def add_all(self):
        self.move_all(self.available_list, self.selected_list)

    def remove_all(self):
        self.move_all(self.selected_list, self.available_list)

    def clear(self):
        self.available_list.clear()
        self.selected_list.clear()

        

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    ui = MultiSelectWidget()
    ui.show()
    sys.exit(app.exec_())
