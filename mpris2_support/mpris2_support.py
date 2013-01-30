# -*- coding: utf-8 -*-


from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls
from plugins.plugin import GajimPluginException
from common import dbus_support

if dbus_support.supported:
    from music_track_listener import MusicTrackListener


class MusicTrackInfo(object):
    __slots__ = ['title', 'album', 'artist', 'duration', 'track_number',
        'paused', 'url', 'albumartist']


class Mpris2Plugin(GajimPlugin):
    @log_calls('Mpris2Plugin')
    def init(self):
        self.description = _('MPRIS2 support. Allows to update status message '
        'according to the music you\'re listening via the MPRIS2 D-Bus API.')
        self.config_dialog = None
        self.artist = self.title = self.source = ''
        self.listener = MusicTrackListener().get()

    @log_calls('NowListenPlugin')
    def activate(self):
        self._last_playing_music = None
        self.bus = dbus_support.session_bus.SessionBus()
        self.bus.add_signal_receiver(self.properties_changed,
            "PropertiesChanged", "org.freedesktop.DBus.Properties")

    @log_calls('Mpris2Plugin')
    def deactivate(self):
        self.bus.remove_signal_receiver(self.properties_changed,
            "PropertiesChanged", "org.freedesktop.DBus.Properties")

    def properties_changed(self,*args,**kw):
        if args[0] != 'org.mpris.MediaPlayer2.Player':
            return
        if 'PlaybackStatus' in args[1]:
            if args[1]['PlaybackStatus'] in ['Paused', 'Stopped']:
                self.title = self.artist = self.source = ''
                self.listener.emit('music-track-changed', None)
            if args[1]['PlaybackStatus'] == 'Playing':
                self.listener.emit('music-track-changed',
                    self._last_playing_music)
        if 'Metadata' not in args[1]:
            return

        data = args[1]['Metadata']
        info = MusicTrackInfo()
        info.title = data.get("xesam:title", '')
        info.album = data.get("xesam:album", '')
        info.artist = data.get("xesam:artist", [''])[0]
        info.albumartist = data.get("xesam:albumArtist", [''])[0]
        info.duration = int(data.get('mpris:length', 0))
        info.track_number = int(data.get('xesam:trackNumber', 0))
        info.url = data.get("xesam:url", '')

        self._last_playing_music = info
        self.listener.emit('music-track-changed', info)
