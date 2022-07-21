# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only



import asyncio
import sys

import qasync
from PyQt5 import QtWidgets

qtapp = None
loop = None

def init_qtapp():
    global qtapp, loop
    if qtapp is None:
        qtapp = QtWidgets.QApplication(sys.argv)
        loop = qasync.QEventLoop(qtapp)
        asyncio.set_event_loop(loop)
    qtapp.processEvents()
    return qtapp, loop
