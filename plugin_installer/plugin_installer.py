# -*- coding: utf-8 -*-
#
## plugins/plugin_installer/plugin_installer.py
##
## Copyright (C) 2010-2012 Denis Fomin <fominde AT gmail.com>
## Copyright (C) 2011-2012 Yann Leboulanger <asterix AT lagaule.org>
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim. If not, see <http://www.gnu.org/licenses/>.
##
from gi.repository import Gtk
from gi.repository import GdkPixbuf
from gi.repository import Pango
from gi.repository import GLib

import io
import threading
import configparser
import os
import ssl
import logging
import posixpath
import urllib.error

from zipfile import ZipFile
from distutils.version import LooseVersion as V
from urllib.request import urlopen
from common import gajim
from plugins import GajimPlugin
from htmltextview import HtmlTextView
from dialogs import WarningDialog, HigDialog, YesNoDialog
from plugins.gui import GajimPluginConfigDialog
from enum import IntEnum
from gtkgui_helpers import get_action

log = logging.getLogger('gajim.plugin_system.plugin_installer')

PLUGINS_URL = 'https://ftp.gajim.org/plugins_1/'
MANIFEST_URL = 'https://ftp.gajim.org/plugins_1/manifests.zip'
MANIFEST_IMAGE_URL = 'https://ftp.gajim.org/plugins_1/manifests_images.zip'
MANDATORY_FIELDS = ['name', 'version', 'description', 'authors', 'homepage']


class Column(IntEnum):
    PIXBUF = 0
    DIR = 1
    NAME = 2
    LOCAL_VERSION = 3
    VERSION = 4
    UPGRADE = 5
    DESCRIPTION = 6
    AUTHORS = 7
    HOMEPAGE = 8


def get_local_version(plugin_name):
    for plugin in gajim.plugin_manager.plugins:
        if plugin.name == plugin_name:
            return plugin.version


