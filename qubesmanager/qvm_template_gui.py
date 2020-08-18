import collections
import concurrent
import concurrent.futures
import itertools
import json
import os
import subprocess
import typing

import gi
gi.require_version('Gtk', '3.0')

#pylint: disable=wrong-import-position
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango

BASE_CMD = ['qvm-template', '--enablerepo=*', '--yes', '--quiet']

class Template(typing.NamedTuple):
    status: str
    name: str
    evr: str
    reponame: str
    size: int
    buildtime: str
    installtime: str
    licence: str
    url: str
    summary: str
    # --- internal ---
    description: str
    default_status: str
    weight: int
    model: Gtk.TreeModel
    # ----------------

    # XXX: Is there a better way of doing this?
    TYPES = [str, str, str, str, int, str, str, str,
        str, str, str, str, int, Gtk.TreeModel]

    COL_NAMES = [
        'Status',
        'Name',
        'Version',
        'Reponame',
        'Size (kB)',
        'Build Time',
        'Install Time',
        'License',
        'URL',
        'Summary']

    @staticmethod
    def build(status, entry, model):
        return Template(
            status,
            entry['name'],
            '%s:%s-%s' % (entry['epoch'], entry['version'], entry['release']),
            entry['reponame'],
            # XXX: This may overflow glib ints, though pretty unlikely in the
            #       foreseeable future
            int(entry['size']) / 1000,
            entry['buildtime'],
            entry['installtime'],
            entry['license'],
            entry['url'],
            entry['summary'],
            entry['description'],
            status,
            Pango.Weight.BOOK,
            model
        )

class Action(typing.NamedTuple):
    op: str
    name: str
    evr: str

    TYPES = [str, str, str]
    COL_NAMES = ['Operation', 'Name', 'Version']

# TODO: Set default window sizes

class ConfirmDialog(Gtk.Dialog):
    def __init__(self, parent, actions):
        super(ConfirmDialog, self).__init__(
            title='Confirmation', transient_for=parent, modal=True)
        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK)

        box = self.get_content_area()
        self.msg = Gtk.Label()
        self.msg.set_markup((
            '<b>WARNING: Local changes made to the following'
            ' templates will be overwritten! Continue?</b>'))
        box.add(self.msg)

        self.store = Gtk.ListStore(*Action.TYPES)
        self.listing = Gtk.TreeView(model=self.store)
        for idx, colname in enumerate(Action.COL_NAMES):
            renderer = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(colname, renderer, text=idx)
            self.listing.append_column(col)
            col.set_sort_column_id(idx)

        for row in actions:
            self.store.append(row)

        self.scrollable_listing = Gtk.ScrolledWindow()
        self.scrollable_listing.add(self.listing)
        box.pack_start(self.scrollable_listing, True, True, 16)

        self.show_all()

class ProgressDialog(Gtk.Dialog):
    def __init__(self, parent):
        super(ProgressDialog, self).__init__(
            title='Processing...', transient_for=parent, modal=True)
        box = self.get_content_area()

        self.spinner = Gtk.Spinner()
        self.spinner.start()
        box.add(self.spinner)

        self.msg = Gtk.Label()
        self.msg.set_text('Processing...')
        box.add(self.msg)

        self.infobox = Gtk.TextView()
        self.scrollable = Gtk.ScrolledWindow()
        self.scrollable.add(self.infobox)

        box.pack_start(self.scrollable, True, True, 16)

        self.show_all()

    def finish(self, success):
        self.spinner.stop()
        if success:
            self.msg.set_text('Operations succeeded.')
        else:
            self.msg.set_markup('<b>Error:</b>')
        self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        self.run()

