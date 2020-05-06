import os
import time
import logging
from datetime import datetime
from pathlib import Path
from functools import partial

import gi
from gi.repository import Gdk
from gi.repository import Gtk

from nbxmpp.structs import LocationData

from gajim.common import app
from gajim.common import ged
from gajim.common import configpaths
from gajim.common.helpers import sanitize_filename

from gajim.gtk.dialogs import DialogButton
from gajim.gtk.dialogs import InputDialog
from gajim.gtk.dialogs import WarningDialog

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _

log = logging.getLogger('gajim.p.set_location')

CHAMPLAIN_AVAILABLE = False
try:
    gi.require_version('Clutter', '1.0')
    gi.require_version('GtkClutter', '1.0')
    gi.require_version('Champlain', '0.12')
    gi.require_version('GtkChamplain', '0.12')
    from gi.repository import Clutter
    from gi.repository import GtkClutter
    GtkClutter.init([])  # Must be initialized before importing those:
    from gi.repository import Champlain
    from gi.repository import GtkChamplain
    CHAMPLAIN_AVAILABLE = True
except Exception:
    log.info('To view the map, you have to install all dependencies')


class SetLocationPlugin(GajimPlugin):
    def init(self):
        self.description = _(
            'Set information about your current geographical '
            'or physical location. \nTo be able to set your location on the '
            'built-in map, you need to have gir1.2-gtkchamplain and '
            'gir1.2-gtkclutter-1.0 installed')
        self.config_dialog = partial(SetLocationConfigDialog, self)
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
            'uri': ('', ''),
            'presets': ({'default': {}}, ''), }

    def activate(self):
        app.ged.register_event_handler('signed-in',
                                       ged.POSTGUI,
                                       self.on_signed_in)
        self.send_locations()

    def deactivate(self):
        for acct in app.connections:
            app.connections[acct].get_module('UserLocation').set_location(None)
        app.ged.remove_event_handler('signed-in',
                                     ged.POSTGUI,
                                     self.on_signed_in)

    def on_signed_in(self, event):
        self.send_locations(account=event.account)

    def send_locations(self, account=None):
        data = {}
        timestamp = time.time()
        timestamp = datetime.utcfromtimestamp(timestamp)
        timestamp = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
        data['timestamp'] = timestamp
        for name in self.config_default_values:
            if name == 'presets':
                continue
            data[name] = self.config[name]

        if account is None:
            # Set geo for all accounts
            for acct in app.connections:
                if app.config.get_per('accounts', acct, 'publish_location'):
                    app.connections[acct].get_module('UserLocation').set_location(
                        LocationData(**data))

        elif app.config.get_per('accounts', account, 'publish_location'):
            app.connections[account].get_module('UserLocation').set_location(
                LocationData(**data))