class PluginInstaller(GajimPlugin):
    def init(self):
        self.description = _('Install and Upgrade Plugins')
        self.config_dialog = PluginInstallerPluginConfigDialog(self)
        self.config_default_values = {'check_update': (True, '')}
        self.window = None
        self.progressbar = None
        self.available_plugins_model = None
        self.timeout_id = 0
        self.connected_ids = {}
        icon = Gtk.Image()
        self.def_icon = icon.render_icon(
            Gtk.STOCK_PREFERENCES, Gtk.IconSize.MENU)

    def activate(self):
        if self.config['check_update']:
            self.timeout_id = GLib.timeout_add_seconds(30, self.check_update)
        if 'plugins' in gajim.interface.instances:
            self.on_activate(gajim.interface.instances['plugins'])

    def warn_update(self, plugins):
        def open_update(dummy):
            get_action('plugins').activate()
            page = self.notebook.page_num(self.paned)
            self.notebook.set_current_page(page)
        if plugins:
            plugins_str = '\n' + '\n'.join(plugins)
            YesNoDialog(
                _('Plugins updates'),
                _('Some updates are available for your installer plugins. '
                  'Do you want to update those plugins:\n%s')
                % plugins_str, on_response_yes=open_update)
        else:
            log.info('No updates found')
            if hasattr(self, 'thread'):
                del self.thread

    def check_update(self):
        if hasattr(self, 'thread'):
            return
        log.info('Checking for Updates...')
        self.start_download(check_update=True)
        self.timeout_id = 0

    def deactivate(self):
        if hasattr(self, 'available_page'):
            self.notebook.remove_page(self.notebook.page_num(self.paned))
            self.notebook.set_current_page(0)
            for id_, widget in list(self.connected_ids.items()):
                widget.disconnect(id_)
            del self.available_page
        if hasattr(self, 'thread'):
            del self.thread
        if self.timeout_id > 0:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = 0

    def on_activate(self, plugin_win):
        if hasattr(self, 'available_page'):
            # 'Available' tab exists
            return
        if hasattr(self, 'thread'):
            del self.thread
        self.installed_plugins_model = plugin_win.installed_plugins_model
        self.notebook = plugin_win.plugins_notebook
        id_ = self.notebook.connect('switch-page', self.on_notebook_switch_page)
        self.connected_ids[id_] = self.notebook
        self.window = plugin_win.window
        id_ = self.window.connect('destroy', self.on_win_destroy)
        self.connected_ids[id_] = self.window
        self.Gtk_BUILDER_FILE_PATH = self.local_file_path('config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.Gtk_BUILDER_FILE_PATH,
                                       ['refresh', 'paned', 'plugin_store'])

        widgets_to_extract = (
            'name_label', 'available_treeview', 'progressbar', 'paned',
            'install_button', 'authors_label', 'homepage_linkbutton',
            'version_label', 'scrolled_description_window')

        for widget_name in widgets_to_extract:
            setattr(self, widget_name, self.xml.get_object(widget_name))

        # Make Link in LinkButton not centered
        style_provider = Gtk.CssProvider()
        css = '.link { padding-left: 0px; padding-right: 0px; }'
        style_provider.load_from_data(css.encode())
        context = self.homepage_linkbutton.get_style_context()
        context.add_provider(style_provider,
                             Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.available_page = self.notebook.append_page(
            self.paned, Gtk.Label.new(_('Available')))

        self.available_plugins_model = self.xml.get_object('plugin_store')
        self.available_plugins_model.set_sort_column_id(
            2, Gtk.SortType.ASCENDING)

        selection = self.available_treeview.get_selection()
        selection.connect(
            'changed', self.available_plugins_treeview_selection_changed)
        selection.set_mode(Gtk.SelectionMode.SINGLE)

        self.description_textview = HtmlTextView()
        self.description_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.scrolled_description_window.add(self.description_textview)

        self.xml.connect_signals(self)
        self.window.show_all()

    def on_win_destroy(self, widget):
        if hasattr(self, 'thread'):
            del self.thread
        if hasattr(self, 'available_page'):
            del self.available_page

    def available_plugins_toggled_cb(self, cell, path):
        is_active = self.available_plugins_model[path][Column.UPGRADE]
        self.available_plugins_model[path][Column.UPGRADE] = not is_active
        dir_list = []
        for i in range(len(self.available_plugins_model)):
            if self.available_plugins_model[i][Column.UPGRADE]:
                dir_list.append(self.available_plugins_model[i][Column.DIR])
        self.install_button.set_property('sensitive', bool(dir_list))

    def on_notebook_switch_page(self, widget, page, page_num):
        tab_label_text = self.notebook.get_tab_label_text(page)
        if tab_label_text != (_('Available')):
            return
        if not hasattr(self, 'thread'):
            self.available_plugins_model.clear()
            self.start_download(upgrading=True)

    def on_install_upgrade_clicked(self, widget):
        self.install_button.set_property('sensitive', False)
        dir_list = []
        for i in range(len(self.available_plugins_model)):
            if self.available_plugins_model[i][Column.UPGRADE]:
                dir_list.append(self.available_plugins_model[i][Column.DIR])

        self.start_download(remote_dirs=dir_list)

    def on_error(self, reason):
        if reason == 'CERTIFICATE_VERIFY_FAILED':
            YesNoDialog(
                _('Security error during download'),
                _('A security error occurred when '
                  'downloading. The certificate of the '
                  'plugin archive could not be verified. '
                  'this might be a security attack. '
                  '\n\nYou can continue at your risk. '
                  'Do you want to do so? '
                  '(not recommended)'
                  ),
                on_response_yes=lambda dlg:
                self.start_download(secure=False, upgrading=True))
        else:
            if self.available_plugins_model:
                for i in range(len(self.available_plugins_model)):
                    self.available_plugins_model[i][Column.UPGRADE] = False
                self.progressbar.hide()
            text = GLib.markup_escape_text(reason)
            WarningDialog(_('Error in download'),
                          _('An error occurred when downloading\n\n'
                          '<tt>[%s]</tt>' % (str(text))), self.window)

    def start_download(self, secure=True, remote_dirs=False,
                       upgrading=False, check_update=False):
        log.info('Start Download...')
        log.debug(
            'secure: %s, remote_dirs: %s, upgrading: %s, check_update: %s',
            secure, remote_dirs, upgrading, check_update)
        self.thread = DownloadAsync(
            self, secure=secure, remote_dirs=remote_dirs,
            upgrading=upgrading, check_update=check_update)
        self.thread.start()

    def on_plugin_downloaded(self, plugin_dirs):
        for _dir in plugin_dirs:
            is_active = False
            plugins = None
            plugin_dir = os.path.join(gajim.PLUGINS_DIRS[1], _dir)
            plugin = gajim.plugin_manager.get_plugin_by_path(plugin_dir)
            if plugin:
                if plugin.active:
                    is_active = True
                    log.info('Deactivate Plugin: %s', plugin)
                    gajim.plugin_manager.deactivate_plugin(plugin)
                gajim.plugin_manager.plugins.remove(plugin)

                model = self.installed_plugins_model
                for row in range(len(model)):
                    if plugin == model[row][0]:
                        model.remove(model.get_iter((row, 0)))
                        break

            log.info('Load Plugin from: %s', plugin_dir)
            plugins = gajim.plugin_manager.scan_dir_for_plugins(
                plugin_dir, package=True)
            if not plugins:
                log.warn('Loading Plugin failed')
                continue
            gajim.plugin_manager.add_plugin(plugins[0])
            plugin = gajim.plugin_manager.plugins[-1]
            log.info('Loading successful')
            for row in range(len(self.available_plugins_model)):
                model_row = self.available_plugins_model[row]
                if plugin.name == model_row[Column.NAME]:
                    model_row[Column.LOCAL_VERSION] = plugin.version
                    model_row[Column.UPGRADE] = False
            if is_active:
                log.info('Activate Plugin: %s', plugin)
                gajim.plugin_manager.activate_plugin(plugin)
            # get plugin icon
            icon_file = os.path.join(plugin.__path__, os.path.split(
                plugin.__path__)[1]) + '.png'
            icon = self.def_icon
            if os.path.isfile(icon_file):
                icon = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_file, 16, 16)
            row = [plugin, plugin.name, is_active, plugin.activatable, icon]
            self.installed_plugins_model.append(row)

        dialog = HigDialog(
            self.window, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
            '', _('All selected plugins downloaded'))
        dialog.set_modal(False)
        dialog.popup()

    def available_plugins_treeview_selection_changed(self, treeview_selection):
        model, iter = treeview_selection.get_selected()
        self.description_textview.get_buffer().set_text('')
        self.name_label.set_text(model.get_value(iter, Column.NAME))
        self.version_label.set_text(model.get_value(iter, Column.VERSION))
        self.authors_label.set_text(model.get_value(iter, Column.AUTHORS))
        self.homepage_linkbutton.set_uri(
            model.get_value(iter, Column.HOMEPAGE))
        self.homepage_linkbutton.set_label(
            model.get_value(iter, Column.HOMEPAGE))
        link_label = self.homepage_linkbutton.get_children()[0]
        link_label.set_ellipsize(Pango.EllipsizeMode.END)
        desc = _(model.get_value(iter, Column.DESCRIPTION))
        if not desc.startswith('<body '):
            desc = ('<body xmlns=\'http://www.w3.org/1999/xhtml\'>'
                    '%s</body>') % desc
            desc = desc.replace('\n', '<br/>')
        self.description_textview.display_html(
            desc, self.description_textview, None)

    def select_root_iter(self):
        selection = self.available_treeview.get_selection()
        if selection.count_selected_rows() == 0:
            root_iter = self.available_plugins_model.get_iter_first()
            path = self.available_plugins_model.get_path(root_iter)
            selection.select_iter(root_iter)
        self.name_label.show()
        self.homepage_linkbutton.show()
        self.available_treeview.scroll_to_cell(path)


