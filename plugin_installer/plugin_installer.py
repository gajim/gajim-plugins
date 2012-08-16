# -*- coding: utf-8 -*-
#
## plugins/plugin_installer/plugin_installer.py
##
## Copyright (C) 2010-2011 Denis Fomin <fominde AT gmail.com>
## Copyright (C) 2011 Yann Leboulanger <asterix AT lagaule.org>
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
import gtk
import pango
import gobject
import ftplib
import io
import threading
import ConfigParser
import os
import fnmatch
import sys
import zipfile

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
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
        self.description = _('Install and upgrade plugins from ftp')
        self.config_dialog = PluginInstallerPluginConfigDialog(self)
        self.config_default_values = {'ftp_server': ('ftp.gajim.org', ''),
                                      'check_update': (True, ''),}
        self.window = None
        self.progressbar = None
        self.available_plugins_model = None
        self.upgrading = False # True when opened from upgrade popup dialog
        icon = gtk.Image()
        self.def_icon = icon.render_icon(gtk.STOCK_PREFERENCES,
            gtk.ICON_SIZE_MENU)

    @log_calls('PluginInstallerPlugin')
    def activate(self):
        self.pl_menuitem = gajim.interface.roster.xml.get_object(
            'plugins_menuitem')
        self.id_ = self.pl_menuitem.connect_after('activate', self.on_activate)
        if 'plugins' in gajim.interface.instances:
            self.on_activate(None)
        if self.config['check_update']:
            gobject.timeout_add_seconds(30, self.check_update)

    @log_calls('PluginInstallerPlugin')
    def warn_update(self, plugins):
        def open_update(dummy):
            self.upgrading = True
            self.pl_menuitem.activate()
            nb = gajim.interface.instances['plugins'].plugins_notebook
            gobject.idle_add(nb.set_current_page, 1)
        if plugins:
            plugins_str = '\n'.join(plugins)
            YesNoDialog(_('Plugins updates'), _('Some updates are available for'
                ' your installer plugins. Do you want to update those plugins:'
                '\n%s') % plugins_str, on_response_yes=open_update)

    def ftp_connect(self):
        if sys.version_info[:2] > (2, 6):
            con = ftplib.FTP_TLS(self.config['ftp_server'])
            con.login()
            con.prot_p()
        else:
            con = ftplib.FTP(self.config['ftp_server'])
            con.login()
        return con

    @log_calls('PluginInstallerPlugin')
    def check_update(self):
        def _run():
            try:
                to_update = []
                con = self.ftp_connect()
                con.cwd('plugins')
                con.retrbinary('RETR manifests.zip', ftp.handleDownload)
                zip_file = zipfile.ZipFile(ftp.buffer_)
                manifest_list = zip_file.namelist()
                for filename in manifest_list:
                    ftp.config.readfp(zip_file.open(filename))
                    local_version = ftp.get_plugin_version(ftp.config.get(
                        'info', 'name'))
                    if local_version:
                        local = convert_version_to_list(local_version)
                        remote = convert_version_to_list(ftp.config.get('info',
                            'version'))
                        if remote > local:
                            to_update.append(ftp.config.get('info', 'name'))
                con.quit()
                gobject.idle_add(self.warn_update, to_update)
            except Exception, e:
                log.debug('Ftp error when check updates: %s' % str(e))
        ftp = Ftp(self)
        ftp.run = _run
        ftp.start()

    @log_calls('PluginInstallerPlugin')
    def deactivate(self):
        self.pl_menuitem.disconnect(self.id_)
        if hasattr(self, 'page_num'):
            self.notebook.remove_page(self.page_num)
            self.notebook.set_current_page(0)
            del self.page_num
        if hasattr(self, 'ftp'):
            del self.ftp

    def on_activate(self, widget):
        if 'plugins' not in gajim.interface.instances:
            return
        if hasattr(self, 'page_num'):
            # 'Available' tab exists
            return
        self.installed_plugins_model = gajim.interface.instances[
            'plugins'].installed_plugins_model
        self.notebook = gajim.interface.instances['plugins'].plugins_notebook
        self.id_n = self.notebook.connect('switch-page',
            self.on_notebook_switch_page)
        self.window = gajim.interface.instances['plugins'].window
        self.window.connect('destroy', self.on_win_destroy)
        self.GTK_BUILDER_FILE_PATH = self.local_file_path('config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['hpaned2'])
        hpaned = self.xml.get_object('hpaned2')
        self.page_num = self.notebook.append_page(hpaned,
            gtk.Label(_('Available')))

        widgets_to_extract = ('plugin_name_label1',
        'available_treeview', 'progressbar', 'inslall_upgrade_button',
        'plugin_authors_label1', 'plugin_authors_label1',
        'plugin_homepage_linkbutton1', 'plugin_description_textview1')

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
        col = gtk.TreeViewColumn(_('Install /\nUpgrade'), renderer, active=C_UPGRADE)
        self.available_treeview.append_column(col)

        if gobject.signal_lookup('error_signal', self.window) is 0:
            gobject.signal_new('error_signal', self.window,
                gobject.SIGNAL_RUN_LAST, gobject.TYPE_STRING,
                (gobject.TYPE_STRING,))
            gobject.signal_new('plugin_downloaded', self.window,
                gobject.SIGNAL_RUN_LAST, gobject.TYPE_STRING,
                (gobject.TYPE_PYOBJECT,))
        self.window.connect('error_signal', self.on_some_ftp_error)
        self.window.connect('plugin_downloaded', self.on_plugin_downloaded)

        selection = self.available_treeview.get_selection()
        selection.connect('changed',
            self.available_plugins_treeview_selection_changed)
        selection.set_mode(gtk.SELECTION_SINGLE)

        self._clear_available_plugin_info()
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
        if not hasattr(self, 'ftp') and self.page_num == page_num:
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
        for _dir in plugin_dirs:
            is_active = False
            plugins = None
            plugin_dir = os.path.join(gajim.PLUGINS_DIRS[1], _dir)
            plugin = gajim.plugin_manager.get_plugin_by_path(plugin_dir)
            if plugin:
                if plugin.active and plugin.name != self.name:
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
            if is_active and plugin.name != self.name:
                gobject.idle_add(gajim.plugin_manager.activate_plugin, plugin)
            if plugin.name != 'Plugin Installer':
                # get plugin icon
                icon_file = os.path.join(plugin.__path__, os.path.split(
                plugin.__path__)[1]) + '.png'
                icon = self.def_icon
                if os.path.isfile(icon_file):
                    icon = gtk.gdk.pixbuf_new_from_file_at_size(icon_file, 16,
                        16)
                if not hasattr(plugin, 'activatable'):
                    # version 0.15
                    plugin.activatable = False
                max_row = [plugin, plugin.name, is_active, plugin.activatable,
                    icon]
                # support old plugin system
                row_len = len(self.installed_plugins_model[0])
                row = max_row[0: row_len]
                self.installed_plugins_model.append(row)

        dialog = HigDialog(None, gtk.MESSAGE_INFO, gtk.BUTTONS_OK,
            '', _('All selected plugins downloaded'))
        dialog.set_modal(False)
        dialog.set_transient_for(self.window)
        dialog.popup()

    def available_plugins_treeview_selection_changed(self, treeview_selection):
        model, iter = treeview_selection.get_selected()
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
            desc_textbuffer = self.plugin_description_textview1.get_buffer()
            desc_textbuffer.set_text(_(model.get_value(iter, C_DESCRIPTION)))
            self.plugin_description_textview1.set_property('sensitive', True)
        else:
            self._clear_available_plugin_info()

    def _clear_available_plugin_info(self):
        self.plugin_name_label1.set_text('')
        self.plugin_authors_label1.set_text('')
        self.plugin_homepage_linkbutton1.set_uri('')
        self.plugin_homepage_linkbutton1.set_label('')
        self.plugin_homepage_linkbutton1.set_property('sensitive', False)

        desc_textbuffer = self.plugin_description_textview1.get_buffer()
        desc_textbuffer.set_text('')
        self.plugin_description_textview1.set_property('sensitive', False)

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
                    module = __import__('%s.%s' % (mod, module_name))
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
                selection.select_iter(root_iter)


class Ftp(threading.Thread):
    def __init__(self, plugin):
        super(Ftp, self).__init__()
        self.plugin = plugin
        self.window = plugin.window
        self.progressbar = plugin.progressbar
        self.model = plugin.available_plugins_model
        self.config = ConfigParser.ConfigParser()
        self.buffer_ = io.BytesIO()
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
            self.ftp = self.plugin.ftp_connect()
            self.ftp.cwd('plugins')
            if not self.remote_dirs:
                gobject.idle_add(self.progressbar.set_text,
                    _('Scan files on the server'))
                self.ftp.retrbinary('RETR manifests_images.zip', self.handleDownload)
                zip_file = zipfile.ZipFile(self.buffer_)
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

                    self.config.readfp(zip_file.open(filename))
                    local_version = self.get_plugin_version(
                        self.config.get('info', 'name'))
                    upgrade = False
                    if self.upgrading and local_version:
                        local = convert_version_to_list(local_version)
                        remote = convert_version_to_list(self.config.get('info',
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
                        self.config.get('info', 'name'), local_version,
                        self.config.get('info', 'version'), upgrade,
                        self.config.get('info', 'description'),
                        self.config.get('info', 'authors'),
                        self.config.get('info', 'homepage'), ])
                self.ftp.quit()
            gobject.idle_add(self.progressbar.set_fraction, 0)
            if self.remote_dirs:
                self.download_plugin()
            gobject.idle_add(self.progressbar.hide)
            gobject.idle_add(self.plugin.select_root_iter)
        except Exception, e:
            self.window.emit('error_signal', str(e))

    def handleDownload(self, block):
        self.buffer_.write(block)

    def download_plugin(self):
        gobject.idle_add(self.progressbar.show)
        self.pulse = gobject.timeout_add(150, self.progressbar_pulse)
        gobject.idle_add(self.progressbar.set_text, _('Creating a list of files'))
        for remote_dir in self.remote_dirs:

            def nlstr(dir_, subdir=None):
                if subdir:
                    dir_ = dir_ + '/' + subdir
                list_ = self.ftp.nlst(dir_)
                for i in list_:
                    name = i.split('/')[-1]
                    if '.' not in name:
                        try:
                            if i == self.ftp.nlst(i)[0]:
                                files.append(i[1:])
                                del dirs[i[1:]]
                        except Exception, e:
                            # empty dir or file
                            continue
                        dirs.append(i[1:])
                        subdirs = name
                        nlstr(dir_, subdirs)
                    else:
                        files.append(i[1:])
            dirs, files = [], []
            nlstr('/plugins/' + remote_dir)

            base_dir, user_dir = gajim.PLUGINS_DIRS
            if not os.path.isdir(user_dir):
                os.mkdir(user_dir)
            local_dir = ld = os.path.join(user_dir, remote_dir)
            if not os.path.isdir(local_dir):
                os.mkdir(local_dir)
            local_dir = os.path.split(user_dir)[0]

            # creating dirs
            for dir_ in dirs:
                try:
                    os.mkdir(os.path.join(local_dir, dir_))
                except OSError, e:
                    if str(e).startswith('[Errno 17]'):
                        continue
                    raise

            # downloading files
            for filename in files:
                gobject.idle_add(self.progressbar.set_text,
                    _('Downloading "%s"') % filename)
                full_filename = os.path.join(local_dir, filename)
                try:
                    self.ftp.retrbinary('RETR /%s' % filename,
                        open(full_filename, 'wb').write)
                    #full_filename.close()
                except ftplib.error_perm:
                    print 'ERROR: cannot read file "%s"' % filename
                    os.unlink(filename)
        self.ftp.quit()
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

    def on_hide(self, widget):
        widget = self.xml.get_object('ftp_server')
        self.plugin.config['ftp_server'] = widget.get_text()

    def on_check_update_toggled(self, widget):
        self.plugin.config['check_update'] = widget.get_active()
