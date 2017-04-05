# -*- coding: utf-8 -*-
#
# Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright 2015 Daniel Gultsch <daniel@cgultsch.de>
#
# This file is part of Gajim-OMEMO plugin.
#
# The Gajim-OMEMO plugin is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Gajim-OMEMO is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# the Gajim-OMEMO plugin.  If not, see <http://www.gnu.org/licenses/>.
#

import logging
import os
import sqlite3
import shutil
import message_control

from common import caps_cache, gajim, ged, configpaths
from common.pep import SUPPORTED_PERSONAL_USER_EVENTS
from plugins import GajimPlugin
from plugins.helpers import log_calls
from nbxmpp.simplexml import Node
from nbxmpp import NS_CORRECT, NS_ADDRESS

from .xmpp import (
    NS_NOTIFY, NS_OMEMO, NS_EME, BundleInformationAnnouncement,
    BundleInformationQuery, DeviceListAnnouncement, DevicelistQuery,
    DevicelistPEP, OmemoMessage, successful, unpack_device_bundle,
    unpack_device_list_update, unpack_encrypted)

from common import demandimport
demandimport.enable()
demandimport.ignore += ['_imp', '_thread', 'axolotl', 'PIL',
                        '__builtin__', 'builtins']

IQ_CALLBACK = {}

CRYPTOGRAPHY_MISSING = 'You are missing Python-Cryptography'
AXOLOTL_MISSING = 'You are missing Python-Axolotl or use an outdated version'
PROTOBUF_MISSING = 'OMEMO cant import Google Protobuf, you can find help in ' \
                   'the GitHub Wiki'
GAJIM_VERSION = 'OMEMO only works with the latest Gajim version, get the ' \
                'latest version from gajim.org'
ERROR_MSG = ''

NS_HINTS = 'urn:xmpp:hints'
NS_PGP = 'urn:xmpp:openpgp:0'
DB_DIR_OLD = gajim.gajimpaths.data_root
DB_DIR_NEW = configpaths.gajimpaths['MY_DATA']

log = logging.getLogger('gajim.plugin_system.omemo')

try:
    from .file_decryption import FileDecryption
except Exception as e:
    log.exception(e)
    ERROR_MSG = CRYPTOGRAPHY_MISSING

try:
    prototest = __import__('google.protobuf')
except Exception as e:
    log.error(e)
    ERROR_MSG = PROTOBUF_MISSING

try:
    axolotltest = __import__('axolotl')
except Exception as e:
    log.error(e)
    ERROR_MSG = AXOLOTL_MISSING

if not ERROR_MSG:
    try:
        from .omemo.state import OmemoState
        from .ui import Ui, OMEMOConfigDialog
    except Exception as e:
        log.error(e)
        ERROR_MSG = 'Error: ' + str(e)

GAJIM_VER = gajim.config.get('version')
GROUPCHAT = False

if os.name != 'nt':
    try:
        SETUPTOOLS_MISSING = False
        pkg = __import__('pkg_resources')
    except Exception as e:
        log.error(e)
        SETUPTOOLS_MISSING = True
        ERROR_MSG = 'You are missing the Setuptools package.'

    if not SETUPTOOLS_MISSING:
        if pkg.parse_version(GAJIM_VER) < pkg.parse_version('0.16.5'):
            ERROR_MSG = GAJIM_VERSION
        if pkg.parse_version(GAJIM_VER) > pkg.parse_version('0.16.5'):
            GROUPCHAT = True
else:
    # if GAJIM_VER < 0.16.5, the Plugin fails on missing dependencys earlier
    if not GAJIM_VER == '0.16.5':
        GROUPCHAT = True

# pylint: disable=no-init
# pylint: disable=attribute-defined-outside-init


