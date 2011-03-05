# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'editfwrulesdlg.ui'
#
# Created: Wed Feb 16 20:55:59 2011
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_EditFwRulesDlg(object):
    def setupUi(self, EditFwRulesDlg):
        EditFwRulesDlg.setObjectName("EditFwRulesDlg")
        EditFwRulesDlg.resize(500, 280)
        self.verticalLayout_3 = QtGui.QVBoxLayout(EditFwRulesDlg)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSizeConstraint(QtGui.QLayout.SetMaximumSize)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.rulesTreeView = QtGui.QTreeView(EditFwRulesDlg)
        self.rulesTreeView.setRootIsDecorated(False)
        self.rulesTreeView.setUniformRowHeights(False)
        self.rulesTreeView.setItemsExpandable(False)
        self.rulesTreeView.setAllColumnsShowFocus(True)
        self.rulesTreeView.setExpandsOnDoubleClick(True)
        self.rulesTreeView.setObjectName("rulesTreeView")
        self.rulesTreeView.header().setDefaultSectionSize(40)
        self.rulesTreeView.header().setStretchLastSection(False)
        self.horizontalLayout.addWidget(self.rulesTreeView)
        self.verticalLayout = QtGui.QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.newRuleButton = QtGui.QPushButton(EditFwRulesDlg)
        self.newRuleButton.setObjectName("newRuleButton")
        self.verticalLayout.addWidget(self.newRuleButton)
        self.editRuleButton = QtGui.QPushButton(EditFwRulesDlg)
        self.editRuleButton.setObjectName("editRuleButton")
        self.verticalLayout.addWidget(self.editRuleButton)
        self.deleteRuleButton = QtGui.QPushButton(EditFwRulesDlg)
        self.deleteRuleButton.setObjectName("deleteRuleButton")
        self.verticalLayout.addWidget(self.deleteRuleButton)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.verticalLayout.addItem(spacerItem)
        self.horizontalLayout.addLayout(self.verticalLayout)
        self.verticalLayout_3.addLayout(self.horizontalLayout)
        self.buttonBox = QtGui.QDialogButtonBox(EditFwRulesDlg)
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout_3.addWidget(self.buttonBox)

        self.retranslateUi(EditFwRulesDlg)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), EditFwRulesDlg.reject)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("accepted()"), EditFwRulesDlg.accept)
        QtCore.QMetaObject.connectSlotsByName(EditFwRulesDlg)
        EditFwRulesDlg.setTabOrder(self.newRuleButton, self.editRuleButton)
        EditFwRulesDlg.setTabOrder(self.editRuleButton, self.deleteRuleButton)
        EditFwRulesDlg.setTabOrder(self.deleteRuleButton, self.rulesTreeView)
        EditFwRulesDlg.setTabOrder(self.rulesTreeView, self.buttonBox)

    def retranslateUi(self, EditFwRulesDlg):
        EditFwRulesDlg.setWindowTitle(QtGui.QApplication.translate("EditFwRulesDlg", "Edit Firewall Rules", None, QtGui.QApplication.UnicodeUTF8))
        self.newRuleButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "&New", None, QtGui.QApplication.UnicodeUTF8))
        self.editRuleButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "&Edit", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteRuleButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "&Delete", None, QtGui.QApplication.UnicodeUTF8))

