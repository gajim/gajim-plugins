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
import sys
from functools import partial

from gi.repository import Gdk
from gi.repository import Gtk
from nbxmpp.structs import TuneData

from gajim.common.dbus.music_track import MusicTrackListener
from gajim.gtk.message_input import MessageInputTextView
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from now_listen.gtk.config import NowListenConfigDialog

log = logging.getLogger("gajim.p.now_listen")


class NowListenPlugin(GajimPlugin):
    def init(self) -> None:
        self.description = _(
            "Copy tune info of playing music to conversation "
            "input box at cursor position (Alt + N)"
        )
        self.config_dialog = partial(NowListenConfigDialog, self)
        self.gui_extension_points = {
            "message_input": (self._on_message_input_created, None)
        }

        self.config_default_values = {
            "format_string": (_('Now listening to: "%title" by %artist'), ""),
        }

        if sys.platform != "linux":
            self.available_text = _("Plugin only available for Linux")
            self.activatable = False

        self._controller = Gtk.EventControllerKey()
        self._controller.connect("key-pressed", self._on_key_pressed)

        self._message_input = cast(MessageInputTextView, None)

    def deactivate(self) -> None:
        self._message_input.remove_controller(self._controller)

    def _on_message_input_created(self, message_input: MessageInputTextView) -> None:
        message_input.add_controller(self._controller)
        self._message_input = message_input

    def _get_tune_string(self, info: TuneData) -> str:
        format_string = cast(str, self.config["format_string"])
        tune_string = format_string.replace("%artist", info.artist or "").replace(
            "%title", info.title or ""
        )
        return tune_string

    def _on_key_pressed(
        self,
        _event_controller_key: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval != Gdk.KEY_n:
            return Gdk.EVENT_PROPAGATE

        if not state & Gdk.ModifierType.ALT_MASK:
            return Gdk.EVENT_PROPAGATE

        info = MusicTrackListener.get().current_tune
        if info is None:
            log.info("No current tune available")
            return Gdk.EVENT_PROPAGATE

        tune_string = self._get_tune_string(info)

        self._message_input.get_buffer().insert_at_cursor(tune_string)
        return Gdk.EVENT_STOP