class OmemoPlugin(GajimPlugin):

    omemo_states = {}
    ui_list = {}
    groupchat = {}
    temp_groupchat = {}

    @log_calls('OmemoPlugin')
    def init(self):
        """ Init """
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            self.config_dialog = None
            return
        self.events_handlers = {
            'mam-message-received': (ged.PRECORE, self.mam_message_received),
            'message-received': (ged.PRECORE, self.message_received),
            'pep-received': (ged.PRECORE, self.handle_device_list_update),
            'raw-iq-received': (ged.PRECORE, self.handle_iq_received),
            'signed-in': (ged.PRECORE, self.signed_in),
            'stanza-message-outgoing':
            (ged.PRECORE, self.handle_outgoing_stanza),
            'message-outgoing':
            (ged.PRECORE, self.handle_outgoing_event)}
        if GROUPCHAT:
            self.events_handlers['gc-stanza-message-outgoing'] =\
                (ged.PRECORE, self.handle_outgoing_gc_stanza)
            self.events_handlers['gc-presence-received'] =\
                (ged.PRECORE, self.gc_presence_received)
            self.events_handlers['gc-config-changed-received'] =\
                (ged.PRECORE, self.gc_config_changed_received)
            self.events_handlers['muc-admin-received'] =\
                (ged.PRECORE, self.room_memberlist_received)

        self.config_dialog = OMEMOConfigDialog(self)
        self.gui_extension_points = {'chat_control': (self.connect_ui,
                                                      self.disconnect_ui),
                                     'groupchat_control': (self.connect_ui,
                                                           self.disconnect_ui)}
        SUPPORTED_PERSONAL_USER_EVENTS.append(DevicelistPEP)
        self.plugin = self
        self.announced = []
        self.query_for_bundles = []
        self.disabled_accounts = []
        self.gc_message = {}

        self.config_default_values = {'DISABLED_ACCOUNTS': ([], ''), }

        for account in self.plugin.config['DISABLED_ACCOUNTS']:
            self.disabled_accounts.append(account)

    def migrate_dbpath(self, account, my_jid):
        old_dbpath = os.path.join(DB_DIR_OLD, 'omemo_' + account + '.db')
        new_dbpath = os.path.join(DB_DIR_NEW, 'omemo_' + my_jid + '.db')

        if os.path.exists(old_dbpath):
            log.debug('Migrating DBName and Path ..')
            try:
                shutil.move(old_dbpath, new_dbpath)
                return new_dbpath
            except Exception:
                log.exception('Migration Error:')
                return old_dbpath

        return new_dbpath

    @log_calls('OmemoPlugin')
    def get_omemo_state(self, account):
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
        if account in self.disabled_accounts:
            return
        if account not in self.omemo_states:
            self.deactivate_gajim_e2e(account)
            my_jid = gajim.get_jid_from_account(account)
            db_path = self.migrate_dbpath(account, my_jid)

            conn = sqlite3.connect(db_path, check_same_thread=False)
            self.omemo_states[account] = OmemoState(my_jid, conn, account,
                                                    self.plugin)

        return self.omemo_states[account]

    @staticmethod
    def deactivate_gajim_e2e(account):
        """ Deativates E2E encryption in Gajim """
        gajim.config.set_per('accounts', account,
                             'autonegotiate_esessions', False)
        gajim.config.set_per('accounts', account,
                             'enable_esessions', False)
        log.info(str(account) + " => Gajim E2E encryption disabled")

    @log_calls('OmemoPlugin')
    def signed_in(self, event):
        """ Method called on SignIn

            Parameters
            ----------
            event : SignedInEvent
        """
        account = event.conn.name
        if account in self.disabled_accounts:
            return
        log.debug(account +
                  ' => Announce Support after Sign In')
        self.query_for_bundles = []
        self.announced = []
        self.announced.append(account)
        self.publish_bundle(account)
        self.query_own_devicelist(account)

    @log_calls('OmemoPlugin')
    def activate(self):
        """ Method called when the Plugin is activated in the PluginManager
        """
        self.query_for_bundles = []
        # Publish bundle information and Entity Caps
        for account in gajim.connections:
            if account in self.disabled_accounts:
                log.debug(account +
                          ' => Account is disabled')
                continue
            if NS_NOTIFY not in gajim.gajim_optional_features[account]:
                gajim.gajim_optional_features[account].append(NS_NOTIFY)
            self._compute_caps_hash(account)
            if account not in self.announced:
                if gajim.account_is_connected(account):
                    log.debug(account +
                              ' => Announce Support after Plugin Activation')
                    self.announced.append(account)
                    self.publish_bundle(account)
                    self.query_own_devicelist(account)

    @log_calls('OmemoPlugin')
    def deactivate(self):
        """ Method called when the Plugin is deactivated in the PluginManager

            Removes OMEMO from the Entity Capabilities list
        """
        for account in gajim.connections:
            if account in self.disabled_accounts:
                continue
            if NS_NOTIFY in gajim.gajim_optional_features[account]:
                gajim.gajim_optional_features[account].remove(NS_NOTIFY)
            self._compute_caps_hash(account)

    @staticmethod
    def _compute_caps_hash(account):
        """ Computes the hash for Entity Capabilities and publishes it """
        gajim.caps_hash[account] = caps_cache.compute_caps_hash(
            [gajim.gajim_identity],
            gajim.gajim_common_features +
            gajim.gajim_optional_features[account])
        # re-send presence with new hash
        connected = gajim.connections[account].connected
        if connected > 1 and gajim.SHOW_LIST[connected] != 'invisible':
            gajim.connections[account].change_status(
                gajim.SHOW_LIST[connected], gajim.connections[account].status)

    @log_calls('OmemoPlugin')
    def mam_message_received(self, msg):
        """ Handles an incoming MAM message

            Payload is decrypted and the plaintext is written into the
            event object. Afterwards the event is passed on further to Gajim.

            Parameters
            ----------
            msg : MamMessageReceivedEvent

            Returns
            -------
            Return means that the Event is passed on to Gajim
        """
        account = msg.conn.name
        if account in self.disabled_accounts:
            return

        if msg.msg_.getTag('openpgp', namespace=NS_PGP):
            return

        omemo_encrypted_tag = msg.msg_.getTag('encrypted', namespace=NS_OMEMO)
        if omemo_encrypted_tag:
            log.debug(account + ' => OMEMO MAM msg received')

            state = self.get_omemo_state(account)

            from_jid = str(msg.msg_.getAttr('from'))
            from_jid = gajim.get_jid_without_resource(from_jid)

            msg_dict = unpack_encrypted(omemo_encrypted_tag)

            msg_dict['sender_jid'] = from_jid

            plaintext = state.decrypt_msg(msg_dict)

            if not plaintext:
                return

            self.print_msg_to_log(msg.msg_)

            msg.msgtxt = plaintext

            contact_jid = msg.with_

            if account in self.ui_list and \
                    contact_jid in self.ui_list[account]:
                self.ui_list[account][contact_jid].activate_omemo()
            return False

        elif msg.msg_.getTag('body'):
            account = msg.conn.name

            jid = msg.with_
            state = self.get_omemo_state(account)
            omemo_enabled = state.encryption.is_active(jid)

            if omemo_enabled:
                msg.msgtxt = '**Unencrypted** ' + msg.msgtxt

    @log_calls('OmemoPlugin')
    def message_received(self, msg):
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
        account = msg.conn.name
        if account in self.disabled_accounts:
            return

        if msg.stanza.getTag('openpgp', namespace=NS_PGP):
            return

        if msg.stanza.getTag('encrypted', namespace=NS_OMEMO):
            log.debug(account + ' => OMEMO msg received')

            state = self.get_omemo_state(account)
            if msg.forwarded and msg.sent:
                from_jid = str(msg.stanza.getTo())  # why gajim? why?
                log.debug('message was forwarded doing magic')
            else:
                from_jid = str(msg.stanza.getFrom())

            self.print_msg_to_log(msg.stanza)
            msg_dict = unpack_encrypted(msg.stanza.getTag
                                        ('encrypted', namespace=NS_OMEMO))

            if msg.mtype == 'groupchat':
                address_tag = msg.stanza.getTag('addresses',
                                                namespace=NS_ADDRESS)
                if address_tag:  # History Message from MUC
                    from_jid = address_tag.getTag(
                        'address', attrs={'type': 'ofrom'}).getAttr('jid')
                else:
                    try:
                        from_jid = self.groupchat[msg.jid][msg.resource]
                    except KeyError:
                        log.debug('Groupchat: Last resort trying to '
                                  'find SID in DB')
                        from_jid = state.store. \
                            getJidFromDevice(msg_dict['sid'])
                        if not from_jid:
                            log.error(account +
                                      ' => Cant decrypt GroupChat Message '
                                      'from ' + msg.resource)
                            return True
                        self.groupchat[msg.jid][msg.resource] = from_jid

                log.debug('GroupChat Message from: %s', from_jid)

            plaintext = ''
            if msg_dict['sid'] == state.own_device_id:
                if msg_dict['payload'] in self.gc_message:
                    plaintext = self.gc_message[msg_dict['payload']]
                    del self.gc_message[msg_dict['payload']]
                else:
                    log.error(account + ' => Cant decrypt own GroupChat '
                              'Message')
            else:
                msg_dict['sender_jid'] = gajim. \
                    get_jid_without_resource(from_jid)
                plaintext = state.decrypt_msg(msg_dict)

            if not plaintext:
                return True

            msg.msgtxt = plaintext
            # Gajim bug: there must be a body or the message
            # gets dropped from history
            msg.stanza.setBody(plaintext)

            if msg.mtype != 'groupchat':
                contact_jid = gajim.get_jid_without_resource(from_jid)
                if account in self.ui_list and \
                        contact_jid in self.ui_list[account]:
                    self.ui_list[account][contact_jid].activate_omemo()
            return False

        elif msg.stanza.getTag('body'):
            account = msg.conn.name

            from_jid = str(msg.stanza.getFrom())
            jid = gajim.get_jid_without_resource(from_jid)
            state = self.get_omemo_state(account)
            omemo_enabled = state.encryption.is_active(jid)

            if omemo_enabled:
                msg.msgtxt = '**Unencrypted** ' + msg.msgtxt
                # msg.stanza.setBody(msg.msgtxt)

                try:
                    gui = self.ui_list[account].get(jid, None)
                    if gui and gui.encryption_active():
                        gui.plain_warning()
                except KeyError:
                    log.debug('No Ui present for ' + jid +
                              ', Ui Warning not shown')

    def room_memberlist_received(self, event):
        account = event.conn.name
        if account in self.disabled_accounts:
            return
        log.debug('Room %s Memberlist received: %s',
                  event.fjid, event.users_dict)
        room = event.fjid

        def jid_known(jid):
            for nick in self.groupchat[room]:
                if self.groupchat[room][nick] == jid:
                    return True
            return False

        for jid in event.users_dict:
            if not jid_known(jid):
                # Add JID with JID because we have no Nick yet
                self.groupchat[room][jid] = jid
                log.debug('JID Added: ' + jid)

    @log_calls('OmemoPlugin')
    def gc_presence_received(self, event):
        account = event.conn.name
        if account in self.disabled_accounts:
            return
        if not hasattr(event, 'real_jid') or not event.real_jid:
            return

        room = event.room_jid
        jid = gajim.get_jid_without_resource(event.real_jid)
        nick = event.nick

        if '303' in event.status_code:  # Nick Changed
            if room in self.groupchat:
                if nick in self.groupchat[room]:
                    del self.groupchat[room][nick]
                self.groupchat[room][event.new_nick] = jid
                log.debug('Nick Change: old: %s, new: %s, jid: %s ',
                          nick, event.new_nick, jid)
                log.debug('Members after Change:  %s', self.groupchat[room])
            else:
                if nick in self.temp_groupchat[room]:
                    del self.temp_groupchat[room][nick]
                self.temp_groupchat[room][event.new_nick] = jid

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
                log.debug('JID Added: ' + jid)

        if '100' in event.status_code:  # non-anonymous Room (Full JID)

            if room not in self.groupchat:
                self.groupchat[room] = self.temp_groupchat[room]

            log.debug('OMEMO capable Room found: %s', room)

            gajim.connections[account].get_affiliation_list(room, 'owner')
            gajim.connections[account].get_affiliation_list(room, 'admin')
            gajim.connections[account].get_affiliation_list(room, 'member')

            self.ui_list[account][room].sensitive(True)

    @log_calls('OmemoPlugin')
    def gc_config_changed_received(self, event):
        account = event.conn.name
        if account in self.disabled_accounts:
            return
        log.debug('CONFIG CHANGE')
        log.debug(event.room_jid)
        log.debug(event.status_code)

    def handle_outgoing_gc_stanza(self, event):
        """ Manipulates the outgoing groupchat stanza

            The body is getting encrypted

            Parameters
            ----------
            event : StanzaMessageOutgoingEvent

            Returns
            -------
            Return if encryption is not activated or any other
            exception or error occurs
        """
        account = event.conn.name
        if account in self.disabled_accounts:
            return
        try:
            # If we send a correction msg, the stanza is saved
            # in correction_msg
            if event.correction_msg:
                event.msg_iq = event.correction_msg
            if not event.msg_iq.getTag('body'):
                return
            state = self.get_omemo_state(account)
            full_jid = str(event.msg_iq.getAttr('to'))
            to_jid = gajim.get_jid_without_resource(full_jid)
            if to_jid not in self.groupchat:
                return
            if not state.encryption.is_active(to_jid):
                return
            # Delete previous Message out of Correction Message Stanza
            if event.msg_iq.getTag('replace', namespace=NS_CORRECT):
                event.msg_iq.delChild('encrypted', attrs={'xmlns': NS_OMEMO})

            plaintext = event.msg_iq.getBody()
            msg_dict = state.create_gc_msg(
                gajim.get_jid_from_account(account),
                to_jid,
                plaintext.encode('utf8'))
            if not msg_dict:
                return True

            self.gc_message[msg_dict['payload']] = plaintext
            encrypted_node = OmemoMessage(msg_dict)
            event.msg_iq.delChild('body')
            event.msg_iq.addChild(node=encrypted_node)

            # XEP-0380: Explicit Message Encryption
            if not event.msg_iq.getTag('encryption', attrs={'xmlns': NS_EME}):
                eme_node = Node('encryption', attrs={'xmlns': NS_EME,
                                                     'name': 'OMEMO',
                                                     'namespace': NS_OMEMO})
                event.msg_iq.addChild(node=eme_node)

            # Add Message for devices that dont support OMEMO
            support_msg = 'You received a message encrypted with ' \
                          'OMEMO but your client doesnt support OMEMO.'
            event.msg_iq.setBody(support_msg)

            # Store Hint for MAM
            store = Node('store', attrs={'xmlns': NS_HINTS})
            event.msg_iq.addChild(node=store)
            if event.correction_msg:
                event.correction_msg = event.msg_iq
                event.msg_iq = None
                self.print_msg_to_log(event.correction_msg)
            else:
                self.print_msg_to_log(event.msg_iq)
        except Exception as e:
            log.debug(e)
            return True

    @log_calls('OmemoPlugin')
    def handle_outgoing_event(self, event):
        """ Handles a message outgoing event

            In this event we have no stanza. XHTML is set to None
            so that it doesnt make its way into the stanza

            Parameters
            ----------
            event : MessageOutgoingEvent

            Returns
            -------
            Return if encryption is not activated
        """
        if event.type_ == 'normal':
            return False

        account = event.account
        if account in self.disabled_accounts:
            return
        state = self.get_omemo_state(account)

        if not state.encryption.is_active(event.jid):
            return False

        event.xhtml = None

    @log_calls('OmemoPlugin')
    def handle_outgoing_stanza(self, event):
        """ Manipulates the outgoing stanza

            The body is getting encrypted

            Parameters
            ----------
            event : StanzaMessageOutgoingEvent

            Returns
            -------
            Return if encryption is not activated or any other
            exception or error occurs
        """
        account = event.conn.name
        if account in self.disabled_accounts:
            return
        try:
            if not event.msg_iq.getTag('body'):
                return

            state = self.get_omemo_state(account)
            full_jid = str(event.msg_iq.getAttr('to'))
            to_jid = gajim.get_jid_without_resource(full_jid)
            if not state.encryption.is_active(to_jid):
                return

            # Delete previous Message out of Correction Message Stanza
            if event.msg_iq.getTag('replace', namespace=NS_CORRECT):
                event.msg_iq.delChild('encrypted', attrs={'xmlns': NS_OMEMO})

            plaintext = event.msg_iq.getBody().encode('utf8')

            msg_dict = state.create_msg(
                gajim.get_jid_from_account(account), to_jid, plaintext)
            if not msg_dict:
                return True

            encrypted_node = OmemoMessage(msg_dict)

            # Check if non-OMEMO resource is online
            contacts = gajim.contacts.get_contacts(account, to_jid)
            non_omemo_resource_online = False
            for contact in contacts:
                if contact.show == 'offline':
                    continue
                if not contact.supports(NS_NOTIFY):
                    log.debug(contact.get_full_jid() +
                              ' => Contact doesnt support OMEMO, '
                              'adding Info Message to Body')
                    support_msg = 'You received a message encrypted with ' \
                                  'OMEMO but your client doesnt support OMEMO.'
                    event.msg_iq.setBody(support_msg)
                    non_omemo_resource_online = True
            if not non_omemo_resource_online:
                event.msg_iq.delChild('body')

            event.msg_iq.addChild(node=encrypted_node)

            # XEP-0380: Explicit Message Encryption
            if not event.msg_iq.getTag('encryption', attrs={'xmlns': NS_EME}):
                eme_node = Node('encryption', attrs={'xmlns': NS_EME,
                                                     'name': 'OMEMO',
                                                     'namespace': NS_OMEMO})
                event.msg_iq.addChild(node=eme_node)

            # Store Hint for MAM
            store = Node('store', attrs={'xmlns': NS_HINTS})
            event.msg_iq.addChild(node=store)
            self.print_msg_to_log(event.msg_iq)
        except Exception as e:
            log.debug(e)
            return True

    @log_calls('OmemoPlugin')
    def handle_device_list_update(self, event):
        """ Check if the passed event is a device list update and store the new
            device ids.

            Parameters
            ----------
            event : PEPReceivedEvent

            Returns
            -------
            bool
                True if the given event was a valid device list update event


            See also
            --------
            4.2 Discovering peer support
                http://conversations.im/xeps/multi-end.html#usecases-discovering
        """

        account = event.conn.name
        if account in self.disabled_accounts:
            return False

        if event.pep_type != 'headline':
            return False

        devices_list = list(set(unpack_device_list_update(event.stanza,
                                                          event.conn.name)))
        contact_jid = gajim.get_jid_without_resource(event.fjid)
        if len(devices_list) == 0:
            log.error(account +
                      ' => Received empty or invalid Devicelist from: ' +
                      contact_jid)
            return False

        state = self.get_omemo_state(account)
        my_jid = gajim.get_jid_from_account(account)

        if contact_jid == my_jid:
            log.info(account + ' => Received own device list:' + str(
                devices_list))
            state.set_own_devices(devices_list)
            state.store.sessionStore.setActiveState(devices_list, my_jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if contact_jid in self.query_for_bundles:
                self.query_for_bundles.remove(contact_jid)

            if not state.own_device_id_published():
                # Our own device_id is not in the list, it could be
                # overwritten by some other client
                self.publish_own_devices_list(account)
        else:
            log.info(account + ' => Received device list for ' +
                     contact_jid + ':' + str(devices_list))
            state.set_devices(contact_jid, devices_list)
            state.store.sessionStore.setActiveState(devices_list, contact_jid)

            # remove contact from list, so on send button pressed
            # we query for bundle and build a session
            if contact_jid in self.query_for_bundles:
                self.query_for_bundles.remove(contact_jid)

            # Enable Encryption on receiving first Device List
            if not state.encryption.exist(contact_jid):
                if account in self.ui_list and \
                        contact_jid in self.ui_list[account]:
                    log.debug(account +
                              ' => Switch encryption ON automatically ...')
                    self.ui_list[account][contact_jid].activate_omemo()
                else:
                    log.debug(account +
                              ' => Switch encryption ON automatically ...')
                    self.omemo_enable_for(contact_jid, account)

            if account in self.ui_list and \
                    contact_jid not in self.ui_list[account]:

                chat_control = gajim.interface.msg_win_mgr.get_control(
                    contact_jid, account)

                if chat_control:
                    self.connect_ui(chat_control)

        return True

    @log_calls('OmemoPlugin')
    def publish_own_devices_list(self, account, new=False):
        """ Get all currently known own active device ids and publish them

            Parameters
            ----------
            account : str
                the account name

            new : bool
                if True, a devicelist with only one
                (the current id of this instance) device id is pushed
        """
        state = self.get_omemo_state(account)
        if new:
            devices_list = [state.own_device_id]
        else:
            devices_list = state.own_devices
            devices_list.append(state.own_device_id)
            devices_list = list(set(devices_list))
        state.set_own_devices(devices_list)

        log.debug(account + ' => Publishing own Devices: ' + str(
            devices_list))
        iq = DeviceListAnnouncement(devices_list)
        gajim.connections[account].connection.send(iq)
        id_ = str(iq.getAttr('id'))
        IQ_CALLBACK[id_] = lambda event: log.debug(event)

    @log_calls('OmemoPlugin')
    def connect_ui(self, chat_control):
        """ Method called from Gajim when a Chat Window is opened

            Parameters
            ----------
            chat_control : ChatControl
                Gajim ChatControl object
        """
        FileDecryption(self).activate(chat_control)
        account = chat_control.contact.account.name
        if account in self.disabled_accounts:
            return
        contact_jid = chat_control.contact.jid
        if account not in self.ui_list:
            self.ui_list[account] = {}
        state = self.get_omemo_state(account)
        my_jid = gajim.get_jid_from_account(account)
        omemo_enabled = state.encryption.is_active(contact_jid)
        if omemo_enabled:
            log.debug(account + " => Adding OMEMO ui for " + contact_jid)
            self.ui_list[account][contact_jid] = Ui(self, chat_control,
                                                    omemo_enabled, state)
            self.ui_list[account][contact_jid].new_fingerprints_available()
            return
        if contact_jid in state.device_ids or contact_jid == my_jid:
            log.debug(account + " => Adding OMEMO ui for " + contact_jid)
            self.ui_list[account][contact_jid] = Ui(self, chat_control,
                                                    omemo_enabled, state)
            self.ui_list[account][contact_jid].new_fingerprints_available()
        else:
            log.warning(account + " => No devices for " + contact_jid)

        if chat_control.type_id == message_control.TYPE_GC:
            self.ui_list[account][contact_jid] = Ui(self, chat_control,
                                                    omemo_enabled, state)
            self.ui_list[account][contact_jid].sensitive(False)

    @log_calls('OmemoPlugin')
    def disconnect_ui(self, chat_control):
        """ Calls the removeUi method to remove all relatad UI objects.

            Parameters
            ----------
            chat_control : ChatControl
                Gajim ChatControl object
        """
        contact_jid = chat_control.contact.jid
        account = chat_control.contact.account.name
        if account in self.disabled_accounts:
            return
        self.ui_list[account][contact_jid].removeUi()

    def are_keys_missing(self, account, contact_jid):
        """ Checks if devicekeys are missing and querys the
            bundles

            Parameters
            ----------
            account : str
                the account name
            contact_jid : str
                bare jid of the contact

            Returns
            -------
            bool
                Returns True if there are no trusted Fingerprints
        """
        state = self.get_omemo_state(account)
        my_jid = gajim.get_jid_from_account(account)

        # Fetch Bundles of own other Devices
        if my_jid not in self.query_for_bundles:

            devices_without_session = state \
                .devices_without_sessions(my_jid)

            self.query_for_bundles.append(my_jid)

            if devices_without_session:
                for device_id in devices_without_session:
                    self.fetch_device_bundle_information(account, my_jid,
                                                         device_id)

        # Fetch Bundles of contacts devices
        if contact_jid not in self.query_for_bundles:

            devices_without_session = state \
                .devices_without_sessions(contact_jid)

            self.query_for_bundles.append(contact_jid)

            if devices_without_session:
                for device_id in devices_without_session:
                    self.fetch_device_bundle_information(account, contact_jid,
                                                         device_id)

        if state.getTrustedFingerprints(contact_jid):
            return False
        else:
            return True

    @staticmethod
    def handle_iq_received(event):
        """ Method called when an IQ is received

            Parameters
            ----------
            event : RawIqReceived
        """
        id_ = str(event.stanza.getAttr("id"))
        if id_ in IQ_CALLBACK:
            try:
                IQ_CALLBACK[id_](event.stanza)
            except:
                raise
            finally:
                del IQ_CALLBACK[id_]

    @log_calls('OmemoPlugin')
    def fetch_device_bundle_information(self, account, jid, device_id):
        """ Fetch bundle information for specified jid, key, and create axolotl
            session on success.

            Parameters
            ----------
            account : str
                The account name
            jid : str
                The jid to query for bundle information
            device_id : int
                The device_id for which we are missing an axolotl session
        """
        log.info(account + ' => Fetch bundle device ' + str(device_id) +
                 '#' + jid)
        iq = BundleInformationQuery(jid, device_id)
        iq_id = str(iq.getAttr('id'))
        IQ_CALLBACK[iq_id] = \
            lambda stanza: self.session_from_prekey_bundle(account,
                                                           stanza, jid,
                                                           device_id)
        gajim.connections[account].connection.send(iq)

    @log_calls('OmemoPlugin')
    def session_from_prekey_bundle(self, account, stanza,
                                   recipient_id, device_id):
        """ Starts a session from a PreKey bundle.

            This method tries to build an axolotl session when a PreKey bundle
            is fetched.

            If a session can not be build it will fail silently but log the a
            warning.

            See also
            --------

            4.4 Building a session:
                http://conversations.im/xeps/multi-end.html#usecases-building

            Parameters:
            -----------
            account : str
                The account name
            stanza
                The stanza object received from callback
            recipient_id : str
                           The recipient jid
            device_id : int
                The device_id for which the bundle was queried

        """
        state = self.get_omemo_state(account)
        bundle_dict = unpack_device_bundle(stanza, device_id)
        if not bundle_dict:
            log.warning('Failed to build Session with ' + recipient_id)
            return

        if state.build_session(recipient_id, device_id, bundle_dict):
            log.info(account + ' => session created for: ' + recipient_id)
            # Trigger dialog to trust new Fingerprints if
            # the Chat Window is Open
            if account in self.ui_list and \
                    recipient_id in self.ui_list[account]:
                self.ui_list[account][recipient_id]. \
                    new_fingerprints_available()

    @log_calls('OmemoPlugin')
    def query_own_devicelist(self, account):
        """ Query own devicelist from the server.

            Parameters
            ----------
            account : str
                the account name
        """
        my_jid = gajim.get_jid_from_account(account)
        iq = DevicelistQuery(my_jid)
        gajim.connections[account].connection.send(iq)
        log.info(account + ' => Querry own devicelist ...')
        id_ = str(iq.getAttr("id"))
        IQ_CALLBACK[id_] = lambda stanza: \
            self.handle_devicelist_result(account, stanza)

    @log_calls('OmemoPlugin')
    def publish_bundle(self, account):
        """ Publish our bundle information to the PEP node.

            Parameters
            ----------
            account : str
                the account name

            See also
            --------
            4.3 Announcing bundle information:
                http://conversations.im/xeps/multi-end.html#usecases-announcing
        """
        state = self.get_omemo_state(account)
        iq = BundleInformationAnnouncement(state.bundle, state.own_device_id)
        gajim.connections[account].connection.send(iq)
        id_ = str(iq.getAttr("id"))
        log.info(account + " => Publishing bundle ...")
        IQ_CALLBACK[id_] = lambda stanza: \
            self.handle_publish_result(account, stanza)

    @staticmethod
    def handle_publish_result(account, stanza):
        """ Log if publishing our bundle was successful

            Parameters
            ----------
            account : str
                the account name
            stanza
                The stanza object received from callback
        """
        if successful(stanza):
            log.info(account + ' => Publishing bundle was successful')
        else:
            log.error(account + ' => Publishing bundle was NOT successful')

    @log_calls('OmemoPlugin')
    def handle_devicelist_result(self, account, stanza):
        """ If query was successful add own device to the list.

            Parameters
            ----------
            account : str
                the account name
            stanza
                The stanza object received from callback
        """

        my_jid = gajim.get_jid_from_account(account)
        state = self.get_omemo_state(account)

        if successful(stanza):
            devices_list = list(set(unpack_device_list_update(stanza, account)))
            if len(devices_list) == 0:
                log.error(account + ' => Devicelistquery was NOT successful')
                self.publish_own_devices_list(account, new=True)
                return False
            contact_jid = stanza.getAttr('from')
            if contact_jid == my_jid:
                state.set_own_devices(devices_list)
                state.store.sessionStore.setActiveState(devices_list, my_jid)
                log.info(account + ' => Devicelistquery was successful')
                # remove contact from list, so on send button pressed
                # we query for bundle and build a session
                if contact_jid in self.query_for_bundles:
                    self.query_for_bundles.remove(contact_jid)

                if not state.own_device_id_published():
                    # Our own device_id is not in the list, it could be
                    # overwritten by some other client
                    self.publish_own_devices_list(account)
        else:
            log.error(account + ' => Devicelistquery was NOT successful')
            self.publish_own_devices_list(account, new=True)

    @log_calls('OmemoPlugin')
    def clear_device_list(self, account):
        """ Clears the local devicelist of our own devices and publishes
            a new one including only the current ID of this device

            Parameters
            ----------
            account : str
                the account name
        """
        connection = gajim.connections[account].connection
        if not connection:
            return
        state = self.get_omemo_state(account)
        devices_list = [state.own_device_id]
        state.set_own_devices(devices_list)

        log.info(account + ' => Clearing devices_list ' + str(devices_list))
        iq = DeviceListAnnouncement(devices_list)
        connection.send(iq)
        id_ = str(iq.getAttr('id'))
        IQ_CALLBACK[id_] = lambda event: log.info(event)

    @staticmethod
    def print_msg_to_log(stanza):
        """ Prints a stanza in a fancy way to the log """
        log.debug('-'*15)
        stanzastr = '\n' + stanza.__str__(fancy=True)
        stanzastr = stanzastr[0:-1]
        log.debug(stanzastr)
        log.debug('-'*15)

    @log_calls('OmemoPlugin')
    def omemo_enable_for(self, jid, account):
        """ Used by the UI to enable OMEMO for a specified contact.

            To activate OMEMO check first if a Ui Object exists for the
            Contact. If it exists use Ui.activate_omemo(). Only if there
            is no Ui Object for the contact this method is to be used.

            Parameters
            ----------
            jid : str
                bare jid
            account : str
                the account name
        """
        state = self.get_omemo_state(account)
        state.encryption.activate(jid)

    @log_calls('OmemoPlugin')
    def omemo_disable_for(self, jid, account):
        """ Used by the UI to disable OMEMO for a specified contact.

            WARNING - OMEMO should only be disabled through
            User interaction with the UI.

            Parameters
            ----------
            jid : str
                bare jid
            account : str
                the account name
        """
        state = self.get_omemo_state(account)
        state.encryption.deactivate(jid)
