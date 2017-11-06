#!/usr/bin/python2
# -*- coding: utf8 -*-
# pylint: skip-file
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2014 Marek Marczykowski-Górecki <marmarek@invisiblethingslab.com>
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

import threading
import time
from PyQt4.QtGui import QMessageBox
from qubes import qubesutils


class QubesBlockDevicesManager():
    def __init__(self, qvm_collection):
        self.qvm_collection = qvm_collection
        self.attached_devs = {}
        self.free_devs = {}

        self.current_blk = {}
        self.current_attached = {}
        self.devs_changed = False

        self.last_update_time = time.time()
        self.blk_state_changed = True
        self.msg = []
        self.check_counter = 0
        self.blk_lock = threading.Lock()
        self.tray_message_func = None

        self.update()

    def block_devs_event(self, xid):
        now = time.time()
        #don't update more often than 1/10 s
        if now - self.last_update_time >= 0.1:
            self.last_update_time = now

            self.blk_lock.acquire()

            self.blk_state_changed = True

            self.blk_lock.release()

    def check_for_updates(self):
        self.blk_lock.acquire()

        ret = (self.blk_state_changed, self.msg)

        if self.blk_state_changed == True:
            self.check_counter += 1

            self.update()
            ret = (self.blk_state_changed, self.msg)

            #let the update last for 3 manager-update cycles
            if self.check_counter == 3:
                self.check_counter = 0
                self.blk_state_changed = False
        self.msg = []

        self.blk_lock.release()

        return ret

    def update(self):
        blk = qubesutils.block_list(self.qvm_collection)
        for b in blk:
            att = qubesutils.block_check_attached(self.qvm_collection, blk[b])
            if b in self.current_blk:
                if blk[b] == self.current_blk[b]:
                    if self.current_attached[b] != att: #devices the same, sth with attaching changed
                        self.current_attached[b] = att
                else:   #device changed ?!
                    self.current_blk[b] = blk[b]
                    self.current_attached[b] = att
            else: #new device
                self.current_blk[b] = blk[b]
                self.current_attached[b] = att
                self.msg.append("Attached new device to <b>{}</b>: {}".format(
                    blk[b]['vm'], blk[b]['device']))

        to_delete = []
        for b in self.current_blk: #remove devices that are not there anymore
            if b not in blk:
                to_delete.append(b)
                self.msg.append("Detached device from <b>{}</b>: {}".format(
                    self.current_blk[b]['vm'],
                    self.current_blk[b]['device']))

        for d in to_delete:
            del self.current_blk[d]
            del self.current_attached[d]

        self.__update_blk_entries__()


    def __update_blk_entries__(self):
        self.free_devs.clear()
        self.attached_devs.clear()

        for b in self.current_attached:
            if self.current_attached[b]:
                self.attached_devs[b] = self.__make_entry__(b, self.current_blk[b], self.current_attached[b])
            else:
                self.free_devs[b] = self.__make_entry__(b, self.current_blk[b], None)

    def __make_entry__(self, k, dev, att):
        size_str = qubesutils.bytes_to_kmg(dev['size'])
        entry = {   'dev': dev['device'],
                    'dev_obj': dev,
                    'backend_name': dev['vm'],
                    'desc': dev['desc'],
                    'mode': dev['mode'],
                    'size': size_str,
                    'attached_to': att, }
        return entry

    def attach_device(self, vm, dev):
        mode = self.free_devs[dev]['mode']
        if self.tray_message_func:
            self.tray_message_func("{0} - attaching {1}"
                                                 .format(vm.name, dev), msecs=3000)
        qubesutils.block_attach(self.qvm_collection, vm,
                                self.free_devs[dev]['dev_obj'], mode=mode)

    def detach_device(self, vm, dev_name):
        frontend = self.attached_devs[dev_name]['attached_to']['frontend']
        vm = self.attached_devs[dev_name]['attached_to']['vm']
        if self.tray_message_func:
            self.tray_message_func("{0} - detaching {1}".format(vm.name,
                                                            dev_name), msecs=3000)
        qubesutils.block_detach(vm, frontend)

    def check_if_serves_as_backend(self, vm):
        serves_for = []
        for d in self.attached_devs:
            if self.attached_devs[d]['backend_name'] == vm.name:
                serves_for.append((self.attached_devs[d]['dev'], self.attached_devs[d]['attached_to']['vm']))

        if len(serves_for) > 0:
            msg = "VM <b>" + vm.name + "</b> attaches block devices to other VMs: "
            msg += ', '.join(["<b>"+v.name+"</b>("+d+")" for (d,v) in serves_for ])
            msg += ".<br><br> Shutting the VM down will dettach the devices from them."

            QMessageBox.warning (None, "Warning!", msg)
