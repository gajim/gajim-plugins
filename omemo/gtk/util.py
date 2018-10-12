# This file is part of Gajim-OMEMO.
#
# Gajim-OMEMO is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim-OMEMO is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim-OMEMO. If not, see <http://www.gnu.org/licenses/>.


from collections import namedtuple
from enum import IntEnum
from enum import Enum

from gi.repository import Gtk

DialogButton = namedtuple('DialogButton', 'text callback action')
DialogButton.__new__.__defaults__ = (None, None)  # type: ignore


class ButtonAction(Enum):
    DESTRUCTIVE = 'destructive-action'
    SUGGESTED = 'suggested-action'


class Trust(IntEnum):
    NOT_TRUSTED = 0
    VERIFIED = 1
    UNKNOWN = 2


class NewConfirmationDialog(Gtk.MessageDialog):
    def __init__(self, text, sec_text, buttons, transient_for=None):
        Gtk.MessageDialog.__init__(self,
                                   transient_for=transient_for,
                                   message_type=Gtk.MessageType.QUESTION,
                                   text=text)

        self._buttons = buttons

        for response, button in buttons.items():
            self.add_button(button.text, response)
            if button.action is not None:
                widget = self.get_widget_for_response(response)
                widget.get_style_context().add_class(button.action.value)

        self.format_secondary_markup(sec_text)

        self.connect('response', self._on_response)

        self.run()

    def _on_response(self, dialog, response):
        if response == Gtk.ResponseType.DELETE_EVENT:
            # Look if DELETE_EVENT is mapped to another response
            response = self._buttons.get(response, None)
            if response is None:
                # If DELETE_EVENT was not mapped we assume CANCEL
                response = Gtk.ResponseType.CANCEL

        button = self._buttons.get(response, None)
        if button is None:
            self.destroy()
            return

        if button.callback is not None:
            button.callback()
        self.destroy()
