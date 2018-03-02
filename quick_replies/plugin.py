from gi.repository import Gtk
from gi.repository import GdkPixbuf

from gajim import gtkgui_helpers
from gajim.common import app

from gajim.plugins import GajimPlugin
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.helpers import log_calls


class QuickRepliesPlugin(GajimPlugin):

    @log_calls('QuickRepliesPlugin')
    def init(self):

        self.description = _('Plugin for quick replies')
        self.config_dialog = QuickRepliesPluginConfigDialog(self)
        self.chat_control = None
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                    self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (self.update_button_state,
                                    None)}
        self.config_default_values = {
            'entry1': ('Hello!', ''),
            'entry2': ('How are you?', ''),
            'entry3': ('Good bye.', ''),
            'entry4': ('', ''),
            'entry5': ('', ''),
            'entry6': ('', ''),
            'entry7': ('', ''),
            'entry8': ('', ''),
            'entry9': ('', ''),
            'entry10': ('', ''),
            }
        self.controls = []

    @log_calls('QuickRepliesPlugin')
    def connect_with_chat_control(self, chat_control):

        self.chat_control = chat_control
        base = Base(self, chat_control)
        self.controls.append(base)

    @log_calls('QuickRepliesPlugin')
    def disconnect_from_chat_control(self, chat_control):

        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    @log_calls('QuickRepliesPlugin')
    def update_button_state(self, chat_control):
        for base in self.controls:
            if base.chat_control != chat_control:
                continue
            base.button.set_sensitive(chat_control.contact.show != 'offline' \
            and app.connections[chat_control.account].connected > 0)


class Base(object):

    def __init__(self, plugin, chat_control):

        self.plugin = plugin
        self.chat_control = chat_control
        self.create_button()
        self.create_menu()

    def create_button(self):

        actions_hbox = self.chat_control.xml.get_object('hbox')
        self.button = Gtk.MenuButton(label=None, stock=None, use_underline=True)
        self.button.get_style_context().add_class(
            'chatcontrol-actionbar-button')
        self.button.set_property('relief', Gtk.ReliefStyle.NONE)
        self.button.set_property('can-focus', False)
        img = Gtk.Image()
        img_path = self.plugin.local_file_path('quick_replies.png')
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(img_path)
        img.set_from_pixbuf(pixbuf)
        self.button.set_image(img)
        self.button.set_tooltip_text(_('Quick replies'))
        actions_hbox.pack_start(self.button, False, False , 0)
        actions_hbox.reorder_child(self.button,
            len(actions_hbox.get_children()) - 2)
        self.button.show()

    def on_insert(self, widget, text):

        text = text.rstrip() + ' '
        message_buffer = self.chat_control.msg_textview.get_buffer()
        self.chat_control.msg_textview.remove_placeholder()
        message_buffer.insert_at_cursor(text)
        self.chat_control.msg_textview.grab_focus()

    def create_menu(self):

        self.menu = Gtk.Menu()

        for count in range(1, 11):
            text = self.plugin.config['entry' + str(count)]
            if not text:
                continue
            item = Gtk.MenuItem(text)
            item.connect('activate', self.on_insert, text)
            self.menu.append(item)
        self.menu.show_all()
        self.button.set_popup(self.menu)

    def disconnect_from_chat_control(self):
        actions_hbox = self.chat_control.xml.get_object('hbox')
        actions_hbox.remove(self.button)


class QuickRepliesPluginConfigDialog(GajimPluginConfigDialog):

    def init(self):

        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['table1'])
        hbox = self.xml.get_object('table1')
        self.get_child().pack_start(hbox, True, True, 0)
        self.xml.connect_signals(self)

    def on_run(self):

        for count in range(1, 11):
            self.xml.get_object('entry' + str(count)).set_text(
                self.plugin.config['entry' + str(count)])

    def entry_changed(self, widget):

        name = Gtk.Buildable.get_name(widget)
        self.plugin.config[name] = widget.get_text()
        for control in self.plugin.controls:
            control.create_menu()
