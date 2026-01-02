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

from typing import Any
from typing import cast
from typing import TYPE_CHECKING

from collections.abc import Callable
from pathlib import Path

from gi.repository import GLib
from gi.repository import Gtk
from nbxmpp import JID

from gajim.common import app
from gajim.gtk.widgets import GajimAppWindow
from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _

from ..modules.pgp_legacy import PGPLegacy

if TYPE_CHECKING:
    from ..plugin import PGPPlugin


class ChooseKeyBuilder(Gtk.Builder):
    liststore: Gtk.ListStore
    box: Gtk.Box
    keys_treeview: Gtk.TreeView
    cancel_button: Gtk.Button
    ok_button: Gtk.Button


class KeyDialog(GajimAppWindow):
    def __init__(
        self, plugin: PGPPlugin, account: str, jid: JID, transient: Gtk.Window
    ) -> None:
        GajimAppWindow.__init__(
            self,
            name="PGPKeyDialog",
            title=_("Assign key for %s") % jid,
            default_width=450,
            transient_for=transient,
            modal=True,
        )

        self.window.set_resizable(True)

        self._plugin = plugin
        self._jid = str(jid)
        self._module = cast(
            PGPLegacy,
            app.get_client(account).get_module("PGPLegacy"),  # pyright: ignore
        )

        self._label = Gtk.Label()

        self._assign_button = Gtk.Button(label=_("Assign Key"))
        self._assign_button.get_style_context().add_class("suggested-action")
        self._assign_button.set_halign(Gtk.Align.CENTER)
        self._assign_button.set_margin_top(18)
        self._connect(self._assign_button, "clicked", self._choose_key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self._label)
        box.append(self._assign_button)

        self.set_child(box)

        self._load_key()
        self.show()

    def _cleanup(self) -> None:
        del self._plugin
        del self._module

    def _choose_key(self, _button: Gtk.Button) -> None:
        ChooseGPGKeyDialog(
            self._module.pgp_backend.get_keys(), self.window, self._on_response
        )

    def _load_key(self) -> None:
        key_data = self._module.get_contact_key_data(self._jid)
        if key_data is None:
            self._set_key(None)
        else:
            key_id, key_user = key_data.values()
            self._set_key((key_id, key_user))

    def _on_response(self, key: tuple[str, str] | None) -> None:
        if key is None:
            self._module.set_contact_key_data(self._jid, None)
            self._set_key(None)
        else:
            self._module.set_contact_key_data(self._jid, key)
            self._set_key(key)

    def _set_key(self, key_data: tuple[str, str] | None) -> None:
        if key_data is None:
            self._label.set_text(_("No key assigned"))
        else:
            key_id, key_user = key_data
            self._label.set_markup(
                "<b><tt>%s</tt> %s</b>" % (key_id, GLib.markup_escape_text(key_user))
            )


class ChooseGPGKeyDialog(GajimAppWindow):
    def __init__(
        self,
        secret_keys: dict[str, str],
        transient: Gtk.Window,
        callback: Callable[[tuple[str, str] | None], None],
    ) -> None:
        GajimAppWindow.__init__(
            self,
            name="PGPChooseKeyDialog",
            title=_("Assign PGP Key"),
            default_width=450,
            default_height=400,
            transient_for=transient,
            modal=True,
        )

        secret_keys[_("None")] = _("None")

        self.window.set_resizable(True)

        self._callback = callback
        self._selected_key = None

        ui_path = Path(__file__).parent
        self._ui = cast(
            ChooseKeyBuilder, get_builder(str(ui_path.resolve() / "choose_key.ui"))
        )

        self._connect(self._ui.cancel_button, "clicked", self._on_cancel)
        self._connect(self._ui.ok_button, "clicked", self._on_ok)
        self._connect(self._ui.keys_treeview, "cursor-changed", self._on_row_changed)

        model = cast(Gtk.ListStore, self._ui.keys_treeview.get_model())
        model.set_sort_func(1, self._sort)

        for key_id, key_label in secret_keys.items():
            model.append((key_id, key_label))

        self.set_child(self._ui.box)
        self.show()

    def _cleanup(self) -> None:
        del self._callback

    @staticmethod
    def _sort(
        model: Gtk.TreeModel, iter1: Gtk.TreeIter, iter2: Gtk.TreeIter, _data: Any
    ) -> int:
        value1 = model[iter1][1]
        value2 = model[iter2][1]
        if value1 == _("None"):
            return -1
        if value2 == _("None"):
            return 1
        if value1 < value2:
            return -1
        return 1

    def _on_cancel(self, _button: Gtk.Button) -> None:
        self.close()

    def _on_ok(self, _button: Gtk.Button) -> None:
        self._callback(self._selected_key)
        self.close()

    def _on_row_changed(self, treeview: Gtk.TreeView) -> None:
        selection = treeview.get_selection()
        model, iter_ = selection.get_selected()
        if iter_ is None:
            self._selected_key = None
        else:
            key_id, key_user = model[iter_][0], model[iter_][1]
            if key_id == _("None"):
                self._selected_key = None
            else:
                self._selected_key = key_id, key_user
