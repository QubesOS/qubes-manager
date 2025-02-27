# The Qubes OS Project, https://www.qubes-os.org/
#
# Copyright (C) 2012  Agnieszka Kostrzewa <agnieszka.kostrzewa@gmail.com>
# Copyright (C) 2012  Marek Marczykowski-Górecki
#                       <marmarek@invisiblethingslab.com>
# Copyright (C) 2017  Wojtek Porczyk <woju@invisiblethingslab.com>
# Copyright (C) 2020  Marta Marczykowska-Górecka
#                       <marmarta@invisiblethingslab.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import itertools
import os
import re
import qubesadmin
import traceback
import asyncio
from contextlib import suppress
import sys
from qubesadmin import events
from qubesadmin import exc
import xdg.BaseDirectory
import pathlib
import shutil

from PyQt6 import QtWidgets, QtCore, QtGui  # pylint: disable=import-error
import qasync


# important usage note: which initialize_widget should I use?
# - if you want a list of VMs, use initialize_widget_with_vms, optionally
#   adding a property if you want to handle qubesadmin.DEFAULT and the
#   current (potentially default) value
# - if you want a list of labels or kernals, use
#       initialize_widget_with_kernels/labels
# - list of some things, but associated with a definite property (optionally
#       with qubesadmin.DEFAULT) - initialize_widget_for_property
# - list of some things, not associated with a property, but still having a
#       default - initialize_widget_with_default
# - just a list, no properties or defaults, just a nice list with a "current"
#       value - initialize_widget

def set_organization():
    """set the organization and config home directory for Qt based Apps."""
    # migrate old config file to the unified config directory
    # TODO: remove the below block when Qubes R4.3 becomes End-of-Life
    old_config_home = xdg.BaseDirectory.xdg_config_home + \
        '/The Qubes Project'
    new_config_home = xdg.BaseDirectory.xdg_config_home + '/qubes-os'
    config_file = 'qubes-qube-manager.conf'
    old_config_file = old_config_home + '/' + config_file
    new_config_file = new_config_home + '/' + config_file
    if os.path.isfile(old_config_file) and \
            not os.path.isfile(new_config_file):
        pathlib.Path(new_config_home).mkdir(parents=True, exist_ok=True)
        shutil.copy(old_config_file, new_config_file)

    QtCore.QCoreApplication.setOrganizationName('qubes-os')
    QtCore.QCoreApplication.setOrganizationDomain('qubes-os.org')
    QtCore.QCoreApplication.setApplicationName('qubes-qube-manager')

def is_internal(vm):
    """checks if the VM is either an AdminVM or has the 'internal' features"""
    try:
        return (vm.klass == 'AdminVM'
                or vm.features.get('internal', False))
    except exc.QubesDaemonAccessError:
        return False


def is_running(vm, default_state):
    """Checks if the VM is running, returns default_state if we have
    insufficient permissions to deteremine that."""
    try:
        return vm.is_running()
    except exc.QubesDaemonAccessError:
        return default_state


def translate(string):
    """helper function for translations"""
    return QtCore.QCoreApplication.translate(
        "ManagerUtils", string)


class SizeSpinBox(QtWidgets.QSpinBox):
    """A SpinBox subclass with extended handling for sizes in MiB and GiB"""
    # pylint: disable=invalid-name
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.pattern = r'(\d+\.?\d?) ?(GiB|MiB)'
        self.regex = re.compile(self.pattern)
        self.validator = QtGui.QRegularExpressionValidator(
            QtCore.QRegularExpression(self.pattern), self)

    def textFromValue(self, v: int) -> str:
        if v > 1024:
            return '{:.1f} GiB'.format(v / 1024)

        return '{} MiB'.format(v)

    def validate(self, text: str, pos: int):
        return self.validator.validate(text, pos)

    def valueFromText(self, text: str) -> int:
        value, unit = self.regex.fullmatch(text.strip()).groups()

        if unit == 'GiB':
            multiplier = 1024
        else:
            multiplier = 1

        return int(float(value) * multiplier)


