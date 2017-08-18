# -*- coding: utf-8 -*-

from gi.repository import Gtk
from gi.repository import Gdk
import os

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.gajimplugin import GajimPluginException
from gajim.common import dbus_support

if dbus_support.supported:
    from gajim.music_track_listener import MusicTrackListener

class NowListenPlugin(GajimPlugin):

    @log_calls('NowListenPlugin')
    def init(self):
        self.description = _('Copy tune info to conversation input box '
            '(alt + n) at cursor position')
        self.config_dialog = NowListenPluginConfigDialog(self)
        self.gui_extension_points = {'chat_control_base':
            (self.connect_with_chat_control, self.disconnect_from_chat_control)}

        self.config_default_values = {
        'format_string': ('Now listen:"%title" by %artist from %album', ''),
        'format_string_http': ('Now listen:"%title" by %artist', ''),}

        self.controls = []
        self.first_run = True
        self.music_track_changed_signal = None
        if os.name == 'nt':
            self.available_text = _('Plugin can\'t be run under Windows.')
            self.activatable = False

    @log_calls('NowListenPlugin')
    def connect_with_chat_control(self, chat_control):
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
            raise GajimPluginException(_('python-dbus is missing!'))
        listener = MusicTrackListener.get()
        if not self.music_track_changed_signal:
            self.music_track_changed_signal = listener.connect(
                'music-track-changed', self.music_track_changed)
        track = listener.get_playing_track()
        self.music_track_changed(listener, track)

    @log_calls('NowListenPlugin')
    def deactivate(self):
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
            if hasattr(music_track_info, 'url'):
                self.url = music_track_info.url
                self.albumartist = music_track_info.albumartist
            else:
                self.url = ''


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.plugin.artist = self.plugin.title = self.plugin.source = ''
        self.plugin.url = self.plugin.albumartist = ''

        self.id_ = self.chat_control.msg_textview.connect('key_press_event',
            self.on_insert)
        self.chat_control.handlers[self.id_] = self.chat_control.msg_textview

    def disconnect_from_chat_control(self):
        if self.id_ not in self.chat_control.handlers:
            return
        if self.chat_control.handlers[self.id_].handler_is_connected(self.id_):
            self.chat_control.handlers[self.id_].disconnect(self.id_)
            del self.chat_control.handlers[self.id_]

    def on_insert(self, widget, event):
        """
        Insert text to conversation input box, at cursor position
        """
        if event.keyval != Gdk.KEY_n:
            return
        if not event.state & Gdk.ModifierType.MOD1_MASK:  # ALT+N
            return

        if self.plugin.artist == self.plugin.title == self.plugin.source == '':
            tune_string = 'paused or stopped'
        else:
            format_string = self.plugin.config['format_string']
            if self.plugin.url and not self.plugin.url.startswith('file://'):
                format_string = self.plugin.config['format_string_http']
            tune_string = format_string.replace(
            '%artist', self.plugin.artist).replace(
            '%title', self.plugin.title).replace('%album',self.plugin.source).\
            replace('%url', self.plugin.url)

        message_buffer = self.chat_control.msg_textview.get_buffer()
        message_buffer.insert_at_cursor(tune_string)
        self.chat_control.msg_textview.grab_focus()
        return True


class NowListenPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['now_listen_config_vbox'])

        self.config_vbox = self.xml.get_object('now_listen_config_vbox')
        self.get_child().pack_start(self.config_vbox, True, True, 0)

        self.format_sting = self.xml.get_object('format_sting')
        self.format_sting_http = self.xml.get_object('format_sting_http')
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)

    def on_run(self):
        self.format_sting.set_text(self.plugin.config['format_string'])
        self.format_sting_http.set_text(self.plugin.config['format_string_http'])

    def on_hide(self, widget):
        self.plugin.config['format_string'] = self.format_sting.get_text()
        self.plugin.config['format_string_http'] = self.format_sting_http.get_text()
