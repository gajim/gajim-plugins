import os
import logging

from gi.repository import Gtk
from gi.repository import GdkPixbuf

from clients_icons.clients import CLIENTS, LIBPURPLE_CLIENTS

from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.common import ged
from gajim.common import app
from gajim.common import caps_cache

# Since Gajim 1.1.0 _() has to be imported
try:
    from gajim.common.i18n import _
except ImportError:
    pass

log = logging.getLogger('gajim.plugin_system.clients_icons')


class ClientsIconsPlugin(GajimPlugin):

    @log_calls('ClientsIconsPlugin')
    def init(self):
        self.description = _('Shows client icons in roster'
                             ' and in groupchats.')
        self.pos_list = [_('after statusicon'), _('before avatar')]
        self.events_handlers = {
            'caps-presence-received': (ged.POSTGUI,
                                       self.caps_presence_received),
            'gc-presence-received': (ged.POSTGUI,
                                     self.gc_presence_received),
            'caps-disco-received': (ged.POSTGUI,
                                    self.caps_disco_received), }
        self.gui_extension_points = {
            'groupchat_control': (self.connect_with_groupchat_control,
                                  self.disconnect_from_groupchat_control),
            'roster_draw_contact': (self.connect_with_roster_draw_contact, None),
            'roster_tooltip_populate': (self.connect_with_roster_tooltip_populate, None),
            'gc_tooltip_populate': (self.connect_with_gc_tooltip_populate, None),
            }
        self.config_default_values = {
                'show_in_roster': (True, ''),
                'show_in_groupchats': (True, ''),
                'show_in_tooltip': (True, ''),
                'show_unknown_icon': (True, ''),
                'pos_in_list': (0, ''),
                'show_facebook': (True, ''),}

        self.config_dialog = ClientsIconsPluginConfigDialog(self)
        icon_path = os.path.join(self.local_file_path('icons'), 'unknown.png')
        self.default_pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            icon_path, 16, 16)
        self.icon_cache = {}

    @log_calls('ClientsIconsPlugin')
    def get_client_name(self, contact, client_name):
        identities = contact.client_caps.get_cache_lookup_strategy()(
            caps_cache.capscache).identities
        if identities:
            log.debug('get_client_name, identities: %s', str(identities))
            for entry in identities:
                if entry['category'] == 'client':
                    client_name = entry.get('name', client_name)
                    break
        return client_name

    def get_client_icon_by_name(self, client_name):
        client_icon = None
        name_splits = client_name.split()
        name_splits = reversed([" ".join(name_splits[:(i+1)]) for i in range(len(name_splits))])
        for name in name_splits:
            if not client_icon:
                log.debug("get_client_icon_by_name, searching for name fragment '%s'..." % name)
                client_icon = CLIENTS.get(name, (None,))[0]
                if client_icon:
                    break
        return client_icon

    @staticmethod
    def is_groupchat(contact):
        if hasattr(contact, 'is_groupchat'):
            return contact.is_groupchat()
        return False

    @log_calls('ClientsIconsPlugin')
    def add_tooltip_row(self, tooltip, contact, tooltip_grid):
        caps = contact.client_caps._node
        log.debug('connect_with_gc_tooltip_populate, caps: %s', caps)
        caps_image, client_name = self.get_icon(caps, contact)
        client_name = self.get_client_name(contact, client_name)
        caps_image.set_halign(Gtk.PositionType.RIGHT)
        log.debug('connect_with_gc_tooltip_populate, client_name: %s', client_name)

        # fill clients table
        self.table = Gtk.Grid()
        self.table.set_name('client_icons_grid')
        self.table.set_property('column-spacing', 5)
        self.table.attach(caps_image, 1, 1, 1, 1)
        label_name = Gtk.Label()
        label_name.set_halign(Gtk.PositionType.RIGHT)
        label_name.set_markup(client_name)
        self.table.attach(label_name, 2, 1, 1, 1)
        self.table.show_all()

        # set label
        label = Gtk.Label()
        label.set_name('client_icons_label')
        label.set_halign(Gtk.PositionType.RIGHT)
        label.set_markup(_('Client:'))
        label.show()

        # set client table to tooltip
        tooltip_grid.insert_next_to(tooltip.resource_label,
                                    Gtk.PositionType.BOTTOM)
        tooltip_grid.attach_next_to(label, tooltip.resource_label,
                                    Gtk.PositionType.BOTTOM, 1, 1)
        tooltip_grid.attach_next_to(self.table, label,
                                    Gtk.PositionType.RIGHT, 1, 1)

    @log_calls('ClientsIconsPlugin')
    def connect_with_gc_tooltip_populate(self, tooltip, contact, tooltip_grid):
        if not self.config['show_in_tooltip']:
            return
        # Check if clients info already attached to tooltip
        has_attached = False
        for child in tooltip_grid.get_children():
            if child.get_name() == 'client_icons_grid':
                caps = contact.client_caps._node
                caps_image, client_name = self.get_icon(caps, contact)
                child.remove(child.get_child_at(1, 1))
                child.attach(caps_image, 1, 1, 1, 1)
                child.get_child_at(2, 1).set_markup(client_name)
                child.show_all()
            if child.get_name() == 'client_icons_label':
                child.show()
                has_attached = True
        if not has_attached:
            self.add_tooltip_row(tooltip, contact, tooltip_grid)

    @log_calls('ClientsIconsPlugin')
    def connect_with_roster_tooltip_populate(self, tooltip, contacts, tooltip_grid):
        if not self.config['show_in_tooltip']:
            return
        if len(contacts) == 1 and contacts[0].jid in app.get_our_jids():
            return
        if self.is_groupchat(contacts[0]):
            return

        # put contacts in dict, where key is priority
        num_resources = 0
        contacts_dict = {}
        for contact in contacts:
            if contact.resource:
                num_resources += 1
                if int(contact.priority) in contacts_dict:
                    contacts_dict[int(contact.priority)].append(contact)
                else:
                    contacts_dict[int(contact.priority)] = [contact]
        contact_keys = sorted(contacts_dict.keys())
        contact_keys.reverse()

        # fill clients table
        self.table = Gtk.Grid()
        self.table.insert_row(0)
        self.table.insert_row(0)
        self.table.insert_column(0)
        self.table.set_property('column-spacing', 2)

        vcard_current_row = 0
        for priority in contact_keys:
            for acontact in contacts_dict[priority]:
                caps = acontact.client_caps._node
                caps_image, client_name = self.get_icon(caps, acontact)
                client_name = self.get_client_name(acontact, client_name)
                caps_image.set_alignment(0, 0)
                self.table.attach(caps_image, 1, vcard_current_row, 1, 1)
                label = Gtk.Label()
                label.set_alignment(0, 0)
                label.set_markup(client_name)
                self.table.attach(label, 2, vcard_current_row, 1, 1)
                vcard_current_row += 1
        self.table.show_all()

        # set label
        label = Gtk.Label()
        label.set_alignment(0, 0)
        if num_resources > 1:
            label.set_markup(_('Clients:'))
        else:
            if contact.show == 'offline':
                return
            label.set_markup(_('Client:'))
        label.show()
        # set clients table to tooltip
        tooltip_grid.insert_next_to(tooltip.resource_label,
                                    Gtk.PositionType.BOTTOM)
        tooltip_grid.attach_next_to(label, tooltip.resource_label,
                                    Gtk.PositionType.BOTTOM, 1, 1)
        tooltip_grid.attach_next_to(self.table, label,
                                    Gtk.PositionType.RIGHT, 1, 1)

    def get_icon(self, caps, contact):
        client_name = _('Unknown')
        caps_ = None
        if caps:
            # libpurple returns pidgin.im/ only, we have to look for ressource name
            if 'pidgin.im/' in caps:
                caps = 'libpurple'
                for client in LIBPURPLE_CLIENTS:
                    if client in contact.resource.lower():
                        caps = LIBPURPLE_CLIENTS[client]

            if 'sleekxmpp.com'in caps:
                caps = 'httр://sleekxmpp.com/ver/1.1.11'
            caps_from_jid = self.check_jid(contact.jid)
            if caps_from_jid:
                caps = caps_from_jid
            caps_ = caps.split('#')[0].split()

        client_name = self.get_client_name(contact, client_name)
        client_icon = self.get_client_icon_by_name(client_name)

        if caps_ and not client_icon:
            client_icon = CLIENTS.get(caps_[0].split()[0], (None,))[0]
            client_name = CLIENTS.get(caps_[0].split()[0], ('', _('Unknown')))[1]

        if not client_icon:
            return Gtk.Image.new_from_pixbuf(self.default_pixbuf), _('Unknown')
        else:
            icon_path = os.path.join(self.local_file_path('icons'), client_icon)
            if icon_path in self.icon_cache:
                return Gtk.Image.new_from_pixbuf(self.icon_cache[icon_path]), \
                    client_name
            else:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 16, 16)
                self.icon_cache[icon_path] = pb
                return Gtk.Image.new_from_pixbuf(pb), client_name

    def check_jid(self, jid):
        caps = None
        if 'facebook.com' in jid and self.config['show_facebook']:
            caps = 'facebook.com'
        elif '@vk.com' in jid and self.config['show_facebook']:
            caps = 'vk.com'
        elif jid == 'juick@juick.com':
            caps = 'http://juick.com/caps'
        elif jid == 'psto@psto.net':
            caps = 'psto@psto.net'
        elif jid == 'rss@isida-bot.com':
            caps = 'rss@isida-bot.com'
        return caps

    @log_calls('ClientsIconsPlugin')
    def connect_with_roster_draw_contact(self, roster, jid, account, contact):
        if not self.active:
            return
        if not self.config['show_in_roster']:
            return
        if self.is_groupchat(contact):
            return
        child_iters = roster._get_contact_iter(jid, account, contact, roster.model)
        if not child_iters:
            return
        for iter_ in child_iters:
            if roster.model[iter_][self.renderer_num] is None:
                caps = contact.client_caps._node
                if not caps:
                    caps = self.check_jid(jid)
                self.set_icon(roster.model, iter_, self.renderer_num, caps, contact)

    @log_calls('ClientsIconsPlugin')
    def connect_with_groupchat_control(self, chat_control):
        chat_control.nb_ext_renderers += 1
        chat_control.columns += [GdkPixbuf.Pixbuf]
        self.groupchats_tree_is_transformed = True
        self.chat_control = chat_control
        col = Gtk.TreeViewColumn()
        self.muc_renderer_num = 4 + chat_control.nb_ext_renderers
        client_icon_rend = (
            'client_icon', Gtk.CellRendererPixbuf(), False,
            'pixbuf', self.muc_renderer_num,
            self.tree_cell_data_func, chat_control)
        # remove old column
        chat_control.list_treeview.remove_column(
            chat_control.list_treeview.get_column(0))
        # add new renderer in renderers list
        position_list = ['name', 'avatar']
        position = position_list[self.config['pos_in_list']]
        for renderer in chat_control.renderers_list:
            if renderer[0] == position:
                break
        num = chat_control.renderers_list.index(renderer)
        chat_control.renderers_list.insert(num, client_icon_rend)
        # fill and append column
        chat_control.fill_column(col)
        chat_control.list_treeview.insert_column(col, 0)

        chat_control.model = Gtk.TreeStore(*chat_control.columns)
        chat_control.model.set_sort_func(1, chat_control.tree_compare_iters)
        chat_control.model.set_sort_column_id(1, Gtk.SortType.ASCENDING)
        chat_control.list_treeview.set_model(chat_control.model)

        # draw roster
        for nick in app.contacts.get_nick_list(
                chat_control.account, chat_control.room_jid):
            gc_contact = app.contacts.get_gc_contact(
                chat_control.account, chat_control.room_jid, nick)
            iter_ = chat_control.add_contact_to_roster(
                nick, gc_contact.show, gc_contact.role,
                gc_contact.affiliation, gc_contact.status, gc_contact.jid)
            if not self.config['show_in_groupchats']:
                log.debug("not showing in groupchats...")
                continue
            caps = gc_contact.client_caps._node
            log.debug("caps: %s" % str(caps))
            self.set_icon(
                chat_control.model, iter_,
                self.muc_renderer_num, caps, gc_contact)
        chat_control.draw_all_roles()
        # Recalculate column width for ellipsizin
        chat_control.list_treeview.columns_autosize()

    @log_calls('ClientsIconsPlugin')
    def disconnect_from_groupchat_control(self, gc_control):
        gc_control.nb_ext_renderers -= 1
        col = gc_control.list_treeview.get_column(0)
        gc_control.list_treeview.remove_column(col)
        col = Gtk.TreeViewColumn()
        for renderer in gc_control.renderers_list:
            if renderer[0] == 'client_icon':
                gc_control.renderers_list.remove(renderer)
                break
        gc_control.fill_column(col)
        gc_control.list_treeview.insert_column(col, 0)
        gc_control.columns = gc_control.columns[:self.muc_renderer_num] + \
            gc_control.columns[self.muc_renderer_num + 1:]
        gc_control.model = Gtk.TreeStore(*gc_control.columns)
        gc_control.model.set_sort_func(1, gc_control.tree_compare_iters)
        gc_control.model.set_sort_column_id(1, Gtk.SortType.ASCENDING)
        gc_control.list_treeview.set_model(gc_control.model)
        gc_control.draw_roster()

    @log_calls('ClientsIconsPlugin')
    def activate(self):
        self.active = None
        roster = app.interface.roster
        col = Gtk.TreeViewColumn()
        roster.nb_ext_renderers += 1
        self.renderer_num = 11 + roster.nb_ext_renderers
        self.renderer = Gtk.CellRendererPixbuf()
        client_icon_rend = (
            'client_icon', self.renderer, False,
            'pixbuf', self.renderer_num,
            roster._fill_pep_pixbuf_renderer, self.renderer_num)
        # remove old column
        roster.tree.remove_column(roster.tree.get_column(0))
        # add new renderer in renderers list
        position_list = ['name', 'avatar']
        position = position_list[self.config['pos_in_list']]
        for renderer in roster.renderers_list:
            if renderer[0] == position:
                break
        num = roster.renderers_list.index(renderer)
        roster.renderers_list.insert(num, client_icon_rend)
        # fill and append column
        roster.fill_column(col)
        roster.tree.insert_column(col, 0)
        # redraw roster
        roster.columns += [GdkPixbuf.Pixbuf]
        self.active = True
        roster.setup_and_draw_roster()

    @log_calls('ClientsIconsPlugin')
    def deactivate(self):
        self.active = None
        roster = app.interface.roster
        roster.nb_ext_renderers -= 1
        col = roster.tree.get_column(0)
        roster.tree.remove_column(col)
        col = Gtk.TreeViewColumn()
        for renderer in roster.renderers_list:
            if renderer[0] == 'client_icon':
                roster.renderers_list.remove(renderer)
                break
        roster.fill_column(col)
        roster.tree.insert_column(col, 0)
        roster.columns = roster.columns[:self.renderer_num] + roster.columns[
            self.renderer_num + 1:]
        roster.setup_and_draw_roster()

    def caps_disco_received(self, iq_obj):
        log.debug("caps disco received...")
        if not self.config['show_in_roster']:
            return
        roster = app.interface.roster
        contact = app.contacts.get_contact_from_full_jid(
            iq_obj.conn.name, iq_obj.jid)
        if self.is_groupchat(contact):
            return
        if contact is None:
            room_jid, nick = app.get_room_and_nick_from_fjid(iq_obj.fjid)
            contact = app.contacts.get_gc_contact(iq_obj.conn.name, room_jid, nick)
            if contact:
                gc_control = app.interface.msg_win_mgr.get_gc_control(
                    iq_obj.jid, iq_obj.conn.name)
                iter_ = gc_control.get_contact_iter(nick)
                self.set_icon(gc_control.model, iter_,
                              self.muc_renderer_num, None, contact)
                return
        if not contact:
            return
        child_iters = roster._get_contact_iter(
            iq_obj.jid, iq_obj.conn.name, contact, roster.model)
        if not child_iters:
            return
        for iter_ in child_iters:
            caps = contact.client_caps._node
            caps_ = self.check_jid(iq_obj.jid)
            if caps_:
                caps = caps_
            self.set_icon(roster.model, iter_, self.renderer_num, caps, contact)

    def caps_presence_received(self, iq_obj):
        log.debug("caps presence received...")
        if not self.config['show_in_roster']:
            return
        roster = app.interface.roster
        contact = app.contacts.get_contact_with_highest_priority(
            iq_obj.conn.name, iq_obj.jid)
        if not contact or self.is_groupchat(contact):
            return

        if iq_obj.resource == 'local':
            # zeroconf
            return

        iters = roster._get_contact_iter(iq_obj.jid, iq_obj.conn.name, contact,
                                         roster.model)
        iter_ = iters[0]

        if contact.show == 'error':
            self.set_icon(roster.model, iter_, self.renderer_num, None, contact)
            return

        # higest contact changed
        if roster.model[iter_][self.renderer_num] is not None:
            caps = contact.client_caps._node
            if caps:
                log.debug('caps_presence_received, caps: %s', caps)
                self.set_icon(roster.model, iter_, self.renderer_num, caps, contact)
                return

        caps = None
        tag = iq_obj.stanza.getTags('c')
        if tag:
            caps = tag[0].getAttr('node')
            if caps:
                if 'pidgin.im/' in caps:
                    caps = 'libpurple'
                    for client in LIBPURPLE_CLIENTS:
                        if client in contact.resource.lower():
                            caps = LIBPURPLE_CLIENTS[client]
                if 'sleekxmpp.com'in caps:
                    caps = 'httр://sleekxmpp.com/ver/1.1.11'

        caps_from_jid = self.check_jid(iq_obj.jid)
        if caps_from_jid:
            caps = caps_from_jid

        for iter_ in iters:
            self.set_icon(roster.model, iter_, self.renderer_num, caps, contact)

    def gc_presence_received(self, iq_obj):
        log.debug("gc presence received...")
        if not self.config['show_in_groupchats']:
            return
        contact = app.contacts.get_gc_contact(
            iq_obj.conn.name, iq_obj.presence_obj.jid, iq_obj.nick)
        if not contact:
            return
        caps = None
        tag = iq_obj.stanza.getTags('c')
        if tag:
            caps = tag[0].getAttr('node')
            if caps:
                log.debug('gc_presence_received, caps: %s', caps)
                if 'pidgin.im/' in caps:
                    caps = 'libpurple'
                if 'sleekxmpp.com' in caps:
                    caps = 'httр://sleekxmpp.com/ver/1.1.11'
        iter_ = iq_obj.gc_control.get_contact_iter(iq_obj.nick)
        model = iq_obj.gc_control.model
        if model[iter_][self.muc_renderer_num] is not None:
            return
        self.set_icon(model, iter_, self.muc_renderer_num, caps, contact)

    def set_icon(self, model, iter_, pos, caps, contact):
        client_icon = self.get_client_icon_by_name(
            self.get_client_name(contact, _('Unknown')))

        if caps and not client_icon:
            caps_ = caps.split('#')[0].split()
            if caps_:
                log.debug('set_icon, caps_: %s', caps_)
                client_icon = CLIENTS.get(caps_[0].split()[0], (None,))[0]

        if not client_icon:
            if self.config['show_unknown_icon']:
                model[iter_][pos] = self.default_pixbuf
        else:
            icon_path = os.path.join(self.local_file_path('icons'), client_icon)
            if icon_path in self.icon_cache:
                model[iter_][pos] = self.icon_cache[icon_path]
            else:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 16, 16)
                model[iter_][pos] = pixbuf
                self.icon_cache[icon_path] = pixbuf

    def tree_cell_data_func(self, column, renderer, model, iter_, control):
        if not model.iter_parent(iter_):
            renderer.set_property('visible', False)
            return
        elif model[iter_][self.muc_renderer_num]:
            renderer.set_property('visible', True)

        contact = app.contacts.get_gc_contact(
            control.account, control.room_jid, model[iter_][1])
        if not contact:
            return

        bgcolor = app.config.get_per('themes', app.config.get(
            'roster_theme'), 'contactbgcolor')
        if bgcolor:
            renderer.set_property('cell-background', bgcolor)
        else:
            renderer.set_property('cell-background', None)
        renderer.set_property('width', 16)


class ClientsIconsPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.Gtk_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.Gtk_BUILDER_FILE_PATH, ['vbox1'])
        vbox = self.xml.get_object('vbox1')
        self.get_child().pack_start(vbox, True, True, 0)
        self.combo = self.xml.get_object('combobox1')
        self.liststore = Gtk.ListStore(str)
        self.combo.set_model(self.liststore)
        cellrenderer = Gtk.CellRendererText()
        self.combo.pack_start(cellrenderer, True)
        self.combo.add_attribute(cellrenderer, 'text', 0)

        for item in self.plugin.pos_list:
            self.liststore.append((item,))
        self.combo.set_active(self.plugin.config['pos_in_list'])

        self.xml.get_object('show_in_roster').set_active(
            self.plugin.config['show_in_roster'])
        self.xml.get_object('show_in_groupchats').set_active(
            self.plugin.config['show_in_groupchats'])
        self.xml.get_object('show_unknown_icon').set_active(
            self.plugin.config['show_unknown_icon'])
        self.xml.get_object('show_facebook').set_active(
            self.plugin.config['show_facebook'])
        self.xml.get_object('show_in_tooltip').set_active(
            self.plugin.config['show_in_tooltip'])

        self.xml.connect_signals(self)

    def redraw_all(self):
        self.plugin.deactivate()
        self.plugin.activate()
        for gc_control in app.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.disconnect_from_groupchat_control(gc_control)
        for gc_control in app.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.connect_with_groupchat_control(gc_control)

    def on_show_in_roster_toggled(self, widget):
        self.plugin.config['show_in_roster'] = widget.get_active()
        self.plugin.deactivate()
        self.plugin.activate()

    def on_show_in_tooltip_toggled(self, widget):
        self.plugin.config['show_in_tooltip'] = widget.get_active()

    def on_show_in_groupchats_toggled(self, widget):
        self.plugin.config['show_in_groupchats'] = widget.get_active()
        for gc_control in app.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.disconnect_from_groupchat_control(gc_control)
        for gc_control in app.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.connect_with_groupchat_control(gc_control)

    def on_show_unknown_icon_toggled(self, widget):
        self.plugin.config['show_unknown_icon'] = widget.get_active()
        self.redraw_all()

    def on_show_facebook_toggled(self, widget):
        self.plugin.config['show_facebook'] = widget.get_active()
        self.redraw_all()

    def on_combobox1_changed(self, widget):
        self.plugin.config['pos_in_list'] = widget.get_active()
        self.redraw_all()
