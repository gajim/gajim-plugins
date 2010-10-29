# -*- coding: utf-8 -*-

import gtk
import pango
import gobject

from common import i18n
from common import gajim

from plugins import GajimPlugin
from plugins.helpers import log, log_calls
from plugins.gui import GajimPluginConfigDialog

class RosterTweaksPlugin(GajimPlugin):

    @log_calls('RosterTweaksPlugin')
    def init(self):
        self.config_dialog = RosterTweaksPluginConfigDialog(self)

        self.config_default_values = {'hide_status_combo': (False,''),
                                      'use_ctr_m': (False,''),
                                      'menu_visible': (True,''),
                                      'quick_status': (False, '')}

    @log_calls('RosterTweaksPlugin')
    def activate(self):
        gajim.interface.roster.status_combobox.set_property('visible',
                not self.config['hide_status_combo'])
        gajim.interface.roster.status_combobox.set_no_show_all(True)
        self.enable_ctrl_m()

        vbox = gajim.interface.roster.xml.get_object('roster_vbox2')
        self.status_widget = gtk.Entry(max=0)
        self.status_widget.set_property('visible', self.config['quick_status'])
        self.status_widget.set_property('no-show-all', True)
        self.status_widget.connect('key-press-event', self.status_changed)
        self.font_desc = self.status_widget.get_pango_context(
            ).get_font_description()
        vbox.pack_start(self.status_widget, False)

    def enable_ctrl_m(self):
        if self.config['use_ctr_m']:
            window = gajim.interface.roster.window
            self.accel_group = gtk.accel_groups_from_object(window)[0]
            self.accel_group.connect_group(gtk.keysyms.m, gtk.gdk.CONTROL_MASK,
                    gtk.ACCEL_MASK, self.on_ctrl_m)
            menubar = gajim.interface.roster.xml.get_object('menubar')
            menubar = gajim.interface.roster.xml.get_object('menubar')
            if self.config['menu_visible']:
                menubar.set_size_request(1, 1)
            else:
                menubar.set_size_request(-1, -1)

    @log_calls('RosterTweaksPlugin')
    def deactivate(self):
        gajim.interface.roster.status_combobox.show()
        self.status_widget.destroy()

    def on_ctrl_m(self, accel_group, acceleratable, keyval, modifier):
        menubar = gajim.interface.roster.xml.get_object('menubar')
        if not self.config['menu_visible']:
            menubar.set_size_request(1, 1)
        else:
            menubar.set_size_request(-1, -1)
        self.config['menu_visible'] = not self.config['menu_visible']
        return True

    def status_changed(self, widget, event):
        if event.keyval == gtk.keysyms.Return or \
            event.keyval == gtk.keysyms.KP_Enter:
            accounts = gajim.connections.keys()
            message = widget.get_text()
            for account in accounts:
                current_show = gajim.SHOW_LIST[
                    gajim.connections[account].connected]
                gajim.interface.roster.send_status(account, current_show,
                    message)
            self.font_desc.set_weight(pango.WEIGHT_BOLD)
            widget.modify_font(self.font_desc)
            self.font_desc.set_weight(pango.WEIGHT_NORMAL)
            gobject.timeout_add(1000, widget.modify_font, self.font_desc)

class RosterTweaksPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain(i18n.APP)
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['roster_tweaks_config_vbox'])
        self.config_vbox = self.xml.get_object('roster_tweaks_config_vbox')
        self.child.pack_start(self.config_vbox)

        self.hide_combo = self.xml.get_object('hide_combo')
        self.use_ctr_m = self.xml.get_object('use_ctr_m')

        self.xml.connect_signals(self)

    def on_run(self):
        self.hide_combo.set_active(self.plugin.config['hide_status_combo'])
        self.use_ctr_m.set_active(self.plugin.config['use_ctr_m'])
        status_widget = self.xml.get_object('quick_status')
        status_widget.set_active(self.plugin.config['quick_status'])

    def on_hide_combo_toggled(self, button):
        self.plugin.config['hide_status_combo'] = button.get_active()
        gajim.interface.roster.status_combobox.set_property('visible',
                not self.plugin.config['hide_status_combo'])

    def on_quick_status_toggled(self, button):
        self.plugin.config['quick_status'] = button.get_active()
        self.plugin.status_widget.set_property('visible', button.get_active())

    def on_use_ctr_m_toggled(self, button):
        is_ctr_m_enabled = button.get_active()
        self.plugin.config['use_ctr_m'] = is_ctr_m_enabled
        if is_ctr_m_enabled:
            self.plugin.enable_ctrl_m()
        else:
            self.plugin.accel_group.disconnect_key(gtk.keysyms.m,
                    gtk.gdk.CONTROL_MASK)
            self.plugin.config['menu_visible'] = True
            gajim.interface.roster.xml.get_object('menubar').set_size_request(
                    -1, -1)
