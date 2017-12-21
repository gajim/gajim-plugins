# -*- coding: utf-8 -*-
"""
Appindicator integration plugin.

Rewriten from Ubuntu Ayatana Integration plugin
2013 Denis Borenko <borenko@rambler.ru>
:license: GPLv3
"""
# Python
import os
import time
import gobject
# GTK
import gtkgui_helpers
import gtk
ERRORMSG = ''
try:
    import appindicator
except:
    ERRORMSG = 'python-appindicator is missing!<br/>Please install it.'
if os.name == 'nt':
    ERRORMSG = 'This is a Plugin for Linux'
# Gajim
from common import gajim, ged
from plugins import GajimPlugin
from plugins.plugin import GajimPluginException
from plugins.helpers import log_calls


class AppindicatorIntegrationPlugin(GajimPlugin):

    @log_calls("AppindicatorIntegrationPlugin")
    def init(self):
        if ERRORMSG:
            self.activatable = False
            self.available_text += _(ERRORMSG)
            return
        else:
            self.config_dialog = None
            self.events_handlers = {'our-show': (ged.GUI2,
                                                 self.set_indicator_icon)}
            self.windowstate = None

    @log_calls("AppindicatorIntegrationPlugin")
    def activate(self):

        self.events = {}

        self.attention_icon  = "mail-unread"
        self.online_icon     = "user-available"
        self.offline_icon    = "user-offline"
        self.connected       = 0

        self.connect_menu_item = gtk.MenuItem('Connect')
        self.connect_menu_item.connect("activate", self.connect)

        self.show_gajim_menu_item = gtk.MenuItem('Show/hide roster')
        self.show_gajim_menu_item.connect("activate", self.roster_raise)
        self.show_gajim_menu_item.show()

        self.event_separator = gtk.SeparatorMenuItem()
        self.menuEventInsertIndex = 3

        itemExitSeparator = gtk.SeparatorMenuItem()
        itemExitSeparator.show()

        itemExit = gtk.MenuItem('Exit')
        itemExit.connect("activate", self.on_exit_menuitem_activate)
        itemExit.show()

        self.menu = gtk.Menu()
        self.menu.append(self.connect_menu_item)
        self.menu.append(self.show_gajim_menu_item)
        self.menu.append(self.event_separator)
        self.menu.append(itemExitSeparator)
        self.menu.append(itemExit)
        self.menu.show()

        self.indicator = appindicator.Indicator("Gajim", self.offline_icon,
            appindicator.CATEGORY_APPLICATION_STATUS)
        self.indicator.set_attention_icon(self.attention_icon)
        self.indicator.set_status(appindicator.STATUS_ACTIVE)
        self.indicator.set_menu(self.menu)

        self.set_indicator_icon()

        gajim.events.event_added_subscribe(self.on_event_added)
        gajim.events.event_removed_subscribe(self.on_event_removed)

        self.roster = gajim.interface.roster.window
        self.handlerid = self.roster.connect('window-state-event',
                                             self.window_state_event_cb)

    def connect(self, widget, data=None):
        for account in gajim.connections:
            if gajim.config.get_per('accounts', account,
                                    'sync_with_global_status'):
                gajim.connections[account].change_status('online',
                                                         'online')

    def window_state_event_cb(self, win, event):
        if event.new_window_state & gtk.gdk.WINDOW_STATE_ICONIFIED:
            self.windowstate = 'iconified'
        elif event.new_window_state & gtk.gdk.WINDOW_STATE_WITHDRAWN:
            self.windowstate = 'hidden'

    def set_indicator_icon(self, obj=''):
        is_connected = 0
        for account in gajim.connections:
            if not gajim.config.get_per('accounts', account,
                                        'sync_with_global_status'):
                continue
            if gajim.account_is_connected(account):
                is_connected = 1
                break
        if self.connected != is_connected:
            self.connected = is_connected
            if self.connected == 1:
                self.indicator.set_icon(self.online_icon)
                self.connect_menu_item.hide()
            else:
                self.indicator.set_icon(self.offline_icon)
                self.connect_menu_item.show()

    @log_calls("AppindicatorPlugin")
    def deactivate(self):
        gajim.events.event_added_unsubscribe(self.on_event_added)
        gajim.events.event_removed_unsubscribe(self.on_event_removed)

        if hasattr(self, 'indicator'):
            self.indicator.set_status(appindicator.STATUS_PASSIVE)
            del self.indicator

        self.roster.disconnect(self.handlerid)

    def roster_raise(self, widget, data=None):
        win = gajim.interface.roster.window
        if win.get_property("visible") and self.windowstate != 'iconified':
            gobject.idle_add(win.hide)
        else:
            win.present()
            self.windowstate = 'shown'

        win.window.focus(gtk.get_current_event_time())

    def on_exit_menuitem_activate(self, widget, data=None):
            gajim.interface.roster.on_quit_request()

    def event_raise(self, widget, event):
        gajim.interface.handle_event(event.account, event.jid, event.type_)
        win = gajim.interface.roster.window
        if not win.is_active():
            win.present()

    def on_event_added(self, event):
        account = event.account
        jid = event.jid
        when = time.localtime()
        contact = ""
        key = (account, jid)

        if event.type_ == "chat" or \
        event.type_ == "printed_chat" or \
        event.type_ == "normal" or \
        event.type_ == "printed_normal" or \
        event.type_ == "file-request" or \
        event.type_ == "jingle-incoming":
            contact = gajim.contacts.get_contact_from_full_jid(account, jid)
            if contact:
                contact = contact.get_shown_name()
            else:
                contact = jid
        elif event.type_ == "pm" or event.type_ == "printed_pm":
            contact = gajim.get_nick_from_jid(gajim.get_room_from_fjid(jid)) + \
                    "/" + gajim.get_room_and_nick_from_fjid(jid)[1]
        elif event.type_ == "printed_marked_gc_msg":
            contact = gajim.get_nick_from_jid(gajim.get_room_from_fjid(jid))
        else:
            return
        #print account, jid, when, contact
        event.time = when
        if key not in self.events:
            icon = None
            if gajim.config.get("show_avatars_in_roster"):
                pixbuf = gtkgui_helpers.get_avatar_pixbuf_from_cache(jid)
                if pixbuf not in (None, "ask"):
                    icon = gtk.Image()
                    icon.set_from_pixbuf(pixbuf)
                else:
                    file_path = gtkgui_helpers.get_path_to_generic_or_avatar(jid)
                    if os.path.isfile(file_path):
                        fd = fopen(file_path, 'rb')
                        data = fd.read()
                        icon = gtk.Image()
                        icon.set_from_pixbuf(gtkgui_helpers.get_pixbuf_from_data(data))
            item = gtk.ImageMenuItem(contact + " (1)")
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
        self.indicator.set_status(appindicator.STATUS_ATTENTION)

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
                    self.indicator.set_status(appindicator.STATUS_ACTIVE)
