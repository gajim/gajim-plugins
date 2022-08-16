from __future__ import annotations

from typing import cast

from functools import partial

from gajim.gui.message_input import MessageInputTextView

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from message_box_size.config_dialog import MessageBoxSizeConfigDialog


class MsgBoxSizePlugin(GajimPlugin):
    def init(self) -> None:
        # pylint: disable=attribute-defined-outside-init
        self.description = _('Allows you to adjust the height '
                             'of the message input.')
        self.config_dialog = partial(MessageBoxSizeConfigDialog, self)
        self.gui_extension_points = {
            'message_input': (self._on_message_input_created, None)
        }
        self.config_default_values = {
            'HEIGHT': (20, ''),
        }
        self._message_input = None

    def _on_message_input_created(self,
                                  message_input: MessageInputTextView
                                  ) -> None:

        self._message_input = message_input
        self.set_input_height(cast(int, self.config['HEIGHT']))

    def deactivate(self) -> None:
        self.set_input_height(-1)

    def set_input_height(self, height: int) -> None:
        assert self._message_input is not None
        self._message_input.set_size_request(-1, height)
