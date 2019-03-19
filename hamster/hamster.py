import os
import dbus
import datetime as dt
import logging

from gi.repository import GObject

from gajim.common import app
from gajim.common import ged
from gajim.common import dbus_support

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.plugins_i18n import _
from gajim.common.const import ACTIVITIES

log = logging.getLogger('gajim.p.hamster')


HAMSTAER_INTERFACE = 'org.gnome.Hamster'
SUBACTIVITIES = []
subactivity_ = [list(ACTIVITIES[x].keys()) for x in list(ACTIVITIES.keys())]
for x in subactivity_ :
    SUBACTIVITIES = SUBACTIVITIES + x
SUBACTIVITIES = set(SUBACTIVITIES)
SUBACTIVITIES.remove('category')
XMPP_ACTIVITIES = set(ACTIVITIES.keys())

class HamsterIntegrationPlugin(GajimPlugin):

    @log_calls('HamsterIntegrationPlugin')
    def init(self):
        self.description = _('Integration with project hamster, see '
                             'http://projecthamster.org/')
        self.config_dialog = None
        self.events_handlers = {}
        if os.name == 'nt':
            self.available_text = _('Plugin can\'t be run under Windows.')
            self.activatable = False

    @log_calls('HamsterIntegrationPlugin')
    def activate(self):
        if not dbus_support.supported:
            return

        self.bus = dbus_support.session_bus.SessionBus()
        try:
            self.session_presence = self.bus.get_object(HAMSTAER_INTERFACE,
                '/org/gnome/Hamster')
        except:
            log.debug('Hamster D-Bus service not found')
            return

        self.bus.add_signal_receiver(self.hamster_facts_changed, 'FactsChanged',
            HAMSTAER_INTERFACE)
        app.ged.register_event_handler('signed-in', ged.POSTGUI,
            self.on_signed_in)

    @log_calls('HamsterIntegrationPlugin')
    def deactivate(self):
        if not dbus_support.supported or not self.active:
            return

        self.bus.remove_signal_receiver(self.hamster_facts_changed,
            "FactsChanged", dbus_interface=HAMSTAER_INTERFACE)
        app.ged.remove_event_handler('signed-in', ged.POSTGUI,
            self.on_signed_in)

    def hamster_facts_changed(self, *args, **kw):
        # get hamster tags
        facts = self.session_presence.GetTodaysFacts(
            dbus_interface=HAMSTAER_INTERFACE)
        if not facts:
            return
        if self.from_dbus_fact(facts[-1])['end_time']:
            accounts = list(app.connections.keys())
            for account in accounts:
                if app.account_is_connected(account):
                    connection = app.connections[account]
                    connection.get_module('UserActivity').send(None)
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
        for account in app.connections:
            if app.account_is_connected(account):
                connection = app.connections[account]
                connection.get_module('UserActivity').send(
                    (activity, subactivity, last_fact['fact']))

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

    def on_signed_in(self, network_event):
        GObject.timeout_add(5000,self.hamster_facts_changed)
