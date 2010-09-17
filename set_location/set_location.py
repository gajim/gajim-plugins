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
    name = u'Set Location'
    short_name = u'set_location'
    version = u'0.1'
    description = _(
    u'''Set information about the current geographical or physical location.''')
    authors = [u'Denis Fomin <fominde@gmail.com>']
    homepage = u'http://bitbucket.org/dicson12/plugins/src/tip/set_location/'

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
                ['config_table'])
        config_table = self.xml.get_object('config_table')
        self.child.pack_start(config_table)
        self.xml.connect_signals(self)

    def on_run(self):
        for name in self.plugin.config_default_values:
            widget = self.xml.get_object(name)
            widget.set_text(str(self.plugin.config[name]))

    def changed(self, entry):
        name = gtk.Buildable.get_name(entry)
        self.plugin.config[name] = entry.get_text()

    def on_apply_clicked(self, widget):
        self.plugin.activate()