class QubeManagerToolBar(QtWidgets.QToolBar): # pylint: disable=too-few-public-methods
    """a toolbar that does not collapse immediately on mouse leave event"""
    def __init__(self, parent=None):
        super().__init__(parent)
    def event(self, e):
        if e.type() == QtCore.QEvent.Type.Leave:
            return True
        return super().event(e)


def get_feature(vm, feature_name, default_value):
    try:
        return vm.features.get(feature_name, default_value)
    except exc.QubesDaemonAccessError:
        return default_value


def get_boolean_feature(vm, feature_name):
    """helper function to get a feature converted to a Bool if it does exist.
    Necessary because of the true/false in features being coded as 1/empty
    string."""
    result = get_feature(vm, feature_name, None)
    if result is not None:
        result = bool(result)
    return result


def did_widget_selection_change(widget):
    """a simple heuristic to check if the widget text contains appropriately
    translated 'current'"""
    if not widget.isEnabled():
        return False
    return not translate(" (current)") in widget.currentText()


def initialize_widget(widget, choices, selected_value=None,
                      icon_getter=None, add_current_label=True):
    """
    populates widget (ListBox or ComboBox) with items. Previous widget contents
    are erased.
    :param widget: QListBox or QComboBox; must support addItem and findText
    :param choices: list of tuples (text, value) to use to populate widget.
        text should be a string, value can be of any type, including None
    :param selected_value: initial widget value
    :param icon_getter: function of value that returns desired icon
    :param add_current_label: if initial value should be labelled as (current)
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

    if add_current_label:
        widget.setItemText(widget.currentIndex(),
                           widget.currentText() + translate(" (current)"))


def initialize_widget_for_property(*, widget, choices, holder, property_name,
                                   allow_default=False, icon_getter=None,
                                   add_current_label=True,
                                   default_text_provider=None):
    """
    populates widget (ListBox or ComboBox) with items, based on a listed
    property. Supports discovering the system default for the given property
    and handling qubesadmin.DEFAULT special value. Value of holder.property
    will be set as current item. Previous widget contents are erased.
    :param widget: QListBox or QComboBox; must support addItem and findText
    :param choices: list of tuples (text, value) to use to populate widget.
        text should be a string, value can be of any type, including None
    :param holder: object to use as property_name's holder
    :param property_name: name of the property
    :param allow_default: boolean, should a position with qubesadmin.DEFAULT
        be added; default False
    :param icon_getter: a function applied to values (from choices) that
        returns a QIcon to be used as a item icon; default None
    :param add_current_label: if initial value should be labelled as (current)
    :param default_text_provider: a function that will calculate the text for
        the default option using the property holder and property value as
        input
    :return:
    """
    if allow_default:
        try:
            default_property = holder.property_get_default(property_name)
        except exc.QubesDaemonAccessError:
            default_property = "ERROR: unavailable"
        if default_property is None:
            default_property = "none"
        if default_text_provider is None:
            choices.append(
                (translate("default ({})").format(default_property),
                qubesadmin.DEFAULT))
        else:
            choices.append(
                (translate("default ({})").format(
                    default_text_provider(holder, default_property)
                ), qubesadmin.DEFAULT))

    # calculate current (can be default)
    try:
        is_default = holder.property_is_default(property_name)
    except exc.QubesDaemonAccessError:
        is_default = False

    if is_default:
        current_value = qubesadmin.DEFAULT
    else:
        current_value = getattr(holder, property_name)

    initialize_widget(widget,
                      choices,
                      selected_value=current_value,
                      icon_getter=icon_getter,
                      add_current_label=add_current_label)


# TODO: improvement: add optional icon support
def initialize_widget_with_vms(
        *, widget, qubes_app, filter_function=(lambda x: True),
        allow_none=False, holder=None, property_name=None,
        allow_default=False, allow_internal=False):
    """
    populates widget (ListBox or ComboBox) with vm items, optionally based on
    a given property. Supports discovering the system default for the property
    and handling qubesadmin.DEFAULT special value. Value of holder.property
    will be set as current item. Previous widget contents are erased.
    :param widget: QListBox or QComboBox; must support addItem and findText
    :param qubes_app: Qubes() object
    :param filter_function: function used to filter vms; optional
    :param allow_none: should a None option be added; default False
    :param holder: object to use as property_name's holder
    :param property_name: name of the property
    :param allow_default: should a position with qubesadmin.DEFAULT be added;
        default False
    :param allow_internal: should AdminVMs and vms with feature 'internal' be
        used
    :return:
    """
    choices = []

    for vm in qubes_app.domains:
        if not allow_internal and is_internal(vm):
            continue
        if not filter_function(vm):
            continue
        choices.append((vm.name, vm))

    if allow_none:
        choices.append((translate("(none)"), None))

    if holder is None:
        initialize_widget(widget,
                          choices,
                          selected_value=choices[0][1],
                          add_current_label=False)
    else:
        initialize_widget_for_property(
            widget=widget, choices=choices, holder=holder,
            property_name=property_name, allow_default=allow_default)


def initialize_widget_with_default(
        *, widget, choices, add_none=False, add_qubes_default=False,
        mark_existing_as_default=False, default_value=None):
    """
    populates widget (ListBox or ComboBox) with items. Used when there is no
    corresponding property, but support for special qubesadmin.DEFAULT value
    is still needed.
    :param widget: QListBox or QComboBox; must support addItem and findText
    :param choices: list of tuples (text, value) to use to populate widget.
        text should be a string, value can be of any type, including None
    :param add_none: should a 'None' position be added
    :param add_qubes_default: should a qubesadmin.DEFAULT position be added
        (requires default_value to be set to something meaningful)
    :param mark_existing_as_default: should an existing value be marked
        as default. If used with conjuction with add_qubes_default, the
        default_value listed will be replaced by qubesadmin.DEFAULT
    :param default_value: what value should be used as the default
    :return:
    """
    added_existing = False

    if mark_existing_as_default:
        existing_default = [item for item in choices
                            if item[1] == default_value]
        if existing_default:
            choices = [item for item in choices if item not in existing_default]

            if add_qubes_default:
                # if for some reason (e.g. storage pools) we want to mark an
                # actual value as default and replace it with qubesadmin.DEFAULT
                default_value = qubesadmin.DEFAULT

            choices.insert(
                0, (translate("default ({})").format(existing_default[0][0]),
                    default_value))
            added_existing = True

    elif add_qubes_default:
        choices.insert(0, (translate("default ({})").format(default_value),
                           qubesadmin.DEFAULT))

    if add_none:
        if mark_existing_as_default and default_value is None and \
                not added_existing:
            choices.append((translate("default (none)"), None))
        else:
            choices.append((translate("(none)"), None))

    if add_qubes_default:
        selected_value = qubesadmin.DEFAULT
    elif mark_existing_as_default:
        selected_value = default_value
    else:
        selected_value = choices[0][1]

    initialize_widget(
        widget=widget, choices=choices, selected_value=selected_value,
        add_current_label=False)


def initialize_widget_with_kernels(
        *, widget, qubes_app, allow_none=False, holder=None,
        property_name=None, allow_default=False):
    """
    populates widget (ListBox or ComboBox) with kernel items, based on a given
    property. Supports discovering the system default for the property
    and handling qubesadmin.DEFAULT special value. Value of holder.property
    will be set as current item. Previous widget contents are erased.
    :param widget: QListBox or QComboBox; must support addItem and findText
    :param qubes_app: Qubes() object
    :param allow_none: should a None item be added
    :param holder: object to use as property_name's holder
    :param property_name: name of the property
    :param allow_default: should a qubesadmin.DEFAULT item be added
    :return:
    """
    kernels = [kernel.vid for kernel in qubes_app.pools['linux-kernel'].volumes]
    kernels = sorted(kernels, key=KernelVersion)

    choices = [(kernel, kernel) for kernel in kernels]

    if allow_none:
        choices.append((translate("(provided by qube)"), ''))

    initialize_widget_for_property(
        widget=widget, choices=choices, holder=holder,
        property_name=property_name, allow_default=allow_default)


def initialize_widget_with_labels(widget, qubes_app,
                                  holder=None, property_name='label'):
    """
    populates widget (ListBox or ComboBox) with label items, optionally based
    on a given property. Value of holder.property will be set as current item.
    Previous widget contents are erased.
    :param widget: QListBox or QComboBox; must support addItem and findText
    :param qubes_app: Qubes() object
    :param holder: object to use as property_name's holder; can be None
    :param property_name: name of the property
    :return:
    """
    labels = sorted(qubes_app.labels.values(), key=lambda l: l.index)
    choices = [(label.name, label) for label in labels]

    def icon_getter(label):
        return QtGui.QIcon.fromTheme(label.icon)

    if holder:
        initialize_widget_for_property(widget=widget,
                                       choices=choices,
                                       holder=holder,
                                       property_name=property_name,
                                       icon_getter=icon_getter)
    else:
        initialize_widget(widget=widget,
                          choices=choices,
                          selected_value=labels[0],
                          icon_getter=icon_getter,
                          add_current_label=False)


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

    path_re = re.compile(r"[a-zA-Z0-9/:.,_+=() ?-]*")
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
    pending = asyncio.all_tasks()
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
    msg_box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(QtCore.QCoreApplication.translate(
        "ManagerUtils", "Houston, we have a problem..."))
    msg_box.setText(QtCore.QCoreApplication.translate(
        "ManagerUtils", "Whoops. A critical error has occurred. "
                        "This is most likely a bug in Qubes Manager.<br><br>"
                        "<b><i>{0}</i></b><br/>at line <b>{1}</b><br/>of file "
                        "{2}.<br/><br/>").format(error, line, filename))

    msg_box.exec()


def run_asynchronous(window_class):
    set_organization()
    qt_app = QtWidgets.QApplication(sys.argv)

    translator = QtCore.QTranslator(qt_app)
    locale = QtCore.QLocale.system().name()
    i18n_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'i18n')
    translator.load("qubesmanager_{!s}.qm".format(locale), i18n_dir)
    qt_app.installTranslator(translator)
    QtCore.QCoreApplication.installTranslator(translator)

    qt_app.lastWindowClosed.connect(loop_shutdown)

    qubes_app = qubesadmin.Qubes()

    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)

    async def setup():
        dispatcher = events.EventsDispatcher(qubes_app)

        window = window_class(qt_app, qubes_app, dispatcher)

        if hasattr(window, "setup_application"):
            window.setup_application()

        window.show()

        await dispatcher.listen_for_events()

    try:
        loop.run_until_complete(asyncio.ensure_future(setup()))
    except asyncio.CancelledError:
        pass
    except Exception:  # pylint: disable=broad-except
        loop_shutdown()
        exc_type, exc_value, exc_traceback = sys.exc_info()[:3]
        handle_exception(exc_type, exc_value, exc_traceback)


def run_synchronous(window_class):
    set_organization()
    qt_app = QtWidgets.QApplication(sys.argv)

    translator = QtCore.QTranslator(qt_app)
    locale = QtCore.QLocale.system().name()
    i18n_dir = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'i18n')
    translator.load("qubesmanager_{!s}.qm".format(locale), i18n_dir)
    qt_app.installTranslator(translator)
    QtCore.QCoreApplication.installTranslator(translator)

    sys.excepthook = handle_exception

    qubes_app = qubesadmin.Qubes()

    window = window_class(qt_app, qubes_app)

    if hasattr(window, "setup_application"):
        window.setup_application()

    window.show()

    qt_app.exec()
    qt_app.exit()

    return window
