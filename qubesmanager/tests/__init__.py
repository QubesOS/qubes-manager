import asyncio
import sys

from PyQt5 import QtWidgets
import qasync

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
