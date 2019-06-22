import logging
from pathlib import Path
from functools import partial

from gi.repository import Gtk

from gajim.roster_window import Column
from gajim.common import ged
from gajim.common import app
from gajim.common import caps_cache
from gajim.gtk.util import load_icon

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from clients_icons import clients
from clients_icons.config_dialog import ClientsIconsConfigDialog

from nbxmpp import JID

log = logging.getLogger('gajim.p.client_icons')


class ClientsIconsPlugin(GajimPlugin):
    def init(self):
        self.description = _('Shows client icons in roster'
                             ' and in groupchats.')
        self.config_dialog = partial(ClientsIconsConfigDialog, self)

        self.events_handlers = {
            'caps-update': (
                ged.POSTGUI, self._on_caps_update),
        }

        self.gui_extension_points = {
            'groupchat_control': (
                self.connect_with_groupchat_control,
                self.disconnect_from_groupchat_control),
            'roster_draw_contact': (
                self.connect_with_roster_draw_contact,
                None),
            'roster_tooltip_populate': (
                self.connect_with_roster_tooltip_populate,
                None),
            'gc_tooltip_populate': (
                self.connect_with_gc_tooltip_populate,
                None),
            }

        self.config_default_values = {
            'show_in_roster': (True, ''),
            'show_in_groupchats': (True, ''),
            'show_in_tooltip': (True, ''),
            'show_unknown_icon': (True, ''),
            'pos_in_list': ('0', ''),
            'show_facebook': (True, ''),
        }

        _icon_theme = Gtk.IconTheme.get_default()
        if _icon_theme is not None:
            _icon_theme.append_search_path(str(Path(__file__).parent))

    @staticmethod
    def get_client_identity_name(contact):
        identities = contact.client_caps.get_cache_lookup_strategy()(
            caps_cache.capscache).identities
        if identities:
            for entry in identities:
                if entry['category'] == 'client':
                    return entry.get('name')

    @staticmethod
    def is_groupchat(contact):
        if hasattr(contact, 'is_groupchat'):
            return contact.is_groupchat
        return False

    def add_tooltip_row(self, tooltip, contact, tooltip_grid):
        caps = contact.client_caps._node
        caps_image, client_name = self.get_icon(caps, contact, tooltip_grid)
        caps_image.set_halign(Gtk.Align.END)

        # Fill clients grid
        self.grid = Gtk.Grid()
        self.grid.set_name('client_icons_grid')
        self.grid.set_property('column-spacing', 5)
        self.grid.attach(caps_image, 1, 1, 1, 1)
        label_name = Gtk.Label()
        label_name.set_halign(Gtk.Align.END)
        label_name.set_valign(Gtk.Align.CENTER)
        label_name.set_markup(client_name)
        self.grid.attach(label_name, 2, 1, 1, 1)
        self.grid.show_all()

        # Set label
        label = Gtk.Label()
        label.set_name('client_icons_label')
        label.set_halign(Gtk.Align.END)
        label.set_valign(Gtk.Align.CENTER)
        label.set_markup(_('Client:'))
        label.show()

        # Set client grid to tooltip
        tooltip_grid.insert_next_to(tooltip.resource_label,
                                    Gtk.PositionType.BOTTOM)
        tooltip_grid.attach_next_to(label, tooltip.resource_label,
                                    Gtk.PositionType.BOTTOM, 1, 1)
        tooltip_grid.attach_next_to(self.grid, label,
                                    Gtk.PositionType.RIGHT, 1, 1)

    def connect_with_gc_tooltip_populate(self, tooltip, contact, tooltip_grid):
        if not self.config['show_in_tooltip']:
            return

        # Check if clients info already attached to tooltip
        node = contact.client_caps._node
        image, client_name = self.get_icon(node, contact, tooltip_grid)
        label = Gtk.Label(label=client_name)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.add(image)
        box.add(label)
        box.show_all()

        tooltip_grid.insert_next_to(tooltip._ui.affiliation,
                                    Gtk.PositionType.BOTTOM)
        tooltip_grid.attach_next_to(box, tooltip._ui.affiliation,
                                    Gtk.PositionType.BOTTOM, 1, 1)

    def connect_with_roster_tooltip_populate(self, tooltip, contacts,
                                             tooltip_grid):
        if not self.config['show_in_tooltip']:
            return
        if len(contacts) == 1 and contacts[0].jid in app.get_our_jids():
            return
        if self.is_groupchat(contacts[0]):
            return

        # Put contacts in dict, where key is priority
        num_resources = 0
        contacts_dict = {}
        for contact in contacts:
            if contact.show == 'offline':
                return
            if contact.resource:
                num_resources += 1
                if int(contact.priority) in contacts_dict:
                    contacts_dict[int(contact.priority)].append(contact)
                else:
                    contacts_dict[int(contact.priority)] = [contact]
        contact_keys = sorted(contacts_dict.keys())
        contact_keys.reverse()

        # Fill clients grid
        grid = Gtk.Grid()
        grid.insert_row(0)
        grid.insert_row(0)
        grid.insert_column(0)
        grid.set_property('column-spacing', 2)

        vcard_current_row = 0
        for priority in contact_keys:
            for acontact in contacts_dict[priority]:
                caps = acontact.client_caps._node
                caps_image, client_name = self.get_icon(
                    caps, acontact, tooltip_grid)
                caps_image.set_valign(Gtk.Align.START)
                grid.attach(caps_image, 1, vcard_current_row, 1, 1)
                label = Gtk.Label(label=client_name)
                label.set_valign(Gtk.Align.START)
                label.set_halign(Gtk.Align.START)
                label.set_xalign(0)
                grid.attach(label, 2, vcard_current_row, 1, 1)
                vcard_current_row += 1
        grid.show_all()
        grid.set_valign(Gtk.Align.START)

        # Set label
        label = Gtk.Label()
        label.set_halign(Gtk.Align.END)
        label.set_valign(Gtk.Align.START)
        if num_resources > 1:
            label.set_text(_('Clients:'))
        else:
            label.set_text(_('Client:'))
        label.show()

        # Set clients grid to tooltip
        tooltip_grid.insert_next_to(tooltip._ui.resource_label,
                                    Gtk.PositionType.BOTTOM)
        tooltip_grid.attach_next_to(label, tooltip._ui.resource_label,
                                    Gtk.PositionType.BOTTOM, 1, 1)
        tooltip_grid.attach_next_to(grid, label,
                                    Gtk.PositionType.RIGHT, 1, 1)

    def get_icon(self, node, contact, widget):
        identity_name = self.get_client_identity_name(contact)
        client_name, icon_name = clients.get_data(identity_name, node)
        surface = load_icon(icon_name, widget=widget)
        return Gtk.Image.new_from_surface(surface), client_name

    def connect_with_roster_draw_contact(self, roster, jid, account, contact):
        if not self.active:
            return
        if not self.config['show_in_roster']:
            return
        if self.is_groupchat(contact):
            return
        child_iters = roster._get_contact_iter(
            jid, account, contact, roster.model)
        if not child_iters:
            return
        for iter_ in child_iters:
            if roster.model[iter_][self.renderer_num] is None:
                node = contact.client_caps._node
                self.set_icon(
                    roster.model, iter_, self.renderer_num, node, contact)

    def connect_with_groupchat_control(self, chat_control):
        chat_control.nb_ext_renderers += 1
        chat_control.columns += [str]
        self.groupchats_tree_is_transformed = True
        self.chat_control = chat_control
        col = Gtk.TreeViewColumn()
        self.muc_renderer_num = 4 + chat_control.nb_ext_renderers
        client_icon_rend = (
            'client_icon', Gtk.CellRendererPixbuf(), False,
            'icon_name', self.muc_renderer_num,
            self.tree_cell_data_func, chat_control)

        # Remove old column
        chat_control.list_treeview.remove_column(
            chat_control.list_treeview.get_column(0))

        # Add new renderer in renderers list
        position_list = ['name', 'avatar']
        position = position_list[int(self.config['pos_in_list'])]
        for renderer in chat_control.renderers_list:
            if renderer[0] == position:
                break
        num = chat_control.renderers_list.index(renderer)
        chat_control.renderers_list.insert(num, client_icon_rend)

        # Fill and append column
        chat_control.fill_column(col)
        chat_control.list_treeview.insert_column(col, 0)

        chat_control.model = Gtk.TreeStore(*chat_control.columns)
        chat_control.model.set_sort_func(1, chat_control.tree_compare_iters)
        chat_control.model.set_sort_column_id(1, Gtk.SortType.ASCENDING)
        chat_control.list_treeview.set_model(chat_control.model)

        # Draw roster
        for nick in app.contacts.get_nick_list(
                chat_control.account, chat_control.room_jid):
            gc_contact = app.contacts.get_gc_contact(
                chat_control.account, chat_control.room_jid, nick)
            iter_ = chat_control.add_contact_to_roster(nick)
            if not self.config['show_in_groupchats']:
                continue
            caps = gc_contact.client_caps._node
            self.set_icon(
                chat_control.model, iter_,
                self.muc_renderer_num, caps, gc_contact)
        chat_control.draw_all_roles()

        # Recalculate column width for ellipsizing
        chat_control.list_treeview.columns_autosize()

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

    def activate(self):
        self.active = None
        roster = app.interface.roster
        col = Gtk.TreeViewColumn()
        roster.nb_ext_renderers += 1
        self.renderer_num = 11 + roster.nb_ext_renderers
        self.renderer = Gtk.CellRendererPixbuf()
        client_icon_rend = (
            'client_icon', self.renderer, False,
            'icon_name', self.renderer_num,
            self._roster_icon_renderer, self.renderer_num)

        # Remove old column
        roster.tree.remove_column(roster.tree.get_column(0))

        # Add new renderer in renderers list
        position_list = ['name', 'avatar']
        position = position_list[int(self.config['pos_in_list'])]
        for renderer in roster.renderers_list:
            if renderer[0] == position:
                break
        num = roster.renderers_list.index(renderer)
        roster.renderers_list.insert(num, client_icon_rend)

        # Fill and append column
        roster.fill_column(col)
        roster.tree.insert_column(col, 0)

        # Redraw roster
        roster.columns += [str]
        self.active = True
        roster.setup_and_draw_roster()

    def _roster_icon_renderer(self, column, renderer, model, titer, data=None):
        try:
            type_ = model[titer][Column.TYPE]
        except TypeError:
            return

        # Allocate space for the icon only if needed
        if model[titer][data] is None:
            renderer.set_property('visible', False)
        else:
            renderer.set_property('visible', True)

            if type_ == 'account':
                app.interface.roster._set_account_row_background_color(renderer)
                renderer.set_property('xalign', 1)
            elif type_:
                if (not model[titer][Column.JID] or
                        not model[titer][Column.ACCOUNT]):
                    # This can append at the moment we add the row
                    return
                jid = model[titer][Column.JID]
                account = model[titer][Column.ACCOUNT]
                app.interface.roster._set_contact_row_background_color(
                    renderer, jid, account)

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

    def _on_caps_update(self, event):
        # Zeroconf
        if event.conn.name == 'Local':
            return

        contact = self._get_contact_or_gc_contact_for_jid(
            event.conn.name, event.fjid)
        if contact is None:
            return

        if contact.is_gc_contact:
            self._draw_gc_contact(event, contact)
        else:
            self._draw_roster_contact(event, contact)

    def _draw_roster_contact(self, event, contact):
        if not self.config['show_in_roster']:
            return

        if contact.is_groupchat:
            return
        roster = app.interface.roster
        iters = roster._get_contact_iter(
            event.jid, event.conn.name, contact, roster.model)
        iter_ = iters[0]

        # Highest contact changed
        caps = contact.client_caps._node
        if not caps:
            return

        if roster.model[iter_][self.renderer_num] is not None:
            self.set_icon(
                roster.model, iter_, self.renderer_num, caps, contact)
            return

        for iter_ in iters:
            self.set_icon(
                roster.model, iter_, self.renderer_num, caps, contact)

    def _draw_gc_contact(self, event, contact):
        if not self.config['show_in_groupchats']:
            return

        control = app.interface.msg_win_mgr.get_gc_control(
            contact.room_jid, event.conn.name)
        if control is None:
            return
        iter_ = control.get_contact_iter(contact.name)
        if control.model[iter_][self.muc_renderer_num] is not None:
            return
        caps = contact.client_caps._node
        if not caps:
            return
        self.set_icon(
            control.model, iter_, self.muc_renderer_num, caps, contact)

    def _get_contact_or_gc_contact_for_jid(self, account, fjid):
        contact = app.contacts.get_contact_from_full_jid(account, fjid)

        if contact is None:
            fjid = JID(fjid)
            room_jid, resource = fjid.getStripped(), fjid.getResource()
            contact = app.contacts.get_gc_contact(account, room_jid, resource)
        return contact

    def set_icon(self, model, iter_, pos, node, contact):
        identity_name = self.get_client_identity_name(contact)
        _client_name, icon_name = clients.get_data(identity_name, node)
        if 'unknown' in icon_name:
            if node is not None:
                log.warning('Unknown client: %s %s', identity_name, node)
            if not self.config['show_unknown_icon']:
                model[iter_][pos] = None
                return

        model[iter_][pos] = icon_name

    def tree_cell_data_func(self, column, renderer, model, iter_, control):
        if not model.iter_parent(iter_):
            renderer.set_property('visible', False)
            return

        if model[iter_][self.muc_renderer_num]:
            renderer.set_property('visible', True)

        contact = app.contacts.get_gc_contact(
            control.account, control.room_jid, model[iter_][1])
        if not contact:
            return

        bgcolor = app.config.get_per(
            'themes', app.config.get('roster_theme'), 'contactbgcolor')
        if bgcolor:
            renderer.set_property('cell-background', bgcolor)
        else:
            renderer.set_property('cell-background', None)
        renderer.set_property('width', 16)
