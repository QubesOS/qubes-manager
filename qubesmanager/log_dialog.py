#!/usr/bin/python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski <marmarek@mimuw.edu.pl>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with this program; if not, see <http://www.gnu.org/licenses/>.
#
#
import sys
import os
from functools import partial
from PyQt5 import QtWidgets  # pylint: disable=import-error
from qubesadmin import Qubes
from . import ui_logdlg   # pylint: disable=no-name-in-module
from . import clipboard

# Display only this size of log
LOG_DISPLAY_SIZE = 1024*1024


class LogDialog(ui_logdlg.Ui_LogDialog, QtWidgets.QDialog):
    # pylint: disable=too-few-public-methods

    def __init__(self, app, logfiles, parent=None):
        super().__init__(parent)

        self.app = app
        self.logfiles = logfiles
        self.displayed_text = ""

        self.setupUi(self)

        self.copy_to_qubes_clipboard.clicked.connect(
            self.copy_to_clipboard_triggered)

        self.__init_log_text__()

    def __init_log_text__(self):
        btns_in_row = 3
        count = 0
        for log_path in self.logfiles:
            button = QtWidgets.QPushButton(log_path)
            button.clicked.connect(partial(self.set_current_log, log_path))
            self.buttonsLayout.addWidget(button,
                    count / btns_in_row, count % btns_in_row)
            count += 1

        self.buttonsLayout.itemAt(0).widget().click()

    def copy_to_clipboard_triggered(self):
        text = self.log_text.textCursor().selectedText() or self.displayed_text
        clipboard.copy_text_to_qubes_clipboard(text)

    def set_current_log(self, log_path):
        self.displayed_text = ""
        self.setWindowTitle(log_path)
        with open(log_path, encoding='ascii', errors='ignore') as log:
            log.seek(0, os.SEEK_END)
            if log.tell() > LOG_DISPLAY_SIZE:
                self.displayed_text = (self.tr(
                    "(Showing only last %d bytes of file)\n") %
                        LOG_DISPLAY_SIZE)
                log.seek(log.tell()-LOG_DISPLAY_SIZE, os.SEEK_SET)
            else:
                log.seek(0, os.SEEK_SET)
            self.displayed_text += log.read()
        self.log_text.setPlainText(self.displayed_text)

def main():
    qubes_app = Qubes()
    qt_app = QtWidgets.QApplication(sys.argv)

    log_window = LogDialog(qubes_app, sys.argv[1:])
    log_window.show()

    qt_app.exec_()
    qt_app.exit()


if __name__ == "__main__":
    main()
