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

from PyQt5 import QtWidgets, QtCore, QtGui  # pylint: disable=import-error


#TODO: remove
def _filter_internal(vm):
    return (not vm.klass == 'AdminVM'
            and not vm.features.get('internal', False))


def is_internal(vm):
    return (vm.klass == 'AdminVM'
            or vm.features.get('internal', False))


def translate(string):
    return QtCore.QCoreApplication.translate(
        "ManagerUtils", string)


class SizeSpinBox(QtWidgets.QSpinBox):
    # pylint: disable=invalid-name, no-self-use
    def __init__(self, *args, **kwargs):
        super(SizeSpinBox, self).__init__(*args, **kwargs)

        self.pattern = r'(\d+\.?\d?) ?(GB|MB)'
        self.regex = re.compile(self.pattern)
        self.validator = QtGui.QRegExpValidator(QtCore.QRegExp(
            self.pattern), self)

    def textFromValue(self, v: int) -> str:
        if v > 1024:
            return '{:.1f} GB'.format(v / 1024)

        return '{} MB'.format(v)

    def validate(self, text: str, pos: int):
        return self.validator.validate(text, pos)

    def valueFromText(self, text: str) -> int:
        value, unit = self.regex.fullmatch(text.strip()).groups()

        if unit == 'GB':
            multiplier = 1024
        else:
            multiplier = 1

        return int(float(value) * multiplier)


def get_boolean_feature(vm, feature_name):
    result = vm.features.get(feature_name, None)
    if result is not None:
        result = bool(result)
    return result

# TODO: doublecheck translation


def did_widget_selection_change(widget):
    return not translate(" (current)") in widget.currentText()


def initialize_widget(widget, choices, selected_value=None, icon_getter=None):
    """
    populates widget (ListBox or ComboBox) with items. Previous widget contents
    are erased.
    :param widget: widget to populate
    :param choices: list of tuples (text, value) to use to populate widget
    :param selected_value: value to populate widget with
    :param icon_getter: function of value that returns desired icon
    :return:
    """

    widget.clear()
    selected_item = None

    for (name, value) in choices:
        if value == selected_value:
            selected_item = name
        if icon_getter is not None:
            widget.addItem(icon_getter(value), name, userData=value)
        else:
            widget.addItem(name, userData=value)

    if selected_item is not None:
        widget.setCurrentIndex(widget.findText(selected_item))
    else:
        widget.addItem(str(selected_value), selected_value)
        widget.setCurrentIndex(widget.findText(str(selected_value)))

    widget.setItemText(widget.currentIndex(),
                       widget.currentText() + translate(" (current)"))


def initialize_widget_for_property(
        widget, choices, holder, property_name, allow_default=False,
        icon_getter=None):
    # potentially add default
    if allow_default:
        default_property = holder.property_get_default(property_name)
        if default_property is None:
            default_property = "none"
        choices.append(
            (translate("default ({})").format(default_property),
             qubesadmin.DEFAULT))

    # calculate current (can be default)
    if holder.property_is_default(property_name):
        current_value = qubesadmin.DEFAULT
    else:
        current_value = getattr(holder, property_name)

    initialize_widget(widget,
                      choices,
                      selected_value=current_value,
                      icon_getter=icon_getter)


# TODO: add use icons here
def initialize_widget_with_vms(widget,
                               qubes_app,
                               filter_function=(lambda x: True),
                               allow_none=False,
                               holder=None,
                               property_name=None,
                               allow_default=False,
                               allow_internal=False):
    choices = []

    for vm in qubes_app.domains:
        if not allow_internal and is_internal(vm):
            continue
        if not filter_function(vm):
            continue
        choices.append((vm.name, vm))

    if allow_none:
        choices.append((translate("(none)"), None))

    initialize_widget_for_property(
        widget=widget, choices=choices, holder=holder,
        property_name=property_name, allow_default=allow_default)


def initialize_widget_with_kernels(widget,
                                   qubes_app,
                                   allow_none=False,
                                   holder=None,
                                   property_name=None,
                                   allow_default=False
                                   ):
    kernels = [kernel.vid for kernel in qubes_app.pools['linux-kernel'].volumes]
    kernels = sorted(kernels, key=KernelVersion)

    choices = [(kernel, kernel) for kernel in kernels]

    if allow_none:
        choices.append((translate("(none)"), None))

    initialize_widget_for_property(
        widget=widget, choices=choices, holder=holder,
        property_name=property_name, allow_default=allow_default)


