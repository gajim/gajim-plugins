# -*- coding: utf-8 -*-

from gi.repository import Gtk

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
                                      'Minimum_lines': (2, ''),}
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
        tbuffer = chat_control.msg_textview.get_buffer()
        min_size = chat_control.msg_textview.get_line_yrange(
            tbuffer.get_start_iter())[1] * plugin.config['Minimum_lines'] + 2

        chat_control.msg_textview.set_property('height-request', min_size)
          #  plugin.config['Minimum_lines'])

        self.id_ = chat_control.msg_textview.connect('size-allocate',
            self.size_request)
        chat_control.handlers[self.id_] = chat_control.msg_textview
        self.chat_control = chat_control
        self.plugin = plugin

    def size_request(self, msg_textview, requisition):
        tbuffer = msg_textview.get_buffer()
        min_size = msg_textview.get_line_yrange(tbuffer.get_start_iter())[1] * \
            self.plugin.config['Minimum_lines'] + 2

        if self.plugin.config['Do_not_resize']:
            self.chat_control.msg_scrolledwindow.set_property(
                'vscrollbar-policy', Gtk.PolicyType.AUTOMATIC)
        elif requisition.height > min_size:
            msg_textview.set_property('height-request', requisition.height)
        else:
            msg_textview.set_property('height-request', min_size)

    def disconnect_from_chat_control(self):
        if self.id_ not in self.chat_control.handlers:
            return
        if self.chat_control.handlers[self.id_].handler_is_connected(self.id_):
            self.chat_control.handlers[self.id_].disconnect(self.id_)
            del self.chat_control.handlers[self.id_]
        self.chat_control.msg_textview.set_property('height-request', -1)
        self.chat_control.msg_textview.queue_draw()


class MsgBoxSizePluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.checkbutton = self.xml.get_object('checkbutton')
        self.spinbutton = self.xml.get_object('minimum_lines')
        self.spinbutton.get_adjustment().configure(20, 1, 10, 1, 10, 0)
        vbox = self.xml.get_object('vbox1')
        self.get_child().pack_start(vbox, False, False, 0)

        self.xml.connect_signals(self)

    def on_run(self):
        self.checkbutton.set_active(self.plugin.config['Do_not_resize'])
        self.spinbutton.set_value(self.plugin.config['Minimum_lines'])

    def on_checkbutton_toggled(self, checkbutton):
        self.plugin.config['Do_not_resize'] = checkbutton.get_active()

    def on_minimum_lines_value_changed(self, spinbutton):
        self.plugin.config['Minimum_lines'] = spinbutton.get_value()
