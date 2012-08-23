# -*- coding: utf-8 -*-

import gtk
import pango
import gobject

from common import gajim, ged, helpers, pep
from plugins import GajimPlugin
from plugins.helpers import log_calls
from plugins.gui import GajimPluginConfigDialog
from dialogs import ChangeActivityDialog, ChangeMoodDialog
import gtkgui_helpers


class RosterTweaksPlugin(GajimPlugin):

    @log_calls('RosterTweaksPlugin')
    def init(self):
        self.description = _('Allows user to tweak roster window appearance '
            '(eg. make it compact).\nBased on ticket #3340:\n'
            'http://trac.gajim.org/ticket/3340.\n'
            'Added ability to quickly change the status message '
            'to all connected accounts.\n'
            'Based on ticket #5085:\n'
            'http://trac.gajim.org/ticket/5085.')
        self.config_dialog = RosterTweaksPluginConfigDialog(self)
        self.config_default_values = {'hide_status_combo': (False, ''),
                                      'use_ctr_m': (False, ''),
                                      'menu_visible': (True, ''),
                                      'quick_status': (False, ''),
                                      'contact_status_subs': (False, ''),}
        self.events_handlers = {'our-show': (ged.GUI2, self.our_show),
                                'pep-received': (ged.GUI2, self.pep_received)}
        self.gui_extension_points = {
                'roster_draw_contact': (self.roster_draw_contact,
                                       self.disconnect_roster_draw_contact),}
        self.roster = gajim.interface.roster

    def roster_draw_contact(self, roster,jid, account, contact):
        self.connected = True
        if not self.active:
            return
        if not self.config['contact_status_subs']:
            return
        child_iters = roster._get_contact_iter(jid, account, contact,
            roster.model)
        if not child_iters:
            return
        name = roster.model[child_iters[0]][1]
        if '\n<span ' not in name:
            roster.model[child_iters[0]][1] = name + '\n'

    def disconnect_roster_draw_contact(self, roster,jid, account, contact):
        if self.connected:
            self.roster.setup_and_draw_roster()
            self.connected = False

    def pep_received(self, obj):
        if obj.jid != gajim.get_jid_from_account(obj.conn.name):
            return

        pep_dict = gajim.connections[obj.conn.name].pep
        if  obj.pep_type == 'mood':
            img = self.xml.get_object('mood_image')
            if 'mood' in pep_dict:
                img.set_from_pixbuf(pep_dict['mood'].asPixbufIcon())
            else:
                img.set_from_stock('gtk-stop', gtk.ICON_SIZE_MENU)
        if  obj.pep_type == 'activity':
            img = self.xml.get_object('activity_image')
            if 'activity' in pep_dict:
                img.set_from_pixbuf(pep_dict['activity'].asPixbufIcon())
            else:
                img.set_from_stock('gtk-stop', gtk.ICON_SIZE_MENU)

    def our_show(self, obj):
        if self.active:
            if helpers.get_global_show() != gajim.SHOW_LIST[0]:
                self.status_widget.set_text(helpers.get_global_status())
            else:
                self.status_widget.set_text('')

    @log_calls('RosterTweaksPlugin')
    def activate(self):
        self.pep_dict = {}
        self.roster.status_combobox.set_property('visible', not self.config[
            'hide_status_combo'])
        self.roster.status_combobox.set_no_show_all(True)
        self.enable_ctrl_m()

        vbox = self.roster.xml.get_object('roster_vbox2')
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
        self.roster.setup_and_draw_roster()

    def enable_ctrl_m(self):
        if self.config['use_ctr_m']:
            window = self.roster.window
            self.accel_group = gtk.accel_groups_from_object(window)[0]
            self.accel_group.connect_group(gtk.keysyms.m, gtk.gdk.CONTROL_MASK,
                    gtk.ACCEL_MASK, self.on_ctrl_m)
            self.config['menu_visible'] = not self.config['menu_visible']
            self.on_ctrl_m(None, None, None, None)

    @log_calls('RosterTweaksPlugin')
    def deactivate(self):
        self.roster.status_combobox.show()
        self.status_widget.destroy()
        self.activity_button.destroy()
        self.mood_button.destroy()
        self.roster.xml.get_object('menubar').set_size_request(-1, -1)

    def on_ctrl_m(self, accel_group, acceleratable, keyval, modifier):
        menubar = self.roster.xml.get_object('menubar')
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
                if not gajim.account_is_connected(account):
                    continue
                current_show = gajim.SHOW_LIST[
                    gajim.connections[account].connected]
                self.roster.send_status(account, current_show, message)
            self.font_desc.set_weight(pango.WEIGHT_BOLD)
            widget.modify_font(self.font_desc)
            self.font_desc.set_weight(pango.WEIGHT_NORMAL)
            gobject.timeout_add(1000, widget.modify_font, self.font_desc)

    def on_activity_button_clicked(self, widget):
        def on_response(activity, subactivity, text):
            self.pep_dict['activity'] = activity or ''
            self.pep_dict['subactivity'] = subactivity or ''
            self.pep_dict['activity_text'] = text
            self.send_pep()
        ChangeActivityDialog(on_response, self.pep_dict.get('activity', None),
            self.pep_dict.get('subactivity', None),
            self.pep_dict.get('activity_text', None))

    def on_mood_button_clicked(self, widget):
        def on_response(mood, text):
            self.pep_dict['mood'] = mood or ''
            self.pep_dict['mood_text'] = text
            self.send_pep()
        ChangeMoodDialog(on_response, self.pep_dict.get('mood', None),
            self.pep_dict.get('mood_text', None))

    def send_pep(self):
        accounts = gajim.connections.keys()
        for account in accounts:
            if gajim.account_is_connected(account):
                self.roster.send_pep(account, self.pep_dict)


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
        self.plugin.roster.status_combobox.set_property('visible', not \
            self.plugin.config['hide_status_combo'])

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
            self.plugin.accel_group.disconnect_key(gtk.keysyms.m,
                    gtk.gdk.CONTROL_MASK)
            self.plugin.config['menu_visible'] = True
            self.plugin.roster.xml.get_object('menubar').set_size_request(-1, -1)

    def on_contact_status_subs_toggled(self, button):
        self.plugin.config['contact_status_subs'] = button.get_active()
        if self.plugin.active:
            self.plugin.roster.setup_and_draw_roster()
