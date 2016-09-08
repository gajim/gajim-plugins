# -*- coding: utf-8 -*-
##

from datetime import datetime
import time
import gtk
import os
import gobject
import urllib2
import logging

from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log, log_calls
from common import gajim
from common import ged
from common import helpers
from common import configpaths
from conversation_textview import TextViewImage
import gtkgui_helpers
from dialogs import InputDialog, WarningDialog


log = logging.getLogger('gajim.plugin_system.set_location')


class SetLocationPlugin(GajimPlugin):
    @log_calls('SetLocationPlugin')
    def init(self):
        self.config_dialog = SetLocationPluginConfigDialog(self)
        self.gui_extension_points = {
            'print_special_text': (self.print_special_text, None)}
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

        self.thumbpath = os.path.join(configpaths.gajimpaths['MY_CACHE'],
                                      'downloads.thumb')
        self.create_path(self.thumbpath)

    @log_calls('SetLocationPlugin')
    def activate(self):
        gajim.ged.register_event_handler('signed-in', ged.POSTGUI,
                                         self.on_signed_in)
        self.send_locations()

    @log_calls('SetLocationPlugin')
    def deactivate(self):
        self._data = {}
        for acct in gajim.connections:
            gajim.connections[acct].send_location(self._data)
        gajim.ged.remove_event_handler('signed-in', ged.POSTGUI,
                                       self.on_signed_in)

    def on_signed_in(self, network_event):
        self.send_locations(network_event.conn.name)

    def print_special_text(self, tv, special_text, other_tags, graphics=True,
                           iter_=None):
        conv_textview = tv
        textview = tv.tv
        # geo:48.2057365,16.3435941
        if not special_text.startswith('geo:'):
            return

        buffer_ = textview.get_buffer()
        if not iter_:
            iter_ = buffer_.get_end_iter()

        # Show URL, until image is loaded (if ever)
        ttt = buffer_.get_tag_table()
        repl_start = buffer_.create_mark(None, iter_, True)
        buffer_.insert_with_tags(iter_, special_text,
            *[(ttt.lookup(t) if isinstance(t, str) else t) for t in ["url"]])
        repl_end = buffer_.create_mark(None, iter_, True)

        zoom = 17
        size = 200
        color = 'blue'

        coordinates = special_text.split(':')[1]

        lat = coordinates.split(',')[0]
        lon = coordinates.split(',')[1]

        if not (len(lat) == 10 and len(lon) == 10):
            return

        filename = coordinates.replace(',', '_').replace('.', '-')
        filepath = os.path.join(self.thumbpath, filename)

        url = 'https://maps.googleapis.com/maps/api/staticmap?center={}' \
              '&zoom={}&size={}x{}&markers=color:{}' \
              '|label:S|{}'.format(coordinates, zoom, size, size,
                                   color, coordinates)

        weburl = 'https://www.google.at/maps/place/{}'.format(coordinates)

        log.debug(url)

        if os.path.exists(filepath):
            gajim.thread_interface(
                self.load_thumbnail, [filepath],
                self.updatechat, [weburl, repl_start, repl_end, textview])
        else:
            gajim.thread_interface(
                self.download, [url, filepath],
                self.updatechat, [weburl, repl_start, repl_end, textview])

        # Don't print the URL in the message window (in the calling function)
        conv_textview.plugin_modified = True

    def updatechat(self, data, weburl, repl_start, repl_end, textview):
        if data:
            try:
                log.debug(weburl)
                eb = gtk.EventBox()
                eb.connect('button-press-event', self.on_button_press_event,
                           weburl)
                eb.connect('enter-notify-event', self.on_enter_event,
                           textview)
                eb.connect('leave-notify-event', self.on_leave_event,
                           textview)

                # this is threadsafe
                # (gtk textview is NOT threadsafe by itself!!)
                def add_to_textview():
                    try:        # textview closed in the meantime etc.
                        buffer_ = repl_start.get_buffer()
                        iter_ = buffer_.get_iter_at_mark(repl_start)
                        buffer_.insert(iter_, "\n")
                        anchor = buffer_.create_child_anchor(iter_)
                        # Use weburl as tooltip for image
                        img = TextViewImage(anchor, weburl)

                        loader = gtk.gdk.PixbufLoader()
                        loader.write(data)
                        loader.close()
                        pixbuf = loader.get_pixbuf()
                        img.set_from_pixbuf(pixbuf)

                        eb.add(img)
                        eb.show_all()
                        textview.add_child_at_anchor(eb, anchor)
                        buffer_.delete(iter_,
                                       buffer_.get_iter_at_mark(repl_end))
                    except:
                        pass
                    return False
                # add to mainloop --> make call threadsafe
                gobject.idle_add(add_to_textview)
            except Exception:
                # URL is already displayed
                log.error('Could not display image for URL: %s'
                          % weburl)
                raise
        else:
            # If image could not be downloaded, URL is already displayed
            log.error('Could not download image for URL: %s -- %s'
                      % weburl)

    def download(self, url, filepath):
        """
        Download a file. This function should
        be launched in a separated thread.
        """
        log.debug('Getting map thumbnail ..')
        try:
            req = urllib2.Request(url)
            req.add_header('User-Agent', 'Gajim')
            f = urllib2.urlopen(req)
        except Exception as ex:
            log.debug('Error loading file %s '
                      % str(ex))
        else:
            try:
                temp = f.read()
                with open(filepath, "wb") as local_file:
                    local_file.write(temp)
                    local_file.closed
                log.debug('Saved map thumbnail ..')
            except Exception as ex:
                log.exception('Error: ')
            if temp:
                return temp

    def load_thumbnail(self, filepath):
        with open(filepath, 'rb') as f:
            data = f.read()
            f.closed
        log.debug('Load map thumbnail')
        return data

    def create_path(self, folder):
        if os.path.exists(folder):
            return
        log.debug("creating folder '%s'" % folder)
        os.mkdir(folder, 0o700)

    def send_locations(self, acct=False):
        self._data = {}
        timestamp = time.time()
        timestamp = datetime.utcfromtimestamp(timestamp)
        timestamp = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
        self._data['timestamp'] = timestamp
        for name in self.config_default_values:
            self._data[name] = self.config[name]

        if not acct:
            # set geo for all accounts
            for acct in gajim.connections:
                if gajim.config.get_per('accounts', acct, 'publish_location'):
                    gajim.connections[acct].send_location(self._data)
        elif gajim.config.get_per('accounts', acct, 'publish_location'):
            gajim.connections[acct].send_location(self._data)

    # Change mouse pointer to HAND2 when
    # mouse enter the eventbox with the image
    def on_enter_event(self, eb, event, tv):
        tv.get_window(
            gtk.TEXT_WINDOW_TEXT).set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))

    # Change mouse pointer to default when mouse leaves the eventbox
    def on_leave_event(self, eb, event, tv):
        tv.get_window(
            gtk.TEXT_WINDOW_TEXT).set_cursor(gtk.gdk.Cursor(gtk.gdk.XTERM))

    def on_button_press_event(self, eb, event, url):
        # left click
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 1:
            helpers.launch_browser_mailer('url', url)


class SetLocationPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                                       ['hbox1', 'image1', 'image2'])
        hbox = self.xml.get_object('hbox1')
        self.child.pack_start(hbox)
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)
        self.is_active = None

        self.preset_combo = self.xml.get_object('preset_combobox')
        self.preset_liststore = gtk.ListStore(str)
        self.preset_combo.set_model(self.preset_liststore)
        cellrenderer = gtk.CellRendererText()
        self.preset_combo.pack_start(cellrenderer, True)
        self.preset_combo.add_attribute(cellrenderer, 'text', 0)
        # self.plugin.config['presets'] = {'default': {}}

    @log_calls('SetLocationPlugin.SetLocationPluginConfigDialog')
    def on_run(self):
        no_map = None
        if not self.is_active:
            pres_keys = sorted(self.plugin.config['presets'].keys())
            for key in pres_keys:
                self.preset_liststore.append((key,))

        for name in self.plugin.config_default_values:
            if name == 'presets':
                continue
            widget = self.xml.get_object(name)
            widget.set_text(str(self.plugin.config[name]))

        try:
            import osmgpsmap
            if osmgpsmap.__version__ < '0.6':
                no_map = True
                log.debug('python-osmgpsmap < 0.6 detected')
        except:
            no_map = True
            log.debug('python-osmgpsmap not detected')

        log.debug('python-osmgpsmap > 0.5 detected')
        if not no_map and not self.is_active:
            from layers import DummyLayer

            vbox = self.xml.get_object('vbox1')
            vbox.set_size_request(400, -1)

            self.osm = osmgpsmap.GpsMap()
            self.osm.layer_add(osmgpsmap.GpsMapOsd(show_dpad=True,
                                                   show_zoom=True))
            self.osm.layer_add(DummyLayer())
            lat = self.plugin.config['lat']
            lon = self.plugin.config['lon']
            if not self.is_valid_coord(lat, lon):
                self.lat = self.lon = 0.0
                self.xml.get_object('lat').set_text('0.0')
                self.xml.get_object('lon').set_text('0.0')
            self.osm.set_center_and_zoom(self.lat, self.lon, 12)
            self.path_to_image = os.path.abspath(gtkgui_helpers.get_icon_path(
                'gajim', 16))
            self.icon = gtk.gdk.pixbuf_new_from_file_at_size(
                self.path_to_image, 16, 16)
            self.osm.connect('button_release_event', self.map_clicked)
            vbox.pack_start(self.osm, expand=True, fill=True, padding=6)
            label = gtk.Label(
                _('Click the right mouse button to specify the location, \n'
                  'middle mouse button to show / '
                  'hide the contacts on the map'))
            vbox.pack_start(label, expand=False, fill=False, padding=6)
            self.is_active = True
            self.images = []
            self.osm_image = self.osm.image_add(self.lat, self.lon, self.icon)
            self.xml.get_object('lat').connect('changed', self.on_lon_changed)
            self.xml.get_object('lon').connect('changed', self.on_lon_changed)

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
            error_text = 'lat or lon field contains wrong value.'
            WarningDialog(_('Wrong coordinates'), error_text, self)

    def map_clicked(self, osm, event):
        lat, lon = self.osm.get_event_location(event).get_degrees()
        if event.button == 3:
            self.osm.image_remove(self.osm_image)
            self.osm_image = self.osm.image_add(lat, lon, self.icon)
            self.xml.get_object('lat').set_text(str(lat))
            self.xml.get_object('lon').set_text(str(lon))
        if event.button == 2:
            self.show_contacts()

    def is_valid_coord(self, lat, lon):
        try:
            self.lat = float(lat)
            self.lon = float(lon)
        except ValueError:
            return
        if not -85 < self.lat < 85 or not -180 < self.lon < 180:
            return
        return True

    def on_lon_changed(self, widget):
        lat = self.xml.get_object('lat').get_text()
        lon = self.xml.get_object('lon').get_text()
        if self.is_valid_coord(lat, lon):
            self.osm.image_remove(self.osm_image)
            self.osm_image = self.osm.image_add(self.lat, self.lon, self.icon)
            self.osm.set_center(self.lat, self.lon)

    def show_contacts(self):
        if not self.images:
            data = {}
            accounts = gajim.contacts._accounts
            for account in accounts:
                if not gajim.account_is_connected(account):
                    continue
                for contact in accounts[account].contacts._contacts:
                    pep = accounts[account].contacts._contacts[contact][0].pep
                    if 'location' not in pep:
                        continue
                    lat = pep['location']._pep_specific_data.get('lat', None)
                    lon = pep['location']._pep_specific_data.get('lon', None)
                    if not lat or not lon:
                        continue
                    data[contact] = (lat, lon)
            for jid in data:
                path = gtkgui_helpers.get_path_to_generic_or_avatar(
                    None, jid=jid, suffix='')
                icon = gtk.gdk.pixbuf_new_from_file_at_size(path, 24, 24)
                image = self.osm.image_add(float(data[jid][0]),
                                           float(data[jid][1]), icon)
                self.images.append(image)
        else:
            for image in self.images:
                self.osm.image_remove(image)
            self.images = []

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
            presets = dict(self.plugin.config['presets'].items() +
                           preset.items())
            if preset_name not in self.plugin.config['presets'].keys():
                iter_ = self.preset_liststore.append((preset_name,))
            self.plugin.config['presets'] = presets
        self.set_modal(False)
        InputDialog(
            _('Save as Preset'),
            _('Please type a name for this preset'),
            is_modal=True, ok_handler=on_ok)

    def on_preset_combobox_changed(self, widget):
        model = widget.get_model()
        active = widget.get_active()
        if active < 0:
            self.xml.get_object('del_preset').set_sensitive(False)
            return
        pres_name = model[active][0].decode('utf-8')
        for name in self.plugin.config['presets'][pres_name].keys():
            widget = self.xml.get_object(name)
            widget.set_text(
                str(self.plugin.config['presets'][pres_name][name]))

        self.xml.get_object('del_preset').set_sensitive(True)

    def on_del_preset_clicked(self, widget):
        active = self.preset_combo.get_active()
        active_iter = self.preset_combo.get_active_iter()
        name = self.preset_liststore[active][0].decode('utf-8')
        presets = self.plugin.config['presets']
        del presets[name]
        self.plugin.config['presets'] = presets
        self.preset_liststore.remove(active_iter)
