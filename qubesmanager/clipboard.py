# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2016  Jean-Philippe Ouellet <jpo@vt.edu>
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski <marmarek@mimuw.edu.pl>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import os
import fcntl
from math import log

# pylint: disable=import-error
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QCoreApplication

APPVIEWER_LOCK = "/var/run/qubes/appviewer.lock"
CLIPBOARD_CONTENTS = "/var/run/qubes/qubes-clipboard.bin"
CLIPBOARD_SOURCE = CLIPBOARD_CONTENTS + ".source"


def do_dom0_copy():
    copy_text_to_qubes_clipboard(QApplication.clipboard().text())


def copy_text_to_qubes_clipboard(text):
    # inter-appviewer lock

    try:
        file = os.open(APPVIEWER_LOCK, os.O_RDWR | os.O_CREAT, 0o0666)
    except Exception:  # pylint: disable=broad-except
        QMessageBox.warning(
            None,
            QCoreApplication.translate("Clipboard", "Warning!"),
            QCoreApplication.translate(
                "Clipboard", "Error while accessing Qubes clipboard!"))
    else:
        try:
            fcntl.flock(file, fcntl.LOCK_EX)
        except Exception:  # pylint: disable=broad-except
            QMessageBox.warning(
                None,
                QCoreApplication.translate("Clipboard", "Warning!"),
                QCoreApplication.translate(
                    "Clipboard", "Error while locking Qubes clipboard!"))
        else:
            try:
                with open(CLIPBOARD_CONTENTS, "w", encoding='utf-8') \
                        as contents:
                    contents.write(text)
                with open(CLIPBOARD_SOURCE, "w", encoding='utf-8') as source:
                    source.write("dom0")
            except Exception:  # pylint: disable=broad-except
                QMessageBox.warning(
                    None,
                    QCoreApplication.translate("Clipboard", "Warning!"),
                    QCoreApplication.translate(
                        "Clipboard", "Error while writing to Qubes clipboard!"))
            fcntl.flock(file, fcntl.LOCK_UN)
        os.close(file)


# pylint: disable=invalid-name
def get_qubes_clipboard_formatted_size():
    units = ['B', 'KiB', 'MiB', 'GiB']

    try:
        file_size = os.path.getsize(CLIPBOARD_CONTENTS)
    except Exception:  # pylint: disable=broad-except
        QMessageBox.warning(
            None,
            QCoreApplication.translate("Clipboard", "Warning!"),
            QCoreApplication.translate(
                "Clipboard", "Error while accessing Qubes clipboard!"))
    else:
        formatted_bytes = QCoreApplication.translate(
            "Clipboard", "%n byte(s)", "", file_size)
        if file_size > 0:
            magnitude = min(int(log(file_size)/log(2)*0.1), len(units)-1)
            if magnitude > 0:
                return '%s (%.1f %s)' % (formatted_bytes,
                                         file_size/(2.0**(10*magnitude)),
                                         units[magnitude])
        return '%s' % formatted_bytes

    return QCoreApplication.translate("Clipboard", '? bytes')
