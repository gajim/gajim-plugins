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
* corrent group chat handling
* hide gajim if the plugin is disabled

:author: Michael Kainer <kaini@linuxlovers.at>
:since: 21st October 2010
:copyright: Copyright (2010) Michael Kainer <kaini1123@gmail.com>
:license: GPLv3
"""
# Python
import time
# Gajim
from plugins import GajimPlugin
from plugins.plugin import GajimPluginException
from plugins.helpers import log_calls
from common import gajim
import gtkgui_helpers
try:
    from xdg.BaseDirectory import load_data_paths
    import indicate
except ImportError:
    pass


class UbuntuIntegrationPlugin(GajimPlugin):
    """
    Class for Messaging Menu and Me Menu.
    """

    @log_calls("UbuntuIntegrationPlugin")
    def init(self):
        """
        Does nothing.
        """
        self.config_dialog = None
        self.test_activatable()

    def test_activatable(self):
        self.available_text = ''
        try:
            from xdg.BaseDirectory import load_data_paths
        except ImportError:
            self.activatable = False
            self.available_text += _('python-xdg is missing! '
                'Install python-xdg.\n')
        try:
            import indicate
        except ImportError:
            self.activatable = False
            self.available_text += _('python-indicate is missing! '
                'Install python-indicate.')

    def show_roster_window(a, b, c):
        roster = gajim.interface.roster.window
        roster.present()

    @log_calls("UbuntuIntegrationPlugin")
    def activate(self):
        """
        Displays gajim in the Messaging Menu.
        """
        # {(account, jid): (indicator, [event, ...]), ...}
        self.events = {}

        version = gajim.version.split('-')[0]
        if version == '0.15' and self.available_text:
            raise GajimPluginException(self.available_text)

        self.server = indicate.indicate_server_ref_default()
        self.server.set_type("message.im")
        dfile = ""
        for file in load_data_paths("applications/gajim.desktop"):
            dfile = file
            break
        if not dfile:
            raise GajimPluginException("Can't locate gajim.desktop!")
        self.server.set_desktop_file(dfile)
        roster = gajim.interface.roster.window
        self.server.connect('server-display', self.show_roster_window)
        self.server.show()

        gajim.events.event_added_subscribe(self.on_event_added)
        gajim.events.event_removed_subscribe(self.on_event_removed)

    @log_calls("UbuntuIntegrationPlugin")
    def deactivate(self):
        """
        Cleaning up.
        """
        gajim.events.event_added_unsubscribe(self.on_event_added)
        gajim.events.event_removed_unsubscribe(self.on_event_removed)

        if hasattr(self, 'server'):
            self.server.hide()
            del self.server

        if hasattr(self, 'events'):
            for (_, event) in self.events:
                event[0].hide()
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
        key = (account, jid)

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
            contact = gajim.get_nick_from_jid(gajim.get_room_from_fjid(jid)) +\
                    "/" + gajim.get_room_and_nick_from_fjid(jid)[1]
        elif event.type_ == "printed_marked_gc_msg":
            contact = gajim.get_nick_from_jid(gajim.get_room_from_fjid(jid))
        else:
            print "ignored"
            return

        print account, jid, when, contact

        # Add a new indicator if necessary
        if key not in self.events:
            indicator = indicate.Indicator()
            indicator.set_property("name", contact)
            indicator.set_property_time("time", when)
            indicator.set_property_bool("draw-attention", True)
            if gajim.config.get("show_avatars_in_roster"):
                pixbuf = gtkgui_helpers.get_avatar_pixbuf_from_cache(jid)
                if pixbuf not in (None, "ask"):
                    indicator.set_property_icon("icon", pixbuf)
            indicator.connect("user-display", self.on_indicator_activate)
            indicator.show()
            indicator.key = key
            self.events[key] = (indicator, [])

        # Prepare the event and save it
        event.time = when
        self.events[key][1].append(event)

    def on_event_removed(self, events):
        """
        Goes through the events and removes them from the array and
        the indicator if there are no longer any events pending.
        """
        for event in events:
            print "====", event.type_

            key = (event.account, event.jid)

            if key not in self.events and \
            event in self.events[key][1]:
                self.events[key][1].remove(event)

                if len(self.events[key][1]) == 0:  # remove indicator
                    self.events[key][0].hide()
                    del self.events[key]
                else:  # set the indicator time to the text event
                    self.events[key][0].set_property_time("time",
                            self.events[key][1][0].time)
            else:
                print "ignored"
