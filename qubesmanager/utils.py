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
import itertools
import os
import re
import qubesadmin
import traceback
import asyncio
from contextlib import suppress
import sys
import quamash
from qubesadmin import events

from PyQt5 import QtWidgets  # pylint: disable=import-error
from PyQt5.QtGui import QIcon  # pylint: disable=import-error


def _filter_internal(vm):
    return (not vm.klass == 'AdminVM'
            and not vm.features.get('internal', False))


def prepare_choice(widget, holder, propname, choice, default,
                   filter_function=None, *,
                   icon_getter=None, allow_internal=None, allow_default=False,
                   allow_none=False, transform=None):

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

    if propname is not None and allow_default:
        default = holder.property_get_default(propname)

    if allow_internal is None:
        allow_internal = propname is None or not propname.endswith('vm')

    if propname is not None:
        if holder.property_is_default(propname):
            oldvalue = qubesadmin.DEFAULT
        else:
            oldvalue = getattr(holder, propname)
            if oldvalue == '':
                oldvalue = None
            if transform is not None and oldvalue is not None:
                oldvalue = transform(oldvalue)
    else:
        oldvalue = object()  # won't match for identity
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
            default_string = str(default) if default is not None else 'none'
            if transform is not None:
                default_string = transform(default_string)
            text = 'default ({})'.format(default_string)
        # N+1: explicit None
        elif item is None:
            text = '(none)'
        # 1..N: choices
        else:
            text = str(item)
            if transform is not None:
                text = transform(text)

        if item == oldvalue:
            text += ' (current)'
            idx = i

        widget.insertItem(i, text)

        if icon_getter is not None:
            icon = icon_getter(item)
            if icon is not None:
                widget.setItemIcon(i, icon)

    widget.setCurrentIndex(idx)

    return choice_list, idx


class KernelVersion:  # pylint: disable=too-few-public-methods
    # Cannot use distutils.version.LooseVersion, because it fails at handling
    # versions that have no numbers in them
    def __init__(self, string):
        self.string = string
        self.groups = re.compile(r'(\d+)').split(self.string)

    def __lt__(self, other):
        for (self_content, other_content) in itertools.zip_longest(
                self.groups, other.groups):
            if self_content == other_content:
                continue
            if self_content is None:
                return True
            if other_content is None:
                return False
            if self_content.isdigit() and other_content.isdigit():
                return int(self_content) < int(other_content)
            return self_content < other_content


def prepare_kernel_choice(widget, holder, propname, default, *args, **kwargs):
    # TODO get from storage API (pool 'linux-kernel') (suggested by @marmarta)
    kernels = sorted(os.listdir('/var/lib/qubes/vm-kernels'),
                     key=KernelVersion)
    return prepare_choice(
        widget, holder, propname, kernels, default, *args, **kwargs)

def prepare_label_choice(widget, holder, propname, default, *args, **kwargs):
    try:
        app = holder.app
    except AttributeError:
        app = holder

    return prepare_choice(widget, holder, propname,
                          sorted(app.labels.values(), key=lambda l: l.index),
                          default, *args,
                          icon_getter=(lambda label:
                                       QIcon.fromTheme(label.icon)),
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


def get_path_from_vm(vm, service_name):
    """
    Displays a file/directory selection window for the given VM.

    :param vm: vm from which to select path
    :param service_name: qubes.SelectFile or qubes.SelectDirectory
    :return: path to file, checked for validity
    """

    path_re = re.compile(r"[a-zA-Z0-9/:.,_+=() -]*")
    path_max_len = 512

    if not vm:
        return None
    stdout, _stderr = vm.run_service_for_stdio(service_name)

    stdout = stdout.strip()

    untrusted_path = stdout.decode(encoding='ascii')[:path_max_len]

    if not untrusted_path:
        return None
    if path_re.fullmatch(untrusted_path):
        assert '../' not in untrusted_path
        assert '\0' not in untrusted_path
        return untrusted_path.strip()
    raise ValueError('Unexpected characters in path.')


def format_dependencies_list(dependencies):
    """Given a list of tuples representing properties, formats them in
    a readable list."""

    list_text = ""
    for (holder, prop) in dependencies:
        if holder is None:
            list_text += "- Global property <b>{}</b> <br>".format(prop)
        else:
            list_text += "- <b>{}</b> for qube <b>{}</b> <br>".format(
                prop, holder.name)

    return list_text


def loop_shutdown():
    pending = asyncio.Task.all_tasks()
    for task in pending:
        with suppress(asyncio.CancelledError):
            task.cancel()


# Bases on the original code by:
# Copyright (c) 2002-2007 Pascal Varet <p.varet@gmail.com>
def handle_exception(exc_type, exc_value, exc_traceback):

    filename, line, _, _ = traceback.extract_tb(exc_traceback).pop()
    filename = os.path.basename(filename)
    error = "%s: %s" % (exc_type.__name__, exc_value)

    strace = ""
    stacktrace = traceback.extract_tb(exc_traceback)
    while stacktrace:
        (filename, line, func, txt) = stacktrace.pop()
        strace += "----\n"
        strace += "line: %s\n" % txt
        strace += "func: %s\n" % func
        strace += "line no.: %d\n" % line
        strace += "file: %s\n" % filename

    msg_box = QtWidgets.QMessageBox()
    msg_box.setDetailedText(strace)
    msg_box.setIcon(QtWidgets.QMessageBox.Critical)
    msg_box.setWindowTitle("Houston, we have a problem...")
    msg_box.setText("Whoops. A critical error has occured. "
                    "This is most likely a bug in Qubes Manager.<br><br>"
                    "<b><i>%s</i></b>" % error +
                    "<br/>at line <b>%d</b><br/>of file %s.<br/><br/>"
                    % (line, filename))

    msg_box.exec_()


def run_asynchronous(app_name, icon_name, window_class):
    qt_app = QtWidgets.QApplication(sys.argv)
    qt_app.setOrganizationName("The Qubes Project")
    qt_app.setOrganizationDomain("http://qubes-os.org")
    qt_app.setApplicationName(app_name)
    qt_app.setWindowIcon(QIcon.fromTheme(icon_name))
    qt_app.lastWindowClosed.connect(loop_shutdown)

    qubes_app = qubesadmin.Qubes()

    loop = quamash.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)
    dispatcher = events.EventsDispatcher(qubes_app)

    window = window_class(qt_app, qubes_app, dispatcher)
    window.show()

    try:
        loop.run_until_complete(
            asyncio.ensure_future(dispatcher.listen_for_events()))
    except asyncio.CancelledError:
        pass
    except Exception:  # pylint: disable=broad-except
        loop_shutdown()
        exc_type, exc_value, exc_traceback = sys.exc_info()[:3]
        handle_exception(exc_type, exc_value, exc_traceback)


def run_synchronous(app_name, window_class):
    qt_app = QtWidgets.QApplication(sys.argv)
    qt_app.setOrganizationName("The Qubes Project")
    qt_app.setOrganizationDomain("http://qubes-os.org")
    qt_app.setApplicationName(app_name)

    sys.excepthook = handle_exception

    qubes_app = qubesadmin.Qubes()

    window = window_class(qt_app, qubes_app)

    window.show()

    qt_app.exec_()
    qt_app.exit()
