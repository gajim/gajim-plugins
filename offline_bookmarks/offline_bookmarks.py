# -*- coding: utf-8 -*-
##

import gtk

from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log_calls
from common import ged
from common import gajim
import gtkgui_helpers
from config import ManageBookmarksWindow


class OfflineBookmarksPlugin(GajimPlugin):

    @log_calls('OfflineBookmarksPlugin')
    def init(self):
        self.description = _('OfflineBookmarks')
        self.pos_list = [_('after statusicon'), _('before avatar')]

        self.events_handlers = {
        'bookmarks-received': (ged.POSTGUI, self.bookmarks_received),
        'signed-in': (ged.POSTGUI, self.handle_event_signed_in),}

        self.gui_extension_points = {
            'groupchat_control': (self.connect_with_gc_control,
                                self.disconnect_from_gc_control),}
        self.controls = []
        self.config_dialog = OfflineBookmarksPluginConfigDialog(self)



    @log_calls('OfflineBookmarksPlugin')
    def activate(self):
        pass


    @log_calls('OfflineBookmarksPlugin')
    def deactivate(self):
        pass

    def save_bookmarks(self, account, bookmarks):
        jid = gajim.get_jid_from_account(account)
        if jid not in self.config:
            self.config[jid] = {}
        self.config[jid] = bookmarks

    def bookmarks_received(self, obj):
        self.save_bookmarks(obj.conn.name, obj.bookmarks)

    def handle_event_signed_in(self, obj):
        account = obj.conn.name
        connection = gajim.connections[account]
        jid = gajim.get_jid_from_account(obj.conn.name)
        bm_jids = [b['jid'] for b in connection.bookmarks]
        if jid in self.config:
            for bm in self.config[jid]:
                if bm['jid'] not in bm_jids:
                    connection.bookmarks.append(bm)
        invisible_show = gajim.SHOW_LIST.index('invisible')
        # do not autojoin if we are invisible
        if connection.connected == invisible_show:
            return
        # do not autojoin if bookmarks supported
        bookmarks_supported = (
            gajim.connections[account].private_storage_supported or \
            (gajim.connections[account].pubsub_supported and \
            gajim.connections[account].pubsub_publish_options_supported))
        if not bookmarks_supported:
            gajim.interface.auto_join_bookmarks(connection.name)

    def connect_with_gc_control(self, gc_control):
        control = Base(self, gc_control)
        self.controls.append(control)

    def disconnect_from_gc_control(self, gc_control):
        for control in self.controls:
            control.disconnect_from_gc_control()
        self.controls = []


class Base(object):
    def __init__(self, plugin, gc_control):
        self.plugin = plugin
        self.gc_control = gc_control
        self.create_buttons()

    def create_buttons(self):
        # create button
        actions_hbox = self.gc_control.xml.get_object('actions_hbox')
        self.button = gtk.Button(label=None, stock=None, use_underline=True)
        self.button.set_property('relief', gtk.RELIEF_NONE)
        self.button.set_property('can-focus', False)
        img = gtk.Image()
        if gtkgui_helpers.gtk_icon_theme.has_icon('bookmark-new'):
            img.set_from_icon_name('bookmark-new', gtk.ICON_SIZE_MENU)
        else:
            img.set_from_stock('gtk-add', gtk.ICON_SIZE_MENU)
        self.button.set_image(img)
        self.button.set_tooltip_text(_('Bookmark this room(local)'))
        send_button = self.gc_control.xml.get_object('send_button')
        send_button_pos = actions_hbox.child_get_property(send_button,
            'position')
        actions_hbox.add_with_properties(self.button, 'position',
            send_button_pos - 1, 'expand', False)
        self.button.set_no_show_all(True)
        id_ = self.button.connect('clicked', self.add_bookmark_button_clicked)
        self.gc_control.handlers[id_] = self.button
        for bm in gajim.connections[self.gc_control.account].bookmarks:
            if bm['jid'] == self.gc_control.contact.jid:
                self.button.hide()
                break
        else:
            account = self.gc_control.account
            bookmarks_supported = (
                gajim.connections[account].private_storage_supported and \
                (gajim.connections[account].pubsub_supported or \
                gajim.connections[account].pubsub_publish_options_supported))
            self.button.set_sensitive(not bookmarks_supported)
            self.button.set_visible(not bookmarks_supported)

    def add_bookmark_button_clicked(self, widget):
        """
        Bookmark the room, without autojoin and not minimized
        """
        from dialogs import ErrorDialog, InformationDialog
        password = gajim.gc_passwords.get(self.gc_control.room_jid, '')
        account = self.gc_control.account

        bm = {'name': self.gc_control.name,
              'jid': self.gc_control.room_jid,
              'autojoin': 0,
              'minimize': 0,
              'password': password,
              'nick': self.gc_control.nick}

        place_found = False
        index = 0
        # check for duplicate entry and respect alpha order
        for bookmark in gajim.connections[account].bookmarks:
            if bookmark['jid'] == bm['jid']:
                ErrorDialog(
                    _('Bookmark already set'),
                    _('Group Chat "%s" is already in your bookmarks.') % \
                    bm['jid'])
                return
            if bookmark['name'] > bm['name']:
                place_found = True
                break
            index += 1
        if place_found:
            gajim.connections[account].bookmarks.insert(index, bm)
        else:
            gajim.connections[account].bookmarks.append(bm)
        self.plugin.save_bookmarks(account, gajim.connections[account].bookmarks)
        gajim.interface.roster.set_actions_menu_needs_rebuild()
        InformationDialog(
            _('Bookmark has been added successfully'),
            _('You can manage your bookmarks via Actions menu in your roster.'))

    def disconnect_from_gc_control(self):
        actions_hbox = self.gc_control.xml.get_object('actions_hbox')
        actions_hbox.remove(self.button)


