from gi.repository import Gtk
from gi.repository import GdkPixbuf

from gajim.common import app
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls

# Since Gajim 1.1.0 _() has to be imported
try:
    from gajim.common.i18n import _
except ImportError:
    pass


class GuiForMe(GajimPlugin):

    @log_calls('GuiForMePlugin')
    def init(self):
        self.description = _('Adds a button for the \'/me\' command.')
        self.config_dialog = None  # GuiForMePluginConfigDialog(self)
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                  self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (self.update_button_state,
                                                None)}
        self.controls = []

    @log_calls('GuiForMePlugin')
    def connect_with_chat_control(self, chat_control):
        if chat_control.widget_name != 'groupchat_control':
            return

        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)


    @log_calls('GuiForMePlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    @log_calls('GuiForMePlugin')
    def update_button_state(self, chat_control):
        for base in self.controls:
            if base.chat_control != chat_control:
                continue
            base.button.set_sensitive(chat_control.contact.show != 'offline' \
            and app.connections[chat_control.account].connected > 0)


class Base(object):
    def __init__(self, plugin, chat_control):
        self.chat_control = chat_control
        self.plugin = plugin
        self.textview = self.chat_control.conv_textview
        self.change_cursor = False

        self.create_buttons()

    def create_buttons(self):
        # create /me button
        actions_hbox = self.chat_control.xml.get_object('hbox')
        self.button = Gtk.Button(label=None, stock=None, use_underline=False)
        self.button.get_style_context().add_class(
            'chatcontrol-actionbar-button')
        self.button.set_relief(Gtk.ReliefStyle.NONE)
        self.button.set_property('can-focus', False)
        img = Gtk.Image()
        img_path = self.plugin.local_file_path('gui_for_me.png')
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(img_path)
        img.set_from_pixbuf(pixbuf)
        self.button.set_image(img)
        self.button.set_tooltip_text(_('Insert /me to conversation input box,'
            ' at cursor position'))
        actions_hbox.pack_start(self.button, False, False , 0)
        actions_hbox.reorder_child(self.button,
            len(actions_hbox.get_children()) - 3)
        id_ = self.button.connect('clicked', self.on_me_button_clicked)
        self.chat_control.handlers[id_] = self.button
        self.button.show()

    def on_me_button_clicked(self, widget):
        """
        Insert /me to conversation input box, at cursor position
        """
        message_buffer = self.chat_control.msg_textview.get_buffer()
        self.chat_control.msg_textview.remove_placeholder()
        message_buffer.insert_at_cursor('/me ')
        self.chat_control.msg_textview.grab_focus()

    def disconnect_from_chat_control(self):
        actions_hbox = self.chat_control.xml.get_object('hbox')
        actions_hbox.remove(self.button)
