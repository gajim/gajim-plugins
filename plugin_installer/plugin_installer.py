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
from gi.repository import GObject

import io
import threading
import configparser
import os
import fnmatch
import sys
import zipfile
import logging
import posixpath

from urllib.request import urlopen
from urllib.parse import urlparse, urljoin
from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from htmltextview import HtmlTextView
from dialogs import WarningDialog, HigDialog, YesNoDialog
from plugins.gui import GajimPluginConfigDialog
from enum import IntEnum

log = logging.getLogger('gajim.plugin_system.plugin_installer')


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


def convert_version_to_list(version_str):
    version_list = version_str.split('.')
    l = []
    while len(version_list):
        l.append(int(version_list.pop(0)))
    return l

class PluginInstaller(GajimPlugin):

    @log_calls('PluginInstallerPlugin')
    def init(self):
        self.description = _('Install and Upgrade Plugins')
        self.config_dialog = PluginInstallerPluginConfigDialog(self)
        self.config_default_values = {'http_server': ('https://ftp.gajim.org', ''),
                                      'check_update': (True, ''),
                                      }
        self.window = None
        self.progressbar = None
        self.available_plugins_model = None
        self.upgrading = False # True when opened from upgrade popup dialog
        self.timeout_id = 0
        self.connected_ids = {}
        icon = Gtk.Image()
        self.def_icon = icon.render_icon(Gtk.STOCK_PREFERENCES,
            Gtk.IconSize.MENU)
        self.server_folder = 'plugins_1'

    @log_calls('PluginInstallerPlugin')
    def activate(self):
        if self.config['check_update']:
            self.timeout_id = GLib.timeout_add_seconds(30, self.check_update)

    @log_calls('PluginInstallerPlugin')
    def warn_update(self, plugins):
        def open_update(dummy):
            self.upgrading = True
            self.pl_menuitem.activate()
            nb = gajim.interface.instances['plugins'].plugins_notebook
            page = nb.page_num(self.hpaned)
            GLib.idle_add(nb.set_current_page, page)
        if plugins:
            plugins_str = '\n'.join(plugins)
            YesNoDialog(_('Plugins updates'), _('Some updates are available for'
                ' your installer plugins. Do you want to update those plugins:'
                '\n%s') % plugins_str, on_response_yes=open_update)

    def parse_manifest(self, buf):
        '''
        given the buffer of the zipfile, returns the list of plugin manifests
        '''
        zip_file = zipfile.ZipFile(buf)
        manifest_list = zip_file.namelist()
        plugins = []
        for filename in manifest_list:
            config = configparser.ConfigParser()
            conf_file = zip_file.open(filename)
            config.read_file(io.TextIOWrapper(conf_file, encoding='utf-8'))
            conf_file.close()
            if not config.has_section('info'):
                continue
            plugins.append(config)
        return plugins

    def retrieve_path(self, directory, fname):
        print('retrive path')
        server = self.config['http_server']
        if not server:
            server = self.config_default_values['http_server'][0]
        if not urlparse(server).scheme:
            server = 'https://' + server
        if urlparse(server).scheme != 'https':
            log.warn('Warning: not using HTTPS is a '
                     'very serious security issue!')
        location = posixpath.join(directory, fname)
        uri = urljoin(server, location)
        log.debug('Fetching {}'.format(uri))
        request = urlopen(uri)

        manifest_buffer = io.BytesIO(request.read())

        return manifest_buffer

    def retrieve_manifest(self):
        return self.retrieve_path(self.server_folder, 'manifests.zip')

    @log_calls('PluginInstallerPlugin')
    def check_update(self):
        def _run():
            try:
                to_update = []
                zipbuf = self.retrieve_manifest()
                plugin_manifests = self.parse_manifest(zipbuf)
                for config in plugin_manifests:
                    opts = config.options('info')
                    if 'name' not in opts or 'version' not in opts or \
                    'description' not in opts or 'authors' not in opts or \
                    'homepage' not in opts:
                        continue
                    local_version = ftp.get_plugin_version(config.get(
                        'info', 'name'))
                    if local_version:
                        local = convert_version_to_list(local_version)
                        remote = convert_version_to_list(config.get('info',
                            'version'))
                        if remote > local:
                            to_update.append(config.get('info', 'name'))
                GLib.idle_add(self.warn_update, to_update)
            except Exception as e:
                log.error('Ftp error when check updates: %s' % str(e), exc_info=True)
        ftp = Ftp(self)
        ftp.run = _run
        ftp.start()
        self.timeout_id = 0

    @log_calls('PluginInstallerPlugin')
    def deactivate(self):
        self.pl_menuitem.disconnect(self.id_)
        if hasattr(self, 'page_num'):
            self.notebook.remove_page(self.notebook.page_num(self.hpaned))
            self.notebook.set_current_page(0)
            for id_, widget in list(self.connected_ids.items()):
                widget.disconnect(id_)
            del self.page_num
        if hasattr(self, 'ftp'):
            del self.ftp
        if self.timeout_id > 0:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = 0

    def on_activate(self, plugin_win):
        if hasattr(self, 'page_num'):
            # 'Available' tab exists
            return
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
            'install_button', 'authors_label',
            'homepage_linkbutton', 'version_label', 'scrolled_description_window')

        for widget_name in widgets_to_extract:
            setattr(self, widget_name, self.xml.get_object(widget_name))

        # Make Link in LinkButton not centered
        style_provider = Gtk.CssProvider()
        css = '.link { padding-left: 0px; padding-right: 0px; }'
        style_provider.load_from_data(css.encode())
        context = self.homepage_linkbutton.get_style_context()
        context.add_provider(style_provider,
                             Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.page_num = self.notebook.append_page(
            self.paned, Gtk.Label.new(_('Available')))

        self.available_plugins_model = self.xml.get_object('plugin_store')
        self.available_plugins_model.set_sort_column_id(2, Gtk.SortType.ASCENDING)

        self.progressbar.set_property('no-show-all', True)

        if GObject.signal_lookup('error_signal', self.window) is 0:
            GObject.signal_new('error_signal', self.window,
                GObject.SignalFlags.RUN_LAST, GObject.TYPE_STRING,
                (GObject.TYPE_STRING,))
            GObject.signal_new('plugin_downloaded', self.window,
                GObject.SignalFlags.RUN_LAST, GObject.TYPE_STRING,
                (GObject.TYPE_PYOBJECT,))

        id_ = self.window.connect('error_signal', self.on_some_ftp_error)
        self.connected_ids[id_] = self.window
        id_ = self.window.connect('plugin_downloaded',
            self.on_plugin_downloaded)
        self.connected_ids[id_] = self.window

        selection = self.available_treeview.get_selection()
        selection.connect(
            'changed', self.available_plugins_treeview_selection_changed)
        selection.set_mode(Gtk.SelectionMode.SINGLE)

        self._clear_available_plugin_info()

        self.description_textview = HtmlTextView()
        self.description_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        self.scrolled_description_window.add(self.description_textview)

        self.xml.connect_signals(self)
        self.window.show_all()

    def on_win_destroy(self, widget):
        if hasattr(self, 'ftp'):
            del self.ftp
        if hasattr(self, 'page_num'):
            del self.page_num

    def available_plugins_toggled_cb(self, cell, path):
        is_active = self.available_plugins_model[path][Column.UPGRADE]
        self.available_plugins_model[path][Column.UPGRADE] = not is_active
        dir_list = []
        for i in range(len(self.available_plugins_model)):
            if self.available_plugins_model[i][Column.UPGRADE]:
                dir_list.append(self.available_plugins_model[i][Column.DIR])
        if not dir_list:
            self.install_button.set_property('sensitive', False)
        else:
            self.install_button.set_property('sensitive', True)

    def on_notebook_switch_page(self, widget, page, page_num):
        tab_label_text = self.notebook.get_tab_label_text(self.paned)
        if tab_label_text != (_('Available')):
            return
        if not hasattr(self, 'ftp'):
            self.available_plugins_model.clear()
            self.progressbar.show()
            self.ftp = Ftp(self)
            self.ftp.remote_dirs = None
            self.ftp.upgrading = True
            self.ftp.start()

    def on_install_upgrade_clicked(self, widget):
        self.install_button.set_property('sensitive', False)
        dir_list = []
        for i in range(len(self.available_plugins_model)):
            if self.available_plugins_model[i][Column.UPGRADE]:
                dir_list.append(self.available_plugins_model[i][Column.DIR])

        ftp = Ftp(self)
        ftp.remote_dirs = dir_list
        ftp.start()

    def on_some_ftp_error(self, widget, error_text):
        for i in range(len(self.available_plugins_model)):
            self.available_plugins_model[i][Column.UPGRADE] = False
        self.progressbar.hide()
        def warn():
            WarningDialog(_('Ftp error'), error_text, self.window)
        GLib.idle_add(warn)

    def on_plugin_downloaded(self, widget, plugin_dirs):
        dialog = HigDialog(None, Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
            '', _('All selected plugins downloaded'))
        dialog.set_modal(False)
        dialog.set_transient_for(self.window)

        for _dir in plugin_dirs:
            is_active = False
            plugins = None
            plugin_dir = os.path.join(gajim.PLUGINS_DIRS[1], _dir)
            plugin = gajim.plugin_manager.get_plugin_by_path(plugin_dir)
            if plugin:
                if plugin.active:
                    is_active = True
                    GLib.idle_add(gajim.plugin_manager.deactivate_plugin,
                        plugin)
                gajim.plugin_manager.plugins.remove(plugin)

                model = self.installed_plugins_model
                for row in range(len(model)):
                    if plugin == model[row][0]:
                        model.remove(model.get_iter((row, 0)))
                        break

            plugins = self.scan_dir_for_plugin(plugin_dir)
            if not plugins:
                continue
            gajim.plugin_manager.add_plugin(plugins[0])
            plugin = gajim.plugin_manager.plugins[-1]
            for row in range(len(self.available_plugins_model)):
                if plugin.name == self.available_plugins_model[row][Column.NAME]:
                    self.available_plugins_model[row][Column.LOCAL_VERSION] = \
                        plugin.version
                    self.available_plugins_model[row][Column.UPGRADE] = False
            if is_active:
                GLib.idle_add(gajim.plugin_manager.activate_plugin, plugin)
            # get plugin icon
            icon_file = os.path.join(plugin.__path__, os.path.split(
                plugin.__path__)[1]) + '.png'
            icon = self.def_icon
            if os.path.isfile(icon_file):
                icon = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_file, 16, 16)
            if not hasattr(plugin, 'activatable'):
                # version 0.15
                plugin.activatable = False
            row = [plugin, plugin.name, is_active, plugin.activatable, icon]
            self.installed_plugins_model.append(row)

        dialog.popup()

    def available_plugins_treeview_selection_changed(self, treeview_selection):
        model, iter = treeview_selection.get_selected()
        self.xml.get_object('scrolled_description_window').get_children()[0].destroy()
        self.description_textview = HtmlTextView()
        self.description_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        sw = self.xml.get_object('scrolled_description_window')
        sw.add(self.description_textview)
        sw.show_all()
        if iter:
            self.name_label.set_text(model.get_value(iter, Column.NAME))
            self.version_label.set_text(model.get_value(iter, Column.VERSION))
            self.authors_label.set_text(model.get_value(iter, Column.AUTHORS))
            self.homepage_linkbutton.set_uri(model.get_value(iter,
                Column.HOMEPAGE))
            self.homepage_linkbutton.set_label(model.get_value(iter,
                Column.HOMEPAGE))
            label = self.homepage_linkbutton.get_children()[0]
            label.set_ellipsize(Pango.EllipsizeMode.END)
            self.homepage_linkbutton.set_property('sensitive', True)
            desc = _(model.get_value(iter, Column.DESCRIPTION))
            if not desc.startswith('<body '):
                desc = '<body  xmlns=\'http://www.w3.org/1999/xhtml\'>' + \
                    desc + ' </body>'
                desc = desc.replace('\n', '<br/>')
            self.description_textview.display_html(
                desc, self.description_textview, None)
            self.description_textview.set_property('sensitive', True)
        else:
            self._clear_available_plugin_info()

    def _clear_available_plugin_info(self):
        self.name_label.set_text('')
        self.version_label.set_text('')
        self.authors_label.set_text('')
        self.homepage_linkbutton.set_uri('')
        self.homepage_linkbutton.set_label('')
        self.homepage_linkbutton.set_property('sensitive', False)

    def scan_dir_for_plugin(self, path):
        plugins_found = []
        conf = configparser.ConfigParser()
        fields = ('name', 'short_name', 'version', 'description', 'authors',
            'homepage')
        if not os.path.isdir(path):
            return plugins_found

        dir_list = os.listdir(path)
        dir_, mod = os.path.split(path)
        sys.path.insert(0, dir_)

        manifest_path = os.path.join(path, 'manifest.ini')
        if not os.path.isfile(manifest_path):
            return plugins_found

        for elem_name in dir_list:
            file_path = os.path.join(path, elem_name)
            module = None

            if os.path.isfile(file_path) and fnmatch.fnmatch(file_path, '*.py'):
                module_name = os.path.splitext(elem_name)[0]
                if module_name == '__init__':
                    continue
                try:
                    full_module_name = '%s.%s' % (mod, module_name)
                    if full_module_name in sys.modules:
                        from imp import reload
                        module = reload(sys.modules[full_module_name])
                    else:
                        module = __import__(full_module_name)
                except ValueError as value_error:
                    pass
                except ImportError as import_error:
                    pass
                except AttributeError as attribute_error:
                    pass
            if module is None:
                continue

            for module_attr_name in [attr_name for attr_name in dir(module)
            if not (attr_name.startswith('__') or attr_name.endswith('__'))]:
                module_attr = getattr(module, module_attr_name)
                try:
                    if not issubclass(module_attr, GajimPlugin) or \
                    module_attr is GajimPlugin:
                        continue
                    module_attr.__path__ = os.path.abspath(os.path.dirname(
                        file_path))

                    # read metadata from manifest.ini
                    conf.readfp(open(manifest_path, 'r'))
                    for option in fields:
                        if conf.get('info', option) is '':
                            raise configparser.NoOptionError
                        setattr(module_attr, option, conf.get('info', option))
                    conf.remove_section('info')
                    plugins_found.append(module_attr)

                except TypeError as type_error:
                    pass
                except configparser.NoOptionError as type_error:
                    # all fields are required
                    pass
        return plugins_found

    def select_root_iter(self):
        if hasattr(self, 'page_num'):
            selection = self.available_treeview.get_selection()
            if selection.count_selected_rows() == 0:
                root_iter = self.available_plugins_model.get_iter_first()
                selection.select_iter(root_iter)
        scr_win = self.xml.get_object('scrolled_description_window')
        vadjustment = scr_win.get_vadjustment()
        if vadjustment:
            vadjustment.set_value(0)


