import sys
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from ui_multiselectwidget import *

class MultiSelectWidget(Ui_MultiSelectWidget, QWidget):

    def __init__(self, parent=None):
        super(MultiSelectWidget, self).__init__()
        self.setupUi(self);
        self.add_selected_button.clicked.connect(self.add_selected)
        self.remove_selected_button.clicked.connect(self.remove_selected)
        self.available_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.selected_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def switch_selected(self, src, dst):
        selected = src.selectedItems()

        for s in selected:
            row = src.indexFromItem(s).row()
            item = src.takeItem(row)
            dst.addItem(item)

    def add_selected(self):
        self.switch_selected(self.available_list, self.selected_list)
        self.selected_list.sortItems()


    def remove_selected(self):
        self.switch_selected(self.selected_list, self.available_list)        
        self.available_list.sortItems()

    def clear(self):
        self.available_list.clear()
        self.selected_list.clear()

        


if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    ui = MultiSelectWidget()
    ui.show()
    sys.exit(app.exec_())
