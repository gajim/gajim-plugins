import os
import time
import logging
from datetime import datetime

import gi
from gi.repository import Gtk

from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _
from gajim.plugins.helpers import log_calls
from gajim.common import app
from gajim.common import ged
from gajim.common import helpers
from gajim.common import configpaths

from gajim import gtkgui_helpers
from gajim.gtk.dialogs import InputDialog, WarningDialog


log = logging.getLogger('gajim.plugin_system.set_location')

CHAMPLAIN_AVAILABLE = True

try:
    gi.require_version('Clutter', '1.0')
    gi.require_version('GtkClutter', '1.0')
    gi.require_version('Champlain', '0.12')
    gi.require_version('GtkChamplain', '0.12')
    from gi.repository import Clutter, GtkClutter
    GtkClutter.init([]) # Must be initialized before importing those:
    from gi.repository import Champlain, GtkChamplain
except:
    log.exception('To view the map, you have to install all dependencies')
    CHAMPLAIN_AVAILABLE = False


class SetLocationPlugin(GajimPlugin):
    @log_calls('SetLocationPlugin')
    def init(self):
        self.description = _('Set information about your current geographical '
            'or physical location. \nTo be able to set your location on the '
            'built-in map, you need to have gir1.2-gtkchamplain and '
            'gir1.2-gtkclutter-1.0 installed')
        self.config_dialog = SetLocationPluginConfigDialog(self)
        self.config_default_values = {
            'alt': (1609, ''),
            'area': ('Central Park', ''),
            'building': ('The Empire State Building', ''),
            'country': ('United States', ''),
            'countrycode': ('US', ''),
            'description': ('Bill\'s house', ''),
            'floor': ('102', ''),
            'lat': (39.75, ''),
            'locality': ('New York City', ''),
            'lon': (-104.99, ''),
            'postalcode': ('10027', ''),
            'region': ('New York', ''),
            'room': ('Observatory', ''),
            'street': ('34th and Broadway', ''),
            'text': ('Northwest corner of the lobby', ''),
            'uri': ('http://beta.plazes.com/plazes/1940:jabber_inc', ''),
            'presets': ({'default': {}}, ''), }

    @log_calls('SetLocationPlugin')
    def activate(self):
        app.ged.register_event_handler('signed-in', ged.POSTGUI,
            self.on_signed_in)
        self.send_locations()

    @log_calls('SetLocationPlugin')
    def deactivate(self):
        self._data = {}
        for acct in app.connections:
            app.connections[acct].get_module('UserLocation').send(self._data)
        app.ged.remove_event_handler('signed-in', ged.POSTGUI,
            self.on_signed_in)

    def on_signed_in(self, network_event):
        self.send_locations(network_event.conn.name)

    def send_locations(self, acct=False):
        self._data = {}
        timestamp = time.time()
        timestamp = datetime.utcfromtimestamp(timestamp)
        timestamp = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
        self._data['timestamp'] = timestamp
        for name in self.config_default_values:
            self._data[name] = self.config[name]

        if not acct:
            # Set geo for all accounts
            for acct in app.connections:
                if app.config.get_per('accounts', acct, 'publish_location'):
                    app.connections[acct].get_module('UserLocation').send(
                        self._data)
        elif app.config.get_per('accounts', acct, 'publish_location'):
            app.connections[acct].get_module('UserLocation').send(self._data)


class SetLocationPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, 
                ['config_box'])
        config_box = self.xml.get_object('config_box')
        self.get_child().pack_start(config_box, True, True, 0)
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)
        self.connect('show', self.on_show)
        self.is_active = None

        self.preset_combo = self.xml.get_object('preset_combobox')
        self.preset_liststore = Gtk.ListStore(str)
        self.preset_combo.set_model(self.preset_liststore)
        cellrenderer = Gtk.CellRendererText()
        self.preset_combo.pack_start(cellrenderer, True)
        self.preset_combo.add_attribute(cellrenderer, 'text', 0)
        #self.plugin.config['presets'] = {'default': {}}


    @log_calls('SetLocationPlugin.SetLocationPluginConfigDialog')
    def on_run(self):
        if not self.is_active:
            pres_keys = sorted(self.plugin.config['presets'].keys())
            for key in pres_keys:
                self.preset_liststore.append((key,))

        for name in self.plugin.config_default_values:
            if name == 'presets':
                continue
            widget = self.xml.get_object(name)
            widget.set_text(str(self.plugin.config[name]))

        map_placeholder = self.xml.get_object('map_placeholder')
        dependency_bar = self.xml.get_object('dependency_warning')

        if CHAMPLAIN_AVAILABLE and not self.is_active:
            map_placeholder.set_no_show_all(True)
            map_placeholder.hide()
            dependency_bar.hide()
            map_box = self.xml.get_object('map_box')
            map_box.set_size_request(400, -1)

            embed = GtkChamplain.Embed()

            self.view = embed.get_view()
            self.view.set_reactive(True)
            self.view.set_property('kinetic-mode', True)
            self.view.set_property('zoom-level', 12)
            self.view.connect('button-release-event', self.map_clicked,
                              self.view)

            scale = Champlain.Scale()
            scale.connect_view(self.view)
            self.view.add_child(scale)

            lat = self.plugin.config['lat']
            lon = self.plugin.config['lon']
            if not self.is_valid_coord(lat, lon):
                self.lat = self.lon = 0.0
                self.xml.get_object('lat').set_text('0.0')
                self.xml.get_object('lon').set_text('0.0')
            self.view.center_on(self.lat, self.lon)

            self.path_to_image = os.path.abspath(gtkgui_helpers.get_icon_path(
                'org.gajim.Gajim', 16))
            map_box.pack_start(embed, expand=True, fill=True, padding=0)

            self.is_active = True
            self.layer = Champlain.MarkerLayer()
            texture = Clutter.Texture()
            texture.set_from_file(self.path_to_image)
            texture.set_size(32,32)
            self.marker = Champlain.Label.new_with_image(texture)
            self.marker.set_location(self.lat, self.lon)
            self.marker.set_text(_('Your location'))
            self.view.add_layer(self.layer)
            self.layer.add_marker(self.marker)
            self.markers_is_visible = False
            self.xml.get_object('lat').connect('changed', self.on_latlon_changed)
            self.xml.get_object('lon').connect('changed', self.on_latlon_changed)
            self.layer.animate_in_all_markers()
            self.contacts_layer = Champlain.MarkerLayer()

    def on_show(self, widget):
        if CHAMPLAIN_AVAILABLE:
            self.contacts_layer.remove_all()
            self.view.center_on(self.lat, self.lon)
            self.show_contacts()

    def on_hide(self, widget):
        for name in self.plugin.config_default_values:
            if name in ['presets', 'lat', 'lon']:
                continue
            widget = self.xml.get_object(name)
            self.plugin.config[name] = widget.get_text()

        lat = self.xml.get_object('lat').get_text()
        lon = self.xml.get_object('lon').get_text()
        if self.is_valid_coord(lat, lon):
            self.plugin.config['lat'] = lat
            self.plugin.config['lon'] = lon
            if self.plugin.active:
                self.plugin.activate()
        else:
            self.plugin.config['lat'] = '0.0'
            self.plugin.config['lon'] = '0.0'
            error_text = _('Latitude or Longitude field contains an invalid value')
            WarningDialog(_('Wrong coordinates'), error_text, self)

    def map_clicked(self, actor, event, view):
        x, y = event.x, event.y
        lat, lon = view.x_to_longitude(x), view.y_to_latitude(y)
        if event.button == 3:
            self.marker.set_location(lat, lon)
            self.xml.get_object('lon').set_text(str(lat))
            self.xml.get_object('lat').set_text(str(lon))
        if event.button == 2:
            if self.markers_is_visible:
                self.contacts_layer.animate_out_all_markers()
            else:
                self.contacts_layer.animate_in_all_markers()
            self.markers_is_visible = not self.markers_is_visible

    def is_valid_coord(self, lat, lon):
        try:
            self.lat = float(lat)
            self.lon = float(lon)
        except ValueError as e:
            return
        if not -85 < self.lat < 85 or not -180 < self.lon < 180:
            return
        return True

    def on_latlon_changed(self, widget):
        lat = self.xml.get_object('lat').get_text()
        lon = self.xml.get_object('lon').get_text()
        if self.is_valid_coord(lat, lon):
            self.marker.set_location(self.lat, self.lon)
            self.view.go_to(self.lat, self.lon)

    def show_contacts(self):
        data = {}
        accounts = app.contacts._accounts
        for account in accounts:
            if not app.account_is_connected(account):
                continue
            for contact in accounts[account].contacts._contacts:
                pep = accounts[account].contacts._contacts[contact][0].pep
                if 'location' not in pep:
                    continue
                lat = pep['location'].data.get('lat', None)
                lon = pep['location'].data.get('lon', None)
                if not lat or not lon:
                    continue
                name = accounts[account].contacts.get_first_contact_from_jid(
                    contact).get_shown_name()
                data[contact] = (lat, lon, name)

        self.contacts_layer = Champlain.MarkerLayer()
        for jid in data:
            path = self.get_path_to_generic_or_avatar(self.path_to_image,
                jid=jid, suffix='')
            texture = Clutter.Texture()
            texture.set_from_file(path)
            texture.set_size(32,32)
            marker = Champlain.Label.new_with_image(texture)
            marker.set_text(data[jid][2])
            marker.set_location(float(data[jid][0]), float(data[jid][1]))
            self.contacts_layer.add_marker(marker)

        self.view.add_layer(self.contacts_layer)
        self.contacts_layer.animate_in_all_markers()
        self.markers_is_visible = True

    def get_path_to_generic_or_avatar(self, generic, jid=None, suffix=None):
        """
        Choose between avatar image and default image

        Returns full path to the avatar image if it exists, otherwise returns full
        path to the image.  generic must be with extension and suffix without
        """
        if jid:
            # we want an avatar
            puny_jid = helpers.sanitize_filename(jid)
            path_to_file = os.path.join(
                configpaths.get('AVATAR'), puny_jid) + suffix
            path_to_local_file = path_to_file + '_local'
            for extension in ('.png', '.jpeg'):
                path_to_local_file_full = path_to_local_file + extension
                if os.path.exists(path_to_local_file_full):
                    return path_to_local_file_full
            for extension in ('.png', '.jpeg'):
                path_to_file_full = path_to_file + extension
                if os.path.exists(path_to_file_full):
                    return path_to_file_full
        return os.path.abspath(generic)

    def on_preset_button_clicked(self, widget):
        def on_ok(preset_name):
            if preset_name == '':
                return
            preset = {}
            for name in self.plugin.config_default_values:
                if name == 'presets':
                    continue
                widget = self.xml.get_object(name)
                preset[name] = widget.get_text()
            preset = {preset_name: preset}
            presets = dict(list(self.plugin.config['presets'].items()) + \
                list(preset.items()))
            if preset_name not in list(self.plugin.config['presets'].keys()):
                iter_ = self.preset_liststore.append((preset_name,))
            self.plugin.config['presets'] = presets
        self.set_modal(False)
        InputDialog(_('Save as Preset'),
                    _('Please type a name for this preset'),
                    'default', is_modal=True, ok_handler=on_ok)

    def on_preset_combobox_changed(self, widget):
        model = widget.get_model()
        active = widget.get_active()
        if active < 0:
            self.xml.get_object('del_preset').set_sensitive(False)
            return
        pres_name = model[active][0]
        for name in list(self.plugin.config['presets'][pres_name].keys()):
            widget = self.xml.get_object(name)
            widget.set_text(str(self.plugin.config['presets'][pres_name][name]))

        self.xml.get_object('del_preset').set_sensitive(True)

    def on_del_preset_clicked(self, widget):
        active = self.preset_combo.get_active()
        active_iter = self.preset_combo.get_active_iter()
        name = self.preset_liststore[active][0]
        presets = self.plugin.config['presets']
        del presets[name]
        self.plugin.config['presets'] = presets
        self.preset_liststore.remove(active_iter)
