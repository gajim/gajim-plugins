# -*- coding: utf-8 -*-

import gtk

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls
from plugins.gui import GajimPluginConfigDialog


class MsgBoxSizePlugin(GajimPlugin):
    @log_calls('MsgBoxSizePlugin')
    def init(self):
        self.description = _('Allows you to adjust the height'
            ' of the new message input field.')
        self.config_dialog = MsgBoxSizePluginConfigDialog(self)
        self.gui_extension_points = {
                'chat_control_base': (self.connect_with_chat_control,
                                       self.disconnect_from_chat_control)}
        self.config_default_values = {'Do_not_resize': (False, ''),
                                      'Message_box_size': (40, ''),}
        self.chat_control = None
        self.controls = []

    @log_calls('MsgBoxSizePlugin')
    def connect_with_chat_control(self, chat_control):
        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)

    @log_calls('MsgBoxSizePlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []


class Base(object):
    def __init__(self, plugin, chat_control):
        if plugin.config['Do_not_resize']:
            chat_control.msg_textview.set_property('height-request',
                plugin.config['Message_box_size'])

        id_ = chat_control.msg_textview.connect('size-request',
            self.size_request)
        chat_control.handlers[id_] = chat_control.msg_textview
        self.chat_control = chat_control
        self.plugin = plugin
        self.scrolledwindow = chat_control.conv_scrolledwindow

    def size_request(self, msg_textview, requisition):
        if msg_textview.window is None:
            return

        if self.plugin.config['Do_not_resize']:
            self.chat_control.conv_scrolledwindow.set_property('height-request',
                self.chat_control.conv_scrolledwindow.allocation.height)
            self.chat_control.msg_scrolledwindow.set_property(
                'vscrollbar-policy', gtk.POLICY_AUTOMATIC)
        else:
            if requisition.height < self.plugin.config['Message_box_size']:
                allc = self.chat_control.msg_textview.allocation
                allc.height = self.plugin.config['Message_box_size']
                msg_textview.set_size_request(allc.width, allc.height)
            else:
                new_req = self.scrolledwindow.allocation.height - (
                    requisition.height - self.plugin.config['Message_box_size'])
                if new_req > 1:
                    self.scrolledwindow.set_property('height-request', new_req)
                self.chat_control.msg_textview.set_property('height-request', -1)

    def disconnect_from_chat_control(self):
        pass


class MsgBoxSizePluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.checkbutton = self.xml.get_object('checkbutton')
        self.spinbutton = self.xml.get_object('message_box_size')
        self.spinbutton.get_adjustment().set_all(20, 15, 320, 1, 10, 0)
        vbox = self.xml.get_object('vbox1')
        self.child.pack_start(vbox)

        self.xml.connect_signals(self)

    def on_run(self):
        self.checkbutton.set_active(self.plugin.config['Do_not_resize'])
        self.spinbutton.set_value(self.plugin.config['Message_box_size'])

    def on_checkbutton_toggled(self, checkbutton):
        self.plugin.config['Do_not_resize'] = checkbutton.get_active()

    def on_message_box_size_value_changed(self, spinbutton):
        self.plugin.config['Message_box_size'] = spinbutton.get_value()
