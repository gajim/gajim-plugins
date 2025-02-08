# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the PGP Gajim Plugin.
#
# PGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# PGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from typing import cast
from typing import TYPE_CHECKING

from pathlib import Path

from gi.repository import GLib
from gi.repository import Gtk

from gajim.common import app
from gajim.gtk.util.classes import SignalManager
from gajim.gtk.widgets import GajimAppWindow
from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _

from ..modules.pgp_legacy import PGPLegacy
from .key import ChooseGPGKeyDialog

if TYPE_CHECKING:
    from ..plugin import PGPPlugin


class ConfigBuilder(Gtk.Builder):
    config_box: Gtk.Box
    sidebar: Gtk.StackSidebar
    stack: Gtk.Stack


class PGPConfigDialog(GajimAppWindow):
    def __init__(self, plugin: PGPPlugin, transient: Gtk.Window) -> None:

        GajimAppWindow.__init__(
            self,
            name="PGPConfigDialog",
            title=_("PGP Configuration"),
            default_width=600,
            default_height=500,
            transient_for=transient,
            modal=True,
        )

        ui_path = Path(__file__).parent
        self._ui = cast(
            ConfigBuilder, get_builder(str(ui_path.resolve() / "config.ui"))
        )

        self.set_child(self._ui.config_box)

        self._plugin = plugin

        for account in app.settings.get_active_accounts():
            module = cast(
                PGPLegacy,
                app.get_client(account).get_module("PGPLegacy"),  # pyright: ignore
            )
            page = Page(module)
            self._ui.stack.add_titled(page, account, app.get_account_label(account))

        self.show()

    def _cleanup(self) -> None:
        del self._plugin


class Page(Gtk.Box, SignalManager):
    def __init__(self, module: PGPLegacy) -> None:
        SignalManager.__init__(self)
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self._module = module

        self._label = Gtk.Label()
        self._button = Gtk.Button(label=_("Assign Key"))
        self._button.add_css_class("suggested-action")
        self._button.set_halign(Gtk.Align.CENTER)
        self._button.set_margin_top(18)
        self._connect(self._button, "clicked", self._on_assign)

        self._load_key()
        self.append(self._label)
        self.append(self._button)

    def _on_assign(self, _button: Gtk.Button) -> None:
        secret_keys = self._module.pgp_backend.get_keys(secret=True)
        ChooseGPGKeyDialog(
            secret_keys, cast(Gtk.Window, self.get_root()), self._on_response
        )

    def _load_key(self) -> None:
        key_data = self._module.get_own_key_data()
        if key_data is None:
            self._set_key(None)
        else:
            self._set_key((key_data["key_id"], key_data["key_user"]))

    def _on_response(self, key: tuple[str, str] | None) -> None:
        if key is None:
            self._module.set_own_key_data(None)
            self._set_key(None)
        else:
            self._module.set_own_key_data(key)
            self._set_key(key)

    def _set_key(self, key_data: tuple[str, str] | None) -> None:
        if key_data is None:
            self._label.set_text(_("No key assigned"))
        else:
            key_id, key_user = key_data
            self._label.set_markup(
                "<b><tt>%s</tt> %s</b>" % (key_id, GLib.markup_escape_text(key_user))
            )

    def do_unroot(self) -> None:
        Gtk.Box.do_unroot(self)
        self._disconnect_all()
        del self._module
        app.check_finalize(self)
