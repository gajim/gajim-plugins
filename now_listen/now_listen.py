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

import sys
import logging
from functools import partial

from gi.repository import Gdk
from gi.repository import GObject

from nbxmpp.structs import TuneData

from gajim.gui.message_input import MessageInputTextView

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from gajim.common.dbus.music_track import MusicTrackListener

from now_listen.gtk.config import NowListenConfigDialog


log = logging.getLogger('gajim.p.now_listen')


class NowListenPlugin(GajimPlugin):
    def init(self) -> None:
        # pylint: disable=attribute-defined-outside-init
        self.description = _('Copy tune info of playing music to conversation '
                             'input box at cursor position (Alt + N)')
        self.config_dialog = partial(NowListenConfigDialog, self)
        self.gui_extension_points = {
            'message_input': (self._on_message_input_created, None)
        }

        self.config_default_values = {
            'format_string':
                (_('Now listening to: "%title" by %artist'), ''),
        }

        if sys.platform != 'linux':
            self.available_text = _('Plugin only available for Linux')
            self.activatable = False

        self._signal_id = None
        self._message_input = None

    def deactivate(self) -> None:
        assert self._message_input is not None
        assert self._signal_id is not None
        if GObject.signal_handler_is_connected(
                self._message_input, self._signal_id):
            self._message_input.disconnect(self._signal_id)

    def _on_message_input_created(self,
                                  message_input: MessageInputTextView
                                  ) -> None:

        self._message_input = message_input
        self._signal_id = message_input.connect(
            'key-press-event', self._on_key_press)

    def _get_tune_string(self, info: TuneData) -> str:
        format_string = cast(str, self.config['format_string'])
        tune_string = format_string.replace(
            '%artist', info.artist or '').replace(
                '%title', info.title or '')
        return tune_string

    def _on_key_press(self,
                      textview: MessageInputTextView,
                      event: Gdk.EventKey
                      ) -> bool:

        # Insert text to message input box, at cursor position
        if event.keyval != Gdk.KEY_n:
            return False
        if not event.state & Gdk.ModifierType.MOD1_MASK:  # ALT+N
            return False

        info = MusicTrackListener.get().current_tune
        if info is None:
            log.info('No current tune available')
            return False

        tune_string = self._get_tune_string(info)

        textview.get_buffer().insert_at_cursor(tune_string)
        textview.grab_focus()
        return True
