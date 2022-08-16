from __future__ import annotations

import json
from pathlib import Path
from functools import partial

from gi.repository import Gtk

from gajim.common import configpaths

from gajim.gui.message_actions_box import MessageActionsBox
from gajim.gui.message_input import MessageInputTextView

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from quick_replies.quick_replies import DEFAULT_DATA
from quick_replies.gtk.config import ConfigDialog


class QuickRepliesPlugin(GajimPlugin):
    def init(self):
        self.description = _('Adds a menu with customizable quick replies')
        self.config_dialog = partial(ConfigDialog, self)
        self.gui_extension_points = {
            'message_actions_box': (self._connect, None),
        }
        self._button = None
        self.quick_replies = self._load_quick_replies()

    def deactivate(self) -> None:
        assert self._button is not None
        self._button.destroy()
        del self._button

    def _connect(self,
                 message_actions_box: MessageActionsBox,
                 gtk_box: Gtk.Box
                 ) -> None:

        self._button = QuickRepliesButton(
            message_actions_box.msg_textview, self.quick_replies)
        gtk_box.pack_start(self._button, False, False, 0)
        self._button.show()

    @staticmethod
    def _load_quick_replies():
        try:
            data_path = Path(configpaths.get('PLUGINS_DATA'))
        except KeyError:
            # PLUGINS_DATA was added in 1.0.99.1
            return DEFAULT_DATA

        path = data_path / 'quick_replies' / 'quick_replies'
        if not path.exists():
            return DEFAULT_DATA

        with path.open('r') as file:
            quick_replies = json.load(file)
        return quick_replies

    @staticmethod
    def _save_quick_replies(quick_replies: list[str]) -> None:
        try:
            data_path = Path(configpaths.get('PLUGINS_DATA'))
        except KeyError:
            # PLUGINS_DATA was added in 1.0.99.1
            return

        path = data_path / 'quick_replies'
        if not path.exists():
            path.mkdir(parents=True)

        filepath = path / 'quick_replies'
        with filepath.open('w') as file:
            json.dump(quick_replies, file)

    def set_quick_replies(self, quick_replies: list[str]) -> None:
        self.quick_replies = quick_replies
        self._save_quick_replies(quick_replies)
        assert self._button is not None
        self._button.update_menu(self.quick_replies)


class QuickRepliesButton(Gtk.MenuButton):
    def __init__(self,
                 message_input: MessageInputTextView,
                 replies: list[str]
                 ) -> None:

        Gtk.MenuButton.__init__(self)
        self.get_style_context().add_class('chatcontrol-actionbar-button')
        self.set_property('relief', Gtk.ReliefStyle.NONE)
        self.set_can_focus(False)
        plugin_path = Path(__file__).parent
        img_path = plugin_path.resolve() / 'quick_replies.png'
        img = Gtk.Image.new_from_file(str(img_path))
        self.set_image(img)
        self.set_tooltip_text(_('Quick Replies'))

        self._message_input = message_input

        self.update_menu(replies)

    def update_menu(self, replies: list[str]) -> None:
        self._menu = Gtk.Menu()
        for reply in replies:
            item = Gtk.MenuItem.new_with_label(label=reply)
            item.connect('activate', self._on_activate, reply)
            self._menu.append(item)
        self._menu.show_all()
        self.set_popup(self._menu)

    def _on_activate(self, _widget: Gtk.MenuItem, text: str) -> None:
        message_buffer = self._message_input.get_buffer()
        message_buffer.insert_at_cursor(text.rstrip() + ' ')
        self._message_input.grab_focus()
