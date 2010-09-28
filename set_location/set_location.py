# -*- coding: utf-8 -*-
##

from datetime import datetime
import time
import gtk
import os
import locale
import gettext

from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from common import gajim

locale_path = os.path.dirname(__file__) + '/locales'
locale.bindtextdomain('setlocation', locale_path)
try:
    gett = gettext.Catalog('setlocation', locale_path)
    _ = gett.gettext
except:
    pass

class SetLocationPlugin(GajimPlugin):
    @log_calls('SetLocationPlugin')
    def init(self):
        self.config_dialog = SetLocationPluginConfigDialog(self)
        self.config_default_values = {
            'alt': (1609,''),
            'area': ('Central Park', ''),
            'building': ('The Empire State Building',''),
            'country': ('United States', ''),
            'countrycode' : ('US', ''),
            'description' : ('Bill\'s house', ''),
            'floor' : ('102', ''),
            'lat' : (39.75, ''),
            'locality' : ('New York City', ''),
            'lon' : (-104.99, ''),
            'postalcode' : ('10027', ''),
            'region' : ('New York', ''),
            'room' : ('Observatory', ''),
            'street' : ('34th and Broadway', ''),
            'text' : ('Northwest corner of the lobby', ''),
            'uri' : ('http://beta.plazes.com/plazes/1940:jabber_inc', ''),}

    @log_calls('SetLocationPlugin')
    def activate(self):
        self._data = {}
        timestamp = time.time()
        timestamp = datetime.utcfromtimestamp(timestamp)
        timestamp = timestamp.strftime('%Y-%m-%dT%H:%MZ')
        self._data['timestamp'] = timestamp
        for name in self.config_default_values:
            self._data[name] = self.config[name]
        for acct in gajim.connections:
            if gajim.connections[acct].connected == 0:
                gajim.connections[acct].to_be_sent_location = self._data
            else:
                gajim.connections[acct].send_location(self._data)

    @log_calls('SetLocationPlugin')
    def deactivate(self):
        self._data = {}
        for acct in gajim.connections:
            gajim.connections[acct].send_location(self._data)


class SetLocationPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('setlocation')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['hbox1'])
        config_table = self.xml.get_object('config_table')
        hbox = self.xml.get_object('hbox1')
        self.child.pack_start(hbox)
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)

    def on_run(self):
        no_map = None
        try:
            import osmgpsmap
        except:
            no_map = True
        if not no_map:
            from layers import DummyLayer
            import gtkgui_helpers

            vbox = self.xml.get_object('vbox1')
            vbox.set_size_request(400, -1)

            self.osm = osmgpsmap.GpsMap()
            self.osm.layer_add(osmgpsmap.GpsMapOsd(show_dpad=True,
                show_zoom=True))
            self.osm.layer_add(DummyLayer())
            lat = float(self.plugin.config['lat'])
            lon = float(self.plugin.config['lon'])
            self.osm.set_center_and_zoom(lat, lon, 12)
            self.path_to_image = os.path.abspath(gtkgui_helpers.get_icon_path(
                'gajim', 16))
            self.icon = gtk.gdk.pixbuf_new_from_file_at_size(
                self.path_to_image, 16, 16)
            self.osm_image = self.osm.image_add(lat, lon, self.icon)
            self.osm.connect('button_release_event', self.map_clicked)
            vbox.pack_start(self.osm)

        for name in self.plugin.config_default_values:
            widget = self.xml.get_object(name)
            widget.set_text(str(self.plugin.config[name]))

    def on_hide(self, widget):
        for name in self.plugin.config_default_values:
            widget = self.xml.get_object(name)
            self.plugin.config[name] = widget.get_text()
            self.plugin.activate()

    def map_clicked(self, osm, event):
        lat, lon = self.osm.get_event_location(event).get_degrees()
        if event.button == 3:
            self.osm.image_remove(self.osm_image)
            self.osm_image = self.osm.image_add(lat, lon, self.icon)
            self.xml.get_object('lat').set_text(str(lat))
            self.xml.get_object('lon').set_text(str(lon))
