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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
#

import sys
import os
from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qubes.qubes import QubesVmCollection
from qubes.qubes import QubesException
from qubes.qubes import QubesDaemonPidfile
from qubes.qubes import QubesHost
from qubes.qubes import qubes_base_dir
import qubesmanager.resources_rc

from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent

import subprocess
import time
from operator import itemgetter
from thread_monitor import *

from qubes import backup
from qubes import qubesutils

from ui_restoredlg import *
from multiselectwidget import *

from backup_utils import *



class RestoreVMsWindow(Ui_Restore, QWizard):

    __pyqtSignals__ = ("restore_progress(int)","backup_progress(int)")

    def __init__(self, app, qvm_collection, blk_manager, parent=None):
        super(RestoreVMsWindow, self).__init__(parent)

        self.app = app
        self.qvm_collection = qvm_collection
        self.blk_manager = blk_manager

        self.dev_mount_path = None
        self.backup_location = None
        self.restore_options = None
        self.backup_vms_list = None
        self.func_output = []

        self.excluded = {}

        for vm in self.qvm_collection.values():
            if vm.qid == 0:
                self.vm = vm
                break;

        assert self.vm != None

        self.setupUi(self)

        self.select_vms_widget = MultiSelectWidget(self)
        self.select_vms_layout.insertWidget(1, self.select_vms_widget)

        self.connect(self, SIGNAL("currentIdChanged(int)"), self.current_page_changed)
        self.connect(self.dev_combobox, SIGNAL("activated(int)"), self.dev_combobox_activated)
        self.connect(self, SIGNAL("restore_progress(QString)"), self.commit_text_edit.append)
        self.connect(self, SIGNAL("backup_progress(int)"), self.progress_bar.setValue)

        self.select_dir_page.isComplete = self.has_selected_dir
        self.select_vms_page.isComplete = self.has_selected_vms
        #FIXME
        #this causes to run isComplete() twice, I don't know why
        self.select_vms_page.connect(self.select_vms_widget, SIGNAL("selected_changed()"), SIGNAL("completeChanged()")) 

        fill_devs_list(self)
        fill_appvms_list(self)
        self.__init_restore_options__()


    def dev_combobox_activated(self, idx):
        dev_combobox_activated(self, idx)

    @pyqtSlot(name='on_select_path_button_clicked')
    def select_path_button_clicked(self):
        select_path_button_clicked(self, True)

    def on_ignore_missing_toggled(self, checked):
        self.restore_options['use-default-template'] = checked
        self.restore_options['use-default-netvm'] = checked

    def on_ignore_uname_mismatch_toggled(self, checked):
        self.restore_options['ignore-username-mismatch'] = checked

    def on_skip_dom0_toggled(self, checked):
        self.restore_options['dom0-home'] = checked


    def __fill_vms_list__(self):
        if self.backup_vms_list != None:
            return

        self.select_vms_widget.selected_list.clear()
        self.select_vms_widget.available_list.clear()

        self.target_appvm = None
        if self.appvm_combobox.currentIndex() != 0:   #An existing appvm chosen
            self.target_appvm = self.qvm_collection.get_vm_by_name(
                    str(self.appvm_combobox.currentText()))

        self.restore_tmpdir, qubes_xml = backup.backup_restore_header(
                str(self.backup_location),
                str(self.passphrase_line_edit.text()),
                encrypted=self.encryption_checkbox.isChecked(),
                appvm=self.target_appvm)
        self.vms_to_restore = backup.backup_restore_prepare(
                str(self.backup_location),
                os.path.join(self.restore_tmpdir, qubes_xml),
                str(self.passphrase_line_edit.text()),
                options=self.restore_options,
                host_collection=self.qvm_collection,
                encrypt=self.encryption_checkbox.isChecked(),
                appvm=self.target_appvm)

        for vmname in self.vms_to_restore:
            self.select_vms_widget.available_list.addItem(vmname)

    def __init_restore_options__(self):
        if not self.restore_options:
            self.restore_options = {}
            backup.backup_restore_set_defaults(self.restore_options)

        if 'use-default-template' in self.restore_options and 'use-default-netvm' in self.restore_options:
            val = self.restore_options['use-default-template'] and self.restore_options['use-default-netvm']
            self.ignore_missing.setChecked(val)
        else:
            self.ignore_missing.setChecked(False)

        if 'ignore-username-mismatch' in self.restore_options:
            self.ignore_uname_mismatch.setChecked(self.restore_options['ignore-username-mismatch'])

        if 'dom0-home' in self.restore_options:
            self.skip_dom0.setChecked(self.restore_options['dom0-home'])

    def gather_output(self, s):
        self.func_output.append(s)

    def restore_error_output(self, s):
        self.emit(SIGNAL("restore_progress(QString)"), '<font color="red">{0}</font>'.format(s))

    def restore_output(self, s):
        self.emit(SIGNAL("restore_progress(QString)"),'<font color="black">{0}</font>'.format(s))

    def update_progress_bar(self, value):
        self.emit(SIGNAL("backup_progress(int)"), value)

    def __do_restore__(self, thread_monitor):
        err_msg = []
        self.qvm_collection.lock_db_for_writing()
        try:
            backup.backup_restore_do(
                    str(self.backup_location),
                    self.restore_tmpdir,
                    str(self.passphrase_line_edit.text()),
                    self.vms_to_restore,
                    self.qvm_collection,
                    encrypted=self.encryption_checkbox.isChecked(),
                    appvm=self.target_appvm,
                    print_callback=self.restore_output,
                    error_callback=self.restore_error_output,
                    progress_callback=self.update_progress_bar)
        except Exception as ex:
            print "Exception:",ex
            err_msg.append(str(ex))

        self.qvm_collection.unlock_db()
        if len(err_msg) > 0 :
            thread_monitor.set_error_msg('\n'.join(err_msg))
            self.emit(SIGNAL("restore_progress(QString)"),'<b><font color="red">{0}</font></b>'.format("Finished with errors!"))
        else:
            self.emit(SIGNAL("restore_progress(QString)"),'<font color="green">{0}</font>'.format("Finished successfully!"))

        thread_monitor.set_finished()

    def current_page_changed(self, id):

        if self.currentPage() is self.select_vms_page:
            self.__fill_vms_list__()

        elif self.currentPage() is self.confirm_page:
            for v in self.excluded:
                self.vms_to_restore[v] = self.excluded[v]
            self.excluded = {}
            for i in range(self.select_vms_widget.available_list.count()):
                vmname =  self.select_vms_widget.available_list.item(i).text()
                self.excluded[str(vmname)] = self.vms_to_restore[str(vmname)]
                del self.vms_to_restore[str(vmname)]

            del self.func_output[:]
            backup.backup_restore_print_summary(
                    self.vms_to_restore, print_callback = self.gather_output)
            self.confirm_text_edit.setReadOnly(True)
            self.confirm_text_edit.setFontFamily("Monospace")
            self.confirm_text_edit.setText("\n".join(self.func_output))


        elif self.currentPage() is self.commit_page:
            self.button(self.CancelButton).setDisabled(True)
            self.button(self.FinishButton).setDisabled(True)

            self.thread_monitor = ThreadMonitor()
            thread = threading.Thread (target= self.__do_restore__ , args=(self.thread_monitor,))
            thread.daemon = True
            thread.start()

            while not self.thread_monitor.is_finished():
                self.app.processEvents()
                time.sleep (0.1)

            #if not self.thread_monitor.success:
                #QMessageBox.warning (None, "Backup error!", "ERROR: {1}".format(self.vm.name, self.thread_monitor.error_msg))

            if self.dev_mount_path != None:
                umount_device(self.dev_mount_path)
            self.button(self.FinishButton).setEnabled(True)

    def reject(self):
        if self.dev_mount_path != None:
            umount_device(self.dev_mount_path)
        self.done(0)

    def has_selected_dir(self):
        return self.backup_location != None

    def has_selected_vms(self):
        return self.select_vms_widget.selected_list.count() > 0



# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>

def handle_exception( exc_type, exc_value, exc_traceback ):
    import sys
    import os.path
    import traceback

    filename, line, dummy, dummy = traceback.extract_tb( exc_traceback ).pop()
    filename = os.path.basename( filename )
    error    = "%s: %s" % ( exc_type.__name__, exc_value )

    QMessageBox.critical(None, "Houston, we have a problem...",
                         "Whoops. A critical error has occured. This is most likely a bug "
                         "in Qubes Restore VMs application.<br><br>"
                         "<b><i>%s</i></b>" % error +
                         "at <b>line %d</b> of file <b>%s</b>.<br/><br/>"
                         % ( line, filename ))




def main():

    global qubes_host
    qubes_host = QubesHost()

    global app
    app = QApplication(sys.argv)
    app.setOrganizationName("The Qubes Project")
    app.setOrganizationDomain("http://qubes-os.org")
    app.setApplicationName("Qubes Restore VMs")

    sys.excepthook = handle_exception

    qvm_collection = QubesVmCollection()
    qvm_collection.lock_db_for_reading()
    qvm_collection.load()
    qvm_collection.unlock_db()

    global restore_window
    restore_window = RestoreVMsWindow()

    restore_window.show()

    app.exec_()
    app.exit()



if __name__ == "__main__":
    main()
