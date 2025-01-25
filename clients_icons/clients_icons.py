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

from __future__ import annotations

from typing import cast

import logging
from functools import partial
from pathlib import Path

from gi.repository import Gtk
from nbxmpp.structs import DiscoInfo

from gajim.common import app
from gajim.common.modules.contacts import GroupchatParticipant
from gajim.common.modules.contacts import ResourceContact
from gajim.gtk.util import get_icon_theme
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from clients_icons import clients
from clients_icons.config_dialog import ClientsIconsConfigDialog

log = logging.getLogger("gajim.p.client_icons")


class ClientsIconsPlugin(GajimPlugin):
    def init(self) -> None:
        self.description = _("Show client icons in the contact tooltip.")
        self.config_dialog = partial(ClientsIconsConfigDialog, self)

        self.gui_extension_points = {
            "contact_tooltip_resource_populate": (
                self._contact_tooltip_resource_populate,
                None,
            ),
        }

        self.config_default_values = {
            "show_unknown_icon": (True, ""),
        }

        icon_theme = get_icon_theme()
        icon_theme.add_search_path(str(Path(__file__).parent))

    @staticmethod
    def _get_client_identity_name(disco_info: DiscoInfo) -> str | None:
        for identity in disco_info.identities:
            if identity.category == "client":
                return identity.name
        return None

    def _get_image_and_client_name(
        self, contact: GroupchatParticipant | ResourceContact, _widget: Gtk.Widget
    ) -> tuple[Gtk.Image, str] | None:

        disco_info = app.storage.cache.get_last_disco_info(contact.jid)
        if disco_info is None:
            return None

        if disco_info.node is None:
            return None

        node = disco_info.node.split("#")[0]
        client_name = self._get_client_identity_name(disco_info)

        log.info("Lookup client: %s %s", client_name, node)
        client_name, icon_name = clients.get_data(client_name, node)
        image = Gtk.Image.new_from_icon_name(icon_name)
        image.set_pixel_size(16)
        return image, client_name

    def _contact_tooltip_resource_populate(
        self, resource_box: Gtk.Box, resource: ResourceContact
    ) -> None:

        result = self._get_image_and_client_name(resource, resource_box)
        if result is None:
            return

        image, client_name = result
        label = Gtk.Label(label=client_name)

        client_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            halign=Gtk.Align.START,
            spacing=6,
        )
        client_box.append(image)
        client_box.append(label)

        box = cast(Gtk.Box, resource_box.get_first_child())
        box.append(client_box)
