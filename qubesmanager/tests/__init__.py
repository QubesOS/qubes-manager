import asyncio
import sys

import quamash
from PyQt5 import QtWidgets

qtapp = None
loop = None

def init_qtapp():
    global qtapp, loop
    if qtapp is None:
        qtapp = QtWidgets.QApplication(sys.argv)
        loop = quamash.QEventLoop(qtapp)
        asyncio.set_event_loop(loop)
    qtapp.processEvents()
    return qtapp, loop
