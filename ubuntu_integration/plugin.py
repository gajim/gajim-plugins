# -*- coding: utf-8 -*-
"""
Ubuntu Ayatana Integration plugin.

TODO:
* handle gc-invitation, subscription_request: it looks like they don't fire
* nice error if plugin can't load
* me menu
* permanent integration into the messaging menu after quitting gajim
* show/hide gajim on root menu entry
* switch workspace on click on events
* pictures in the menu
* hide gajim if the plugin is disabled

:author: Michael Kainer <kaini@jabber.hot-chilli.net>
:since: 21st October 2010
:copyright: Copyright (2010) Michael Kainer <kaini1123@gmx.at>
:license: GPLv3
"""
# Python
import time
import os
# Gajim
from plugins import GajimPlugin
from plugins.plugin import GajimPluginException
from plugins.helpers import log, log_calls
from common import ged
from common import gajim
# 3rd party
try:
    import indicate
    HAS_INDICATE = True
except:
    HAS_INDICATE = False
try:
    from xdg.DesktopEntry import DesktopEntry
    from xdg.BaseDirectory import load_data_paths
    HAS_PYXDG = True
except:
    HAS_PYXDG = False

class UbuntuIntegrationPlugin(GajimPlugin):
    """
    Class for Messaging Menu and Me Menu.
    """
    
    @log_calls("UbuntuIntegrationPlugin")
    def init(self):
        """
        Does nothing.
        """
        pass
    
    @log_calls("UbuntuIntegrationPlugin")
    def activate(self):
        """
        Displays gajim in the Messaging Menu.
        """
        if not HAS_INDICATE:
            raise GajimPluginException("python-indicate is missing!")
        if not HAS_PYXDG:
            raise GajimPluginException("python-xdg is missing!")
        
        self.server = indicate.indicate_server_ref_default()
        self.server.set_type("message.im")
        dfile = ""
        for file in load_data_paths("applications/gajim.desktop"):
            dfile = file
            break
        if not dfile:
            raise GajimPluginException("Can't locate gajim.desktop!")
        self.server.set_desktop_file(dfile)
        self.server.show()
        
        # {(account, jid): (indicator, [event, ...]), ...}
        self.events = {}
        
        gajim.events.event_added_subscribe(self.on_event_added)
        gajim.events.event_removed_subscribe(self.on_event_removed)
        
    @log_calls("UbuntuIntegrationPlugin")
    def deactivate(self):
        """
        Cleaning up.
        """
        gajim.events.event_added_unsubscribe(self.on_event_added)
        gajim.events.event_removed_unsubscribe(self.on_event_removed)
        
        for (_, event) in self.events:
            event[0].hide()
        self.server.hide()
        
        del self.server
        del self.events
    
    def on_indicator_activate(self, indicator, _):
        """
        Forwards the action to gajims event handler.
        """
        key = indicator.key
        event = self.events[key][1][0]
        gajim.interface.handle_event(event.account, event.jid, event.type_)
    
    def on_event_added(self, event):
        """
        Adds "Nickname Time" to the Messaging menu.
        """
        print "----", event.type_
        
        # Basic variables
        account = event.account
        jid = event.jid
        when = time.time()
        contact = ""
        
        # Check if the event is valid and modify the variables
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
            print "ignored";
            return
        
        print account, jid, when, contact
        
        # Add a new indicator if necessary
        key = (account, jid)
        if not self.events.has_key(key):
            indicator = indicate.Indicator()
            indicator.set_property("name", contact)
            indicator.set_property_time("time", when)
            indicator.set_property_bool("draw-attention", True);
            indicator.connect("user-display", self.on_indicator_activate)
            indicator.show()
            indicator.key = key
            self.events[key] = (indicator, [])
        
        # Prepare the event and save it
        event.time = when
        self.events[key][1].append(event);
    
    def on_event_removed(self, events):
        """
        Goes through the events and removes them from the array and
        the indicator if there are no longer any events pending.
        """
        for event in events:
            print "====", event.type_
            
            key = (event.account, event.jid)
            
            if self.events.has_key(key) and \
            event in self.events[key][1]:
                self.events[key][1].remove(event)
                
                if len(self.events[key][1]) == 0: # remove indicator
                    self.events[key][0].hide()
                    del self.events[key]
                else: # set the indicator time to the text event
                    self.events[key][0].set_property_time("time",
                            self.events[key][1][0].time)
            else:
                print "ignored"
