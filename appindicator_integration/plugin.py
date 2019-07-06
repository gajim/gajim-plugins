# -*- coding: utf-8 -*-
"""
Appindicator integration plugin.

Rewriten from Ubuntu Ayatana Integration plugin
2013 Denis Borenko <borenko@rambler.ru>
2017 Philipp Hörist <philipp@hoerist.com>
:license: GPLv3
"""

import time

import gi
from gi.repository import Gtk, GLib, Gdk

try:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as appindicator
    ERRORMSG = None
except (ValueError, ImportError):
    try:
        gi.require_version('AyatanaAppIndicator3', '0.1')
        from gi.repository import AyatanaAppIndicator3 as appindicator
        ERRORMSG = None
    except (ValueError, ImportError):
        ERRORMSG = 'Please install libappindicator3'

from gajim.common import app, ged
from gajim.common import configpaths
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls

# Since Gajim 1.1.0 _() has to be imported
try:
    from gajim.common.i18n import _
except ImportError:
    pass


class AppindicatorIntegrationPlugin(GajimPlugin):

    @log_calls("AppindicatorIntegrationPlugin")
    def init(self):
        if ERRORMSG:
            self.activatable = False
            self.available_text += ERRORMSG
            return
        self.config_dialog = None
        self.events_handlers = {'our-show': (ged.GUI2,
                                             self.set_indicator_icon)}
        self.windowstate = None

    @log_calls("AppindicatorIntegrationPlugin")
    def activate(self):

        self.events = {}

        self.online_icon = 'org.gajim.Gajim'
        self.offline_icon = 'org.gajim.Gajim-symbolic'
        self.connected = 0

        self.connect_menu_item = Gtk.MenuItem('Connect')
        self.connect_menu_item.connect("activate", self.connect)

        self.show_gajim_menu_item = Gtk.MenuItem('Show/hide roster')
        self.show_gajim_menu_item.connect("activate", self.roster_raise)
        self.show_gajim_menu_item.show()

        self.event_separator = Gtk.SeparatorMenuItem()
        self.menuEventInsertIndex = 3

        itemExitSeparator = Gtk.SeparatorMenuItem()
        itemExitSeparator.show()

        itemExit = Gtk.MenuItem('Exit')
        itemExit.connect("activate", self.on_exit_menuitem_activate)
        itemExit.show()

        self.menu = Gtk.Menu()
        self.menu.append(self.connect_menu_item)
        self.menu.append(self.show_gajim_menu_item)
        self.menu.append(self.event_separator)
        self.menu.append(itemExitSeparator)
        self.menu.append(itemExit)
        self.menu.show()

        self.indicator = appindicator.Indicator.new(
            'Gajim', self.offline_icon,
            appindicator.IndicatorCategory.COMMUNICATIONS)
        self.indicator.set_icon_theme_path(configpaths.get('ICONS'))
        self.indicator.set_attention_icon('mail-unread')
        self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.menu)

        self.set_indicator_icon()

        app.events.event_added_subscribe(self.on_event_added)
        app.events.event_removed_subscribe(self.on_event_removed)

        self.roster = app.interface.roster.window
        self.handlerid = self.roster.connect('window-state-event',
                                             self.window_state_event_cb)

    def connect(self, widget, data=None):
        for account in app.connections:
            if app.config.get_per('accounts', account,
                                  'sync_with_global_status'):
                app.connections[account].change_status('online',
                                                       'online')

    def window_state_event_cb(self, win, event):
        if event.new_window_state & Gdk.WindowState.ICONIFIED:
            self.windowstate = 'iconified'
        elif event.new_window_state & Gdk.WindowState.WITHDRAWN:
            self.windowstate = 'hidden'

    def set_indicator_icon(self, *args):
        is_connected = 0
        for account in app.connections:
            if not app.config.get_per('accounts', account,
                                      'sync_with_global_status'):
                continue
            if app.account_is_connected(account):
                is_connected = 1
                break
        if self.connected != is_connected:
            self.connected = is_connected
            if self.connected == 1:
                self.indicator.set_icon_full(self.online_icon, _('Online'))
                self.connect_menu_item.hide()
            else:
                self.indicator.set_icon_full(self.offline_icon, _('Offline'))
                self.connect_menu_item.show()

    @log_calls("AppindicatorPlugin")
    def deactivate(self):
        app.events.event_added_unsubscribe(self.on_event_added)
        app.events.event_removed_unsubscribe(self.on_event_removed)

        if hasattr(self, 'indicator'):
            self.indicator.set_status(appindicator.IndicatorStatus.PASSIVE)
            del self.indicator

        self.roster.disconnect(self.handlerid)

    def roster_raise(self, widget, data=None):
        win = app.interface.roster.window
        if win.get_property("visible") and self.windowstate != 'iconified':
            GLib.idle_add(win.hide)
        else:
            win.present()
            self.windowstate = 'shown'

    def on_exit_menuitem_activate(self, widget, data=None):
        app.interface.roster.on_quit_request()

    def event_raise(self, widget, event):
        app.interface.handle_event(event.account, event.jid, event.type_)
        win = app.interface.roster.window
        if not win.is_active():
            win.present()

    def on_event_added(self, event):
        account = event.account
        jid = event.jid
        when = time.time()
        contact = ""
        key = (account, jid)


        events = ['chat', 'printed_chat', 'printed_normal',
                  'normal', 'file-request', 'jingle-incoming']

        if event.type_ in events:
            contact = app.contacts.get_contact_from_full_jid(account, jid)
            if contact:
                contact = contact.get_shown_name()
            else:
                contact = jid
        elif event.type_ == "pm" or event.type_ == "printed_pm":
            contact = app.get_nick_from_jid(app.get_room_from_fjid(jid)) + \
                    "/" + app.get_room_and_nick_from_fjid(jid)[1]
        elif event.type_ == "printed_marked_gc_msg":
            contact = app.get_nick_from_jid(app.get_room_from_fjid(jid))
        else:
            return

        event.time = when
        if key not in self.events:
            icon = None
            if app.config.get("show_avatars_in_roster"):
                pix = app.contacts.get_avatar(account, jid, size=16)
                icon = Gtk.Image()
                icon.set_from_pixbuf(pix)
            item = Gtk.ImageMenuItem(contact + " (1)")
            if icon:
                item.set_image(icon)
                item.set_always_show_image(True)
            item.connect("activate", self.event_raise, event)
            item.show()
            self.menu.insert(item, self.menuEventInsertIndex)
            self.event_separator.show()
            self.events[key] = {}
            self.events[key]['item'] = item
            self.events[key]['contact'] = contact
            self.events[key]['events'] = [event]
        else:
            self.events[key]['events'].append(event)
            item = self.events[key]['item']
            item.set_label(self.events[key]['contact'] +
                " (" + str(len(self.events[key]['events'])) + ")")
        self.indicator.set_status(appindicator.IndicatorStatus.ATTENTION)

    def on_event_removed(self, events):
        for event in events:
            key = (event.account, event.jid)
            if key in self.events and event in self.events[key]['events']:
                self.events[key]['events'].remove(event)
                if len(self.events[key]['events']) == 0:  # remove indicator
                    self.menu.remove(self.events[key]['item'])
                    del self.events[key]
                else:
                    self.events[key]['item'].connect("activate",
                        self.event_raise, self.events[key]['events'][-1])
                if len(self.events) == 0:
                    self.event_separator.hide()
                    self.indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
