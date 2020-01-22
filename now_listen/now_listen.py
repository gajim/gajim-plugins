import os
import logging

from gi.repository import Gtk
from gi.repository import Gdk

from gajim.plugins import GajimPlugin
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.plugins_i18n import _

from gajim.common.dbus.music_track import MusicTrackListener


log = logging.getLogger('gajim.p.now_listen')


class NowListenPlugin(GajimPlugin):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        self.description = _('Copy tune info of playing music to conversation '
                             'input box at cursor position (Alt + N)')
        self.config_dialog = NowListenPluginConfigDialog(self)
        self.gui_extension_points = {'chat_control_base':
                                     (self._on_connect_chat_control,
                                      self._on_disconnect_chat_control)}

        self.config_default_values = {
            'format_string':
                (_('Now listening to: "%title" by %artist from %album'), ''),
            'format_string_http':
                (_('Now listening to: "%title" by %artist'), ''), }

        if os.name == 'nt':
            self.available_text = _('Plugin cannot be run under Windows.')
            self.activatable = False

        self._event_ids = {}
        self._track_changed_id = None
        self._music_track_info = None

    def _on_connect_chat_control(self, control):
        signal_id = control.msg_textview.connect('key-press-event',
                                                 self._on_insert)
        self._event_ids[control.control_id] = signal_id

    def _on_disconnect_chat_control(self, control):
        signal_id = self._event_ids.pop(control.control_id)
        # Raises a warning because the textview is already destroyed
        # But for the deactivate() case this method is called for all active
        # controls and in this case the textview is not destroyed
        # We need someway to detect if the textview is already destroyed
        control.msg_textview.disconnect(signal_id)

    def activate(self):
        listener = MusicTrackListener.get()
        self._track_changed_id = listener.connect(
            'music-track-changed',
            self._on_music_track_changed)

        listener.start()

    def deactivate(self):
        listener = MusicTrackListener.get()
        if self._track_changed_id is not None:
            listener.disconnect(self._track_changed_id)
            self._track_changed_id = None

    def _on_music_track_changed(self, _listener, music_track_info):
        self._music_track_info = music_track_info

    def _get_tune_string(self):
        format_string = self.config['format_string']
        tune_string = format_string.\
            replace('%artist', self._music_track_info.artist).\
            replace('%title', self._music_track_info.title).\
            replace('%album', self._music_track_info.album)
        return tune_string

    def _on_insert(self, textview, event):
        # Insert text to message input box, at cursor position
        if event.keyval != Gdk.KEY_n:
            return
        if not event.state & Gdk.ModifierType.MOD1_MASK:  # ALT+N
            return

        if self._music_track_info is None:
            return

        tune_string = self._get_tune_string()

        textview.get_buffer().insert_at_cursor(tune_string)
        textview.grab_focus()
        return True


class NowListenPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                                       ['now_listen_config'])

        self.config_vbox = self.xml.get_object('now_listen_config')
        self.get_child().pack_start(self.config_vbox, True, True, 0)

        self.format_string = self.xml.get_object('format_string')
        self.format_string_http = self.xml.get_object('format_string_http')
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)

    def on_run(self):
        self.format_string.set_text(self.plugin.config['format_string'])
        self.format_string_http.set_text(self.plugin.config['format_string_http'])

    def on_hide(self, widget):
        self.plugin.config['format_string'] = self.format_string.get_text()
        self.plugin.config['format_string_http'] = self.format_string_http.get_text()
