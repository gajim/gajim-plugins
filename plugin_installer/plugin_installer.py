# -*- coding: utf-8 -*-
#
## plugins/plugin_installer/plugin_installer.py
##
## Copyright (C) 2010-2012 Denis Fomin <fominde AT gmail.com>
## Copyright (C) 2011-2012 Yann Leboulanger <asterix AT lagaule.org>
## Copyright (C) 2017      Philipp Hörist <philipp AT hoerist.com>
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

import io
import threading
import configparser
import os
import ssl
import logging
import posixpath
from enum import IntEnum
from zipfile import ZipFile
from distutils.version import LooseVersion as V
import urllib.error
from urllib.request import urlopen

from gi.repository import Gtk
from gi.repository import GdkPixbuf
from gi.repository import GLib

from gajim.common import app
from gajim.common import configpaths
from gajim.plugins import GajimPlugin
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.plugins_i18n import _
from gajim.plugins.helpers import get_builder
from gajim.gtk.dialogs import WarningDialog
from gajim.gtk.dialogs import HigDialog
from gajim.gtk.dialogs import YesNoDialog
from gajim.gtk.dialogs import ConfirmationDialogCheck
from gajim.gtkgui_helpers import get_action

log = logging.getLogger('gajim.plugin_system.plugin_installer')

PLUGINS_URL = 'https://ftp.gajim.org/plugins_1.1_zip/'
MANIFEST_URL = 'https://ftp.gajim.org/plugins_1.1_zip/manifests.zip'
MANIFEST_IMAGE_URL = 'https://ftp.gajim.org/plugins_1.1_zip/manifests_images.zip'
MANDATORY_FIELDS = ['name', 'version', 'description', 'authors', 'homepage']
FALLBACK_ICON = Gtk.IconTheme.get_default().load_icon(
    'preferences-system', Gtk.IconSize.MENU, 0)


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


def get_local_version(plugin_manifest):
    name = plugin_manifest['name']
    short_name = plugin_manifest['short_name']

    for plugin in app.plugin_manager.plugins:
        if plugin.name == name:
            return plugin.version

    # Fallback:
    # If the plugin has errors and is not loaded by the
    # PluginManager. Look in the Gajim config if the plugin is
    # known and active, if yes load the manifest from the Plugin
    # dir and parse the version
    active = app.config.get_per('plugins', short_name, 'active')
    if not active:
        return
    manifest_path = os.path.join(
        configpaths.get('PLUGINS_USER'), short_name, 'manifest.ini')
    if not os.path.exists(manifest_path):
        return
    conf = configparser.ConfigParser()
    with open(manifest_path, encoding='utf-8') as conf_file:
        try:
            conf.read_file(conf_file)
        except configparser.Error:
            log.warning('Cant parse version for %s from manifest',
                        short_name)
            return

    version = conf.get('info', 'version', fallback=None)
    return version


