# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of OMEMO Gajim Plugin.
#
# OMEMO Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

# XEP-0384: OMEMO Encryption

import os
import time
import logging
import sqlite3

import nbxmpp
from nbxmpp.protocol import NodeProcessed
from nbxmpp.util import is_error_result
from nbxmpp.const import StatusCode
from nbxmpp.const import PresenceType
from nbxmpp.structs import StanzaHandler
from nbxmpp.modules.omemo import create_omemo_message

from gajim.common import app
from gajim.common import ged
from gajim.common import helpers
from gajim.common import configpaths
from gajim.common.nec import NetworkEvent
from gajim.common.const import EncryptionData
from gajim.common.modules.base import BaseModule
from gajim.common.modules.util import event_node

from omemo.backend.state import OmemoState
from omemo.backend.state import KeyExchangeMessage
from omemo.backend.state import SelfMessage
from omemo.backend.state import MessageNotForDevice
from omemo.backend.state import DecryptionFailed
from omemo.backend.state import DuplicateMessage
from omemo.modules.util import prepare_stanza


ALLOWED_TAGS = [
    ('request', nbxmpp.NS_RECEIPTS),
    ('active', nbxmpp.NS_CHATSTATES),
    ('gone', nbxmpp.NS_CHATSTATES),
    ('inactive', nbxmpp.NS_CHATSTATES),
    ('paused', nbxmpp.NS_CHATSTATES),
    ('composing', nbxmpp.NS_CHATSTATES),
    ('no-store', nbxmpp.NS_MSG_HINTS),
    ('store', nbxmpp.NS_MSG_HINTS),
    ('no-copy', nbxmpp.NS_MSG_HINTS),
    ('no-permanent-store', nbxmpp.NS_MSG_HINTS),
    ('replace', nbxmpp.NS_CORRECT),
    ('thread', None),
    ('origin-id', nbxmpp.NS_SID),
]

log = logging.getLogger('gajim.plugin_system.omemo')

ENCRYPTION_NAME = 'OMEMO'

# Module name
name = 'OMEMO'
zeroconf = False