class OfflineBookmarksPluginConfigDialog(GajimPluginConfigDialog,
        ManageBookmarksWindow):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['vbox86'])
        vbox = self.xml.get_object('vbox86')
        self.child.pack_start(vbox)

    def on_run(self):
        from common.i18n import Q_
        # Account-JID, RoomName, Room-JID, Autojoin, Minimize, Passowrd, Nick,
        # Show_Status
        self.treestore = gtk.TreeStore(str, str, str, bool, bool, str, str, str)
        self.treestore.set_sort_column_id(1, gtk.SORT_ASCENDING)

        # Store bookmarks in treeview.
        for account in gajim.connections:
            if gajim.connections[account].connected <= 1:
                continue
            if gajim.connections[account].is_zeroconf:
                continue
            #if not gajim.connections[account].private_storage_supported:
                #continue
            iter_ = self.treestore.append(None, [None, account, None, None,
                    None, None, None, None])

            for bookmark in gajim.connections[account].bookmarks:
                if bookmark['name'] == '':
                    # No name was given for this bookmark.
                    # Use the first part of JID instead...
                    name = bookmark['jid'].split("@")[0]
                    bookmark['name'] = name
                from common import helpers
                # make '1', '0', 'true', 'false' (or other) to True/False
                autojoin = helpers.from_xs_boolean_to_python_boolean(
                        bookmark['autojoin'])

                minimize = helpers.from_xs_boolean_to_python_boolean(
                        bookmark['minimize'])

                print_status = bookmark.get('print_status', '')
                if print_status not in ('', 'all', 'in_and_out', 'none'):
                    print_status = ''
                self.treestore.append(iter_, [
                                account,
                                bookmark['name'],
                                bookmark['jid'],
                                autojoin,
                                minimize,
                                bookmark['password'],
                                bookmark['nick'],
                                print_status ])

        self.print_status_combobox = self.xml.get_object('print_status_combobox')
        model = gtk.ListStore(str, str)

        self.option_list = {'': _('Default'), 'all': Q_('?print_status:All'),
                'in_and_out': _('Enter and leave only'),
                'none': Q_('?print_status:None')}
        opts = sorted(self.option_list.keys())
        for opt in opts:
            model.append([self.option_list[opt], opt])

        self.print_status_combobox.set_model(model)
        self.print_status_combobox.set_active(1)

        self.view = self.xml.get_object('bookmarks_treeview')
        self.view.set_model(self.treestore)
        self.view.expand_all()

        renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn('Bookmarks', renderer, text=1)
        if self.view.get_column(0):
            self.view.remove_column(self.view.get_column(0))
        self.view.append_column(column)

        self.selection = self.view.get_selection()
        self.selection.connect('changed', self.bookmark_selected)

        #Prepare input fields
        self.title_entry = self.xml.get_object('title_entry')
        self.title_entry.connect('changed', self.on_title_entry_changed)
        self.nick_entry = self.xml.get_object('nick_entry')
        self.nick_entry.connect('changed', self.on_nick_entry_changed)
        self.server_entry = self.xml.get_object('server_entry')
        self.server_entry.connect('changed', self.on_server_entry_changed)
        self.room_entry = self.xml.get_object('room_entry')
        self.room_entry.connect('changed', self.on_room_entry_changed)
        self.pass_entry = self.xml.get_object('pass_entry')
        self.pass_entry.connect('changed', self.on_pass_entry_changed)
        self.autojoin_checkbutton = self.xml.get_object('autojoin_checkbutton')
        self.minimize_checkbutton = self.xml.get_object('minimize_checkbutton')

        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)
        self.show_all()
        # select root iter
        self.selection.select_iter(self.treestore.get_iter_root())

    def on_hide(self, widget):
        """
        Parse the treestore data into our new bookmarks array, then send the new
        bookmarks to the server.
        """
        (model, iter_) = self.selection.get_selected()
        if iter_ and model.iter_parent(iter_):
            #bookmark selected, check it
            if not self.check_valid_bookmark():
                return

        for account in self.treestore:
            account_unicode = account[1].decode('utf-8')
            gajim.connections[account_unicode].bookmarks = []

            for bm in account.iterchildren():
                # Convert True/False/None to '1' or '0'
                autojoin = unicode(int(bm[3]))
                minimize = unicode(int(bm[4]))
                name = bm[1]
                if name:
                    name = name.decode('utf-8')
                jid = bm[2]
                if jid:
                    jid = jid.decode('utf-8')
                pw = bm[5]
                if pw:
                    pw = pw.decode('utf-8')
                nick = bm[6]
                if nick:
                    nick = nick.decode('utf-8')

                # create the bookmark-dict
                bmdict = { 'name': name, 'jid': jid, 'autojoin': autojoin,
                    'minimize': minimize, 'password': pw, 'nick': nick,
                    'print_status': bm[7]}

                gajim.connections[account_unicode].bookmarks.append(bmdict)

            #gajim.connections[account_unicode].store_bookmarks()
            self.plugin.save_bookmarks(account_unicode,
                gajim.connections[account_unicode].bookmarks)
        gajim.interface.roster.set_actions_menu_needs_rebuild()
