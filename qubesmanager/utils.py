#
# The Qubes OS Project, https://www.qubes-os.org
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski-Górecki
#                       <marmarek@invisiblethingslab.com>
# Copyright (C) 2017  Wojtek Porczyk <woju@invisiblethingslab.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import functools
import os

import qubesadmin

from PyQt4.QtGui import QIcon

def _filter_internal(vm):
    return (not isinstance(vm, qubesadmin.vm.AdminVM)
        and not vm.features.get('internal', False))

def prepare_choice(widget, holder, propname, choice, default,
        filter_function=None, *,
        icon_getter=None, allow_internal=None, allow_default=False,
        allow_none=False):

    # for newly created vms, set propname to None

    debug(
        'prepare_choice(widget={widget!r}, '
        'holder={holder!r}, '
        'propname={propname!r}, '
        'choice={choice!r}, '
        'default={default!r}, '
        'filter_function={filter_function!r}, '
        'icon_getter={icon_getter!r}, '
        'allow_internal={allow_internal!r}, '
        'allow_default={allow_default!r}, '
        'allow_none={allow_none!r})'.format(**locals()))

    if allow_internal is None:
        allow_internal = propname is None or not propname.endswith('vm')

    if propname is not None:
        oldvalue = getattr(holder, propname)
        is_default = holder.property_is_default(propname)
    else:
        oldvalue = object()  # won't match for identity
        is_default = False
    idx = 0

    choice_list = list(choice)[:]
    if not allow_internal:
        choice_list = filter(_filter_internal, choice_list)
    if filter_function is not None:
        choice_list = filter(filter_function, choice_list)
    choice_list = list(choice_list)

    if allow_default:
        choice_list.insert(0, qubesadmin.DEFAULT)
    if allow_none:
        choice_list.append(None)

    for i, item in enumerate(choice_list):
        debug('i={} item={}'.format(i, item))
        # 0: default (unset)
        if item is qubesadmin.DEFAULT:
            text = 'default ({})'.format(
                str(default) if default is not None else 'none')
        # N+1: explicit None
        elif item is None:
            text = 'none'
        # 1..N: choices
        else:
            text = str(item)

        if item is qubesadmin.DEFAULT and is_default \
        or item is not qubesadmin.DEFAULT and item is oldvalue:
            text += ' (current)'
            idx = i

        widget.insertItem(i, text)

        if icon_getter is not None:
            icon = icon_getter(item)
            if icon is not None:
                widget.setItemIcon(i, icon)

    widget.setCurrentIndex(idx)

    return choice_list, idx

def prepare_kernel_choice(widget, holder, propname, default, *args, **kwargs):
    # TODO get from storage API (pool 'linux-kernel') (suggested by @marmarta)
    return prepare_choice(widget, holder, propname,
        os.listdir('/var/lib/qubes/vm-kernels'), default, *args, **kwargs)

def prepare_label_choice(widget, holder, propname, default, *args, **kwargs):
    try:
        app = holder.app
    except AttributeError:
        app = holder

    return prepare_choice(widget, holder, propname,
        sorted(app.labels, key=lambda l: l.index),
        default, *args,
        icon_getter=(lambda label: QIcon.fromTheme(label.icon)),
        **kwargs)

def prepare_vm_choice(widget, holder, propname, default, *args, **kwargs):
    try:
        app = holder.app
    except AttributeError:
        app = holder

    return prepare_choice(widget, holder, propname, app.domains, default,
        *args, **kwargs)

def is_debug():
    return os.getenv('QUBES_MANAGER_DEBUG', '') not in ('', '0')

def debug(*args, **kwargs):
    if not is_debug():
        return
    print(*args, **kwargs)
