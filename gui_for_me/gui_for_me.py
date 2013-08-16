# -*- coding: utf-8 -*-

import gtk

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls


class GuiForMe(GajimPlugin):

    @log_calls('GuiForMePlugin')
    def init(self):
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
            and gajim.connections[chat_control.account].connected > 0)


class Base(object):
    def __init__(self, plugin, chat_control):
        self.chat_control = chat_control
        self.plugin = plugin
        self.textview = self.chat_control.conv_textview
        self.change_cursor = False

        self.create_buttons()

    def create_buttons(self):
        # create /me button
        actions_hbox = self.chat_control.xml.get_object('actions_hbox')
        self.button = gtk.Button(label=None, stock=None, use_underline=True)
        self.button.set_property('relief', gtk.RELIEF_NONE)
        self.button.set_property('can-focus', False)
        img = gtk.Image()
        img_path = self.plugin.local_file_path('gui_for_me.png')
        pixbuf = gtk.gdk.pixbuf_new_from_file(img_path)
        iconset = gtk.IconSet(pixbuf=pixbuf)
        factory = gtk.IconFactory()
        factory.add('gui_for_me', iconset)
        factory.add_default()
        img.set_from_stock('gui_for_me', gtk.ICON_SIZE_MENU)
        self.button.set_image(img)
        self.button.set_tooltip_text(_('Insert /me to conversation input box,'
            ' at cursor position'))
        send_button = self.chat_control.xml.get_object('send_button')
        send_button_pos = actions_hbox.child_get_property(send_button,
            'position')
        actions_hbox.add_with_properties(self.button, 'position',
            send_button_pos - 1, 'expand', False)
        id_ = self.button.connect('clicked', self.on_me_button_clicked)
        self.chat_control.handlers[id_] = self.button
        self.button.show()

    def on_me_button_clicked(self, widget):
        """
        Insert /me to conversation input box, at cursor position
        """
        message_buffer = self.chat_control.msg_textview.get_buffer()
        message_buffer.insert_at_cursor('/me ')
        self.chat_control.msg_textview.grab_focus()

    def disconnect_from_chat_control(self):
        actions_hbox = self.chat_control.xml.get_object('actions_hbox')
        actions_hbox.remove(self.button)