class SetLocationConfigDialog(Gtk.ApplicationWindow):
    def __init__(self, plugin, transient):
        Gtk.ApplicationWindow.__init__(self)
        self.set_application(app.app)
        self.set_show_menubar(False)
        self.set_title(_('Set Location Configuration'))
        self.set_transient_for(transient)
        self.set_default_size(400, 600)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_modal(True)
        self.set_destroy_with_parent(True)

        self._plugin = plugin

        ui_path = Path(__file__).parent
        self._ui = get_builder(ui_path.resolve() / 'config_dialog.ui')
        self._ui.set_translation_domain('gajim_plugins')
        self.add(self._ui.config_box)
        self.show_all()

        self._ui.connect_signals(self)
        self.connect('hide', self._on_hide)
        self.connect('show', self._on_show)

        self.is_active = None
        self._initialize()

    def _initialize(self):
        self._preset_liststore = Gtk.ListStore(str)
        self._ui.preset_combobox.set_model(self._preset_liststore)
        cellrenderer = Gtk.CellRendererText()
        self._ui.preset_combobox.pack_start(cellrenderer, True)
        self._ui.preset_combobox.add_attribute(cellrenderer, 'text', 0)


        if not self.is_active:
            pres_keys = sorted(self._plugin.config['presets'].keys())
            for key in pres_keys:
                self._preset_liststore.append((key,))
        self._ui.preset_combobox.set_active(0)

        for name in self._plugin.config_default_values:
            if name == 'presets':
                continue
            widget = self._ui.get_object(name)
            widget.set_text(str(self._plugin.config[name]))

        if CHAMPLAIN_AVAILABLE and not self.is_active:
            self._ui.map_placeholder.set_no_show_all(True)
            self._ui.map_placeholder.hide()
            self._ui.dependency_warning.hide()
            self._ui.map_box.set_size_request(400, -1)

            embed = GtkChamplain.Embed()

            self.view = embed.get_view()
            self.view.set_reactive(True)
            self.view.set_property('kinetic-mode', True)
            self.view.set_property('zoom-level', 12)
            self.view.connect('button-release-event', self._map_clicked,
                              self.view)

            scale = Champlain.Scale()
            scale.connect_view(self.view)
            self.view.add_child(scale)

            lat = self._plugin.config['lat']
            lon = self._plugin.config['lon']
            if not self._is_valid_coord(lat, lon):
                self.lat = self.lon = 0.0
                self._ui.lat.set_text('0.0')
                self._ui.lon.set_text('0.0')
            self.view.center_on(self.lat, self.lon)

            icon = 'org.gajim.Gajim.svg'
            icons_dir = Path(configpaths.get('ICONS')) / 'hicolor/scalable/apps'
            self.path_to_image = icons_dir / icon

            self._ui.map_box.pack_start(
                embed, expand=True, fill=True, padding=0)
            self._ui.map_box.show_all()

            self.is_active = True
            self.layer = Champlain.MarkerLayer()

            texture = Clutter.Texture()
            texture.set_from_file(str(self.path_to_image))
            texture.set_size(32, 32)
            self.marker = Champlain.Label.new_with_image(texture)
            self.marker.set_location(self.lat, self.lon)
            self.marker.set_text(_('Your location'))
            self.view.add_layer(self.layer)
            self.layer.add_marker(self.marker)
            self.markers_is_visible = False
            self._ui.lat.connect('changed', self._on_latlon_changed)
            self._ui.lon.connect('changed', self._on_latlon_changed)
            self.layer.animate_in_all_markers()
            self.contacts_layer = Champlain.MarkerLayer()

    def _on_show(self, _widget):
        if CHAMPLAIN_AVAILABLE:
            self.contacts_layer.remove_all()
            self.view.center_on(self.lat, self.lon)
            self._show_contacts()

    def _on_hide(self, widget):
        for name in self._plugin.config_default_values:
            if name in ['presets', 'lat', 'lon']:
                continue
            widget = self._ui.get_object(name)
            self._plugin.config[name] = widget.get_text()

        lat = self._ui.lat.get_text()
        lon = self._ui.lon.get_text()
        if self._is_valid_coord(lat, lon):
            self._plugin.config['lat'] = lat
            self._plugin.config['lon'] = lon
            if self._plugin.active:
                self._plugin.activate()
        else:
            self._plugin.config['lat'] = '0.0'
            self._plugin.config['lon'] = '0.0'
            error_text = _('Latitude or Longitude field contains an invalid '
                           'value')
            WarningDialog(_('Wrong coordinates'), error_text, self)

    def _map_clicked(self, _actor, event, view):
        x_coord, y_coord = event.x, event.y
        lat, lon = view.x_to_longitude(x_coord), view.y_to_latitude(y_coord)
        if event.button == 3:
            self.marker.set_location(lat, lon)
            self._ui.lon.set_text(str(lat))
            self._ui.lat.set_text(str(lon))
        if event.button == 2:
            if self.markers_is_visible:
                self.contacts_layer.animate_out_all_markers()
            else:
                self.contacts_layer.animate_in_all_markers()
            self.markers_is_visible = not self.markers_is_visible

    def _is_valid_coord(self, lat, lon):
        try:
            self.lat = float(lat)
            self.lon = float(lon)
        except ValueError:
            return
        if not -85 < self.lat < 85 or not -180 < self.lon < 180:
            return
        return True

    def _on_latlon_changed(self, _widget):
        lat = self._ui.lat.get_text()
        lon = self._ui.lon.get_text()
        if self._is_valid_coord(lat, lon):
            self.marker.set_location(self.lat, self.lon)
            self.view.go_to(self.lat, self.lon)

    def _show_contacts(self):
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
            path = self._get_path_to_generic_or_avatar(
                self.path_to_image, jid=jid, suffix='')
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

    @staticmethod
    def _get_path_to_generic_or_avatar(generic, jid=None, suffix=None):
        """
        Choose between avatar image and default image

        Returns full path to the avatar image if it exists, otherwise returns full
        path to the image.  generic must be with extension and suffix without
        """
        if jid:
            # we want an avatar
            puny_jid = sanitize_filename(jid)
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

    def _on_preset_button_clicked(self, _widget):
        def _on_save(preset_name):
            if preset_name == '':
                return
            preset = {}
            for name in self._plugin.config_default_values:
                if name == 'presets':
                    continue
                widget = self._ui.get_object(name)
                preset[name] = widget.get_text()
            preset = {preset_name: preset}
            presets = dict(list(
                self._plugin.config['presets'].items()) + list(preset.items()))
            if preset_name not in list(self._plugin.config['presets'].keys()):
                iter_ = self._preset_liststore.append((preset_name,))
                self._ui.preset_combobox.set_active_iter(iter_)
            self._plugin.config['presets'] = presets

        active_preset = self._ui.preset_combobox.get_active()
        current_preset = self._preset_liststore[active_preset][0]

        InputDialog(_('Save as Preset'),
                    _('Save as Preset'),
                    _('Please enter a name for this preset'),
                    [DialogButton.make('Cancel'),
                     DialogButton.make('Accept',
                                       text=_('Save'),
                                       callback=_on_save)],
                    input_str=current_preset).show()

    def _on_preset_combobox_changed(self, widget):
        active = widget.get_active_iter()
        if active is None:
            self._ui.del_preset.set_sensitive(False)
            return

        pres_name = self._preset_liststore[active][0]
        self._ui.del_preset.set_sensitive(pres_name != 'default')
        for name in list(self._plugin.config['presets'][pres_name].keys()):
            widget = self._ui.get_object(name)
            widget.set_text(str(self._plugin.config['presets'][pres_name][name]))

    def _on_del_preset_clicked(self, _widget):
        active = self._ui.preset_combobox.get_active()
        active_iter = self._ui.preset_combobox.get_active_iter()
        name = self._preset_liststore[active][0]
        if name == 'default':
            return
        presets = self._plugin.config['presets']
        del presets[name]
        self._plugin.config['presets'] = presets
        self._preset_liststore.remove(active_iter)
        self._ui.preset_combobox.set_active(0)
