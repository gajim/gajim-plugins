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
from gajim.gui.util import load_icon_surface

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from clients_icons import clients
from clients_icons.config_dialog import ClientsIconsConfigDialog

log = logging.getLogger('gajim.p.client_icons')


class ClientsIconsPlugin(GajimPlugin):
    def init(self):
        self.description = _('Shows client icons in your contact list '
                             'and in the groupchat participants list.')
        self.config_dialog = partial(ClientsIconsConfigDialog, self)

        self.gui_extension_points = {
            'roster_tooltip_resource_populate': (
                self._roster_tooltip_resource_populate,
                None),
            'gc_tooltip_populate': (
                self._gc_roster_tooltip_populate,
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

    def _get_image_and_client_name(self, contact, _widget):
        disco_info = app.storage.cache.get_last_disco_info(contact.jid)
        if disco_info is None:
            return None

        if disco_info.node is None:
            return None

        node = disco_info.node.split('#')[0]
        client_name = self._get_client_identity_name(disco_info)

        log.info('Lookup client: %s %s', client_name, node)
        client_name, icon_name = clients.get_data(client_name, node)
        surface = load_icon_surface(icon_name)
        return Gtk.Image.new_from_surface(surface), client_name

    def _roster_tooltip_resource_populate(self, resource_box, resource):
        if not self.config['show_in_tooltip']:
            return

        result = self._get_image_and_client_name(resource, resource_box)
        if result is None:
            return

        image, client_name = result
        label = Gtk.Label(label=client_name)

        client_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                             halign=Gtk.Align.START)
        client_box.add(image)
        client_box.add(label)

        children = resource_box.get_children()
        children[0].add(client_box)

    def _gc_roster_tooltip_populate(self, tooltip, contact, tooltip_grid):
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
