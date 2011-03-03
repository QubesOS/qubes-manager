# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'newfwruledlg.ui'
#
# Created: Thu Mar  3 17:36:19 2011
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_NewFwRuleDlg(object):
    def setupUi(self, NewFwRuleDlg):
        NewFwRuleDlg.setObjectName("NewFwRuleDlg")
        NewFwRuleDlg.setWindowModality(QtCore.Qt.NonModal)
        NewFwRuleDlg.resize(381, 121)
        NewFwRuleDlg.setModal(True)
        self.buttonBox = QtGui.QDialogButtonBox(NewFwRuleDlg)
        self.buttonBox.setGeometry(QtCore.QRect(10, 80, 361, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.label_2 = QtGui.QLabel(NewFwRuleDlg)
        self.label_2.setGeometry(QtCore.QRect(10, 14, 62, 17))
        self.label_2.setObjectName("label_2")
        self.addressEdit = QtGui.QLineEdit(NewFwRuleDlg)
        self.addressEdit.setGeometry(QtCore.QRect(70, 10, 301, 27))
        self.addressEdit.setObjectName("addressEdit")
        self.label_4 = QtGui.QLabel(NewFwRuleDlg)
        self.label_4.setGeometry(QtCore.QRect(10, 44, 61, 21))
        self.label_4.setObjectName("label_4")
        self.serviceComboBox = QtGui.QComboBox(NewFwRuleDlg)
        self.serviceComboBox.setGeometry(QtCore.QRect(70, 40, 301, 27))
        self.serviceComboBox.setEditable(True)
        self.serviceComboBox.setObjectName("serviceComboBox")

        self.retranslateUi(NewFwRuleDlg)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("accepted()"), NewFwRuleDlg.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), NewFwRuleDlg.reject)
        QtCore.QMetaObject.connectSlotsByName(NewFwRuleDlg)
        NewFwRuleDlg.setTabOrder(self.addressEdit, self.serviceComboBox)
        NewFwRuleDlg.setTabOrder(self.serviceComboBox, self.buttonBox)

    def retranslateUi(self, NewFwRuleDlg):
        NewFwRuleDlg.setWindowTitle(QtGui.QApplication.translate("NewFwRuleDlg", "New Address", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("NewFwRuleDlg", "Address", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("NewFwRuleDlg", "Service", None, QtGui.QApplication.UnicodeUTF8))

