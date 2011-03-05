# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'newfwruledlg.ui'
#
# Created: Wed Feb 16 20:55:59 2011
#      by: PyQt4 UI code generator 4.7.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

class Ui_NewFwRuleDlg(object):
    def setupUi(self, NewFwRuleDlg):
        NewFwRuleDlg.setObjectName("NewFwRuleDlg")
        NewFwRuleDlg.setWindowModality(QtCore.Qt.NonModal)
        NewFwRuleDlg.resize(311, 202)
        NewFwRuleDlg.setModal(True)
        self.buttonBox = QtGui.QDialogButtonBox(NewFwRuleDlg)
        self.buttonBox.setGeometry(QtCore.QRect(30, 160, 271, 32))
        self.buttonBox.setOrientation(QtCore.Qt.Horizontal)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Cancel|QtGui.QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.label = QtGui.QLabel(NewFwRuleDlg)
        self.label.setGeometry(QtCore.QRect(10, 10, 62, 17))
        self.label.setObjectName("label")
        self.groupBox = QtGui.QGroupBox(NewFwRuleDlg)
        self.groupBox.setGeometry(QtCore.QRect(10, 40, 291, 121))
        self.groupBox.setTitle("")
        self.groupBox.setObjectName("groupBox")
        self.label_2 = QtGui.QLabel(self.groupBox)
        self.label_2.setGeometry(QtCore.QRect(10, 10, 62, 17))
        self.label_2.setObjectName("label_2")
        self.label_3 = QtGui.QLabel(self.groupBox)
        self.label_3.setGeometry(QtCore.QRect(190, 10, 62, 17))
        self.label_3.setObjectName("label_3")
        self.allowCheckBox = QtGui.QCheckBox(self.groupBox)
        self.allowCheckBox.setGeometry(QtCore.QRect(200, 80, 71, 23))
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.allowCheckBox.sizePolicy().hasHeightForWidth())
        self.allowCheckBox.setSizePolicy(sizePolicy)
        self.allowCheckBox.setObjectName("allowCheckBox")
        self.addressEdit = QtGui.QLineEdit(self.groupBox)
        self.addressEdit.setGeometry(QtCore.QRect(10, 30, 171, 27))
        self.addressEdit.setObjectName("addressEdit")
        self.label_4 = QtGui.QLabel(self.groupBox)
        self.label_4.setGeometry(QtCore.QRect(10, 62, 31, 21))
        self.label_4.setObjectName("label_4")
        self.label_5 = QtGui.QLabel(self.groupBox)
        self.label_5.setGeometry(QtCore.QRect(123, 62, 16, 21))
        self.label_5.setObjectName("label_5")
        self.netmaskComboBox = QtGui.QComboBox(self.groupBox)
        self.netmaskComboBox.setGeometry(QtCore.QRect(190, 30, 84, 27))
        self.netmaskComboBox.setObjectName("netmaskComboBox")
        self.portBeginSpinBox = QtGui.QSpinBox(self.groupBox)
        self.portBeginSpinBox.setGeometry(QtCore.QRect(50, 60, 71, 27))
        self.portBeginSpinBox.setMaximum(65535)
        self.portBeginSpinBox.setProperty("value", 0)
        self.portBeginSpinBox.setObjectName("portBeginSpinBox")
        self.portEndSpinBox = QtGui.QSpinBox(self.groupBox)
        self.portEndSpinBox.setGeometry(QtCore.QRect(130, 60, 71, 27))
        self.portEndSpinBox.setMaximum(65535)
        self.portEndSpinBox.setObjectName("portEndSpinBox")
        self.nameEdit = QtGui.QLineEdit(NewFwRuleDlg)
        self.nameEdit.setGeometry(QtCore.QRect(60, 4, 241, 27))
        self.nameEdit.setObjectName("nameEdit")

        self.retranslateUi(NewFwRuleDlg)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("accepted()"), NewFwRuleDlg.accept)
        QtCore.QObject.connect(self.buttonBox, QtCore.SIGNAL("rejected()"), NewFwRuleDlg.reject)
        QtCore.QMetaObject.connectSlotsByName(NewFwRuleDlg)
        NewFwRuleDlg.setTabOrder(self.nameEdit, self.addressEdit)
        NewFwRuleDlg.setTabOrder(self.addressEdit, self.netmaskComboBox)
        NewFwRuleDlg.setTabOrder(self.netmaskComboBox, self.portBeginSpinBox)
        NewFwRuleDlg.setTabOrder(self.portBeginSpinBox, self.portEndSpinBox)
        NewFwRuleDlg.setTabOrder(self.portEndSpinBox, self.allowCheckBox)
        NewFwRuleDlg.setTabOrder(self.allowCheckBox, self.buttonBox)

    def retranslateUi(self, NewFwRuleDlg):
        NewFwRuleDlg.setWindowTitle(QtGui.QApplication.translate("NewFwRuleDlg", "New Firewall Rule", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("NewFwRuleDlg", "Name", None, QtGui.QApplication.UnicodeUTF8))
        self.label_2.setText(QtGui.QApplication.translate("NewFwRuleDlg", "Address", None, QtGui.QApplication.UnicodeUTF8))
        self.label_3.setText(QtGui.QApplication.translate("NewFwRuleDlg", "Netmask", None, QtGui.QApplication.UnicodeUTF8))
        self.allowCheckBox.setText(QtGui.QApplication.translate("NewFwRuleDlg", "Allow", None, QtGui.QApplication.UnicodeUTF8))
        self.label_4.setText(QtGui.QApplication.translate("NewFwRuleDlg", "Port", None, QtGui.QApplication.UnicodeUTF8))
        self.label_5.setText(QtGui.QApplication.translate("NewFwRuleDlg", "-", None, QtGui.QApplication.UnicodeUTF8))

