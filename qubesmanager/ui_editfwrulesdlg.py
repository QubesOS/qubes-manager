# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'editfwrulesdlg.ui'
#
# Created: Thu Mar  3 17:36:19 2011
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_EditFwRulesDlg(object):
    def setupUi(self, EditFwRulesDlg):
        EditFwRulesDlg.setObjectName("EditFwRulesDlg")
        EditFwRulesDlg.resize(500, 335)
        self.verticalLayout_3 = QtGui.QVBoxLayout(EditFwRulesDlg)
        self.verticalLayout_3.setObjectName("verticalLayout_3")
        self.policyAllowRadioButton = QtGui.QRadioButton(EditFwRulesDlg)
        self.policyAllowRadioButton.setObjectName("policyAllowRadioButton")
        self.verticalLayout_3.addWidget(self.policyAllowRadioButton)
        self.policyDenyRadioButton = QtGui.QRadioButton(EditFwRulesDlg)
        self.policyDenyRadioButton.setObjectName("policyDenyRadioButton")
        self.verticalLayout_3.addWidget(self.policyDenyRadioButton)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setSizeConstraint(QtGui.QLayout.SetMaximumSize)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.verticalLayout_2 = QtGui.QVBoxLayout()
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.rulesTreeView = QtGui.QTreeView(EditFwRulesDlg)
        self.rulesTreeView.setRootIsDecorated(False)
        self.rulesTreeView.setUniformRowHeights(False)
        self.rulesTreeView.setItemsExpandable(False)
        self.rulesTreeView.setAllColumnsShowFocus(True)
        self.rulesTreeView.setExpandsOnDoubleClick(True)
        self.rulesTreeView.setObjectName("rulesTreeView")
        self.rulesTreeView.header().setDefaultSectionSize(40)
        self.rulesTreeView.header().setStretchLastSection(False)
        self.verticalLayout_2.addWidget(self.rulesTreeView)
        self.dnsCheckBox = QtGui.QCheckBox(EditFwRulesDlg)
        self.dnsCheckBox.setChecked(True)
        self.dnsCheckBox.setObjectName("dnsCheckBox")
        self.verticalLayout_2.addWidget(self.dnsCheckBox)
        self.horizontalLayout.addLayout(self.verticalLayout_2)
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
        EditFwRulesDlg.setTabOrder(self.policyAllowRadioButton, self.policyDenyRadioButton)
        EditFwRulesDlg.setTabOrder(self.policyDenyRadioButton, self.dnsCheckBox)
        EditFwRulesDlg.setTabOrder(self.dnsCheckBox, self.rulesTreeView)
        EditFwRulesDlg.setTabOrder(self.rulesTreeView, self.newRuleButton)
        EditFwRulesDlg.setTabOrder(self.newRuleButton, self.editRuleButton)
        EditFwRulesDlg.setTabOrder(self.editRuleButton, self.deleteRuleButton)
        EditFwRulesDlg.setTabOrder(self.deleteRuleButton, self.buttonBox)

    def retranslateUi(self, EditFwRulesDlg):
        EditFwRulesDlg.setWindowTitle(QtGui.QApplication.translate("EditFwRulesDlg", "VM Firewall", None, QtGui.QApplication.UnicodeUTF8))
        self.policyAllowRadioButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "Allow network access except...", None, QtGui.QApplication.UnicodeUTF8))
        self.policyDenyRadioButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "Deny network access except...", None, QtGui.QApplication.UnicodeUTF8))
        self.dnsCheckBox.setText(QtGui.QApplication.translate("EditFwRulesDlg", "Allow DNS queries", None, QtGui.QApplication.UnicodeUTF8))
        self.newRuleButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "&New", None, QtGui.QApplication.UnicodeUTF8))
        self.editRuleButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "&Edit", None, QtGui.QApplication.UnicodeUTF8))
        self.deleteRuleButton.setText(QtGui.QApplication.translate("EditFwRulesDlg", "&Delete", None, QtGui.QApplication.UnicodeUTF8))

