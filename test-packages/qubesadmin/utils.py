# SPDX-FileCopyrightText: 2015 Michael Carbone, <michael@qubes-os.org> et al.
#
# SPDX-License-Identifier: GPL-2.0-only



### mock qubesadmin.utils module

def parse_size(*args, **kwargs):
    return args[0]

def updates_vms_status(*args, **kwargs):
    return args[0]

def size_to_human(*args, **kwargs):
    return args[0]

def vm_dependencies(*args):
    return args[0]
