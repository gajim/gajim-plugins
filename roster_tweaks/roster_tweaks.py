# -*- coding: utf-8 -*-

import gtk
import pango
import gobject

from common import gajim

from plugins import GajimPlugin
from plugins.helpers import log, log_calls
from plugins.gui import GajimPluginConfigDialog
from dialogs import ChangeActivityDialog, ChangeMoodDialog
from common import pep
import gtkgui_helpers


class RosterTweaksPlugin(GajimPlugin):

    @log_calls('RosterTweaksPlugin')
    def init(self):
        self.config_dialog = RosterTweaksPluginConfigDialog(self)

        self.config_default_values = {'hide_status_combo': (False, ''),
                                      'use_ctr_m': (False, ''),
                                      'menu_visible': (True, ''),
                                      'quick_status': (False, '')}

    @log_calls('RosterTweaksPlugin')
    def activate(self):
        self.pep_dict = {}
        gajim.interface.roster.status_combobox.set_property('visible',
                not self.config['hide_status_combo'])
        gajim.interface.roster.status_combobox.set_no_show_all(True)
        self.enable_ctrl_m()

        vbox = gajim.interface.roster.xml.get_object('roster_vbox2')
        self.GTK_BUILDER_FILE_PATH = self.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['hbox1'])
        self.status_widget = self.xml.get_object('status_entry')
        self.status_widget.set_property('visible', self.config['quick_status'])
        self.status_widget.set_property('no-show-all', True)
        self.font_desc = self.status_widget.get_pango_context(
            ).get_font_description()
        self.activity_button = self.xml.get_object('activity_button')
        self.activity_button.set_property('no-show-all', True)
        self.activity_button.set_property('visible', self.config[
            'quick_status'])
        self.mood_button = self.xml.get_object('mood_button')
        self.mood_button.set_property('no-show-all', True)
        self.mood_button.set_property('visible', self.config['quick_status'])
        hbox = self.xml.get_object('hbox1')
        vbox.pack_start(hbox, False)
        self.xml.connect_signals(self)

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

    def on_activity_button_clicked(self, widget):
        def on_response(activity, subactivity, text):
            self.pep_dict['activity'] = activity or ''
            self.pep_dict['subactivity'] = subactivity or ''
            self.pep_dict['activity_text'] = text
            self.draw_activity()
            accounts = gajim.connections.keys()
            for account in accounts:
                gajim.interface.roster.send_pep(account, self.pep_dict)
        ChangeActivityDialog(on_response, self.pep_dict.get('activity', None),
            self.pep_dict.get('subactivity', None),
            self.pep_dict.get('activity_text', None))

    def on_mood_button_clicked(self, widget):
        def on_response(mood, text):
            self.pep_dict['mood'] = mood or ''
            self.pep_dict['mood_text'] = text
            self.draw_mood()
            accounts = gajim.connections.keys()
            for account in accounts:
                gajim.interface.roster.send_pep(account, self.pep_dict)
        ChangeMoodDialog(on_response, self.pep_dict.get('mood', None),
            self.pep_dict.get('mood_text', None))

    def draw_activity(self):
        """
        Set activity button
        """
        img = self.xml.get_object('activity_image')
        if 'activity' in self.pep_dict and self.pep_dict['activity'] in \
           pep.ACTIVITIES:
            if 'subactivity' in self.pep_dict and self.pep_dict['subactivity'] \
            in pep.ACTIVITIES[self.pep_dict['activity']]:
                img.set_from_pixbuf(gtkgui_helpers.load_activity_icon(
                    self.pep_dict['activity'], self.pep_dict['subactivity']).\
                        get_pixbuf())
            else:
                img.set_from_pixbuf(gtkgui_helpers.load_activity_icon(
                    self.pep_dict['activity']).get_pixbuf())
        else:
            img.set_from_stock('gtk-stop', gtk.ICON_SIZE_MENU)

    def draw_mood(self):
        """
        Set mood button
        """
        img = self.xml.get_object('mood_image')
        if 'mood' in self.pep_dict and self.pep_dict['mood'] in pep.MOODS:
            img.set_from_pixbuf(gtkgui_helpers.load_mood_icon(
                self.pep_dict['mood']).get_pixbuf())
        else:
            img.set_from_stock('gtk-stop', gtk.ICON_SIZE_MENU)


class RosterTweaksPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
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
        self.plugin.mood_button.set_property('visible', button.get_active())
        self.plugin.activity_button.set_property('visible', button.get_active())

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
