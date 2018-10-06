# -*- coding: utf-8 -*-

## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##

'''
Message length notifier plugin.

:author: Mateusz Biliński <mateusz@bilinski.it>
:since: 1st June 2008
:copyright: Copyright (2008) Mateusz Biliński <mateusz@bilinski.it>
:license: GPL
'''

from gi.repository import Gtk
from gi.repository import Gdk

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.gui import GajimPluginConfigDialog

# Since Gajim 1.1.0 _() has to be imported
try:
    from gajim.common.i18n import _
except ImportError:
    pass


class LengthNotifierPlugin(GajimPlugin):

    @log_calls('LengthNotifierPlugin')
    def init(self):
        self.description = _('Highlights message entry field in chat window '
            'when given length of message is exceeded.')
        self.config_dialog = LengthNotifierPluginConfigDialog(self)

        self.gui_extension_points = {
            'chat_control' : (self.connect_with_chat_control,
                self.disconnect_from_chat_control)
        }

        self.config_default_values = {
            'MESSAGE_WARNING_LENGTH' : (140, 'Message length at which notification is invoked.'),
            'WARNING_COLOR' : ('#F0DB3E', 'Background color of text entry field in chat window when notification is invoked.'),
            'JIDS' : ([], 'JabberIDs that plugin should be used with (eg. restrict only to one microblogging bot). If empty plugin is used with every JID. [not implemented]')
            }

    @log_calls('LengthNotifierPlugin')
    def textview_length_warning(self, tb, chat_control):
        tv = chat_control.msg_textview
        d = chat_control.length_notifier_plugin_data
        if tv.has_text():
            t = tb.get_text(tb.get_start_iter(), tb.get_end_iter(), True)
            len_t = len(t)
            if len_t > self.config['MESSAGE_WARNING_LENGTH']:
                if not d['prev_color']:
                    #FIXME: That doesn't work
                    context = tv.get_style_context()
                    d['prev_color'] = context.get_background_color(
                        Gtk.StateFlags.NORMAL)
                color = Gdk.RGBA()
                Gdk.RGBA.parse(color, self.config['WARNING_COLOR'])
                tv.override_background_color(Gtk.StateFlags.NORMAL, color)
            elif d['prev_color']:
                tv.override_background_color(Gtk.StateFlags.NORMAL,
                    d['prev_color'])
                d['prev_color'] = None
        elif d['prev_color']:
            tv.override_background_color(Gtk.StateFlags.NORMAL, d['prev_color'])
            d['prev_color'] = None

    @log_calls('LengthNotifierPlugin')
    def connect_with_chat_control(self, chat_control):
        jid = chat_control.contact.jid
        if self.jid_is_ok(jid):
            d = {'prev_color' : None}
            tv = chat_control.msg_textview
            tb = tv.get_buffer()
            h_id = tb.connect('changed', self.textview_length_warning,
                chat_control)
            d['h_id'] = h_id

            if tv.has_text():
                t = tb.get_text(tb.get_start_iter(), tb.get_end_iter(), True)
                len_t = len(t)
                if len_t > self.config['MESSAGE_WARNING_LENGTH']:
                    context = tv.get_style_context()
                    d['prev_color'] = context.get_background_color(
                        Gtk.StateFlags.NORMAL)
                    color = Gdk.RGBA()
                    Gdk.RGBA.parse(color, self.config['WARNING_COLOR'])
                    tv.override_background_color(Gtk.StateType.NORMAL, color)

            chat_control.length_notifier_plugin_data = d

            return True

        return False

    @log_calls('LengthNotifierPlugin')
    def disconnect_from_chat_control(self, chat_control):
        try:
            d = chat_control.length_notifier_plugin_data
            tv = chat_control.msg_textview
            tv.get_buffer().disconnect(d['h_id'])
            if d['prev_color']:
                tv.override_background_color(Gtk.StateType.NORMAL,
                    d['prev_color'])
        except AttributeError as error:
            pass
            #log.debug('Length Notifier Plugin was (probably) never connected with this chat window.\n Error: %s' % (error))

    @log_calls('LengthNotifierPlugin')
    def jid_is_ok(self, jid):
        if jid in self.config['JIDS'] or not self.config['JIDS']:
            return True

        return False

class LengthNotifierPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
            ['length_notifier_config_table'])
        self.config_table = self.xml.get_object('length_notifier_config_table')
        self.get_child().pack_start(self.config_table, False, False, 0)

        self.message_length_spinbutton = self.xml.get_object(
            'message_length_spinbutton')
        self.message_length_spinbutton.get_adjustment().configure(140, 0, 500,
            1, 10, 0)
        self.notification_colorbutton = self.xml.get_object(
            'notification_colorbutton')
        self.jids_entry = self.xml.get_object('jids_entry')

        self.xml.connect_signals(self)

    def on_run(self):
        self.message_length_spinbutton.set_value(self.plugin.config[
            'MESSAGE_WARNING_LENGTH'])
        color = Gdk.Color.parse(self.plugin.config['WARNING_COLOR'])[1]
        self.notification_colorbutton.set_color(color)
        #self.jids_entry.set_text(self.plugin.config['JIDS'])
        self.jids_entry.set_text(','.join(self.plugin.config['JIDS']))

    @log_calls('LengthNotifierPluginConfigDialog')
    def on_message_length_spinbutton_value_changed(self, spinbutton):
        self.plugin.config['MESSAGE_WARNING_LENGTH'] = spinbutton.get_value()

    @log_calls('LengthNotifierPluginConfigDialog')
    def on_notification_colorbutton_color_set(self, colorbutton):
        self.plugin.config['WARNING_COLOR'] = colorbutton.get_color().\
            to_string()

    @log_calls('LengthNotifierPluginConfigDialog')
    def on_jids_entry_changed(self, entry):
        text = entry.get_text()
        if len(text) > 0:
            self.plugin.config['JIDS'] = entry.get_text().split(',')
        else:
            self.plugin.config['JIDS'] = []

    @log_calls('LengthNotifierPluginConfigDialog')
    def on_jids_entry_editing_done(self, entry):
        pass
