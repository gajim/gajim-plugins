# -*- coding: utf-8 -*-

import dbus
import gobject
import datetime as dt
from common import gajim
from common import ged
from common import dbus_support

from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from common.pep import ACTIVITIES

HAMSTAER_INTERFACE = 'org.gnome.Hamster'
SUBACTIVITIES = []
subactivity_ = [ACTIVITIES[x].keys() for x in ACTIVITIES.keys()]
for x in subactivity_ :
    SUBACTIVITIES = SUBACTIVITIES + x
SUBACTIVITIES = set(SUBACTIVITIES)
SUBACTIVITIES.remove('category')
XMPP_ACTIVITIES = set(ACTIVITIES.keys())

class HamsterIntegrationPlugin(GajimPlugin):

    @log_calls('HamsterIntegrationPlugin')
    def init(self):
        self.description = _('Integration with project hamster\n'
        'see https://trac.gajim.org/ticket/6993\n'
        'and http://projecthamster.wordpress.com/about/')
        self.config_dialog = None
        self.events_handlers = {}

    @log_calls('HamsterIntegrationPlugin')
    def activate(self):
        if not dbus_support.supported:
            return

        self.bus = dbus_support.session_bus.SessionBus()
        try:
            self.session_presence = self.bus.get_object(HAMSTAER_INTERFACE,
                '/org/gnome/Hamster')
        except:
            gajim.log.debug('Hamster D-Bus service not found')
            return

        self.active = True
        self.bus.add_signal_receiver(self.hamster_facts_changed, 'FactsChanged',
            HAMSTAER_INTERFACE)
        gajim.ged.register_event_handler('our-show', ged.POSTGUI,
            self.on_our_status)
        self.pep_dict ={}

    @log_calls('HamsterIntegrationPlugin')
    def deactivate(self):
        if not dbus_support.supported or not self.active:
            return

        self.active = False
        self.bus.remove_signal_receiver(self.hamster_facts_changed, "FactsChanged",
                                        dbus_interface=HAMSTAER_INTERFACE)

    def hamster_facts_changed(self, *args, **kw):
        # get hamster tags
        facts = self.session_presence.GetTodaysFacts(
            dbus_interface=HAMSTAER_INTERFACE)

        if self.from_dbus_fact(facts[-1])['end_time']:
            accounts = gajim.connections.keys()
            for account in accounts:
                if gajim.account_is_connected(account):
                    connection = gajim.connections[account]
                    connection.retract_activity()
            return

        last_fact = self.from_dbus_fact(facts[-1])
        tags = set(last_fact['tags'])

        activity = "Other"
        activity_candidates = XMPP_ACTIVITIES.intersection(tags)
        if len(activity_candidates) >= 1:
            activity=list(activity_candidates)[0]
        subactivity = 'other'
        subactivity_candidates = SUBACTIVITIES.intersection(tags)
        if len(subactivity_candidates) >= 1:
            subactivity=list(subactivity_candidates)[0]

        # send activity
        accounts = gajim.connections.keys()
        for account in accounts:
            if gajim.account_is_connected(account):
                connection = gajim.connections[account]
                connection.send_activity(activity, subactivity,
                    last_fact['fact'])

    def from_dbus_fact(self, fact):
        '''unpack the struct into a proper dict'''
        return dict(fact = fact[4],
            start_time  = dt.datetime.utcfromtimestamp(fact[1]),
            end_time = dt.datetime.utcfromtimestamp(fact[2]) if fact[2] else None,
            description = fact[3],
            activity_id = fact[5],
            category = fact[6],
            tags = fact[7],
            date = dt.datetime.utcfromtimestamp(fact[8]).date(),
            delta = dt.timedelta(days = fact[9] // (24 * 60 * 60),
            seconds = fact[9] % (24 * 60 * 60)),
            id = fact[0])

    def on_our_status(self, network_event):
        gajim.ged.remove_event_handler('our-show', ged.POSTGUI,
            self.on_our_status)
        gobject.timeout_add(10000, self.hamster_facts_changed)
