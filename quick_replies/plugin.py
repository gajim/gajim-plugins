from __future__ import annotations

from typing import cast

import json
from pathlib import Path
from functools import partial

from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Gtk

from gajim.common import app
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
            'message_actions_box': (self._message_actions_box_created, None),
        }
        self._button = None
        self.quick_replies = self._load_quick_replies()

    def deactivate(self) -> None:
        assert self._button is not None
        self._button.destroy()
        del self._button

    def _message_actions_box_created(self,
                                     message_actions_box: MessageActionsBox,
                                     gtk_box: Gtk.Box
                                     ) -> None:

        self._button = QuickRepliesButton(
            self,
            message_actions_box.msg_textview)
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
        self._button.update_menu()


class QuickRepliesButton(Gtk.MenuButton):
    def __init__(self,
                 plugin: QuickRepliesPlugin,
                 message_input: MessageInputTextView
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

        self._plugin = plugin
        self._message_input = message_input

        self._menu = Gio.Menu()
        self._popover = Gtk.Popover()
        self._popover.bind_model(self._menu)
        self.set_popover(self._popover)

        self.update_menu()

    def update_menu(self) -> None:
        self._menu.remove_all()

        # Add config item
        action_data = GLib.Variant('s', 'plugin-configuration')
        menu_item = Gio.MenuItem()
        menu_item.set_label(_('Manage Replies…'))
        menu_item.set_attribute_value('action-data', action_data)
        self._menu.append_item(menu_item)

        # Add quick replies
        for reply in self._plugin.quick_replies:
            assert isinstance(reply, str)
            action_data = GLib.Variant('s', reply)
            menu_item = Gio.MenuItem()
            menu_item.set_label(reply)
            menu_item.set_attribute_value('action-data', action_data)
            self._menu.append_item(menu_item)

        menu_buttons = self._get_menu_buttons()
        for button in menu_buttons:
            button.connect(
                'clicked',
                self._on_button_clicked,
                menu_buttons.index(button))

    def _on_button_clicked(self, _button: Gtk.MenuButton, index: int) -> None:
        variant = self._menu.get_item_attribute_value(
            index, 'action-data')
        if variant.get_string() == 'plugin-configuration':
            self._popover.popdown()
            self._plugin.config_dialog(app.window)
            return

        message_buffer = self._message_input.get_buffer()
        message_buffer.insert_at_cursor(variant.get_string().rstrip() + ' ')
        self._popover.popdown()
        self._message_input.grab_focus()

    def _get_menu_buttons(self) -> list[Gtk.ModelButton]:
        stack = cast(Gtk.Stack, self._popover.get_children()[0])
        menu_section_box = cast(Gtk.Box, stack.get_children()[0])
        box = cast(Gtk.Box, menu_section_box.get_children()[0])
        items = cast(list[Gtk.ModelButton], box.get_children())
        return items
