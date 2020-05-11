import json
from pathlib import Path
from functools import partial

from gi.repository import Gtk

from gajim.common import configpaths

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from quick_replies.quick_replies import DEFAULT_DATA
from quick_replies.gtk.config import ConfigDialog


class QuickRepliesPlugin(GajimPlugin):
    def init(self):
        self.description = _('Adds a menu with customizable quick replies')
        self.config_dialog = partial(ConfigDialog, self)
        self.gui_extension_points = {
            'chat_control_base': (self._connect_chat_control,
                                  self._disconnect_chat_control),
            }
        self._buttons = {}
        self.quick_replies = self._load_quick_replies()

    def _connect_chat_control(self, chat_control):
        button = QuickRepliesButton(chat_control, self.quick_replies)
        self._buttons[chat_control.control_id] = button
        actions_hbox = chat_control.xml.get_object('hbox')
        actions_hbox.pack_start(button, False, False, 0)
        actions_hbox.reorder_child(
            button, len(actions_hbox.get_children()) - 2)
        button.show()

    def _disconnect_chat_control(self, chat_control):
        button = self._buttons.get(chat_control.control_id)
        if button is not None:
            button.destroy()
            self._buttons.pop(chat_control.control_id, None)

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
    def _save_quick_replies(quick_replies):
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

    def set_quick_replies(self, quick_replies):
        self.quick_replies = quick_replies
        self._save_quick_replies(quick_replies)
        self._update_buttons()

    def _update_buttons(self):
        for button in self._buttons.values():
            button.update_menu(self.quick_replies)


class QuickRepliesButton(Gtk.MenuButton):
    def __init__(self, chat_control, replies):
        Gtk.MenuButton.__init__(self)
        self.get_style_context().add_class('chatcontrol-actionbar-button')
        self.set_property('relief', Gtk.ReliefStyle.NONE)
        self.set_can_focus(False)
        plugin_path = Path(__file__).parent
        img_path = plugin_path.resolve() / 'quick_replies.png'
        img = Gtk.Image.new_from_file(str(img_path))
        self.set_image(img)
        self.set_tooltip_text(_('Quick Replies'))

        self._chat_control = chat_control

        self.update_menu(replies)

    def update_menu(self, replies):
        self._menu = Gtk.Menu()
        for reply in replies:
            item = Gtk.MenuItem.new_with_label(label=reply)
            item.connect('activate', self._on_insert, reply)
            self._menu.append(item)
        self._menu.show_all()
        self.set_popup(self._menu)

    def _on_insert(self, _widget, text):
        message_buffer = self._chat_control.msg_textview.get_buffer()
        self._chat_control.msg_textview.remove_placeholder()
        message_buffer.insert_at_cursor(text.rstrip() + ' ')
        self._chat_control.msg_textview.grab_focus()