class DownloadAsync(threading.Thread):
    def __init__(self, plugin, secure, remote_dirs, upgrading, check_update):
        threading.Thread.__init__(self)
        self.plugin = plugin
        self.window = plugin.window
        self.progressbar = plugin.progressbar
        self.model = plugin.available_plugins_model
        self.remote_dirs = remote_dirs
        self.upgrading = upgrading
        self.secure = secure
        self.check_update = check_update
        self.pulse = None
        icon = Gtk.Image()
        self.def_icon = icon.render_icon(
            Gtk.STOCK_PREFERENCES, Gtk.IconSize.MENU)

    def model_append(self, row):
        row_data = [
            row['icon'], row['remote_dir'], row['name'], row['local_version'],
            row['version'], row['upgrade'], row['description'], row['authors'],
            row['homepage']
            ]
        self.model.append(row_data)
        return False

    def progressbar_pulse(self):
        self.progressbar.pulse()
        return True

    def run(self):
        try:
            if self.check_update:
                self.run_check_update()
            else:
                GLib.idle_add(self.progressbar.show)
                self.pulse = GLib.timeout_add(150, self.progressbar_pulse)
                self.run_download_plugin_list()
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLError):
                ssl_reason = exc.reason.reason
                if ssl_reason == 'CERTIFICATE_VERIFY_FAILED':
                    log.exception('Certificate verify failed')
                    GLib.idle_add(self.plugin.on_error, ssl_reason)
        except Exception as exc:
            GLib.idle_add(self.plugin.on_error, str(exc))
            log.exception('Error fetching plugin list')
        finally:
            if self.pulse:
                GLib.source_remove(self.pulse)
                GLib.idle_add(self.progressbar.hide)
                self.pulse = None

    def parse_manifest(self, buf):
        '''
        given the buffer of the zipfile, returns the list of plugin manifests
        '''
        zip_file = ZipFile(buf)
        manifest_list = zip_file.namelist()
        plugins = []
        for filename in manifest_list:
            # Parse manifest
            if not filename.endswith('manifest.ini'):
                continue
            config = configparser.ConfigParser()
            conf_file = zip_file.open(filename)
            config.read_file(io.TextIOWrapper(conf_file, encoding='utf-8'))
            conf_file.close()
            if not config.has_section('info'):
                log.warn('Plugin is missing INFO section in manifest.ini. '
                         'Plugin not loaded.')
                continue
            opts = config.options('info')
            if not set(MANDATORY_FIELDS).issubset(opts):
                log.warn('Plugin is missing mandatory fields in manifest.ini. '
                         'Plugin not loaded.')
                continue
            # Add icon and remote dir
            icon = None
            remote_dir = filename.split('/')[0]
            png_filename = '{0}/{0}.png'.format(remote_dir)
            icon = self.def_icon
            if png_filename in manifest_list:
                data = zip_file.open(png_filename).read()
                pix = GdkPixbuf.PixbufLoader()
                pix.set_size(16, 16)
                pix.write(data)
                pix.close()
                icon = pix.get_pixbuf()

            # transform to dictonary
            config_dict = {}
            for key, value in config.items('info'):
                config_dict[key] = value
            config_dict['icon'] = icon
            config_dict['remote_dir'] = remote_dir
            config_dict['upgrade'] = False

            plugins.append(config_dict)
        return plugins

    def download_url(self, url):
        log.info('Fetching %s', url)
        ssl_args = {}
        if self.secure:
            ssl_args['context'] = ssl.create_default_context(
                cafile=self.plugin.local_file_path('DST_Root_CA_X3.pem'))
        else:
            ssl_args['context'] = ssl.create_default_context()
            ssl_args['context'].check_hostname = False
            ssl_args['context'].verify_mode = ssl.CERT_NONE

        for flag in ('OP_NO_SSLv2', 'OP_NO_SSLv3',
                     'OP_NO_TLSv1', 'OP_NO_TLSv1_1',
                     'OP_NO_COMPRESSION',
                     ):
            log.debug('SSL Options: +%s' % flag)
            ssl_args['context'].options |= getattr(ssl, flag)
        request = urlopen(url, **ssl_args)

        return io.BytesIO(request.read())

    def run_check_update(self):
        to_update = []
        zipbuf = self.download_url(MANIFEST_URL)
        plugin_list = self.parse_manifest(zipbuf)
        for plugin in plugin_list:
            local_version = get_local_version(plugin['name'])
            if local_version:
                if V(plugin['version']) > V(local_version):
                    to_update.append(plugin['name'])
        GLib.idle_add(self.plugin.warn_update, to_update)

    def run_download_plugin_list(self):
        if not self.remote_dirs:
            log.info('Downloading Pluginlist...')
            zipbuf = self.download_url(MANIFEST_IMAGE_URL)
            plugin_list = self.parse_manifest(zipbuf)
            for plugin in plugin_list:
                plugin['local_version'] = get_local_version(plugin['name'])
                if self.upgrading and plugin['local_version']:
                    if V(plugin['version']) > V(plugin['local_version']):
                        plugin['upgrade'] = True
                        GLib.idle_add(
                            self.plugin.install_button.set_property,
                            'sensitive', True)
                GLib.idle_add(self.model_append, plugin)
            GLib.idle_add(self.plugin.select_root_iter)
        else:
            self.download_plugin()

    def download_plugin(self):
        for remote_dir in self.remote_dirs:
            filename = remote_dir + '.zip'
            log.info('Download: %s', filename)
            base_dir, user_dir = gajim.PLUGINS_DIRS
            if not os.path.isdir(user_dir):
                os.mkdir(user_dir)
            local_dir = os.path.join(user_dir, remote_dir)
            if not os.path.isdir(local_dir):
                os.mkdir(local_dir)
            local_dir = os.path.split(user_dir)[0]

            # downloading zip file
            try:
                plugin = posixpath.join(PLUGINS_URL, filename)
                buf = self.download_url(plugin)
            except:
                log.exception("Error downloading plugin %s" % filename)
                continue
            with ZipFile(buf) as zip_file:
                zip_file.extractall(os.path.join(local_dir, 'plugins'))
        GLib.idle_add(self.plugin.on_plugin_downloaded, self.remote_dirs)


class PluginInstallerPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        glade_file_path = self.plugin.local_file_path('config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(glade_file_path, ['config_grid'])
        grid = self.xml.get_object('config_grid')
        self.get_child().pack_start(grid, True, True, 0)

        self.xml.connect_signals(self)

    def on_run(self):
        self.xml.get_object('check_update').set_active(
            self.plugin.config['check_update'])

    def on_check_update_toggled(self, widget):
        self.plugin.config['check_update'] = widget.get_active()
