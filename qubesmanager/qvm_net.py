#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Show network tree

@author: unman
"""

from qubes.qubes import QubesVmCollection
qvm_collection = QubesVmCollection()
qvm_collection.lock_db_for_reading()
qvm_collection.load()
qvm_collection.unlock_db()
qvm_collection.pop(0)

def tree(netvm, padding):
    names={}
    padding = padding + '      '
    connected = netvm.connected_vms
    for i in connected:
        names[i] = connected[i].name
    for name in sorted(names.values()):
        vm = qvm_collection.get_qid_by_name(name)
        if qvm_collection[vm].is_running():
            vm_name  = qvm_collection[vm].name + '* '
        else:
            vm_name  = qvm_collection[vm].name
        if qvm_collection[vm].is_template():
            print(padding,'|->',vm_name,'(Tpl)')
        else:
            print(padding,'|->',vm_name)
        if qvm_collection[vm].is_netvm() :
            tree(qvm_collection[vm], padding)         
          
padding=''
for vm in qvm_collection:
    if qvm_collection[vm].is_netvm() and not qvm_collection[vm].netvm :
        print(qvm_collection[vm].name)
        tree(qvm_collection[vm], padding)
