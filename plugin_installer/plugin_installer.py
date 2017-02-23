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
import fnmatch
import sys
import zipfile
import logging
import posixpath

from urllib.request import urlopen
from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from htmltextview import HtmlTextView
from dialogs import WarningDialog, HigDialog, YesNoDialog
from plugins.gui import GajimPluginConfigDialog
from enum import IntEnum
from gtkgui_helpers import get_action

log = logging.getLogger('gajim.plugin_system.plugin_installer')

PLUGINS_URL = 'https://ftp.gajim.org/plugins_1/'
MANIFEST_URL = 'https://ftp.gajim.org/plugins_1/manifests.zip'
MANIFEST_IMAGE_URL = 'https://ftp.gajim.org/plugins_1/manifests_images.zip'


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


def get_plugin_version(plugin_name):
    for plugin in gajim.plugin_manager.plugins:
        if plugin.name == plugin_name:
            return plugin.version


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
        self.config_default_values = {'check_update': (True, '')}
        self.window = None
        self.progressbar = None
        self.available_plugins_model = None
        self.timeout_id = 0
        self.connected_ids = {}
        icon = Gtk.Image()
        self.def_icon = icon.render_icon(Gtk.STOCK_PREFERENCES,
            Gtk.IconSize.MENU)

    @log_calls('PluginInstallerPlugin')
    def activate(self):
        if self.config['check_update']:
            self.timeout_id = GLib.timeout_add_seconds(30, self.check_update)
        if 'plugins' in gajim.interface.instances:
            self.on_activate(gajim.interface.instances['plugins'])

    @log_calls('PluginInstallerPlugin')
    def warn_update(self, plugins):
        def open_update(dummy):
            get_action('plugins').activate()
            page = self.notebook.page_num(self.paned)
            self.notebook.set_current_page(page)
        if plugins:
            plugins_str = '\n' + '\n'.join(plugins)
            YesNoDialog(_('Plugins updates'), _('Some updates are available for'
                ' your installer plugins. Do you want to update those plugins:'
                '\n%s') % plugins_str, on_response_yes=open_update)
        else:
            if hasattr(self, 'thread'):
                del self.thread

    def check_update(self):
        if hasattr(self, 'thread'):
            return
        self.thread = DownloadAsync(self, check_update=True)
        self.thread.start()
        self.timeout_id = 0

    @log_calls('PluginInstallerPlugin')
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

        self.available_page = self.notebook.append_page(
            self.paned, Gtk.Label.new(_('Available')))

        self.available_plugins_model = self.xml.get_object('plugin_store')
        self.available_plugins_model.set_sort_column_id(2, Gtk.SortType.ASCENDING)

        self.progressbar.set_property('no-show-all', True)

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
            self.thread = DownloadAsync(self, upgrading=True)
            self.thread.start()

    def on_install_upgrade_clicked(self, widget):
        self.install_button.set_property('sensitive', False)
        dir_list = []
        for i in range(len(self.available_plugins_model)):
            if self.available_plugins_model[i][Column.UPGRADE]:
                dir_list.append(self.available_plugins_model[i][Column.DIR])

        self.thread = DownloadAsync(self, remote_dirs=dir_list)
        self.thread.start()

    def on_error(self, error_text):
        if self.available_plugins_model:
            for i in range(len(self.available_plugins_model)):
                self.available_plugins_model[i][Column.UPGRADE] = False
            self.progressbar.hide()
        text = GLib.markup_escape_text(error_text)
        WarningDialog(_('Error'), text, self.window)

    def on_plugin_downloaded(self, plugin_dirs):
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
                    gajim.plugin_manager.deactivate_plugin(plugin)
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
                gajim.plugin_manager.activate_plugin(plugin)
            # get plugin icon
            icon_file = os.path.join(plugin.__path__, os.path.split(
                plugin.__path__)[1]) + '.png'
            icon = self.def_icon
            if os.path.isfile(icon_file):
                icon = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_file, 16, 16)
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
        if hasattr(self, 'available_page'):
            selection = self.available_treeview.get_selection()
            if selection.count_selected_rows() == 0:
                root_iter = self.available_plugins_model.get_iter_first()
                selection.select_iter(root_iter)
        scr_win = self.xml.get_object('scrolled_description_window')
        vadjustment = scr_win.get_vadjustment()
        if vadjustment:
            vadjustment.set_value(0)


class DownloadAsync(threading.Thread):
    def __init__(self, plugin, remote_dirs=None,
                 upgrading=False, check_update=False):
        threading.Thread.__init__(self)
        self.plugin = plugin
        self.window = plugin.window
        self.progressbar = plugin.progressbar
        self.model = plugin.available_plugins_model
        self.remote_dirs = remote_dirs
        self.upgrading = upgrading
        self.check_update = check_update
        icon = Gtk.Image()
        self.def_icon = icon.render_icon(
            Gtk.STOCK_PREFERENCES, Gtk.IconSize.MENU)

    def model_append(self, row):
        self.model.append(row)
        return False

    def progressbar_pulse(self):
        self.progressbar.pulse()
        return True

    def run(self):
        try:
            if self.check_update:
                self.run_check_update()
            else:
                self.run_download_plugin_list()
        except Exception as e:
            GLib.idle_add(self.plugin.on_error, str(e))
            log.exception('Error fetching plugin list')

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

    def download_url(self, url):
        log.debug('Fetching {}'.format(url))
        request = urlopen(url)
        return io.BytesIO(request.read())

    def run_check_update(self):
        to_update = []
        zipbuf = self.download_url(MANIFEST_URL)
        plugin_manifests = self.parse_manifest(zipbuf)
        for config in plugin_manifests:
            opts = config.options('info')
            if 'name' not in opts or 'version' not in opts or \
            'description' not in opts or 'authors' not in opts or \
            'homepage' not in opts:
                continue
            local_version = get_plugin_version(config.get(
                'info', 'name'))
            if local_version:
                local = convert_version_to_list(local_version)
                remote = convert_version_to_list(config.get('info',
                    'version'))
                if remote > local:
                    to_update.append(config.get('info', 'name'))
        GLib.idle_add(self.plugin.warn_update, to_update)

    def run_download_plugin_list(self):
        GLib.idle_add(self.progressbar.show)
        self.pulse = GLib.timeout_add(150, self.progressbar_pulse)
        if not self.remote_dirs:
            buf = self.download_url(MANIFEST_IMAGE_URL)
            zip_file = zipfile.ZipFile(buf)
            manifest_list = zip_file.namelist()
            for filename in manifest_list:
                if not filename.endswith('manifest.ini'):
                    continue
                dir_ = filename.split('/')[0]
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

                local_version = get_plugin_version(
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
        else:
            self.download_plugin()
        GLib.source_remove(self.pulse)
        GLib.idle_add(self.progressbar.hide)
        GLib.idle_add(self.plugin.select_root_iter)

    def download_plugin(self):
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
            try:
                plugin = posixpath.join(PLUGINS_URL, filename)
                buf = self.download_url(plugin)
            except:
                log.exception("Error downloading plugin %s" % filename)
                continue
            with zipfile.ZipFile(buf) as zip_file:
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
