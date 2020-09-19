# This file is part of Gajim.
#
# Gajim is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

import logging
from pathlib import Path
from functools import partial

from gi.repository import Gtk

from gajim.common import app
from gajim.gtk.util import load_icon

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from clients_icons import clients
from clients_icons.config_dialog import ClientsIconsConfigDialog

log = logging.getLogger('gajim.p.client_icons')


class ClientsIconsPlugin(GajimPlugin):
    def init(self):
        self.description = _('Shows client icons in roster'
                             ' and in groupchats.')
        self.config_dialog = partial(ClientsIconsConfigDialog, self)

        self.gui_extension_points = {
            'roster_tooltip_populate': (
                self.connect_with_roster_tooltip_populate,
                None),
            'gc_tooltip_populate': (
                self.connect_with_gc_tooltip_populate,
                None),
            }

        self.config_default_values = {
            'show_in_tooltip': (True, ''),
            'show_unknown_icon': (True, ''),
        }

        _icon_theme = Gtk.IconTheme.get_default()
        if _icon_theme is not None:
            _icon_theme.append_search_path(str(Path(__file__).parent))

    @staticmethod
    def _get_client_identity_name(disco_info):
        for identity in disco_info.identities:
            if identity.category == 'client':
                return identity.name

    def _get_image_and_client_name(self, contact, widget):
        disco_info = app.storage.cache.get_last_disco_info(
            contact.get_full_jid())
        if disco_info is None:
            return None

        if disco_info.node is None:
            return None

        node = disco_info.node.split('#')[0]
        client_name = self._get_client_identity_name(disco_info)

        log.info('Lookup client: %s %s', client_name, node)
        client_name, icon_name = clients.get_data(client_name, node)
        surface = load_icon(icon_name, widget=widget)
        return Gtk.Image.new_from_surface(surface), client_name

    @staticmethod
    def _is_groupchat(contact):
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

        result = self._get_image_and_client_name(contact, tooltip_grid)
        if result is None:
            return

        image, client_name = result

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

        if self._is_groupchat(contacts[0]):
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

                result = self._get_image_and_client_name(acontact, tooltip_grid)
                if result is None:
                    continue
                image, client_name = result

                image.set_valign(Gtk.Align.START)
                grid.attach(image, 1, vcard_current_row, 1, 1)
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
