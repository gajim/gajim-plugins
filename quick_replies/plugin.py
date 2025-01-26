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

import json
from functools import partial
from pathlib import Path

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from gajim.common import app
from gajim.common import configpaths
from gajim.gtk.message_actions_box import MessageActionsBox
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from quick_replies.gtk.config import ConfigDialog
from quick_replies.quick_replies import DEFAULT_DATA


class QuickRepliesPlugin(GajimPlugin):
    def init(self) -> None:
        self.description = _("Adds a menu with customizable quick replies")
        self.config_dialog = partial(ConfigDialog, self)
        self.gui_extension_points = {
            "message_actions_box": (self._message_actions_box_created, None),
        }

        self._quick_replies = self._load_quick_replies()

        self._actions: list[Gio.SimpleAction] = []
        self._button = self._create_menu_button()

        self._create_actions()

    def _create_menu_button(self) -> Gtk.MenuButton:
        plugin_path = Path(__file__).parent
        img_path = plugin_path.resolve() / "quick_replies.png"
        img = Gtk.Image.new_from_file(str(img_path))

        button = Gtk.MenuButton(
            tooltip_text=_("Quick Replies"),
            menu_model=self._create_menu(),
            child=img,
        )

        return button

    def _create_actions(self) -> None:
        actions = [
            ("quick-reply", "s"),
            ("quick-reply-config", None),
        ]

        for action, variant_type in actions:
            if variant_type is not None:
                variant_type = GLib.VariantType(variant_type)
            act = Gio.SimpleAction.new(action, variant_type)
            act.connect("activate", self._on_action)
            self._actions.append(act)

    def deactivate(self) -> None:
        self._action_box.remove(self._button)
        for action in self._actions:
            app.window.remove_action(action.get_name())

    def _message_actions_box_created(
        self, message_actions_box: MessageActionsBox, gtk_box: Gtk.Box
    ) -> None:

        for action in self._actions:
            app.window.add_action(action)

        self._message_input = message_actions_box.msg_textview
        self._action_box = gtk_box
        self._action_box.append(self._button)

    @staticmethod
    def _load_quick_replies() -> list[str]:
        try:
            data_path = Path(configpaths.get("PLUGINS_DATA"))
        except KeyError:
            # PLUGINS_DATA was added in 1.0.99.1
            return DEFAULT_DATA

        path = data_path / "quick_replies" / "quick_replies"
        if not path.exists():
            return DEFAULT_DATA

        with path.open("r") as file:
            quick_replies = json.load(file)
        return quick_replies

    @staticmethod
    def _save_quick_replies(quick_replies: list[str]) -> None:
        try:
            data_path = Path(configpaths.get("PLUGINS_DATA"))
        except KeyError:
            # PLUGINS_DATA was added in 1.0.99.1
            return

        path = data_path / "quick_replies"
        if not path.exists():
            path.mkdir(parents=True)

        filepath = path / "quick_replies"
        with filepath.open("w") as file:
            json.dump(quick_replies, file)

    def set_quick_replies(self, quick_replies: list[str]) -> None:
        self._quick_replies = quick_replies
        self._save_quick_replies(quick_replies)
        self._button.set_menu_model(self._create_menu())

    def get_quick_replies(self) -> list[str]:
        return self._quick_replies

    def _create_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append_item(
            Gio.MenuItem.new(_("Manage Replies…"), "win.quick-reply-config")
        )

        for reply in self._quick_replies:
            menu.append_item(Gio.MenuItem.new(reply[:15], f"win.quick-reply::{reply}"))

        return menu

    def _on_action(
        self, action: Gio.SimpleAction, param: GLib.Variant | None
    ) -> int | None:
        name = action.get_name()
        if name == "quick-reply-config":
            self.config_dialog(app.window)

        elif name == "quick-reply":
            assert param is not None
            message_buffer = self._message_input.get_buffer()
            message_buffer.insert_at_cursor(param.get_string().rstrip() + " ")
            self._message_input.grab_focus()
