#!/usr/bin/python2
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
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
import re
from PyQt4 import QtGui  # pylint: disable=import-error
from PyQt4 import QtCore  # pylint: disable=import-error

import subprocess
from . import utils
import yaml

path_re = re.compile(r"[a-zA-Z0-9/:.,_+=() -]*")
path_max_len = 512


def fill_appvms_list(dialog):
    """
    Helper function, designed to fill the destination vm combobox in both backup
    and restore GUI tools.
    :param dialog: QtGui.QWizard with a combobox called appvm_combobox
    """
    dialog.appvm_combobox.clear()
    dialog.appvm_combobox.addItem("dom0")

    dialog.appvm_combobox.setCurrentIndex(0)  # current selected is null ""

    for vm in dialog.qubes_app.domains:
        if vm.features.get('internal', False) or vm.klass == 'TemplateVM':
            continue

        if vm.is_running() and vm.qid != 0:
            dialog.appvm_combobox.addItem(vm.name)


def enable_dir_line_edit(dialog, boolean):
    dialog.dir_line_edit.setEnabled(boolean)
    dialog.select_path_button.setEnabled(boolean)


def select_path_button_clicked(dialog, select_file=False, read_only=False):
    """
    Helper function that displays a file/directory selection wizard. Used by
    backup and restore GUI tools.
    :param dialog: QtGui.QWizard with a dir_line_edit text box that wants to
    receive a file/directory path and appvm_combobox with VM to use
    :param select_file: True: select file dialog; False: select directory
    dialog
    :param read_only: should the dir_line_edit be changed after selecting a file
    or directory
    :return:
    """
    backup_location = str(dialog.dir_line_edit.text())
    file_dialog = QtGui.QFileDialog()
    file_dialog.setReadOnly(True)

    new_path = None

    new_appvm = str(dialog.appvm_combobox.currentText())
    vm = dialog.qubes_app.domains[new_appvm]
    try:
        new_path = utils.get_path_from_vm(
            vm,
            "qubes.SelectFile" if select_file
            else "qubes.SelectDirectory")
    except subprocess.CalledProcessError:
        if not read_only:
            QtGui.QMessageBox.warning(
                None,
                dialog.tr("Nothing selected!"),
                dialog.tr("No file or directory selected."))
        else:
            return

    if new_path and not read_only:
        dialog.dir_line_edit.setText(new_path)

    if new_path and backup_location and not read_only:
        dialog.select_dir_page.emit(QtCore.SIGNAL("completeChanged()"))


def get_profile_name(use_temp):
    backup_profile_name = 'qubes-manager-backup'
    temp_backup_profile_name = 'qubes-manager-backup-tmp'

    return temp_backup_profile_name if use_temp else backup_profile_name


def get_profile_path(use_temp):
    path = '/etc/qubes/backup/' + get_profile_name(use_temp) + '.conf'
    return path


def load_backup_profile(use_temp=False):

    path = get_profile_path(use_temp)

    with open(path) as profile_file:
        profile_data = yaml.safe_load(profile_file)
    return profile_data


def write_backup_profile(args, use_temp=False):

    acceptable_fields = ['include', 'passphrase_text', 'compression',
                         'destination_vm', 'destination_path']

    profile_data = {key: value for key, value in args.items()
                    if key in acceptable_fields}

    path = get_profile_path(use_temp)

    with open(path, 'w') as profile_file:
        yaml.safe_dump(profile_data, profile_file)