class QubesTemplateApp(Gtk.Window):
    def __init__(self):
        super(QubesTemplateApp, self).__init__(title='Qubes Template Manager')

        self.iconsize = Gtk.IconSize.SMALL_TOOLBAR

        self.executor = concurrent.futures.ThreadPoolExecutor()
        self.outerbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.__build_action_models()
        self.__build_toolbar()
        self.__build_listing()
        self.__build_infobox()

        self.add(self.outerbox)

    def __build_action_models(self):
        #pylint: disable=invalid-name
        OPS = [
            ['Installed', 'Reinstall', 'Remove'],
            ['Extra', 'Remove'],
            ['Upgradable', 'Upgrade', 'Remove'],
            ['Downgradable', 'Downgrade', 'Remove'],
            ['Available', 'Install']
        ]
        self.action_models = {}
        for ops in OPS:
            # First element is the default status for the certain class of
            # templates
            self.action_models[ops[0]] = Gtk.ListStore(str)
            for oper in ops:
                self.action_models[ops[0]].append([oper])

    def __build_toolbar(self):
        self.toolbar = Gtk.Toolbar()
        self.btn_refresh = Gtk.ToolButton(
            icon_widget=Gtk.Image.new_from_icon_name(
                'view-refresh', self.iconsize),
            label='Refresh')
        self.btn_refresh.connect('clicked', self.refresh)
        self.toolbar.insert(self.btn_refresh, 0)

        self.btn_install = Gtk.ToolButton(
            icon_widget=Gtk.Image.new_from_icon_name('go-down', self.iconsize),
            label='Apply')
        self.btn_install.connect('clicked', self.show_confirm)
        self.toolbar.insert(self.btn_install, 1)

        self.outerbox.pack_start(self.toolbar, False, True, 0)

    def __build_listing(self):
        self.store = Gtk.ListStore(*Template.TYPES)

        self.listing = Gtk.TreeView(model=self.store)
        self.cols = []
        for idx, colname in enumerate(Template.COL_NAMES):
            if colname == 'Status':
                renderer = Gtk.CellRendererCombo()
                renderer.set_property('editable', True)
                renderer.set_property('has-entry', False)
                renderer.set_property('text-column', 0)
                renderer.connect('edited', self.entry_edit)
                col = Gtk.TreeViewColumn(
                    colname,
                    renderer,
                    text=idx,
                    weight=len(Template.TYPES) - 2,
                    model=len(Template.TYPES) - 1)
            else:
                renderer = Gtk.CellRendererText()
                col = Gtk.TreeViewColumn(
                    colname,
                    renderer,
                    text=idx,
                    weight=len(Template.TYPES) - 2)
            # Right-align for integers
            if Template.TYPES[idx] is int:
                renderer.set_property('xalign', 1.0)
            self.cols.append(col)
            self.listing.append_column(col)
            col.set_sort_column_id(idx)
        sel = self.listing.get_selection()
        sel.set_mode(Gtk.SelectionMode.MULTIPLE)
        sel.connect('changed', self.update_info)

        self.scrollable_listing = Gtk.ScrolledWindow()
        self.scrollable_listing.add(self.listing)
        self.scrollable_listing.set_visible(False)

        self.spinner = Gtk.Spinner()

        self.outerbox.pack_start(self.scrollable_listing, True, True, 0)
        self.outerbox.pack_start(self.spinner, True, True, 0)

    def __build_infobox(self):
        self.infobox = Gtk.TextView()
        self.outerbox.pack_start(self.infobox, True, True, 16)

    def refresh(self, button=None):
        # Ignore if we're already doing a refresh
        #pylint: disable=no-member
        if self.spinner.props.active:
            return
        self.scrollable_listing.set_visible(False)
        self.spinner.start()
        self.spinner.set_visible(True)
        self.store.clear()
        def worker():
            cmd = BASE_CMD[:]
            if button is not None:
                # Force refresh if triggered by button press
                cmd.append('--refresh')
            cmd.extend(['info', '--machine-readable-json', '--installed',
                '--available', '--upgrades', '--extras'])
            output = subprocess.check_output(cmd)
            # Default type is dict as we're going to replace the lists with
            # dicts shortly after
            tpls = collections.defaultdict(dict, json.loads(output))
            # Remove duplicates
            # Should this be done in qvm-template?
            # TODO: Merge templates with same name?
            #       If so, we may need to have a separate UI to force versions.
            local_names = set(x['name'] for x in tpls['installed'])
            # Convert to dict for easier subtraction
            for key in tpls:
                tpls[key] = {
                    (x['name'], x['epoch'], x['version'], x['release']): x
                    for x in tpls[key]}
            tpls['installed'] = {
                k: v for k, v in tpls['installed'].items()
                    if k not in tpls['extra'] and k not in tpls['upgradable']}
            tpls['available'] = {
                k: v for k, v in tpls['available'].items()
                    if k not in tpls['installed']
                        and k not in tpls['upgradable']}
            # If the package name is installed but the specific version is
            # neither installed or an upgrade, then it must be a downgrade
            tpls['downgradable'] = {
                k: v for k, v in tpls['available'].items()
                    if k[0] in local_names}
            tpls['available'] = {
                k: v for k, v in tpls['available'].items()
                    if k not in tpls['downgradable']}
            # Convert back to list
            for key in tpls:
                tpls[key] = list(tpls[key].values())
            for status, seq in tpls.items():
                status_str = status.title()
                for entry in seq:
                    self.store.append(Template.build(
                        status_str, entry, self.action_models[status_str]))

        def finish_cb(future):
            def callback():
                if future.exception() is not None:
                    buf = self.infobox.get_buffer()
                    buf.set_text('Error:\n' + str(future.exception()))
                self.spinner.set_visible(False)
                self.spinner.stop()
                self.scrollable_listing.set_visible(True)
            GLib.idle_add(callback)

        future = self.executor.submit(worker)
        future.add_done_callback(finish_cb)

    def show_confirm(self, button=None):
        _ = button # unused
        actions = []
        for row in self.store:
            tpl = Template(*row)
            if tpl.status != tpl.default_status:
                actions.append(Action(tpl.status, tpl.name, tpl.evr))
        dialog = ConfirmDialog(self, actions)
        resp = dialog.run()
        dialog.destroy()
        if resp == Gtk.ResponseType.OK:
            self.do_install(actions)

    def do_install(self, actions):
        dialog = ProgressDialog(self)
        def worker():
            actions.sort()
            for oper, grp in itertools.groupby(actions, lambda x: x[0]):
                oper = oper.lower()
                # No need to specify versions for local operations
                if oper in ('remove', 'purge'):
                    specs = [x.name for x in grp]
                else:
                    specs = [x.name + '-' + x.evr for x in grp]
                # FIXME: (C)Python versions before 3.9 fully-buffers stderr in
                #        this context, cf. https://bugs.python.org/issue13601
                #        Forcing it to be unbuffered for the time being so that
                #        the messages can be displayed in time.
                envs = os.environ.copy()
                envs['PYTHONUNBUFFERED'] = '1'
                proc = subprocess.Popen(
                    BASE_CMD + [oper, '--'] + specs,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=envs)
                #pylint: disable=cell-var-from-loop
                for line in iter(proc.stdout.readline, ''):
                    # Need to modify the buffers in the main thread
                    def callback():
                        buf = dialog.infobox.get_buffer()
                        end_iter = buf.get_end_iter()
                        buf.insert(end_iter, line)
                    GLib.idle_add(callback)
                if proc.wait() != 0:
                    return False
            return True

        def finish_cb(future):
            def callback():
                dialog.finish(future.result())
                dialog.destroy()
                self.refresh()
            GLib.idle_add(callback)

        future = self.executor.submit(worker)
        future.add_done_callback(finish_cb)

    def update_info(self, sel):
        model, treeiters = sel.get_selected_rows()
        if not treeiters:
            return
        buf = self.infobox.get_buffer()
        if len(treeiters) > 1:
            def row_to_spec(row):
                tpl = Template(*row)
                return tpl.name + '-' + tpl.evr
            text = '\n'.join(row_to_spec(model[it]) for it in treeiters)
            buf.set_text('Selected templates:\n' + text)
        else:
            itr = treeiters[0]
            tpl = Template(*model[itr])
            text = 'Name: %s\n\nDescription:\n%s' % (tpl.name, tpl.description)
            buf.set_text(text)

    def entry_edit(self, widget, path, text):
        _ = widget # unused
        #pylint: disable=unsubscriptable-object
        tpl = Template(*self.store[path])
        tpl = tpl._replace(status=text)
        if text == tpl.default_status:
            tpl = tpl._replace(weight=Pango.Weight.BOOK)
        else:
            tpl = tpl._replace(weight=Pango.Weight.BOLD)
        #pylint: disable=unsupported-assignment-operation
        self.store[path] = tpl

if __name__ == '__main__':
    main = QubesTemplateApp()
    main.connect('destroy', Gtk.main_quit)
    main.show_all()
    main.refresh()
    Gtk.main()