class OMEMO(BaseModule):

    _nbxmpp_extends = 'OMEMO'
    _nbxmpp_methods = [
        'set_devicelist',
        'request_devicelist',
        'set_bundle',
        'request_bundle',
    ]

    def __init__(self, con):
        BaseModule.__init__(self, con)

        self.handlers = [
            StanzaHandler(name='message',
                          callback=self._message_received,
                          ns=nbxmpp.NS_OMEMO_TEMP,
                          priority=9),
            StanzaHandler(name='presence',
                          callback=self._on_muc_user_presence,
                          ns=nbxmpp.NS_MUC_USER,
                          priority=48),
        ]

        self._register_pubsub_handler(self._devicelist_notification_received)

        self.available = True
        # self.plugin = plugin
        self.own_jid = self._con.get_own_jid().getStripped()
        self.omemo = self.__get_omemo()

        self.groupchat = {}
        self.temp_groupchat = {}
        self.gc_message = {}
        self.query_for_bundles = []
        self.query_for_devicelists = []

        app.ged.register_event_handler('signed-in', ged.PRECORE,
                                       self.signed_in)
        app.ged.register_event_handler('muc-config-changed', ged.GUI2,
                                       self._on_config_changed)

    def get_own_jid(self, stripped=False):
        if stripped:
            return self._con.get_own_jid().getStripped()
        return self._con.get_own_jid()

    def __get_omemo(self):
        data_dir = configpaths.get('MY_DATA')
        db_path = os.path.join(data_dir, 'omemo_' + self.own_jid + '.db')
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA secure_delete=1")
        return OmemoState(self.own_jid, conn, self._account, self)

    def signed_in(self, event):
        if event.conn.name != self._account:
            return

        log.info('%s => Announce Support after Sign In', self._account)
        self.query_for_bundles = []
        self.set_bundle()
        self.request_devicelist()

    def activate(self):
        """ Method called when the Plugin is activated in the PluginManager
        """
        if app.caps_hash[self._account] != '':
            # Gajim has already a caps hash calculated, update it
            helpers.update_optional_features(self._account)

        if app.account_is_connected(self._account):
            log.info('%s => Announce Support after Plugin Activation',
                     self._account)
            self.query_for_bundles = []
            self.set_bundle()
            self.request_devicelist()

    def deactivate(self):
        """ Method called when the Plugin is deactivated in the PluginManager
        """
        self.query_for_bundles = []

    @staticmethod
    def update_caps(account):
        node = '%s+notify' % nbxmpp.NS_OMEMO_TEMP_DL
        if node not in app.gajim_optional_features[account]:
            app.gajim_optional_features[account].append(node)

    def _message_received(self, _con, stanza, properties):
        if not properties.is_omemo:
            return

        if properties.is_mam_message:
            from_jid = self._process_mam_message(properties)
        elif properties.from_muc:
            from_jid = self._process_muc_message(properties)
        else:
            from_jid = properties.jid.getBare()

        if from_jid is None:
            return

        log.info('%s => Message received from: %s', self._account, from_jid)

        try:
            return self.omemo.decrypt_message(properties.omemo,
                                              from_jid)
        except (KeyExchangeMessage, DuplicateMessage):
            raise NodeProcessed

        except SelfMessage:
            if properties.from_muc:
                if properties.omemo.payload in self.gc_message:
                    plaintext = self.gc_message[properties.omemo.payload]
                    del self.gc_message[properties.omemo.payload]
                    return plaintext

                log.warning("%s => Can't decrypt own GroupChat Message",
                            self._account)
            raise NodeProcessed

        except (DecryptionFailed, MessageNotForDevice):
            return

        prepare_stanza(stanza, plaintext)
        self._debug_print_stanza(stanza)
        properties.encrypted = EncryptionData({'name': ENCRYPTION_NAME})

    def _process_muc_message(self, properties):
        room_jid = properties.jid.getBare()
        resource = properties.jid.getResource()
        if properties.muc_ofrom is not None:
            # History Message from MUC
            return properties.muc_ofrom.getBare()

        try:
            return self.groupchat[room_jid][resource]
        except KeyError:
            log.info('%s => Groupchat: Last resort trying to '
                     'find SID in DB', self._account)
            from_jid = self.omemo.store.getJidFromDevice(properties.omemo.sid)
            if not from_jid:
                log.error("%s => Can't decrypt GroupChat Message "
                          "from %s", self._account, resource)
                return
            self.groupchat[room_jid][resource] = from_jid
            return from_jid

    def _process_mam_message(self, properties):
        log.info('%s => Message received, archive: %s',
                 self._account, properties.mam.archive)
        from_jid = properties.jid.getBare()
        if properties.from_muc:
            log.info('%s => MUC MAM Message received', self._account)
            if properties.muc_user.jid is None:
                log.info('%s => No real jid found', self._account)
                return
            from_jid = properties.muc_user.jid.getBare()
        return from_jid

    def _on_muc_user_presence(self, _con, _stanza, properties):
        if properties.type == PresenceType.ERROR:
            return

        if properties.is_muc_destroyed:
            return

        room = properties.jid.getBare()
        nick = properties.muc_nickname
        status_codes = properties.muc_status_codes or []

        jid = properties.muc_user.jid
        if jid is None:
            # No real jid found
            return

        jid = jid.getBare()

        if properties.is_nickname_changed:
            new_nick = properties.muc_user.nick

            if room in self.groupchat:
                if nick in self.groupchat[room]:
                    del self.groupchat[room][nick]
                self.groupchat[room][new_nick] = jid
                log.debug('Nick Change: old: %s, new: %s, jid: %s ',
                          nick, new_nick, jid)
                log.debug('Members after Change:  %s', self.groupchat[room])
            else:
                if nick in self.temp_groupchat[room]:
                    del self.temp_groupchat[room][nick]
                self.temp_groupchat[room][new_nick] = jid

            return

        if room not in self.groupchat:
            if room not in self.temp_groupchat:
                self.temp_groupchat[room] = {}

            if nick not in self.temp_groupchat[room]:
                self.temp_groupchat[room][nick] = jid

        else:
            # Check if we received JID over Memberlist
            if jid in self.groupchat[room]:
                del self.groupchat[room][jid]

            # Add JID with Nick
            if nick not in self.groupchat[room]:
                self.groupchat[room][nick] = jid
                log.debug('JID Added: %s', jid)

            if not self.is_contact_in_roster(jid):
                # Query Devicelists from JIDs not in our Roster
                log.info('%s not in Roster, query devicelist...', jid)
                self.request_devicelist(jid)

        if properties.is_muc_self_presence:
            if StatusCode.NON_ANONYMOUS in status_codes:
                # non-anonymous Room (Full JID)
                if room not in self.groupchat:
                    self.groupchat[room] = self.temp_groupchat[room]

                log.info('OMEMO capable Room found: %s', room)
                self.get_affiliation_list(room)

    def get_affiliation_list(self, room_jid):
        for affiliation in ('owner', 'admin', 'member'):
            self._nbxmpp('MUC').get_affiliation(
                room_jid,
                affiliation,
                callback=self._on_affiliations_received,
                user_data=room_jid)

    def _on_affiliations_received(self, result, room_jid):
        if is_error_result(result):
            log.info('Affiliation request failed: %s', result)
            return

        log.info('Room %s Memberlist received', room_jid)
        if room_jid not in self.groupchat:
            self.groupchat[room_jid] = {}

        def jid_known(jid):
            for nick in self.groupchat[room_jid]:
                if self.groupchat[room_jid][nick] == jid:
                    return True
            return False

        for user_jid in result.users:
            try:
                jid = helpers.parse_jid(user_jid)
            except helpers.InvalidFormat:
                log.warning('Invalid JID: %s, ignoring it', user_jid)
                continue

            if not jid_known(jid):
                # Add JID with JID because we have no Nick yet
                self.groupchat[room_jid][jid] = jid
                log.info('JID Added: %s', jid)

            if not self.is_contact_in_roster(jid):
                # Query Devicelists from JIDs not in our Roster
                log.info('%s not in Roster, query devicelist...', jid)
                self.request_devicelist(jid)

    def is_contact_in_roster(self, jid):
        if jid == self.own_jid:
            return True
        contact = app.contacts.get_first_contact_from_jid(self._account, jid)
        if contact is None:
            return False
        return contact.sub == 'both'

    def _on_config_changed(self, event):
        if event.account != self._account:
            return

        room = event.jid.getBare()
        status_codes = event.status_codes or []
        if StatusCode.CONFIG_NON_ANONYMOUS in status_codes:
            if room not in self.groupchat:
                self.groupchat[room] = self.temp_groupchat[room]
            log.info('Room config change: non-anonymous')

    def gc_encrypt_message(self, conn, event, callback):
        if event.conn.name != self._account:
            return

        if not event.message:
            callback(event)
            return

        to_jid = app.get_jid_without_resource(event.jid)

        try:
            omemo_message = self.omemo.create_gc_msg(
                self.own_jid, to_jid, event.message)
            if omemo_message is None:
                raise OMEMOError('Error while encrypting')

        except OMEMOError as error:
            log.error(error)
            app.nec.push_incoming_event(
                NetworkEvent(
                    'message-not-sent', conn=conn, jid=event.jid, message=event.message,
                    error=error, time_=time.time(), session=None))
            return

        self.gc_message[omemo_message.payload] = event.message
        create_omemo_message(event.msg_iq, omemo_message,
                             node_whitelist=ALLOWED_TAGS)

        self._debug_print_stanza(event.msg_iq)
        callback(event)

    def encrypt_message(self, conn, event, callback):
        if event.conn.name != self._account:
            return

        if not event.message:
            callback(event)
            return

        to_jid = app.get_jid_without_resource(event.jid)

        try:
            omemo_message = self.omemo.create_msg(to_jid, event.message)
            if omemo_message is None:
                raise OMEMOError('Error while encrypting')

        except OMEMOError as error:
            log.error(error)
            app.nec.push_incoming_event(
                NetworkEvent(
                    'message-not-sent', conn=conn, jid=event.jid, message=event.message,
                    error=error, time_=time.time(), session=event.session))
            return

        create_omemo_message(event.msg_iq, omemo_message,
                             node_whitelist=ALLOWED_TAGS)

        self._debug_print_stanza(event.msg_iq)
        event.xhtml = None
        event.encrypted = ENCRYPTION_NAME
        event.additional_data['encrypted'] = {'name': ENCRYPTION_NAME}
        callback(event)

    def are_keys_missing(self, contact_jid):
        """ Checks if devicekeys are missing and queries the
            bundles

            Parameters
            ----------
            contact_jid : str
                bare jid of the contact

            Returns
            -------
            bool
                Returns True if there are no trusted Fingerprints
        """

        # Fetch Bundles of own other Devices
        if self.own_jid not in self.query_for_bundles:

            devices_without_session = self.omemo \
                .devices_without_sessions(self.own_jid)

            self.query_for_bundles.append(self.own_jid)

            if devices_without_session:
                for device_id in devices_without_session:
                    self.request_bundle(self.own_jid, device_id)

        # Fetch Bundles of contacts devices
        if contact_jid not in self.query_for_bundles:

            devices_without_session = self.omemo \
                .devices_without_sessions(contact_jid)

            self.query_for_bundles.append(contact_jid)

            if devices_without_session:
                for device_id in devices_without_session:
                    self.request_bundle(contact_jid, device_id)

        if self.omemo.getTrustedFingerprints(contact_jid):
            return False
        return True

    def set_bundle(self):
        self._nbxmpp('OMEMO').set_bundle(self.omemo.bundle,
                                         self.omemo.own_device_id)

    def request_bundle(self, jid, device_id):
        log.info('%s => Fetch device bundle %s %s',
                 self._account, device_id, jid)

        self._nbxmpp('OMEMO').request_bundle(
            jid,
            device_id,
            callback=self._bundle_received,
            user_data=(jid, device_id))

    def _bundle_received(self, bundle, user_data):
        jid, device_id = user_data
        if is_error_result(bundle):
            log.info('%s => Bundle request failed: %s %s: %s',
                     self._account, jid, device_id, bundle)
            return

        if self.omemo.build_session(jid, device_id, bundle):
            log.info('%s => session created for: %s',
                     self._account, jid)
            # Trigger dialog to trust new Fingerprints if
            # the Chat Window is Open
            ctrl = app.interface.msg_win_mgr.get_control(
                jid, self._account)
            if ctrl:
                app.nec.push_incoming_event(
                    NetworkEvent('omemo-new-fingerprint', chat_control=ctrl))

    def set_devicelist(self, new=False):
        """ Get all currently known own active device ids and publish them

            Parameters
            ----------
            new : bool
                if True, a devicelist with only the id of this device
                is published
        """
        if new:
            devicelist = [self.omemo.own_device_id]
        else:
            devicelist = self.omemo.own_devices
            devicelist.append(self.omemo.own_device_id)
            devicelist = list(set(devicelist))
        self.omemo.set_own_devices(devicelist)
        log.info('%s => Publishing own devicelist: %s',
                 self._account, devicelist)
        self._nbxmpp('OMEMO').set_devicelist(devicelist)

    def request_devicelist(self, jid=None, fetch_bundle=False):
        if jid in self.query_for_devicelists:
            return

        self._nbxmpp('OMEMO').request_devicelist(
            jid,
            callback=self._devicelist_received,
            user_data=(jid, fetch_bundle))
        self.query_for_devicelists.append(jid)

    def _devicelist_received(self, devicelist, user_data):
        jid, fetch_bundle = user_data
        if is_error_result(devicelist):
            log.info('%s => Devicelist request failed: %s %s',
                     self._account, jid, devicelist)
            devicelist = []

        self._process_devicelist_update(jid, devicelist, fetch_bundle)

    @event_node(nbxmpp.NS_OMEMO_TEMP_DL)
    def _devicelist_notification_received(self, _con, _stanza, properties):
        devicelist = []
        if not properties.pubsub_event.empty:
            devicelist = properties.pubsub_event.data

        self._process_devicelist_update(str(properties.jid), devicelist, False)

    def _process_devicelist_update(self, jid, devicelist, fetch_bundle):
        if jid is None or self._con.get_own_jid().bareMatch(jid):
            log.info('%s => Received own device list: %s',
                     self._account, devicelist)
            self.omemo.set_own_devices(devicelist)
            self.omemo.store.setActiveState(devicelist, self.own_jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if jid in self.query_for_bundles:
                self.query_for_bundles.remove(jid)

            if not self.omemo.own_device_id_published():
                # Our own device_id is not in the list, it could be
                # overwritten by some other client
                self.set_devicelist()

        else:
            log.info('%s => Received device list for %s: %s',
                     self._account, jid, devicelist)
            self.omemo.set_devices(jid, devicelist)
            self.omemo.store.setActiveState(devicelist, jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if jid in self.query_for_bundles:
                self.query_for_bundles.remove(jid)

            if fetch_bundle:
                self.are_keys_missing(jid)

    @staticmethod
    def _debug_print_stanza(stanza):
        log.debug('-'*15)
        stanzastr = '\n' + stanza.__str__(fancy=True)
        stanzastr = stanzastr[0:-1]
        log.debug(stanzastr)
        log.debug('-'*15)


class OMEMOError(Exception):
    pass


def get_instance(*args, **kwargs):
    return OMEMO(*args, **kwargs), 'OMEMO'
