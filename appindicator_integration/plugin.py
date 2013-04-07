# -*- coding: utf-8 -*-
"""
Appindicator integration plugin.

Rewriten from Ubuntu Ayatana Integration plugin
2013 Denis Borenko <borenko@rambler.ru>
:license: GPLv3     
"""
# Python
import time
#GTK
import gtkgui_helpers
import gtk
try:
    import appindicator
except: 
    appindicator = None
# Gajim
from common import gajim
from plugins import GajimPlugin
from plugins.plugin import GajimPluginException
from plugins.helpers import log_calls

    

class AppindicatorIntegrationPlugin(GajimPlugin):

    @log_calls("AppindicatorIntegrationPlugin")
    def init(self):
        self.description = _('This plugin integrates Gajim with the appindicator.\n'
            'You must have python-appindicator (and Gajim obviously) installed to enable this plugin.\n')
        self.config_dialog = None
        self.test_activatable()

    def test_activatable(self):
        self.available_text = ''
        if not appindicator:
            self.activatable = False
            self.available_text += _('\n\n Error: python-appindicator is missing! \n'
                'Please install it.\n')

    @log_calls("AppindicatorIntegrationPlugin")
    def activate(self):

        self.events={};

        self.show_gajim_menu_item = gtk.MenuItem('Show/hide roster')
        self.show_gajim_menu_item.connect("activate", self.roster_raise)
        self.show_gajim_menu_item.show()

        self.event_separator = gtk.SeparatorMenuItem();
        self.menuEventInsertIndex = 2;
        
        itemExitSeparator = gtk.SeparatorMenuItem()
        itemExitSeparator.show()
    
        itemExit = gtk.MenuItem('Exit')
        itemExit.connect("activate", self.on_exit_menuitem_activate)
        itemExit.show()
        
        self.menu = gtk.Menu()
        self.menu.append(self.show_gajim_menu_item)
        self.menu.append(self.event_separator)
        self.menu.append(itemExitSeparator)
        self.menu.append(itemExit)
        self.menu.show()
        
        self.indicator = appindicator.Indicator ("Gajim","tray-online", appindicator.CATEGORY_APPLICATION_STATUS)
        self.indicator.set_attention_icon ("tray-message")
        self.indicator.set_status (appindicator.STATUS_ACTIVE)
        self.indicator.set_menu(self.menu)

        gajim.events.event_added_subscribe(self.on_event_added)
        gajim.events.event_removed_subscribe(self.on_event_removed)

    @log_calls("AppindicatorPlugin")
    def deactivate(self):
        gajim.events.event_added_unsubscribe(self.on_event_added)
        gajim.events.event_removed_unsubscribe(self.on_event_removed)

        if hasattr(self, 'indicator'):
            self.indicator.set_status (appindicator.STATUS_PASSIVE)
            del self.indicator

    def roster_raise(self, widget, data=None):
        win = gajim.interface.roster.window
        if win.is_active():
            win.hide()
        else:
            win.present()

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
        when = time.time()
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
            contact = gajim.get_nick_from_jid(gajim.get_room_from_fjid(jid)) +\
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
                    icon = pixbuf
                else:
                    file_path = get_path_to_generic_or_avatar(jid)
                    if os.path.isfile(file_path):
                        fd = fopen(file_path, 'rb')
                        data = fd.read()
                        icon = gtkgui_helpers.get_pixbuf_from_data(data)
            item = gtk.ImageMenuItem(contact+" (1)")
            if icon:
                item.setImage(icon)
                item.set_always_show_image(True)
            item.connect("activate", self.event_raise, event)
            item.show()
            self.menu.insert(item, self.menuEventInsertIndex)
            self.event_separator.show()
            self.events[key] = {}
            self.events[key]['item']=item
            self.events[key]['contact']=contact
            self.events[key]['events']=[event]
        else:
            self.events[key]['events'].append(event)
            item = self.events[key]['item']
            item.set_label(self.events[key]['contact']+" ("+str(len(self.events[key]['events']))+")")
        self.indicator.set_status (appindicator.STATUS_ATTENTION)

    def on_event_removed(self, events):
        for event in events:
            key = (event.account, event.jid)
            if key in self.events and \
            event in self.events[key]['events']:
                self.events[key]['events'].remove(event)
                if len(self.events[key]['events']) == 0:  # remove indicator
                    self.menu.remove(self.events[key]['item'])
                    del self.events[key]
                    self.event_separator.hide()
                    self.indicator.set_status (appindicator.STATUS_ACTIVE)
                else:
                    self.events[key]['item'].connect("activate", self.event_raise, self.events[key]['events'][-1])