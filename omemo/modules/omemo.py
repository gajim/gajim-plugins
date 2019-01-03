# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of OMEMO.
#
# OMEMO is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO. If not, see <http://www.gnu.org/licenses/>.

# XEP-0384: OMEMO Encryption

import os
import time
import logging
import sqlite3

import nbxmpp
from nbxmpp.simplexml import Node
from nbxmpp.protocol import JID
from nbxmpp.const import StatusCode
from nbxmpp.const import PresenceType
from nbxmpp.structs import StanzaHandler

from gajim.common import app
from gajim.common import ged
from gajim.common import helpers
from gajim.common import configpaths
from gajim.common.nec import NetworkEvent

from gajim.plugins.plugins_i18n import _

from omemo.xmpp import (
    NS_NOTIFY, NS_OMEMO, NS_EME, NS_HINTS, NS_BUNDLES,
    BundleInformationQuery, DevicelistQuery, make_bundle,
    OmemoMessage, successful, unpack_device_bundle,
    unpack_device_list_update, unpack_encrypted, NS_DEVICE_LIST)
from omemo.omemo.state import OmemoState

ALLOWED_TAGS = [('request', nbxmpp.NS_RECEIPTS),
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


class OMEMO:
    def __init__(self, con):
        self._con = con
        self._account = con.name

        self.handlers = [
            StanzaHandler(name='presence',
                          callback=self._on_muc_user_presence,
                          ns=nbxmpp.NS_MUC_USER,
                          priority=48),
        ]
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

    def send_with_callback(self, stanza, callback, data=None):
        if data is None:
            self._con.connection.SendAndCallForResponse(stanza, callback)
        else:
            self._con.connection.SendAndCallForResponse(
                stanza, callback, data)

    def get_own_jid(self, stripped=False):
        if stripped:
            return self._con.get_own_jid().getStripped()
        return self._con.get_own_jid()

    def __get_omemo(self):
        """ Returns the the OmemoState for the specified account.
            Creates the OmemoState if it does not exist yet.

            Parameters
            ----------
            account : str
                the account name

            Returns
            -------
            OmemoState
        """
        data_dir = configpaths.get('MY_DATA')
        db_path = os.path.join(data_dir, 'omemo_' + self.own_jid + '.db')
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA secure_delete=1")
        return OmemoState(self.own_jid, conn, self._account, self)

    def signed_in(self, event):
        """ Method called on SignIn

            Parameters
            ----------
            event : SignedInEvent
        """
        if event.conn.name != self._account:
            return

        log.info('%s => Announce Support after Sign In', self._account)
        self.query_for_bundles = []
        self.publish_bundle()
        self.query_devicelist()

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
            self.publish_bundle()
            self.query_devicelist()

    def deactivate(self):
        """ Method called when the Plugin is deactivated in the PluginManager
        """
        self.query_for_bundles = []

    @staticmethod
    def update_caps(account):
        if NS_NOTIFY not in app.gajim_optional_features[account]:
            app.gajim_optional_features[account].append(NS_NOTIFY)

    def message_received(self, conn, obj, callback):
        if obj.encrypted:
            return
        if obj.name == 'message-received':
            self._message_received(obj)
        elif obj.name == 'mam-message-received':
            self._mam_message_received(obj)
        elif obj.name == 'mam-gc-message-received':
            self._mam_gc_message_received(obj)
        if obj.encrypted == 'OMEMO':
            callback(obj)

    def _mam_gc_message_received(self, event):
        """ Handles an incoming GC MAM message

            Payload is decrypted and the plaintext is written into the
            event object. Afterwards the event is passed on further to Gajim.

            Parameters
            ----------
            event : MamGcMessageReceivedEvent

            Returns
            -------
            Return means that the Event is passed on to Gajim
        """
        if event.conn.name != self._account:
            return

        # Compatibility for Gajim 1.0.3
        if hasattr(event, 'message'):
            message = event.message
        else:
            message = event.msg_

        omemo = message.getTag('encrypted', namespace=NS_OMEMO)
        if omemo is None:
            return

        if event.real_jid is None:
            log.error('%s => Received Groupchat Message without real jid',
                      self._account)
            return

        log.info('%s => Groupchat Message received', self._account)

        msg_dict = unpack_encrypted(omemo)
        msg_dict['sender_jid'] = JID(event.real_jid).getStripped()

        plaintext = self.omemo.decrypt_msg(msg_dict)

        if not plaintext:
            event.encrypted = 'drop'
            return

        self.print_msg_to_log(message)

        event.msgtxt = plaintext
        event.encrypted = ENCRYPTION_NAME
        self.add_additional_data(event.additional_data)

    def _mam_message_received(self, event):
        """ Handles an incoming MAM message

            Payload is decrypted and the plaintext is written into the
            event object. Afterwards the event is passed on further to Gajim.

            Parameters
            ----------
            event : MamMessageReceivedEvent

            Returns
            -------
            Return means that the Event is passed on to Gajim
        """
        if event.conn.name != self._account:
            return

        # Compatibility for Gajim 1.0.3
        if hasattr(event, 'message'):
            message = event.message
        else:
            message = event.msg_

        omemo_encrypted_tag = message.getTag('encrypted', namespace=NS_OMEMO)
        if omemo_encrypted_tag:
            log.debug('%s => OMEMO MAM msg received', self._account)

            msg_dict = unpack_encrypted(omemo_encrypted_tag)
            if msg_dict is None:
                log.error('Invalid omemo message received:\n%s', message)
                event.encrypted = 'drop'
                return

            msg_dict['sender_jid'] = message.getFrom().getStripped()

            plaintext = self.omemo.decrypt_msg(msg_dict)

            if not plaintext:
                event.encrypted = 'drop'
                return

            self.print_msg_to_log(message)

            event.msgtxt = plaintext
            event.encrypted = ENCRYPTION_NAME
            self.add_additional_data(event.additional_data)
            return

    def _message_received(self, msg):
        """ Handles an incoming message

            Payload is decrypted and the plaintext is written into the
            event object. Afterwards the event is passed on further to Gajim.

            Parameters
            ----------
            msg : MessageReceivedEvent

            Returns
            -------
            Return means that the Event is passed on to Gajim
        """
        if msg.conn.name != self._account:
            return
        if msg.stanza.getTag('encrypted', namespace=NS_OMEMO):
            log.debug('%s => OMEMO msg received', self._account)

            if msg.forwarded and msg.sent:
                from_jid = self.own_jid
                log.debug('Sent Carbon')
            else:
                from_jid = str(msg.stanza.getFrom())

            self.print_msg_to_log(msg.stanza)
            msg_dict = unpack_encrypted(msg.stanza.getTag
                                        ('encrypted', namespace=NS_OMEMO))

            if msg.mtype == 'groupchat':
                address_tag = msg.stanza.getTag('addresses',
                                                namespace=nbxmpp.NS_ADDRESS)
                if address_tag:  # History Message from MUC
                    from_jid = address_tag.getTag(
                        'address', attrs={'type': 'ofrom'}).getAttr('jid')
                else:
                    try:
                        from_jid = self.groupchat[msg.jid][msg.resource]
                    except KeyError:
                        log.debug('Groupchat: Last resort trying to '
                                  'find SID in DB')
                        from_jid = self.omemo.store. \
                            getJidFromDevice(msg_dict['sid'])
                        if not from_jid:
                            log.error("%s => Can't decrypt GroupChat Message "
                                      "from %s", self._account, msg.resource)
                            msg.encrypted = 'drop'
                            return
                        self.groupchat[msg.jid][msg.resource] = from_jid

                log.debug('GroupChat Message from: %s', from_jid)

            plaintext = ''
            if msg_dict['sid'] == self.omemo.own_device_id:
                if msg_dict['payload'] in self.gc_message:
                    plaintext = self.gc_message[msg_dict['payload']]
                    del self.gc_message[msg_dict['payload']]
                else:
                    log.error("%s => Can't decrypt own GroupChat Message",
                              self._account)
                    msg.encrypted = 'drop'
                    return
            else:
                msg_dict['sender_jid'] = app. \
                    get_jid_without_resource(from_jid)
                plaintext = self.omemo.decrypt_msg(msg_dict)

            if not plaintext:
                msg.encrypted = 'drop'
                return

            msg.msgtxt = plaintext
            # Gajim bug: there must be a body or the message
            # gets dropped from history
            msg.stanza.setBody(plaintext)
            msg.encrypted = ENCRYPTION_NAME
            self.add_additional_data(msg.additional_data)

    def room_memberlist_received(self, stanza):
        if not nbxmpp.isResultNode(stanza):
            log.error('Room %s Memberlist received: %s',
                      stanza.getFrom(), stanza.getError())
            return

        room_jid = stanza.getFrom().getStripped()
        log.info('Room %s Memberlist received', room_jid)
        if room_jid not in self.groupchat:
            self.groupchat[room_jid] = {}

        def jid_known(jid):
            for nick in self.groupchat[room_jid]:
                if self.groupchat[room_jid][nick] == jid:
                    return True
            return False

        items = stanza.getTag(
            'query', namespace=nbxmpp.NS_MUC_ADMIN).getTags('item')

        for item in items:
            if not item.has_attr('jid'):
                continue
            try:
                jid = helpers.parse_jid(item.getAttr('jid'))
            except helpers.InvalidFormat:
                log.warning(
                    'Invalid JID: %s, ignoring it', item.getAttr('jid'))
                continue

            if not jid_known(jid):
                # Add JID with JID because we have no Nick yet
                self.groupchat[room_jid][jid] = jid
                log.info('JID Added: %s', jid)

            if not self.is_contact_in_roster(jid):
                # Query Devicelists from JIDs not in our Roster
                log.info('%s not in Roster, query devicelist...', jid)
                self.query_devicelist(jid)

    def is_contact_in_roster(self, jid):
        if jid == self.own_jid:
            return True
        contact = app.contacts.get_first_contact_from_jid(self._account, jid)
        if contact is None:
            return False
        return contact.sub == 'both'

    def _on_muc_user_presence(self, _con, _stanza, properties):
        if properties.type == PresenceType.ERROR:
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
                self.query_devicelist(jid)

        if properties.is_muc_self_presence:
            if StatusCode.NON_ANONYMOUS in status_codes:
                # non-anonymous Room (Full JID)
                if room not in self.groupchat:
                    self.groupchat[room] = self.temp_groupchat[room]

                log.info('OMEMO capable Room found: %s', room)

                self.get_affiliation_list(room, 'owner')
                self.get_affiliation_list(room, 'admin')
                self.get_affiliation_list(room, 'member')

    def get_affiliation_list(self, room_jid, affiliation):
        iq = nbxmpp.Iq(typ='get', to=room_jid, queryNS=nbxmpp.NS_MUC_ADMIN)
        item = iq.setQuery().setTag('item')
        item.setAttr('affiliation', affiliation)
        self._con.connection.SendAndCallForResponse(
            iq, self.room_memberlist_received)

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
        """ Manipulates the outgoing groupchat stanza

            The body is getting encrypted

            Parameters
            ----------
            conn :      nbxmpp.NonBlockingClient

            event :     GcStanzaMessageOutgoingEvent

            callback:   func
                The callback. Its only called if the stanza was encrypted.
                This prevents any accidental sending of unencrypted messages.

        """
        if event.conn.name != self._account:
            return
        try:
            self.cleanup_stanza(event)

            if not event.message:
                callback(event)
                return

            to_jid = app.get_jid_without_resource(event.jid)

            msg_dict = self.omemo.create_gc_msg(
                self.own_jid, to_jid, event.message.encode('utf8'))
            if not msg_dict:
                raise OMEMOError('Error while encrypting')

        except OMEMOError as error:
            log.error(error)
            app.nec.push_incoming_event(
                NetworkEvent(
                    'message-not-sent', conn=conn, jid=event.jid, message=event.message,
                    error=error, time_=time.time(), session=None))
            return

        self.gc_message[msg_dict['payload']] = event.message
        encrypted_node = OmemoMessage(msg_dict)

        event.msg_iq.addChild(node=encrypted_node)

        # XEP-0380: Explicit Message Encryption
        eme_node = Node('encryption', attrs={'xmlns': NS_EME,
                                             'name': 'OMEMO',
                                             'namespace': NS_OMEMO})
        event.msg_iq.addChild(node=eme_node)

        # Add Message for devices that don't support OMEMO
        support_msg = _("You received a message encrypted with " \
                      "OMEMO but your client doesn't support OMEMO.")
        event.msg_iq.setBody(support_msg)

        # Store Hint for MAM
        store = Node('store', attrs={'xmlns': NS_HINTS})
        event.msg_iq.addChild(node=store)

        self.print_msg_to_log(event.msg_iq)
        callback(event)

    def encrypt_message(self, conn, event, callback):
        """ Manipulates the outgoing stanza

            Encrypt the body

            Parameters
            ----------
            conn :      nbxmpp.NonBlockingClient

            event :     StanzaMessageOutgoingEvent

            callback:   func
                The callback. Its only called if the stanza was encrypted.
                This prevents any accidental sending of unencrypted messages.
        """
        if event.conn.name != self._account:
            return
        try:
            self.cleanup_stanza(event)

            if not event.message:
                callback(event)
                return

            to_jid = app.get_jid_without_resource(event.jid)

            plaintext = event.message.encode('utf8')
            msg_dict = self.omemo.create_msg(self.own_jid, to_jid, plaintext)
            if not msg_dict:
                raise OMEMOError('Error while encrypting')

        except OMEMOError as error:
            log.error(error)
            app.nec.push_incoming_event(
                NetworkEvent(
                    'message-not-sent', conn=conn, jid=event.jid, message=event.message,
                    error=error, time_=time.time(), session=event.session))
            return

        encrypted_node = OmemoMessage(msg_dict)
        event.msg_iq.addChild(node=encrypted_node)

        # XEP-0380: Explicit Message Encryption
        eme_node = Node('encryption', attrs={'xmlns': NS_EME,
                                             'name': 'OMEMO',
                                             'namespace': NS_OMEMO})
        event.msg_iq.addChild(node=eme_node)

        # Store Hint for MAM
        store = Node('store', attrs={'xmlns': NS_HINTS})
        event.msg_iq.addChild(node=store)
        self.print_msg_to_log(event.msg_iq)
        event.xhtml = None
        event.encrypted = ENCRYPTION_NAME
        self.add_additional_data(event.additional_data)
        callback(event)

    @staticmethod
    def cleanup_stanza(obj):
        ''' We make sure only allowed tags are in the stanza '''

        stanza = nbxmpp.Message(
            to=obj.msg_iq.getTo(),
            typ=obj.msg_iq.getType())
        stanza.setID(obj.stanza_id)
        stanza.setThread(obj.msg_iq.getThread())
        for tag, ns in ALLOWED_TAGS:
            node = obj.msg_iq.getTag(tag, namespace=ns)
            if node:
                stanza.addChild(node=node)
        obj.msg_iq = stanza

    def device_list_received(self, device_list, jid):
        if not device_list:
            log.error('%s => Received empty or invalid Devicelist from: %s',
                      self._account, jid)
            return

        if self.get_own_jid().bareMatch(jid):
            log.info('%s => Received own device list: %s',
                     self._account, device_list)
            self.omemo.set_own_devices(device_list)
            self.omemo.store.sessionStore.setActiveState(
                device_list, self.own_jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if jid in self.query_for_bundles:
                self.query_for_bundles.remove(jid)

            if not self.omemo.own_device_id_published():
                # Our own device_id is not in the list, it could be
                # overwritten by some other client
                self.publish_own_devices_list()
        else:
            log.info('%s => Received device list for %s: %s',
                     self._account, jid, device_list)
            self.omemo.set_devices(jid, device_list)
            self.omemo.store.sessionStore.setActiveState(
                device_list, jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if jid in self.query_for_bundles:
                self.query_for_bundles.remove(jid)


    def _handle_device_list_update(self, conn, stanza, fetch_bundle=False):
        """ Check if the passed event is a device list update and store the new
            device ids.

            Parameters
            ----------
            conn :          nbxmpp.NonBlockingClient

            stanza:         nbxmpp.Iq

            fetch_bundle:   If True, bundles are fetched for the device ids

        """

        devices_list = list(set(unpack_device_list_update(stanza,
                                                          self._account)))
        contact_jid = stanza.getFrom().getStripped()
        if not devices_list:
            log.error('%s => Received empty or invalid Devicelist from: %s',
                      self._account, contact_jid)
            return False

        if self.get_own_jid().bareMatch(contact_jid):
            log.info('%s => Received own device list: %s',
                     self._account, devices_list)
            self.omemo.set_own_devices(devices_list)
            self.omemo.store.sessionStore.setActiveState(
                devices_list, self.own_jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if contact_jid in self.query_for_bundles:
                self.query_for_bundles.remove(contact_jid)

            if not self.omemo.own_device_id_published():
                # Our own device_id is not in the list, it could be
                # overwritten by some other client
                self.publish_own_devices_list()
        else:
            log.info('%s => Received device list for %s: %s',
                     self._account, contact_jid, devices_list)
            self.omemo.set_devices(contact_jid, devices_list)
            self.omemo.store.sessionStore.setActiveState(
                devices_list, contact_jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if contact_jid in self.query_for_bundles:
                self.query_for_bundles.remove(contact_jid)

            if fetch_bundle:
                self.are_keys_missing(contact_jid)
            # Enable Encryption on receiving first Device List
            # TODO

    def publish_own_devices_list(self, new=False):
        """ Get all currently known own active device ids and publish them

            Parameters
            ----------
            new : bool
                if True, a devicelist with only one
                (the current id of this instance) device id is pushed
        """
        if new:
            devices_list = [self.omemo.own_device_id]
        else:
            devices_list = self.omemo.own_devices
            devices_list.append(self.omemo.own_device_id)
            devices_list = list(set(devices_list))
        self.omemo.set_own_devices(devices_list)

        list_node = Node('list', attrs={'xmlns': NS_OMEMO})
        for device in devices_list:
            list_node.addChild('device').setAttr('id', device)

        con = app.connections[self._account]
        con.get_module('PubSub').send_pb_publish(
            '', NS_DEVICE_LIST, list_node, 'current',
            cb=self.device_list_publish_result)

        log.info('%s => Publishing own Devices: %s',
                 self._account, devices_list)

    def device_list_publish_result(self, _con, stanza):
        if not nbxmpp.isResultNode(stanza):
            log.error('%s => Publishing devicelist failed: %s',
                      self._account, stanza.getError())

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
                    self.fetch_device_bundle_information(self.own_jid,
                                                         device_id)

        # Fetch Bundles of contacts devices
        if contact_jid not in self.query_for_bundles:

            devices_without_session = self.omemo \
                .devices_without_sessions(contact_jid)

            self.query_for_bundles.append(contact_jid)

            if devices_without_session:
                for device_id in devices_without_session:
                    self.fetch_device_bundle_information(contact_jid,
                                                         device_id)

        if self.omemo.getTrustedFingerprints(contact_jid):
            return False
        return True

    def fetch_device_bundle_information(self, jid, device_id):
        """ Fetch bundle information for specified jid, key, and create axolotl
            session on success.

            Parameters
            ----------
            jid : str
                The jid to query for bundle information
            device_id : int
                The device id for which we want the bundle
        """
        log.info('%s => Fetch bundle device %s#%s',
                 self._account, device_id, jid)
        bundle_query = BundleInformationQuery(jid, device_id)
        self.send_with_callback(bundle_query,
                                self.session_from_prekey_bundle,
                                {'jid': jid, 'device_id': device_id})

    def session_from_prekey_bundle(self, conn, stanza, jid, device_id):
        """ Starts a session from a PreKey bundle.
            This method tries to build an axolotl session when a PreKey bundle
            is fetched.
            If a session can not be build it will fail silently but log the a
            warning.

            Parameters
            ----------
            conn : nbxmpp.NonBlockingClient

            stanza : nbxmpp.Iq
                The stanza
            jid : str
                Jid of the contact
            device_id : int
                The device id
        """

        bundle_dict = unpack_device_bundle(stanza, device_id)
        if not bundle_dict:
            log.warning('Failed to build Session with %s', jid)
            return

        if self.omemo.build_session(jid, device_id, bundle_dict):
            log.info('%s => session created for: %s',
                     self._account, jid)
            # Trigger dialog to trust new Fingerprints if
            # the Chat Window is Open
            ctrl = app.interface.msg_win_mgr.get_control(
                jid, self._account)
            if ctrl:
                app.nec.push_incoming_event(
                    NetworkEvent('omemo-new-fingerprint', chat_control=ctrl))

    def query_devicelist(self, jid=None, fetch_bundle=False):
        """ Query own devicelist from the server """
        if jid in self.query_for_devicelists:
            return
        if jid is None:
            device_query = DevicelistQuery(self.own_jid)
            log.info('%s => Querry own devicelist ...', self._account)
            self.send_with_callback(device_query,
                                    self.handle_devicelist_result)
        else:
            device_query = DevicelistQuery(jid)
            log.info('%s => Querry devicelist from %s', self._account, jid)
            self.send_with_callback(device_query,
                                    self._handle_device_list_update,
                                    data={'fetch_bundle': fetch_bundle})
        self.query_for_devicelists.append(jid)

    def publish_bundle(self):
        """ Publish our bundle information to the PEP node """

        bundle = make_bundle(self.omemo.bundle)
        node = '%s%s' % (NS_BUNDLES, self.omemo.own_device_id)

        log.info('%s => Publishing bundle ...', self._account)

        con = app.connections[self._account]
        con.get_module('PubSub').send_pb_publish(
            '', node, bundle, 'current', cb=self.handle_publish_result)

    def handle_publish_result(self, _con, stanza):
        """ Log if publishing our bundle was successful

            Parameters
            ----------
            stanza : nbxmpp.Iq
                The stanza
        """
        if successful(stanza):
            log.info('%s => Publishing bundle was successful', self._account)
        else:
            log.error('%s => Publishing bundle was NOT successful',
                      self._account)

    def handle_devicelist_result(self, stanza):
        """ If query was successful add own device to the list.

            Parameters
            ----------
            stanza : nbxmpp.Iq
                The stanza
        """

        if successful(stanza):
            devices_list = list(set(unpack_device_list_update(stanza, self._account)))
            if not devices_list:
                self.publish_own_devices_list(new=True)
                return

            self.omemo.set_own_devices(devices_list)
            self.omemo.store.sessionStore.setActiveState(
                devices_list, self.own_jid)
            log.info('%s => Devicelistquery was successful', self._account)
            if not self.omemo.own_device_id_published():
                # Our own device_id is not in the list, it could be
                # overwritten by some other client
                self.publish_own_devices_list()
        else:
            log.error('%s => Devicelistquery was NOT successful: %s',
                      self._account, stanza.getError())
            self.publish_own_devices_list(new=True)

    @staticmethod
    def print_msg_to_log(stanza):
        """ Prints a stanza in a fancy way to the log """

        log.debug('-'*15)
        stanzastr = '\n' + stanza.__str__(fancy=True)
        stanzastr = stanzastr[0:-1]
        log.debug(stanzastr)
        log.debug('-'*15)

    def add_additional_data(self, data):
        data['encrypted'] = {'name': ENCRYPTION_NAME}


class OMEMOError(Exception):
    pass


def get_instance(*args, **kwargs):
    return OMEMO(*args, **kwargs), 'OMEMO'
