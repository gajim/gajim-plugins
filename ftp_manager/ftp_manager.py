# -*- coding: utf-8 -*-

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

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from dialogs import WarningDialog


class FtpManager(GajimPlugin):

    @log_calls('FtpManagerPlugin')
    def init(self):
        self.config_dialog = None#FtpManagerPluginConfigDialog(self)


    @log_calls('FtpManagerPlugin')
    def activate(self):
        self.pl_menuitem = gajim.interface.roster.xml.get_object(
            'plugins_menuitem')
        self.id_ = self.pl_menuitem.connect_after('activate', self.on_activate)
        if gajim.interface.instances.has_key('plugins'):
            self.on_activate(None)

    @log_calls('FtpManagerPlugin')
    def deactivate(self):
        self.pl_menuitem.disconnect(self.id_)
        if hasattr(self, 'page_num'):
            self.notebook.remove_page(self.page_num)
        if hasattr(self, 'ftp'):
            del self.ftp

    def on_activate(self, widget):
        if not gajim.interface.instances.has_key('plugins'):
            return
        self.installed_plugins_model = gajim.interface.instances[
            'plugins'].installed_plugins_model
        self.notebook = gajim.interface.instances['plugins'].plugins_notebook
        self.id_n = self.notebook.connect('switch-page',
            self.on_notebook_switch_page)
        self.window = gajim.interface.instances['plugins'].window
        self.window.connect('destroy', self.on_win_destroy)
        self.GTK_BUILDER_FILE_PATH = self.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        #self.xml.set_translation_domain('FtpManagerPlugin')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['hpaned2'])
        hpaned = self.xml.get_object('hpaned2')
        self.page_num = self.notebook.append_page(hpaned,
            gtk.Label('Ftp Manager'))

        widgets_to_extract = ('plugin_name_label1',
        'available_treeview', 'progressbar', 'inslall_upgrade_button',
        'plugin_authors_label1', 'plugin_authors_label1',
        'plugin_homepage_linkbutton1', 'plugin_description_textview1')

        for widget_name in widgets_to_extract:
                setattr(self, widget_name, self.xml.get_object(widget_name))

        attr_list = pango.AttrList()
        attr_list.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, -1))
        self.plugin_name_label1.set_attributes(attr_list)

        self.available_plugins_model = gtk.ListStore(gobject.TYPE_PYOBJECT,
            gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING,
            gobject.TYPE_BOOLEAN, gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT,
            gobject.TYPE_PYOBJECT)
        self.available_treeview.set_model(self.available_plugins_model)

        self.progressbar.set_property('no-show-all', True)
        renderer = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_('Plugin'), renderer, text=1)
        col.set_resizable(True)
        col.set_property('expand', True)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_GROW_ONLY)
        self.available_treeview.append_column(col)
        col = gtk.TreeViewColumn(_('Installed\nversion'), renderer, text=2)
        self.available_treeview.append_column(col)
        col = gtk.TreeViewColumn(_('Available\nversion'), renderer, text=3)
        col.set_property('expand', False)
        self.available_treeview.append_column(col)

        renderer = gtk.CellRendererToggle()
        renderer.set_property('activatable', True)
        renderer.connect('toggled', self.available_plugins_toggled_cb)
        col = gtk.TreeViewColumn(_('Install /\nUpgrade'), renderer, active=4)
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

    def available_plugins_toggled_cb(self, cell, path):
        is_active = self.available_plugins_model[path][4]
        self.available_plugins_model[path][4] = not is_active
        dir_list = []
        for i in xrange(len(self.available_plugins_model)):
            if self.available_plugins_model[i][4]:
                dir_list.append(self.available_plugins_model[i][0])
        if not dir_list:
            self.inslall_upgrade_button.set_property('sensitive', False)
        else:
            self.inslall_upgrade_button.set_property('sensitive', True)

    def on_notebook_switch_page(self, widget, page, page_num,):
        if not hasattr(self, 'ftp') and self.page_num == page_num:
            self.available_plugins_model.clear()
            self.progressbar.show()
            self.ftp = Ftp(self)
            self.ftp.remote_dirs = None
            self.ftp.start()

    def on_inslall_upgrade_clicked(self, widget):
        self.inslall_upgrade_button.set_property('sensitive', False)
        dir_list = []
        for i in xrange(len(self.available_plugins_model)):
            if self.available_plugins_model[i][4]:
                dir_list.append(self.available_plugins_model[i][0])

        ftp = Ftp(self)
        ftp.remote_dirs = dir_list
        ftp.start()

    def on_some_ftp_error(self, widget, error_text):
        for i in xrange(len(self.available_plugins_model)):
            self.available_plugins_model[i][4] = False
        self.progressbar.hide()
        WarningDialog('Ftp error', error_text, self.window)

    def on_plugin_downloaded(self, widget, plugin_dirs):
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
                if plugin.name == self.available_plugins_model[row][1]:
                    self.available_plugins_model[row][2] = plugin.version
                    self.available_plugins_model[row][4] = False
                    continue
            if is_active:
                gajim.plugin_manager.activate_plugin(plugin)
            self.installed_plugins_model.append([plugin, plugin.name,
                is_active])

    def available_plugins_treeview_selection_changed(self, treeview_selection):
        model, iter = treeview_selection.get_selected()
        if iter:
            self.plugin_name_label1.set_text(model.get_value(iter, 1))
            self.plugin_authors_label1.set_text(model.get_value(iter, 6))
            self.plugin_homepage_linkbutton1.set_uri(model.get_value(iter, 7))
            self.plugin_homepage_linkbutton1.set_label('Visit homepage')#model.get_value(iter, 7))
            self.plugin_homepage_linkbutton1.set_property('sensitive', True)
            desc_textbuffer = self.plugin_description_textview1.get_buffer()
            desc_textbuffer.set_text(model.get_value(iter, 5))
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
                    module = __import__('%s.%s' %(mod, module_name))
                except ValueError, value_error:
                    pass
                except ImportError, import_error:
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