class Ftp(threading.Thread):
    def __init__(self, plugin):
        super(Ftp, self).__init__()
        self.plugin = plugin
        self.window = plugin.window
        self.progressbar = plugin.progressbar
        self.model = plugin.available_plugins_model
        self.remote_dirs = None
        self.append_to_model = True
        self.upgrading = False
        icon = Gtk.Image()
        self.def_icon = icon.render_icon(
            Gtk.STOCK_PREFERENCES, Gtk.IconSize.MENU)

    def model_append(self, row):
        self.model.append(row)
        return False

    def progressbar_pulse(self):
        self.progressbar.pulse()
        return True

    def get_plugin_version(self, plugin_name):
        for plugin in gajim.plugin_manager.plugins:
            if plugin.name == plugin_name:
                return plugin.version

    def run(self):
        try:
            GLib.idle_add(self.progressbar.set_text,
                _('Connecting to server'))
            if not self.remote_dirs:
                GLib.idle_add(self.progressbar.set_text,
                                 _('Scan files on the server'))
                try:
                    buf = self.plugin.retrieve_path(self.plugin.server_folder, 'manifests_images.zip')
                except:
                    log.exception("Error fetching plugin list")
                    return
                zip_file = zipfile.ZipFile(buf)
                manifest_list = zip_file.namelist()
                progress_step = 1.0 / len(manifest_list)
                for filename in manifest_list:
                    if not filename.endswith('manifest.ini'):
                        continue
                    dir_ = filename.split('/')[0]
                    fract = self.progressbar.get_fraction() + progress_step
                    GLib.idle_add(self.progressbar.set_fraction, fract)
                    GLib.idle_add(self.progressbar.set_text,
                        _('Reading "%s"') % dir_)

                    config = configparser.ConfigParser()
                    conf_file = zip_file.open(filename)
                    config.read_file(io.TextIOWrapper(conf_file, encoding='utf-8'))
                    conf_file.close()
                    if not config.has_section('info'):
                        continue
                    opts = config.options('info')
                    if 'name' not in opts or 'version' not in opts or \
                    'description' not in opts or 'authors' not in opts or \
                    'homepage' not in opts:
                        continue

                    local_version = self.get_plugin_version(
                        config.get('info', 'name'))
                    upgrade = False
                    if self.upgrading and local_version:
                        local = convert_version_to_list(local_version)
                        remote = convert_version_to_list(config.get('info',
                            'version'))
                        if remote > local:
                            upgrade = True
                            GLib.idle_add(
                                self.plugin.install_button.set_property,
                                'sensitive', True)
                    png_filename = dir_ + '/' + dir_ + '.png'
                    if png_filename in manifest_list:
                        data = zip_file.open(png_filename).read()
                        pbl = GdkPixbuf.PixbufLoader()
                        pbl.set_size(16, 16)
                        pbl.write(data)
                        pbl.close()
                        def_icon = pbl.get_pixbuf()
                    else:
                        def_icon = self.def_icon
                    if local_version:
                        base_dir, user_dir = gajim.PLUGINS_DIRS
                        local_dir = os.path.join(user_dir, dir_)
                    GLib.idle_add(self.model_append, [def_icon, dir_,
                        config.get('info', 'name'), local_version,
                        config.get('info', 'version'), upgrade,
                        config.get('info', 'description'),
                        config.get('info', 'authors'),
                        config.get('info', 'homepage'), ])
                self.ftp.quit()
            GLib.idle_add(self.progressbar.set_fraction, 0)
            if self.remote_dirs:
                self.download_plugin()
            GLib.idle_add(self.progressbar.hide)
            GLib.idle_add(self.plugin.select_root_iter)
        except Exception as e:
            self.window.emit('error_signal', str(e))

    def download_plugin(self):
        GLib.idle_add(self.progressbar.show)
        self.pulse = GLib.timeout_add(150, self.progressbar_pulse)
        GLib.idle_add(self.progressbar.set_text, _('Creating a list of files'))
        for remote_dir in self.remote_dirs:
            filename = remote_dir + '.zip'
            base_dir, user_dir = gajim.PLUGINS_DIRS
            if not os.path.isdir(user_dir):
                os.mkdir(user_dir)
            local_dir = os.path.join(user_dir, remote_dir)
            if not os.path.isdir(local_dir):
                os.mkdir(local_dir)
            local_dir = os.path.split(user_dir)[0]

            # downloading zip file
            GLib.idle_add(self.progressbar.set_text,
                             _('Downloading "%s"') % filename)
            try:
                buf = self.plugin.retrieve_path(self.plugin.server_folder,
                                                filename)
            except:
                log.exception("Error downloading plugin %s" % filename)
                continue
            with zipfile.ZipFile(buf) as zip_file:
                zip_file.extractall(os.path.join(local_dir, 'plugins'))
        self.ftp.quit()
        GLib.idle_add(self.window.emit, 'plugin_downloaded', self.remote_dirs)
        GLib.source_remove(self.pulse)


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
