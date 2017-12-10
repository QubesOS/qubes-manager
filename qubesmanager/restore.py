#!/usr/bin/python2
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
import shutil
from PyQt4 import QtCore
from PyQt4 import QtGui
import threading
import time
import os
import os.path
import traceback

import signal

from qubes import backup

from . import ui_restoredlg
from . import multiselectwidget
from . import backup_utils
from . import thread_monitor

from multiprocessing import Queue, Event
from multiprocessing.queues import Empty
from qubesadmin import Qubes, exc
from qubesadmin.backup import restore


class RestoreVMsWindow(ui_restoredlg.Ui_Restore, QtGui.QWizard):

    __pyqtSignals__ = ("restore_progress(int)", "backup_progress(int)")

    def __init__(self, app, qvm_collection, parent=None):
        super(RestoreVMsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection

        self.vms_to_restore = None
        self.func_output = []
        self.feedback_queue = Queue()
        self.canceled = False
        self.tmpdir_to_remove = None
        self.error_detected = Event()
        self.thread_monitor = None
        self.backup_restore = None
        self.target_appvm = None

        self.setupUi(self)

        self.select_vms_widget = multiselectwidget.MultiSelectWidget(self)
        self.select_vms_layout.insertWidget(1, self.select_vms_widget)

        self.connect(self,
                     QtCore.SIGNAL("currentIdChanged(int)"),
                     self.current_page_changed)
        self.connect(self,
                     QtCore.SIGNAL("restore_progress(QString)"),
                     self.commit_text_edit.append)
        self.connect(self,
                     QtCore.SIGNAL("backup_progress(int)"),
                     self.progress_bar.setValue)
        self.dir_line_edit.connect(self.dir_line_edit,
                                   QtCore.SIGNAL("textChanged(QString)"),
                                   self.backup_location_changed)
        self.connect(self.verify_only, QtCore.SIGNAL("stateChanged(int)"),
                     self.on_verify_only_toogled)

        self.select_dir_page.isComplete = self.has_selected_dir
        self.select_vms_page.isComplete = self.has_selected_vms
        self.confirm_page.isComplete = self.all_vms_good
        # FIXME
        # this causes to run isComplete() twice, I don't know why
        self.select_vms_page.connect(
            self.select_vms_widget,
            QtCore.SIGNAL("selected_changed()"),
            QtCore.SIGNAL("completeChanged()"))

        backup_utils.fill_appvms_list(self)

    @QtCore.pyqtSlot(name='on_select_path_button_clicked')
    def select_path_button_clicked(self):
        backup_utils.select_path_button_clicked(self, True)

    def cleanupPage(self, p_int):  # pylint: disable=invalid-name
        if self.page(p_int) is self.select_vms_page:
            self.vms_to_restore = None
        else:
            super(RestoreVMsWindow, self).cleanupPage(p_int)

    def __fill_vms_list__(self):
        if self.vms_to_restore is not None:
            return

        self.select_vms_widget.selected_list.clear()
        self.select_vms_widget.available_list.clear()

        self.target_appvm = None
        if self.appvm_combobox.currentIndex() != 0:   # An existing appvm chosen
            self.target_appvm = self.qvm_collection.domains[
                str(self.appvm_combobox.currentText())]

        try:
            self.backup_restore = restore.BackupRestore(
                self.qvm_collection,
                self.dir_line_edit.text(),
                self.target_appvm,
                self.passphrase_line_edit.text()
            )

            if self.ignore_missing.isChecked():
                self.backup_restore.options.use_default_template = True
                self.backup_restore.options.use_default_netvm = True

            if self.ignore_uname_mismatch.isChecked():
                self.backup_restore.options.ignore_username_mismatch = True

            if self.verify_only.isChecked():
                self.backup_restore.options.verify_only = True

            self.vms_to_restore = self.backup_restore.get_restore_info()

            for vmname in self.vms_to_restore:
                if vmname.startswith('$'):
                    # Internal info
                    continue
                self.select_vms_widget.available_list.addItem(vmname)
        except exc.QubesException as ex:
            QtGui.QMessageBox.warning(None, self.tr("Restore error!"), str(ex))

    def restore_error_output(self, text):
        self.error_detected.set()
        self.feedback_queue.put((QtCore.SIGNAL("restore_progress(QString)"),
                                 u'<font color="red">{0}</font>'.format(text)))

    def restore_output(self, text):
        self.feedback_queue.put((
            QtCore.SIGNAL("restore_progress(QString)"),
            u'<font color="black">{0}</font>'.format(text)))

    def update_progress_bar(self, value):
        self.feedback_queue.put((QtCore.SIGNAL("backup_progress(int)"), value))

    def __do_restore__(self, t_monitor):
        err_msg = []
        try:
            self.backup_restore.progress_callback = self.update_progress_bar
            self.backup_restore.restore_do(self.vms_to_restore)

        except backup.BackupCanceledError as ex:
            self.canceled = True
            self.tmpdir_to_remove = ex.tmpdir
            err_msg.append(str(ex))
        except Exception as ex:  # pylint: disable=broad-except
            err_msg.append(str(ex))
            err_msg.append(
                self.tr("Partially restored files left in /var/tmp/restore_*, "
                        "investigate them and/or clean them up"))

        if self.canceled:
            self.emit(QtCore.SIGNAL("restore_progress(QString)"),
                      '<b><font color="red">{0}</font></b>'
                      .format(self.tr("Restore aborted!")))
        elif len(err_msg) > 0 or self.error_detected.is_set():
            if len(err_msg) > 0:
                t_monitor.set_error_msg('\n'.join(err_msg))
            self.emit(QtCore.SIGNAL("restore_progress(QString)"),
                      '<b><font color="red">{0}</font></b>'
                      .format(self.tr("Finished with errors!")))
        else:
            self.emit(QtCore.SIGNAL("restore_progress(QString)"),
                      '<font color="green">{0}</font>'
                      .format(self.tr("Finished successfully!")))

        t_monitor.set_finished()

    def current_page_changed(self, page_id):  # pylint: disable=unused-argument

        old_sigchld_handler = signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        if self.currentPage() is self.select_vms_page:
            self.__fill_vms_list__()

        elif self.currentPage() is self.confirm_page:

            self.vms_to_restore = self.backup_restore.get_restore_info()

            for i in range(self.select_vms_widget.available_list.count()):
                vmname = self.select_vms_widget.available_list.item(i).text()
                del self.vms_to_restore[str(vmname)]

            self.vms_to_restore = self.backup_restore.restore_info_verify(
                self.vms_to_restore)

            self.func_output = self.backup_restore.get_restore_summary(
                self.vms_to_restore
            )

            self.confirm_text_edit.setReadOnly(True)
            self.confirm_text_edit.setFontFamily("Monospace")
            self.confirm_text_edit.setText(self.func_output)

            self.confirm_page.emit(QtCore.SIGNAL("completeChanged()"))

        elif self.currentPage() is self.commit_page:
            self.button(self.FinishButton).setDisabled(True)
            self.showFileDialog.setEnabled(True)
            self.showFileDialog.setChecked(self.showFileDialog.isEnabled()
                                           and str(self.dir_line_edit.text())
                                           .count("media/") > 0)

            self.thread_monitor = thread_monitor.ThreadMonitor()
            thread = threading.Thread(target=self.__do_restore__,
                                      args=(self.thread_monitor,))
            thread.daemon = True
            thread.start()

            while not self.thread_monitor.is_finished():
                self.app.processEvents()
                time.sleep(0.1)
                try:
                    for (signal_to_emit, data) in iter(
                            self.feedback_queue.get_nowait, None):
                        self.emit(signal_to_emit, data)
                except Empty:
                    pass

            if not self.thread_monitor.success:
                if self.canceled:
                    if self.tmpdir_to_remove and \
                        QtGui.QMessageBox.warning(
                            None,
                            self.tr("Restore aborted"),
                            self.tr("Do you want to remove temporary files "
                                    "from %s?") % self.tmpdir_to_remove,
                            QtGui.QMessageBox.Yes,
                            QtGui.QMessageBox.No) == QtGui.QMessageBox.Yes:
                        shutil.rmtree(self.tmpdir_to_remove)
                else:
                    QtGui.QMessageBox.warning(
                        None,
                        self.tr("Backup error!"),
                        self.tr("ERROR: {0}").format(
                            self.thread_monitor.error_msg))

            if self.showFileDialog.isChecked():  # TODO: this is not working
                self.emit(QtCore.SIGNAL("restore_progress(QString)"),
                          '<b><font color="black">{0}</font></b>'.format(
                              self.tr(
                                  "Please unmount your backup volume and cancel"
                                  " the file selection dialog.")))
                if self.target_appvm: # TODO does this work at all?
                    self.target_appvm.run("QUBESRPC %s dom0" %
                                          "qubes.SelectDirectory")
                else:
                    file_dialog = QtGui.QFileDialog()
                    file_dialog.setReadOnly(True)
                    file_dialog.getExistingDirectory(
                        self, self.tr("Detach backup device"),
                        os.path.dirname(self.dir_line_edit.text()))
            self.progress_bar.setValue(100)
            self.button(self.FinishButton).setEnabled(True)
            self.button(self.CancelButton).setEnabled(False)
            self.showFileDialog.setEnabled(False)

        signal.signal(signal.SIGCHLD, old_sigchld_handler)

    def all_vms_good(self):
        for vm_info in self.vms_to_restore.values():
            if not vm_info.vm:
                continue
            if not vm_info.good_to_go:
                return False
        return True

    def reject(self):  # TODO: probably not working too
        if self.currentPage() is self.commit_page:
            if self.backup_restore.canceled:
                self.emit(QtCore.SIGNAL("restore_progress(QString)"),
                          '<font color="red">{0}</font>'
                          .format(self.tr("Aborting the operation...")))
                self.button(self.CancelButton).setDisabled(True)
        else:
            self.done(0)

    def has_selected_dir(self):
        backup_location = self.dir_line_edit.text()
        if not backup_location:
            return False
        if self.appvm_combobox.currentIndex() == 0:
            if os.path.isfile(backup_location) or \
                    os.path.isfile(os.path.join(backup_location, 'qubes.xml')):
                return True
        else:
            return True

        return False

    def has_selected_vms(self):
        return self.select_vms_widget.selected_list.count() > 0

    def backup_location_changed(self, new_dir=None):
        # pylint: disable=unused-argument
        self.select_dir_page.emit(QtCore.SIGNAL("completeChanged()"))


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception(exc_type, exc_value, exc_traceback):

    filename, line, dummy, dummy = traceback.extract_tb(exc_traceback).pop()
    filename = os.path.basename(filename)
    error = "%s: %s" % (exc_type.__name__, exc_value)

    QtGui.QMessageBox.critical(None, "Houston, we have a problem...",
                         "Whoops. A critical error has occured. "
                         "This is most likely a bug "
                         "in Qubes Restore VMs application.<br><br>"
                         "<b><i>%s</i></b>" % error +
                         "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
                                      % (line, filename))


def main():

    qtapp = QtGui.QApplication(sys.argv)
    qtapp.setOrganizationName("The Qubes Project")
    qtapp.setOrganizationDomain("http://qubes-os.org")
    qtapp.setApplicationName("Qubes Restore VMs")

    sys.excepthook = handle_exception

    app = Qubes()

    restore_window = RestoreVMsWindow(qtapp, app)

    restore_window.show()

    qtapp.exec_()
    qtapp.exit()


if __name__ == "__main__":
    main()
