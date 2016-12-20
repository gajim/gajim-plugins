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
import io
import threading
import ConfigParser
import os
import fnmatch
import sys
import zipfile

import gtk
import pango
import gobject
import ftplib

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from htmltextview import HtmlTextView
from dialogs import WarningDialog, HigDialog, YesNoDialog
from plugins.gui import GajimPluginConfigDialog

(
C_PIXBUF,
C_DIR,
C_NAME,
C_LOCAL_VERSION,
C_VERSION,
C_UPGRADE,
C_DESCRIPTION,
C_AUTHORS,
C_HOMEPAGE
) = range(9)

def convert_version_to_list(version_str):
    version_list = version_str.split('.')
    l = []
    while len(version_list):
        l.append(int(version_list.pop(0)))
    return l

class PluginInstaller(GajimPlugin):

    @log_calls('PluginInstallerPlugin')
    def init(self):
        self.config_dialog = PluginInstallerPluginConfigDialog(self)
        self.config_default_values = {'ftp_server': ('ftp.gajim.org', ''),
                                      'check_update': (True, ''),
                                      'TLS': (True, ''),}
        self.window = None
        self.progressbar = None
        self.available_plugins_model = None
        self.upgrading = False # True when opened from upgrade popup dialog
        self.timeout_id = 0
        self.connected_ids = {}
        icon = gtk.Image()
        self.def_icon = icon.render_icon(gtk.STOCK_PREFERENCES,
            gtk.ICON_SIZE_MENU)
        if gajim.version.startswith('0.15'):
            self.server_folder = 'plugins_0.15'
        elif gajim.version.startswith('0.16.10'):
            self.server_folder = 'plugins_gtk3'
        else:
            self.server_folder = 'plugins_0.16_zip'

    @log_calls('PluginInstallerPlugin')
    def activate(self):
        self.pl_menuitem = gajim.interface.roster.xml.get_object(
            'plugins_menuitem')
        self.id_ = self.pl_menuitem.connect_after('activate', self.on_activate)
        if 'plugins' in gajim.interface.instances:
            self.on_activate(None)
        if self.config['check_update']:
            self.timeout_id = gobject.timeout_add_seconds(30, self.check_update)

    @log_calls('PluginInstallerPlugin')
    def warn_update(self, plugins):
        def open_update(dummy):
            self.upgrading = True
            self.pl_menuitem.activate()
            nb = gajim.interface.instances['plugins'].plugins_notebook
            page = nb.page_num(self.hpaned)
            gobject.idle_add(nb.set_current_page, page)
        if plugins:
            plugins_str = '\n'.join(plugins)
            YesNoDialog(_('Plugins updates'), _('Some updates are available for'
                ' your installer plugins. Do you want to update those plugins:'
                '\n%s') % plugins_str, on_response_yes=open_update)

    def ftp_connect(self):
        if sys.version_info[:2] > (2, 6) and self.config['TLS'] :
            con = ftplib.FTP_TLS(self.config['ftp_server'])
            con.login()
            con.prot_p()
        else:
            con = ftplib.FTP(self.config['ftp_server'])
            con.login()
        return con

    def parse_manifest(self, buf):
        '''
        given the buffer of the zipfile, returns the list of plugin manifests
        '''
        zip_file = zipfile.ZipFile(buf)
        manifest_list = zip_file.namelist()
        plugins = []
        for filename in manifest_list:
            config = ConfigParser.ConfigParser()
            config.readfp(zip_file.open(filename))
            if not config.has_section('info'):
                continue
            plugins.add(config)

    def retrieve_path(self, directory, fname):
        con = self.ftp_connect()
        con.cwd(directory)
        manifest_buffer = io.BytesIO()

        def dl_handler(block):
            manifest_buffer.write(block)
        con.retrbinary('RETR %s' % fname, dl_handler)
        con.quit()
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
                gobject.idle_add(self.warn_update, to_update)
            except Exception, e:
                log.debug('Ftp error when check updates: %s' % str(e))
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
            for id_, widget in self.connected_ids.items():
                widget.disconnect(id_)
            del self.page_num
        if hasattr(self, 'ftp'):
            del self.ftp
        if self.timeout_id > 0:
            gobject.source_remove(self.timeout_id)
            self.timeout_id = 0

    def on_activate(self, widget):
        if 'plugins' not in gajim.interface.instances:
            return
        if hasattr(self, 'page_num'):
            # 'Available' tab exists
            return
        self.installed_plugins_model = gajim.interface.instances[
            'plugins'].installed_plugins_model
        self.notebook = gajim.interface.instances['plugins'].plugins_notebook
        id_ = self.notebook.connect('switch-page', self.on_notebook_switch_page)
        self.connected_ids[id_] = self.notebook
        self.window = gajim.interface.instances['plugins'].window
        id_ = self.window.connect('destroy', self.on_win_destroy)
        self.connected_ids[id_] = self.window
        self.GTK_BUILDER_FILE_PATH = self.local_file_path('config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['hpaned2',
            'image1'])
        self.hpaned = self.xml.get_object('hpaned2')
        self.page_num = self.notebook.append_page(self.hpaned,
            gtk.Label(_('Available')))

        widgets_to_extract = ('plugin_name_label1',
        'available_treeview', 'progressbar', 'inslall_upgrade_button',
        'plugin_authors_label1', 'plugin_authors_label1',
        'plugin_homepage_linkbutton1')

        for widget_name in widgets_to_extract:
            setattr(self, widget_name, self.xml.get_object(widget_name))

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, -1))
        self.plugin_name_label1.set_attributes(attr_list)

        self.available_plugins_model = gtk.ListStore(gtk.gdk.Pixbuf,
            gobject.TYPE_PYOBJECT, gobject.TYPE_STRING, gobject.TYPE_STRING,
            gobject.TYPE_STRING, gobject.TYPE_BOOLEAN, gobject.TYPE_PYOBJECT,
            gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT)
        self.available_treeview.set_model(self.available_plugins_model)
        self.available_treeview.set_rules_hint(True)
        self.available_plugins_model.set_sort_column_id(2, gtk.SORT_ASCENDING)

        self.progressbar.set_property('no-show-all', True)
        renderer = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_('Plugin'))
        cell = gtk.CellRendererPixbuf()
        col.pack_start(cell, False)
        col.add_attribute(cell, 'pixbuf', C_PIXBUF)
        col.pack_start(renderer, True)
        col.add_attribute(renderer, 'text', C_NAME)
        col.set_resizable(True)
        col.set_property('expand', True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_GROW_ONLY)
        self.available_treeview.append_column(col)
        col = gtk.TreeViewColumn(_('Installed\nversion'), renderer,
            text=C_LOCAL_VERSION)
        self.available_treeview.append_column(col)
        col = gtk.TreeViewColumn(_('Available\nversion'), renderer,
            text=C_VERSION)
        col.set_property('expand', False)
        self.available_treeview.append_column(col)

        renderer = gtk.CellRendererToggle()
        renderer.set_property('activatable', True)
        renderer.connect('toggled', self.available_plugins_toggled_cb)
        col = gtk.TreeViewColumn(_('Install /\nUpgrade'), renderer,
            active=C_UPGRADE)
        self.available_treeview.append_column(col)

        if gobject.signal_lookup('error_signal', self.window) is 0:
            gobject.signal_new('error_signal', self.window,
                gobject.SIGNAL_RUN_LAST, gobject.TYPE_STRING,
                (gobject.TYPE_STRING,))
            gobject.signal_new('plugin_downloaded', self.window,
                gobject.SIGNAL_RUN_LAST, gobject.TYPE_STRING,
                (gobject.TYPE_PYOBJECT,))
        id_ = self.window.connect('error_signal', self.on_some_ftp_error)
        self.connected_ids[id_] = self.window
        id_ = self.window.connect('plugin_downloaded',
            self.on_plugin_downloaded)
        self.connected_ids[id_] = self.window

        selection = self.available_treeview.get_selection()
        selection.connect('changed',
            self.available_plugins_treeview_selection_changed)
        selection.set_mode(gtk.SELECTION_SINGLE)

        self._clear_available_plugin_info()

        self.plugin_description_textview = HtmlTextView()
        sw = self.xml.get_object('scrolledwindow1')
        sw.add(self.plugin_description_textview)

        self.xml.connect_signals(self)
        self.window.show_all()

    def on_win_destroy(self, widget):
        if hasattr(self, 'ftp'):
            del self.ftp
        if hasattr(self, 'page_num'):
            del self.page_num

    def available_plugins_toggled_cb(self, cell, path):
        is_active = self.available_plugins_model[path][C_UPGRADE]
        self.available_plugins_model[path][C_UPGRADE] = not is_active
        dir_list = []
        for i in xrange(len(self.available_plugins_model)):
            if self.available_plugins_model[i][C_UPGRADE]:
                dir_list.append(self.available_plugins_model[i][C_DIR])
        if not dir_list:
            self.inslall_upgrade_button.set_property('sensitive', False)
        else:
            self.inslall_upgrade_button.set_property('sensitive', True)

    def on_notebook_switch_page(self, widget, page, page_num):
        tab_label_text = self.notebook.get_tab_label_text(self.hpaned)
        if tab_label_text != (_('Available')):
            return
        if not hasattr(self, 'ftp'):
            self.available_plugins_model.clear()
            self.progressbar.show()
            self.ftp = Ftp(self)
            self.ftp.remote_dirs = None
            self.ftp.upgrading = True
            self.ftp.start()

    def on_inslall_upgrade_clicked(self, widget):
        self.inslall_upgrade_button.set_property('sensitive', False)
        dir_list = []
        for i in xrange(len(self.available_plugins_model)):
            if self.available_plugins_model[i][C_UPGRADE]:
                dir_list.append(self.available_plugins_model[i][C_DIR])

        ftp = Ftp(self)
        ftp.remote_dirs = dir_list
        ftp.start()

    def on_some_ftp_error(self, widget, error_text):
        for i in xrange(len(self.available_plugins_model)):
            self.available_plugins_model[i][C_UPGRADE] = False
        self.progressbar.hide()
        WarningDialog(_('Ftp error'), error_text, self.window)

    def on_plugin_downloaded(self, widget, plugin_dirs):
        dialog = HigDialog(None, gtk.MESSAGE_INFO, gtk.BUTTONS_OK,
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
                    gobject.idle_add(gajim.plugin_manager.deactivate_plugin,
                        plugin)
                gajim.plugin_manager.plugins.remove(plugin)

                model = self.installed_plugins_model
                for row in xrange(len(model)):
                    if plugin == model[row][0]:
                        model.remove(model.get_iter((row, 0)))
                        break

            plugins = self.scan_dir_for_plugin(plugin_dir)
            if not plugins:
                continue
            gajim.plugin_manager.add_plugin(plugins[0])
            plugin = gajim.plugin_manager.plugins[-1]
            for row in xrange(len(self.available_plugins_model)):
                if plugin.name == self.available_plugins_model[row][C_NAME]:
                    self.available_plugins_model[row][C_LOCAL_VERSION] = \
                        plugin.version
                    self.available_plugins_model[row][C_UPGRADE] = False
            if is_active:
                gobject.idle_add(gajim.plugin_manager.activate_plugin, plugin)
            # get plugin icon
            icon_file = os.path.join(plugin.__path__, os.path.split(
                plugin.__path__)[1]) + '.png'
            icon = self.def_icon
            if os.path.isfile(icon_file):
                icon = gtk.gdk.pixbuf_new_from_file_at_size(icon_file, 16, 16)
            if not hasattr(plugin, 'activatable'):
                # version 0.15
                plugin.activatable = False
            max_row = [plugin, plugin.name, is_active, plugin.activatable, icon]
            # support old plugin system
            if len(self.installed_plugins_model):
                row_len = len(self.installed_plugins_model[0])
            else:
                row_len = 5
            row = max_row[0: row_len]
            self.installed_plugins_model.append(row)

        dialog.popup()

    def available_plugins_treeview_selection_changed(self, treeview_selection):
        model, iter = treeview_selection.get_selected()
        self.xml.get_object('scrolledwindow1').get_children()[0].destroy()
        self.plugin_description_textview = HtmlTextView()
        sw = self.xml.get_object('scrolledwindow1')
        sw.add(self.plugin_description_textview)
        sw.show_all()
        if iter:
            self.plugin_name_label1.set_text(model.get_value(iter, C_NAME))
            self.plugin_authors_label1.set_text(model.get_value(iter, C_AUTHORS))
            self.plugin_homepage_linkbutton1.set_uri(model.get_value(iter,
                C_HOMEPAGE))
            self.plugin_homepage_linkbutton1.set_label(model.get_value(iter,
                C_HOMEPAGE))
            label = self.plugin_homepage_linkbutton1.get_children()[0]
            label.set_ellipsize(pango.ELLIPSIZE_END)
            self.plugin_homepage_linkbutton1.set_property('sensitive', True)
            desc = _(model.get_value(iter, C_DESCRIPTION))
            if not desc.startswith('<body '):
                desc = "<body  xmlns='http://www.w3.org/1999/xhtml'>" + \
                    desc + ' </body>'
                desc = desc.replace('\n', '<br/>')
            self.plugin_description_textview.display_html(desc,
                self.plugin_description_textview, None)
            self.plugin_description_textview.set_property('sensitive', True)
        else:
            self._clear_available_plugin_info()

    def _clear_available_plugin_info(self):
        self.plugin_name_label1.set_text('')
        self.plugin_authors_label1.set_text('')
        self.plugin_homepage_linkbutton1.set_uri('')
        self.plugin_homepage_linkbutton1.set_label('')
        self.plugin_homepage_linkbutton1.set_property('sensitive', False)

    def scan_dir_for_plugin(self, path):
        plugins_found = []
        conf = ConfigParser.ConfigParser()
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
                        module = reload(sys.modules[full_module_name])
                    else:
                        module = __import__(full_module_name)
                except ValueError, value_error:
                    pass
                except ImportError, import_error:
                    pass
                except AttributeError, attribute_error:
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
                            raise ConfigParser.NoOptionError, 'field empty'
                        setattr(module_attr, option, conf.get('info', option))
                    conf.remove_section('info')
                    plugins_found.append(module_attr)

                except TypeError, type_error:
                    pass
                except ConfigParser.NoOptionError, type_error:
                    # all fields are required
                    pass
        return plugins_found

    def select_root_iter(self):
        if hasattr(self, 'page_num'):
            selection = self.available_treeview.get_selection()
            if selection.count_selected_rows() == 0:
                root_iter = self.available_plugins_model.get_iter_root()
                if root_iter:
                    selection.select_iter(root_iter)
        scr_win = self.xml.get_object('scrolledwindow2')
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
        icon = gtk.Image()
        self.def_icon = icon.render_icon(gtk.STOCK_PREFERENCES,
            gtk.ICON_SIZE_MENU)

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
            gobject.idle_add(self.progressbar.set_text,
                _('Connecting to server'))
            if not self.remote_dirs:
                gobject.idle_add(self.progressbar.set_text,
                    _('Scan files on the server'))
                zip_file = zipfile.ZipFile(self.plugin.retrieve_path(self.plugin.server_folder,
                                                              'manifests_images.zip'))
                manifest_list = zip_file.namelist()
                progress_step = 1.0 / len(manifest_list)
                for filename in manifest_list:
                    if not filename.endswith('manifest.ini'):
                        continue
                    dir_ = filename.split('/')[0]
                    fract = self.progressbar.get_fraction() + progress_step
                    gobject.idle_add(self.progressbar.set_fraction, fract)
                    gobject.idle_add(self.progressbar.set_text,
                        _('Reading "%s"') % dir_)

                    config = ConfigParser.ConfigParser()
                    config.readfp(zip_file.open(filename))
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
                            gobject.idle_add(
                                self.plugin.inslall_upgrade_button.set_property,
                                'sensitive', True)
                    png_filename = dir_ + '/' + dir_ + '.png'
                    if png_filename in manifest_list:
                        data = zip_file.open(png_filename).read()
                        pbl = gtk.gdk.PixbufLoader()
                        pbl.set_size(16, 16)
                        pbl.write(data)
                        pbl.close()
                        def_icon = pbl.get_pixbuf()
                    else:
                        def_icon = self.def_icon
                    if local_version:
                        base_dir, user_dir = gajim.PLUGINS_DIRS
                        local_dir = os.path.join(user_dir, dir_)

                    gobject.idle_add(self.model_append, [def_icon, dir_,
                        config.get('info', 'name'), local_version,
                        config.get('info', 'version'), upgrade,
                        config.get('info', 'description'),
                        config.get('info', 'authors'),
                        config.get('info', 'homepage'), ])
                self.ftp.quit()
            gobject.idle_add(self.progressbar.set_fraction, 0)
            if self.remote_dirs:
                self.download_plugin()
            gobject.idle_add(self.progressbar.hide)
            gobject.idle_add(self.plugin.select_root_iter)
        except Exception, e:
            self.window.emit('error_signal', str(e))

    def download_plugin(self):
        gobject.idle_add(self.progressbar.show)
        self.pulse = gobject.timeout_add(150, self.progressbar_pulse)
        gobject.idle_add(self.progressbar.set_text, _('Creating a list of files'))
        for remote_dir in self.remote_dirs:
            filename = remote_dir + '.zip'
            base_dir, user_dir = gajim.PLUGINS_DIRS
            if not os.path.isdir(user_dir):
                os.mkdir(user_dir)
            local_dir = ld = os.path.join(user_dir, remote_dir)
            if not os.path.isdir(local_dir):
                os.mkdir(local_dir)
            local_dir = os.path.split(user_dir)[0]

            # downloading zip file
            gobject.idle_add(self.progressbar.set_text,
                _('Downloading "%s"') % filename)
            try:
                buf = self.plugin.retrieve_path(self.plugin.server_folder, filename)
            except ftplib.error_perm:
                print 'ERROR: cannot read file "%s"' % filename
            with zipfile.ZipFile(buf) as zip_file:
                zip_file.extractall(os.path.join(local_dir, 'plugins'))

        gobject.idle_add(self.window.emit, 'plugin_downloaded',
            self.remote_dirs)
        gobject.source_remove(self.pulse)


class PluginInstallerPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['hbox111'])
        hbox = self.xml.get_object('hbox111')
        self.child.pack_start(hbox)

        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)

    def on_run(self):
        widget = self.xml.get_object('ftp_server')
        widget.set_text(str(self.plugin.config['ftp_server']))
        self.xml.get_object('check_update').set_active(
            self.plugin.config['check_update'])
        self.xml.get_object('TLS').set_active(self.plugin.config['TLS'])

    def on_hide(self, widget):
        widget = self.xml.get_object('ftp_server')
        self.plugin.config['ftp_server'] = widget.get_text()

    def on_check_update_toggled(self, widget):
        self.plugin.config['check_update'] = widget.get_active()

    def on_tls_toggled(self, widget):
        self.plugin.config['TLS'] = widget.get_active()