def initialize_widget_with_labels(widget,
                                  qubes_app,
                                  holder=None,
                                  property_name='label'):
    labels = sorted(qubes_app.labels.values(), key=lambda l: l.index)
    choices = [(label.name, label) for label in labels]

    initialize_widget_for_property(
        widget=widget,
        choices=choices,
        holder=holder,
        property_name=property_name,
        icon_getter=(lambda label:
                     QtGui.QIcon.fromTheme(label.icon)))


def prepare_choice(widget, holder, propname, choice, default,
                   filter_function=None, *,
                   icon_getter=None, allow_internal=None, allow_default=False,
                   allow_none=False, transform=None):
    # for newly created vms, set propname to None

    # clear the widget, so that prepare_choice functions can be used
    # to refresh widget values
    while widget.count() > 0:
        widget.removeItem(0)

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
            text = QtCore.QCoreApplication.translate(
                "ManagerUtils", 'default ({})').format(default_string)
        # N+1: explicit None
        elif item is None:
            text = QtCore.QCoreApplication.translate("ManagerUtils", '(none)')
        # 1..N: choices
        else:
            text = str(item)
            if transform is not None:
                text = transform(text)

        if item == oldvalue:
            text += QtCore.QCoreApplication.translate(
                "ManagerUtils", ' (current)')
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
    try:
        app = holder.app
    except AttributeError:
        app = holder
    kernels = [kernel.vid for kernel in app.pools['linux-kernel'].volumes]
    kernels = sorted(kernels, key=KernelVersion)

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
                                       QtGui.QIcon.fromTheme(label.icon)),
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
    raise ValueError(QtCore.QCoreApplication.translate(
        "ManagerUtils", 'Unexpected characters in path.'))


def format_dependencies_list(dependencies):
    """Given a list of tuples representing properties, formats them in
    a readable list."""

    list_text = ""
    for (holder, prop) in dependencies:
        if holder is None:
            list_text += QtCore.QCoreApplication.translate(
                "ManagerUtils", "- Global property <b>{}</b> <br>").format(prop)
        else:
            list_text += QtCore.QCoreApplication.translate(
                "ManagerUtils", "- <b>{0}</b> for qube <b>{1}</b> <br>").format(
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
    msg_box.setWindowTitle(QtCore.QCoreApplication.translate(
        "ManagerUtils", "Houston, we have a problem..."))
    msg_box.setText(QtCore.QCoreApplication.translate(
        "ManagerUtils", "Whoops. A critical error has occured. "
                        "This is most likely a bug in Qubes Manager.<br><br>"
                        "<b><i>{0}</i></b><br/>at line <b>{1}</b><br/>of file "
                        "{2}.<br/><br/>").format(error, line, filename))

    msg_box.exec_()


def run_asynchronous(window_class):
    qt_app = QtWidgets.QApplication(sys.argv)

    translator = QtCore.QTranslator(qt_app)
    locale = QtCore.QLocale.system().name()
    i18n_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'i18n')
    translator.load("qubesmanager_{!s}.qm".format(locale), i18n_dir)
    qt_app.installTranslator(translator)
    QtCore.QCoreApplication.installTranslator(translator)

    qt_app.setOrganizationName("The Qubes Project")
    qt_app.setOrganizationDomain("http://qubes-os.org")
    qt_app.lastWindowClosed.connect(loop_shutdown)

    qubes_app = qubesadmin.Qubes()

    loop = quamash.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)
    dispatcher = events.EventsDispatcher(qubes_app)

    window = window_class(qt_app, qubes_app, dispatcher)

    if hasattr(window, "setup_application"):
        window.setup_application()

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


def run_synchronous(window_class):
    qt_app = QtWidgets.QApplication(sys.argv)

    translator = QtCore.QTranslator(qt_app)
    locale = QtCore.QLocale.system().name()
    i18n_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'i18n')
    translator.load("qubesmanager_{!s}.qm".format(locale), i18n_dir)
    qt_app.installTranslator(translator)
    QtCore.QCoreApplication.installTranslator(translator)

    qt_app.setOrganizationName("The Qubes Project")
    qt_app.setOrganizationDomain("http://qubes-os.org")

    sys.excepthook = handle_exception

    qubes_app = qubesadmin.Qubes()

    window = window_class(qt_app, qubes_app)

    if hasattr(window, "setup_application"):
        window.setup_application()

    window.show()

    qt_app.exec_()
    qt_app.exit()
