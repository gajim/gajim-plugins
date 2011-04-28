# -*- coding: utf-8 -*-

import gtk
import gobject

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls
from plugins.gui import GajimPluginConfigDialog
from plugins.plugin import GajimPluginException
from common import dbus_support

if dbus_support.supported:
    from music_track_listener import MusicTrackListener

class NowListenPlugin(GajimPlugin):

    @log_calls('NowListenPlugin')
    def init(self):
        self.config_dialog = NowListenPluginConfigDialog(self)
        self.gui_extension_points = {'chat_control_base':
            (self.connect_with_chat_control, self.disconnect_from_chat_control)}

        self.config_default_values = {
        'format_string': ('Now listen:"%title" by %artist from %album', '')}

        self.controls = []
        self.first_run = True
        self.music_track_changed_signal = None

    @log_calls('NowListenPlugin')
    def connect_with_chat_control(self, chat_control):
        #if not dbus_support.supported:
            #return
        if self.first_run:
            # ALT + N
            gtk.binding_entry_add_signal(chat_control.msg_textview,
                gtk.keysyms.n, gtk.gdk.MOD1_MASK, 'mykeypress',
                int, gtk.keysyms.n, gtk.gdk.ModifierType, gtk.gdk.MOD1_MASK)
            self.first_run = False
        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)

    @log_calls('NowListenPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    @log_calls('NowListenPlugin')
    def activate(self):
        if not dbus_support.supported:
            raise GajimPluginException("python-dbus is missing!")
        listener = MusicTrackListener.get()
        if not self.music_track_changed_signal:
            self.music_track_changed_signal = listener.connect(
                'music-track-changed', self.music_track_changed)
        track = listener.get_playing_track()
        self.music_track_changed(listener, track)

    @log_calls('NowListenPlugin')
    def deactivate(self):
        if hasattr(self, 'chat_control'):
            gtk.binding_entry_remove(self.chat_control.msg_textview,
                gtk.keysyms.n, gtk.gdk.MOD1_MASK)
        self.first_run = True
        if dbus_support.supported:
            listener = MusicTrackListener.get()
            if self.music_track_changed_signal:
                listener.disconnect(self.music_track_changed_signal)
                self.music_track_changed_signal = None

    def music_track_changed(self, unused_listener, music_track_info,
        account=None):
        is_paused = hasattr(music_track_info, 'paused') and \
            music_track_info.paused == 0
        if not music_track_info or is_paused:
            self.artist = self.title = self.source = ''
        else:
            self.artist = music_track_info.artist
            self.title = music_track_info.title
            self.source = music_track_info.album


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control

        self.id_ = chat_control.msg_textview.connect('mykeypress',
            self.on_insert)
        self.chat_control.handlers[self.id_] = self.chat_control.msg_textview

    def disconnect_from_chat_control(self):
        if self.chat_control.handlers[self.id_].handler_is_connected(self.id_):
            self.chat_control.handlers[self.id_].disconnect(self.id_)
            del self.chat_control.handlers[self.id_]

    def on_insert(self, widget, event_keyval, event_keymod):
        """
        Insert text to conversation input box, at cursor position
        """
        # construct event instance from binding
        event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)  # it's always a key-press here
        event.keyval = event_keyval
        event.state = event_keymod
        event.time = 0  # assign current time

        if event.keyval != gtk.keysyms.n:
            return
        if event.state != gtk.gdk.MOD1_MASK:  # ALT+N
            return

        if self.plugin.artist == self.plugin.title == self.plugin.source == '':
            tune_string = 'paused or stopped'
        else:
            tune_string =  self.plugin.config['format_string'].replace(
            '%artist', self.plugin.artist).replace(
            '%title', self.plugin.title).replace('%album',self.plugin.source)

        message_buffer = self.chat_control.msg_textview.get_buffer()
        message_buffer.insert_at_cursor(tune_string)
        self.chat_control.msg_textview.grab_focus()


class NowListenPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        #self.xml.set_translation_domain(i18n.APP)
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['now_listen_config_vbox'])

        self.config_vbox = self.xml.get_object('now_listen_config_vbox')
        self.child.pack_start(self.config_vbox)

        self.format_sting = self.xml.get_object('format_sting')
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)

    def on_run(self):
        self.format_sting.set_text(self.plugin.config['format_string'])

    def on_hide(self, widget):
        self.plugin.config['format_string'] = self.format_sting.get_text()
