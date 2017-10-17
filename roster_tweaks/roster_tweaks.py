# -*- coding: utf-8 -*-

from gi.repository import Pango
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib

from gajim.common import app, ged, helpers
from gajim.plugins import GajimPlugin
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.dialogs import ChangeActivityDialog, ChangeMoodDialog
from gajim import gtkgui_helpers


class RosterTweaksPlugin(GajimPlugin):
    def init(self):
        self.description = _(
            'Allows user to tweak roster window appearance '
            '(eg. make it compact).')
        self.config_default_values = {'hide_status_combo': (False, ''),
                                      'use_ctr_m': (False, ''),
                                      'menu_visible': (True, ''),
                                      'quick_status': (False, ''),
                                      'contact_status_subs': (False, ''), }
        self.events_handlers = {'our-show': (ged.GUI2, self.our_show),
                                'pep-received': (ged.GUI2, self.pep_received)}
        self.gui_extension_points = {
            'roster_draw_contact': (self.roster_draw_contact,
                                    self.disconnect_roster_draw_contact), }
        self.roster = app.interface.roster
        self.config_dialog = RosterTweaksPluginConfigDialog(self)

    def roster_draw_contact(self, roster, jid, account, contact):
        self.connected = True
        if not self.active:
            return
        if not self.config['contact_status_subs']:
            return
        child_iters = roster._get_contact_iter(
            jid, account, contact, roster.model)
        if not child_iters:
            return
        name = roster.model[child_iters[0]][1]
        if '\n<span ' not in name:
            roster.model[child_iters[0]][1] = name + '\n'

    def disconnect_roster_draw_contact(self, *args):
        if self.connected:
            self.roster.setup_and_draw_roster()
            self.connected = False

    def pep_received(self, obj):
        if obj.jid != app.get_jid_from_account(obj.conn.name):
            return

        pep_dict = app.connections[obj.conn.name].pep
        if obj.pep_type == 'mood':
            img = self.xml.get_object('mood_image')
            if 'mood' in pep_dict:
                pixbuf = gtkgui_helpers.get_pep_as_pixbuf(pep_dict['mood'])
                img.set_from_pixbuf(pixbuf)
            else:
                img.set_from_stock('gtk-stop', Gtk.IconSize.MENU)
        if obj.pep_type == 'activity':
            img = self.xml.get_object('activity_image')
            if 'activity' in pep_dict:
                pb = gtkgui_helpers.get_pep_as_pixbuf(pep_dict['activity'])
                img.set_from_pixbuf(pb)
            else:
                img.set_from_stock('gtk-stop', Gtk.IconSize.MENU)

    def our_show(self, *args):
        if self.active:
            if helpers.get_global_show() != app.SHOW_LIST[0]:
                self.status_widget.set_text(helpers.get_global_status())
            else:
                self.status_widget.set_text('')

    def activate(self):
        self.pep_dict = {}
        self.roster.status_combobox.set_property('visible', not self.config[
            'hide_status_combo'])
        self.roster.status_combobox.set_no_show_all(True)
        self.enable_ctrl_m()

        vbox = self.roster.xml.get_object('roster_vbox2')
        self.GTK_BUILDER_FILE_PATH = self.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
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
        vbox.pack_start(hbox, False, True, 0)
        self.xml.connect_signals(self)
        self.roster.setup_and_draw_roster()

    def enable_ctrl_m(self):
        if self.config['use_ctr_m']:
            window = self.roster.window
            self.accel_group = Gtk.accel_groups_from_object(window)[0]
            self.accel_group.connect(Gdk.KEY_m,
                                     Gdk.ModifierType.CONTROL_MASK,
                                     Gtk.AccelFlags.MASK,
                                     self.on_ctrl_m)
            self.config['menu_visible'] = not self.config['menu_visible']
            self.on_ctrl_m()

    def deactivate(self):
        self.roster.status_combobox.show()
        self.status_widget.destroy()
        self.activity_button.destroy()
        self.mood_button.destroy()
        self.roster.window.set_show_menubar(True)

    def on_ctrl_m(self, *args):
        self.roster.window.set_show_menubar(self.config['menu_visible'])
        self.config['menu_visible'] = not self.config['menu_visible']
        return True

    def status_changed(self, widget, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            accounts = app.connections.keys()
            message = widget.get_text()
            for account in accounts:
                if not app.account_is_connected(account):
                    continue
                current_show = app.SHOW_LIST[
                    app.connections[account].connected]
                self.roster.send_status(account, current_show, message)
            self.font_desc.set_weight(Pango.Weight.BOLD)
            widget.modify_font(self.font_desc)
            self.font_desc.set_weight(Pango.Weight.NORMAL)
            GLib.timeout_add(1000, widget.modify_font, self.font_desc)

    def on_activity_button_clicked(self, widget):
        def on_response(activity, subactivity, text):
            self.pep_dict['activity'] = activity or ''
            self.pep_dict['subactivity'] = subactivity or ''
            self.pep_dict['activity_text'] = text
            self.send_pep()
        ChangeActivityDialog(on_response, 
                             self.pep_dict.get('activity', None),
                             self.pep_dict.get('subactivity', None),
                             self.pep_dict.get('activity_text', None))

    def on_mood_button_clicked(self, widget):
        def on_response(mood, text):
            self.pep_dict['mood'] = mood or ''
            self.pep_dict['mood_text'] = text
            self.send_pep()
        ChangeMoodDialog(on_response, 
                         self.pep_dict.get('mood', None),
                         self.pep_dict.get('mood_text', None))

    def send_pep(self):
        accounts = app.connections.keys()
        for account in accounts:
            if app.account_is_connected(account):
                self.roster.send_pep(account, self.pep_dict)


class RosterTweaksPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(
            self.GTK_BUILDER_FILE_PATH, ['roster_tweaks_config_vbox'])

        self.config_vbox = self.xml.get_object('roster_tweaks_config_vbox')
        self.get_child().pack_start(self.config_vbox, True, True, 0)

        self.hide_combo = self.xml.get_object('hide_combo')
        self.use_ctr_m = self.xml.get_object('use_ctr_m')
        status_widget = self.xml.get_object('contact_status_subs')
        status_widget.set_active(self.plugin.config['contact_status_subs'])

        self.xml.connect_signals(self)

    def on_run(self):
        self.hide_combo.set_active(self.plugin.config['hide_status_combo'])
        self.use_ctr_m.set_active(self.plugin.config['use_ctr_m'])
        status_widget = self.xml.get_object('quick_status')
        status_widget.set_active(self.plugin.config['quick_status'])

    def on_hide_combo_toggled(self, button):
        self.plugin.config['hide_status_combo'] = button.get_active()
        self.plugin.roster.status_combobox.set_property(
            'visible', not self.plugin.config['hide_status_combo'])

    def on_quick_status_toggled(self, button):
        self.plugin.config['quick_status'] = button.get_active()
        if not self.plugin.active:
            return
        self.plugin.status_widget.set_property('visible', button.get_active())
        self.plugin.mood_button.set_property('visible', button.get_active())
        self.plugin.activity_button.set_property('visible', button.get_active())
        self.plugin.status_widget.set_text(helpers.get_global_status())

    def on_use_ctr_m_toggled(self, button):
        is_ctr_m_enabled = button.get_active()
        self.plugin.config['use_ctr_m'] = is_ctr_m_enabled
        if is_ctr_m_enabled:
            self.plugin.enable_ctrl_m()
        else:
            self.plugin.accel_group.disconnect_key(
                Gdk.KEY_m, Gdk.ModifierType.CONTROL_MASK)
            self.plugin.config['menu_visible'] = True
            self.plugin.roster.window.set_show_menubar(True)

    def on_contact_status_subs_toggled(self, button):
        self.plugin.config['contact_status_subs'] = button.get_active()
        if self.plugin.active:
            self.plugin.roster.setup_and_draw_roster()