class Ftp(threading.Thread):
    def __init__(self, window):
        super(Ftp, self).__init__()
        self.window = window.window
        self.progressbar = window.progressbar
        self.model = window.available_plugins_model
        self.config = ConfigParser.ConfigParser()
        self.buffer_ = io.BytesIO()
        self.remote_dirs = None
        self.append_to_model = True

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
            self.ftp = ftplib.FTP('ftp.gajim.org')
            self.ftp.login()
            self.ftp.cwd('plugins')
            if not self.remote_dirs:
                self.plugins_dirs = self.ftp.nlst()
                progress_step = 1.0 / len(self.plugins_dirs)
                for dir_ in self.plugins_dirs:
                    fract = self.progressbar.get_fraction() + progress_step
                    gobject.idle_add(self.progressbar.set_fraction, fract)
                    try:
                        self.ftp.retrbinary('RETR %s/manifest.ini' %dir_,
                            self.handleDownload)
                    except Exception, error:
                        if str(error).startswith('550'):
                            continue
                    self.config.readfp(io.BytesIO(self.buffer_.getvalue()))
                    local_version = self.get_plugin_version(
                        self.config.get('info', 'name'))
                    gobject.idle_add(self.model_append,[dir_,
                        self.config.get('info', 'name'), local_version,
                        self.config.get('info', 'version'), False,
                        self.config.get('info', 'description'),
                        self.config.get('info', 'authors'),
                        self.config.get('info', 'homepage'),])
                self.plugins_dirs = None
                self.ftp.quit()
            gobject.idle_add(self.progressbar.set_fraction, 0)
            if self.remote_dirs:
                self.download_plugin()
            gobject.idle_add(self.progressbar.hide)
        except Exception, e:
            self.window.emit('error_signal', str(e))


    def handleDownload(self, block):
        self.buffer_.write(block)

    def download_plugin(self):
        gobject.idle_add(self.progressbar.show)
        self.pulse = gobject.timeout_add(150, self.progressbar_pulse)
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
                        except Exception,e:
                            # empty dir or file
                            continue
                        dirs.append(i[1:])
                        subdirs = name
                        nlstr(dir_, subdirs)
                    else:
                        files.append(i[1:])
            dirs,files = [], []
            nlstr('/plugins/' + remote_dir)

            if not os.path.isdir(gajim.PLUGINS_DIRS[1]):
                os.mkdir(gajim.PLUGINS_DIRS[1])
            local_dir = ld = os.path.join(gajim.PLUGINS_DIRS[1], remote_dir)
            if not os.path.isdir(local_dir):
                os.mkdir(local_dir)
            local_dir = os.path.split(gajim.PLUGINS_DIRS[1])[0]

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
                full_filename = os.path.join(local_dir, filename)
                try:
                    self.ftp.retrbinary('RETR /%s' % filename,
                        open(full_filename, 'wb').write)
                    #full_filename.close()
                except ftplib.error_perm:
                    print 'ERROR: cannot read file "%s"' % filename
                    os.unlink(filename)
        self.ftp.quit()
        self.window.emit('plugin_downloaded', self.remote_dirs)
        gobject.source_remove(self.pulse)