class PluginInstaller(GajimPlugin):
    def init(self):
        self.description = _('Install and Upgrade Plugins')
        self.config_dialog = PluginInstallerPluginConfigDialog(self)
        self.config_default_values = {'check_update': (True, ''),
                                      'auto_update': (False, ''),
                                      'auto_update_feedback': (True, '')}
        self.gui_extension_points = {'plugin_window': (self.on_activate, None)}
        self.window = None
        self.progressbar = None
        self.available_plugins_model = None
        self.timeout_id = 0
        self.connected_ids = {}

    def activate(self):
        if self.config['check_update']:
            self.timeout_id = GLib.timeout_add_seconds(30, self.check_update)
        if 'plugins' in app.interface.instances:
            self.on_activate(app.interface.instances['plugins'])

    def warn_update(self, plugins):
        def open_update(checked):
            if checked:
                self.config['auto_update'] = True
            get_action('plugins').activate()
            page = self.notebook.page_num(self.available_plugins_box)
            self.notebook.set_current_page(page)
        if plugins:
            plugins_str = '\n' + '\n'.join(plugins)
            YesNoDialog(
                _('Plugin updates'),
                _('There are updates available for plugins you have installed.\n'
                  'Do you want to update those plugins:\n%s') % plugins_str,
                checktext=_('Update plugins automatically next time'),
                on_response_yes=open_update)
        else:
            log.info('No updates found')
            if hasattr(self, 'thread'):
                del self.thread

    def check_update(self):
        if hasattr(self, 'thread'):
            return
        log.info('Checking for Updates...')
        auto_update = self.config['auto_update']
        self.start_download(check_update=True, auto_update=auto_update)
        self.timeout_id = 0

    def deactivate(self):
        if hasattr(self, 'available_page'):
            self.notebook.remove_page(self.notebook.page_num(self.available_plugins_box))
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
        path = self.local_file_path('installer.ui')
        self.xml = get_builder(
            path, widgets=['refresh', 'available_plugins_box', 'plugin_store'])

        widgets_to_extract = (
            'available_plugins_box', 'install_plugin_button', 'plugin_name_label',
            'plugin_version_label', 'plugin_authors_label', 'plugin_description',
            'plugin_homepage_linkbutton', 'progressbar', 'available_plugins_treeview',
            'available_text', 'available_text_label')

        for widget_name in widgets_to_extract:
            setattr(self, widget_name, self.xml.get_object(widget_name))

        self.available_page = self.notebook.append_page(
            self.available_plugins_box, Gtk.Label.new(_('Available')))

        self.available_plugins_model = self.xml.get_object('plugin_store')
        self.available_plugins_model.set_sort_column_id(
            2, Gtk.SortType.ASCENDING)

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
        self.install_plugin_button.set_property('sensitive', bool(dir_list))

    def on_notebook_switch_page(self, widget, page, page_num):
        tab_label_text = self.notebook.get_tab_label_text(page)
        if tab_label_text != (_('Available')):
            return
        if not hasattr(self, 'thread'):
            self.available_plugins_model.clear()
            self.start_download(upgrading=True)

    def on_install_upgrade_clicked(self, widget):
        self.install_plugin_button.set_property('sensitive', False)
        dir_list = []
        for i in range(len(self.available_plugins_model)):
            if self.available_plugins_model[i][Column.UPGRADE]:
                dir_list.append(self.available_plugins_model[i][Column.DIR])

        self.start_download(remote_dirs=dir_list, auto_update=False)

    def on_error(self, reason):
        if reason == 'CERTIFICATE_VERIFY_FAILED':
            YesNoDialog(
                _('Security error during download'),
                _('A security error occurred while '
                  'downloading. The certificate of the '
                  'plugin archive could not be verified. '
                  'This might be a security attack. '
                  '\n\nYou can continue at your own risk (not recommended). '
                  'Do you want to continue?'
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

    def start_download(self, secure=True, remote_dirs=False, upgrading=False,
                       check_update=False, auto_update=False):
        log.info('Start Download...')
        log.debug(
            'secure: %s, remote_dirs: %s, upgrading: %s, check_update: %s, auto_update: %s',
            secure, remote_dirs, upgrading, check_update, auto_update)
        self.thread = DownloadAsync(
            self, secure=secure, remote_dirs=remote_dirs, upgrading=upgrading,
            check_update=check_update, auto_update=auto_update)
        self.thread.start()

    def on_plugin_downloaded(self, plugin_dirs, auto_update):
        need_restart = False
        for _dir in plugin_dirs:
            updated = app.plugin_manager.update_plugins(replace=False, activate=True, plugin_name=_dir)
            if updated:
                if not auto_update:
                    plugin = app.plugin_manager.get_active_plugin(updated[0])
                    for row in range(len(self.available_plugins_model)):
                        model_row = self.available_plugins_model[row]
                        if plugin.name == model_row[Column.NAME]:
                            model_row[Column.LOCAL_VERSION] = plugin.version
                            model_row[Column.UPGRADE] = False
                            break
                if not auto_update:
                    # Get plugin icon
                    icon_file = os.path.join(plugin.__path__, os.path.split(
                        plugin.__path__)[1]) + '.png'
                    icon = FALLBACK_ICON
                    if os.path.isfile(icon_file):
                        icon = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_file, 16, 16)
                    row = [plugin, plugin.name, True, plugin.activatable, icon]
                    self.installed_plugins_model.append(row)
            else:
                need_restart = True

        if need_restart:
            txt = _('All plugins downloaded.\nThe updates will '
                    'be installed the next time Gajim is started.')
        else:
            txt = _('All selected plugins downloaded and activated')
        if not auto_update:
            dialog = HigDialog(
                self.window, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, '', txt)
            dialog.set_modal(False)
            dialog.popup()
        if auto_update and self.config['auto_update_feedback']:
            def on_ok(checked):
                if checked:
                    self.config['auto_update_feedback'] = False
            # Hide cancel button to mimic InfoDialogCheck
            ConfirmationDialogCheck(_('Plugins updated'),
                                    _('Plugin updates have successfully been downloaded.'
                                      'Updates will be installed on next Gajim restart.'),
                                    _('Do not show this message again'),
                                    on_response_ok=on_ok).get_widget_for_response(
                                        Gtk.ResponseType.CANCEL).hide()
        if auto_update and not self.config['auto_update_feedback']:
            log.info('Updates downloaded, will install on next restart')


    def available_plugins_treeview_selection_changed(self, treeview_selection):
        model, iter_ = treeview_selection.get_selected()
        if not iter_:
            self.plugin_name_label.set_text('')
            self.plugin_version_label.set_text('')
            self.plugin_authors_label.set_text('')
            self.plugin_homepage_linkbutton.set_text('')
            self.install_plugin_button.set_sensitive(False)
            return
        self.plugin_name_label.set_text(model.get_value(iter_, Column.NAME))
        self.plugin_version_label.set_text(model.get_value(iter_, Column.VERSION))
        self.plugin_authors_label.set_text(model.get_value(iter_, Column.AUTHORS))
        homepage = model.get_value(iter_, Column.HOMEPAGE)
        markup = '<a href="%s">%s</a>' % (homepage, homepage)
        self.plugin_homepage_linkbutton.set_markup(markup)
        self.plugin_description.set_text(model.get_value(iter_, Column.DESCRIPTION))

    def select_root_iter(self):
        selection = self.available_plugins_treeview.get_selection()
        model, iter_ = selection.get_selected()
        if not iter_:
            iter_ = self.available_plugins_model.get_iter_first()
            selection.select_iter(iter_)
        self.plugin_name_label.show()
        self.plugin_homepage_linkbutton.show()
        path = self.available_plugins_model.get_path(iter_)
        self.available_plugins_treeview.scroll_to_cell(path)


class DownloadAsync(threading.Thread):
    def __init__(self, plugin, secure, remote_dirs,
                 upgrading, check_update, auto_update):
        threading.Thread.__init__(self)
        self.plugin = plugin
        self.window = plugin.window
        self.progressbar = plugin.progressbar
        self.model = plugin.available_plugins_model
        self.remote_dirs = remote_dirs
        self.upgrading = upgrading
        self.secure = secure
        self.check_update = check_update
        self.auto_update = auto_update
        self.pulse = None

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
                if not self.auto_update:
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
                log.warning('Plugin is missing INFO section in manifest.ini. '
                         'Plugin not loaded.')
                continue
            opts = config.options('info')
            if not set(MANDATORY_FIELDS).issubset(opts):
                log.warning(
                        '%s is missing mandatory fields %s. '
                        'Plugin not loaded.',
                        filename,
                        set(MANDATORY_FIELDS).difference(opts))
                continue
            # Add icon and remote dir
            icon = None
            remote_dir = filename.split('/')[0]
            png_filename = '{0}/{0}.png'.format(remote_dir)
            icon = FALLBACK_ICON
            if png_filename in manifest_list:
                data = zip_file.open(png_filename).read()
                pix = GdkPixbuf.PixbufLoader()
                pix.set_size(16, 16)
                pix.write(data)
                pix.close()
                icon = pix.get_pixbuf()

            # Transform to dictonary
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

    def plugin_is_valid(self, plugin):
        gajim_v = V(app.config.get('version'))
        min_v = plugin.get('min_gajim_version', None)
        min_v = V(min_v) if min_v else gajim_v
        max_v = plugin.get('max_gajim_version', None)
        max_v = V(max_v) if max_v else gajim_v
        if (gajim_v >= min_v) and (gajim_v <= max_v):
            return True
        return False

    def run_check_update(self):
        to_update = []
        auto_update_list = []
        zipbuf = self.download_url(MANIFEST_URL)
        plugin_list = self.parse_manifest(zipbuf)
        for plugin in plugin_list:
            local_version = get_local_version(plugin)
            if local_version:
                if (V(plugin['version']) > V(local_version)) and \
                self.plugin_is_valid(plugin):
                    to_update.append(plugin['name'])
                    auto_update_list.append(plugin['remote_dir'])
        if not self.auto_update:
            GLib.idle_add(self.plugin.warn_update, to_update)
        else:
            if auto_update_list:
                self.remote_dirs = auto_update_list
                GLib.idle_add(self.download_plugin)
            else:
                log.info('No updates found')
                if hasattr(self.plugin, 'thread'):
                    del self.plugin.thread

    def run_download_plugin_list(self):
        if not self.remote_dirs:
            log.info('Downloading Pluginlist...')
            zipbuf = self.download_url(MANIFEST_IMAGE_URL)
            plugin_list = self.parse_manifest(zipbuf)
            nb_plugins = 0
            for plugin in plugin_list:
                if not self.plugin_is_valid(plugin):
                    continue
                nb_plugins += 1
                plugin['local_version'] = get_local_version(plugin)
                if self.upgrading and plugin['local_version']:
                    if V(plugin['version']) > V(plugin['local_version']):
                        plugin['upgrade'] = True
                        GLib.idle_add(
                            self.plugin.install_plugin_button.set_property,
                            'sensitive', True)
                GLib.idle_add(self.model_append, plugin)
            if nb_plugins:
                GLib.idle_add(self.plugin.select_root_iter)
        else:
            self.download_plugin()

    def download_plugin(self):
        for remote_dir in self.remote_dirs:
            filename = remote_dir + '.zip'
            log.info('Download: %s', filename)

            user_dir = configpaths.get('PLUGINS_DOWNLOAD')
            local_dir = os.path.join(user_dir, remote_dir)
            if not os.path.isdir(local_dir):
                os.mkdir(local_dir)
            local_dir = os.path.dirname(local_dir)

            # Downloading zip file
            try:
                plugin = posixpath.join(PLUGINS_URL, filename)
                buf = self.download_url(plugin)
            except:
                log.exception("Error downloading plugin %s" % filename)
                continue
            with ZipFile(buf) as zip_file:
                zip_file.extractall(local_dir)
        GLib.idle_add(self.plugin.on_plugin_downloaded,
                      self.remote_dirs, self.auto_update)


class PluginInstallerPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        glade_file_path = self.plugin.local_file_path('config.ui')
        self.xml = get_builder(glade_file_path)
        self.get_child().pack_start(self.xml.config_grid, True, True, 0)

        self.xml.connect_signals(self)

    def on_run(self):
        self.xml.check_update.set_active(self.plugin.config['check_update'])
        self.xml.auto_update.set_sensitive(self.plugin.config['check_update'])
        self.xml.auto_update.set_active(self.plugin.config['auto_update'])
        self.xml.auto_update_feedback.set_sensitive(self.plugin.config['check_update'])
        self.xml.auto_update_feedback.set_active(self.plugin.config['auto_update_feedback'])

    def on_check_update_toggled(self, widget):
        self.plugin.config['check_update'] = widget.get_active()
        if not self.plugin.config['check_update']:
            self.plugin.config['auto_update'] = False
        self.xml.auto_update.set_sensitive(self.plugin.config['check_update'])
        self.xml.auto_update.set_active(self.plugin.config['auto_update'])
        self.xml.auto_update_feedback.set_sensitive(self.plugin.config['auto_update'])
        self.xml.auto_update_feedback.set_active(self.plugin.config['auto_update_feedback'])

    def on_auto_update_toggled(self, widget):
        self.plugin.config['auto_update'] = widget.get_active()
        self.xml.auto_update_feedback.set_sensitive(self.plugin.config['auto_update'])

    def on_auto_update_feedback_toggled(self, widget):
        self.plugin.config['auto_update_feedback'] = widget.get_active()
