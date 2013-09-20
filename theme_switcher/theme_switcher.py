# -*- coding: utf-8 -*-
##

import gtk

from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log_calls
from common import gajim


class ThemeSwitcherPlugin(GajimPlugin):
    @log_calls('ThemeSwitcherPlugin')
    def init(self):
        self.config_dialog = ThemeSwitcherPluginConfigDialog(self)
        settings = gtk.settings_get_default()
        default_theme = settings.get_property('gtk-theme-name')
        self.config['DEFAULT_THEME'] = default_theme
        self.theme = default_theme
        self.config_default_values = {'THEME': (default_theme, '')}

    @log_calls('ThemeSwitcherPlugin')
    def activate(self):
        settings = gtk.settings_get_default()
        settings.set_property('gtk-theme-name', self.config['THEME'])

    @log_calls('ThemeSwitcherPlugin')
    def deactivate(self):
        settings = gtk.settings_get_default()
        settings.set_property('gtk-theme-name', self.config['DEFAULT_THEME'])


class ThemeSwitcherPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
            ['vbox2', 'image1'])
        hbox = self.xml.get_object('vbox2')
        self.child.pack_start(hbox)
        self.xml.connect_signals(self)

        theme_combo = self.xml.get_object('theme_combobox')
        self.theme_liststore = gtk.ListStore(str)
        theme_combo.set_model(self.theme_liststore)
        cellrenderer = gtk.CellRendererText()
        theme_combo.pack_start(cellrenderer, True)
        theme_combo.add_attribute(cellrenderer, 'text', 0)
        self._id = theme_combo.connect('changed', self.on_theme_combobox_changed)

    @log_calls('ThemeSwitcherPluginConfigDialog')
    def on_run(self):
        from os import listdir
        from os.path import join
        theme_d = gtk.rc_get_theme_dir()
        theme_names = []
        theme_combo = self.xml.get_object('theme_combobox')
        theme_combo.handler_block(self._id)
        self.theme_liststore.clear()
        theme_combo.handler_unblock(self._id)
        for theme in listdir(theme_d):
            try:
                if "gtk-2.0" in listdir(join(theme_d, theme)):
                    theme_names.append(theme)
            except:
                pass

        theme_names = sorted(theme_names)
        for name in theme_names:
            self.theme_liststore.append((name,))

    def on_reset_theme_button_clicked(self, widget):
        settings = gtk.settings_get_default()
        settings.set_property('gtk-theme-name',
            self.plugin.config['DEFAULT_THEME'])
        self.plugin.config['THEME'] = self.plugin.config['DEFAULT_THEME']

    def on_theme_combobox_changed(self, widget):
        model = widget.get_model()
        active = widget.get_active()
        self.theme = model[active][0].decode('utf-8')
        settings = gtk.settings_get_default()
        settings.set_property('gtk-theme-name', self.theme)
        self.plugin.config['THEME'] = self.theme
