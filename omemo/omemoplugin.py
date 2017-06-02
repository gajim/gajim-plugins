# -*- coding: utf-8 -*-

'''
Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
Copyright 2015 Daniel Gultsch <daniel@cgultsch.de>
Copyright 2016 Philipp Hörist <philipp@hoerist.com>

This file is part of Gajim-OMEMO plugin.

The Gajim-OMEMO plugin is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

Gajim-OMEMO is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
the Gajim-OMEMO plugin.  If not, see <http://www.gnu.org/licenses/>.
'''

import logging
import os
import sqlite3
import shutil
import nbxmpp

from nbxmpp.simplexml import Node
from nbxmpp import NS_ADDRESS

import dialogs
from common import caps_cache, gajim, ged, configpaths
from common.pep import SUPPORTED_PERSONAL_USER_EVENTS
from plugins import GajimPlugin
from groupchat_control import GroupchatControl

from .xmpp import (
    NS_NOTIFY, NS_OMEMO, NS_EME, BundleInformationAnnouncement,
    BundleInformationQuery, DeviceListAnnouncement, DevicelistQuery,
    DevicelistPEP, OmemoMessage, successful, unpack_device_bundle,
    unpack_device_list_update, unpack_encrypted)

from common.connection_handlers_events import (
    MessageReceivedEvent, MamMessageReceivedEvent)


IQ_CALLBACK = {}

CRYPTOGRAPHY_MISSING = 'You are missing Python-Cryptography'
AXOLOTL_MISSING = 'You are missing Python-Axolotl or use an outdated version'
PROTOBUF_MISSING = 'OMEMO cant import Google Protobuf, you can find help in ' \
                   'the GitHub Wiki'
ERROR_MSG = ''

NS_HINTS = 'urn:xmpp:hints'
DB_DIR_OLD = gajim.gajimpaths.data_root
DB_DIR_NEW = configpaths.gajimpaths['MY_DATA']

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
                ('thread', None)]

log = logging.getLogger('gajim.plugin_system.omemo')

try:
    from .file_decryption import FileDecryption
except Exception as e:
    log.exception(e)
    ERROR_MSG = CRYPTOGRAPHY_MISSING

try:
    import google.protobuf
except Exception as e:
    log.error(e)
    ERROR_MSG = PROTOBUF_MISSING

try:
    import axolotl
except Exception as e:
    log.error(e)
    ERROR_MSG = AXOLOTL_MISSING

if not ERROR_MSG:
    try:
        from .omemo.state import OmemoState
        from .ui import OMEMOConfigDialog, FingerprintWindow
    except Exception as e:
        log.error(e)
        ERROR_MSG = 'Error: ' + str(e)

# pylint: disable=no-init
# pylint: disable=attribute-defined-outside-init


class OmemoPlugin(GajimPlugin):

    omemo_states = {}
    groupchat = {}
    temp_groupchat = {}

    def init(self):
        """ Init """
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            self.config_dialog = None
            return
        self.encryption_name = 'OMEMO'
        self.allow_groupchat = True
        self.events_handlers = {
            'pep-received': (ged.PRECORE, self.handle_device_list_update),
            'raw-iq-received': (ged.PRECORE, self.handle_iq_received),
            'signed-in': (ged.PRECORE, self.signed_in),
            'gc-presence-received': (ged.PRECORE, self.gc_presence_received),
            'gc-config-changed-received':
            (ged.PRECORE, self.gc_config_changed_received),
            'muc-admin-received': (ged.PRECORE, self.room_memberlist_received),
            }

        self.config_dialog = OMEMOConfigDialog(self)
        self.gui_extension_points = {
            'hyperlink_handler': (self.file_decryption, None),
            'encrypt' + self.encryption_name: (self._encrypt_message, None),
            'gc_encrypt' + self.encryption_name: (self._gc_encrypt_message, None),
            'decrypt': (self.message_received, None),
            'send_message' + self.encryption_name: (
                self.before_sendmessage, None),
            'encryption_dialog' + self.encryption_name: (
                self.on_encryption_button_clicked, None),
            'encryption_state' + self.encryption_name: (
                self.encryption_state, None)}

        SUPPORTED_PERSONAL_USER_EVENTS.append(DevicelistPEP)
        self.announced = []
        self.query_for_bundles = []
        self.disabled_accounts = []
        self.gc_message = {}
        self.windowinstances = {}

        self.config_default_values = {'DISABLED_ACCOUNTS': ([], ''), }

        for account in self.config['DISABLED_ACCOUNTS']:
            self.disabled_accounts.append(account)

        # add aesgcm:// uri scheme to config
        schemes = gajim.config.get('uri_schemes')
        if 'aesgcm://' not in schemes.split():
            schemes += ' aesgcm://'
            gajim.config.set('uri_schemes', schemes)

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
            my_jid = gajim.get_jid_from_account(account)
            db_path = self.migrate_dbpath(account, my_jid)

            conn = sqlite3.connect(db_path, check_same_thread=False)
            self.omemo_states[account] = OmemoState(my_jid, conn, account,
                                                    self)

        return self.omemo_states[account]

    def file_decryption(self, url, kind, instance, window):
        FileDecryption(self).hyperlink_handler(url, kind, instance, window)

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

    def activate_encryption(self, chat_control):
        if isinstance(chat_control, GroupchatControl):
            if chat_control.room_jid not in self.groupchat:
                dialogs.ErrorDialog(
                _('Bad Configuration'),
                _('To use OMEMO in a Groupchat, the Groupchat should be'
                  ' non-anonymous and members-only.'))
                return False
        return True

    @staticmethod
    def encryption_state(chat_control, state):
        state['visible'] = True
        state['authenticated'] = True

    def on_encryption_button_clicked(self, chat_control):
        self.show_fingerprint_window(chat_control)

    def before_sendmessage(self, chat_control):
        account = chat_control.account
        contact = chat_control.contact
        self.new_fingerprints_available(chat_control)
        if isinstance(chat_control, GroupchatControl):
            room = chat_control.room_jid
            missing = True
            own_jid = gajim.get_jid_from_account(account)
            for nick in self.groupchat[room]:
                real_jid = self.groupchat[room][nick]
                if real_jid == own_jid:
                    continue
                if not self.are_keys_missing(account, real_jid):
                    missing = False
            if missing:
                log.debug(account + ' => No Trusted Fingerprints for ' + room)
                self.no_trusted_fingerprints_warning(chat_control)
        else:
            if self.are_keys_missing(account, contact.jid):
                log.debug(account + ' => No Trusted Fingerprints for ' +
                          contact.jid)
                self.no_trusted_fingerprints_warning(chat_control)
                chat_control.sendmessage = False
            else:
                log.debug(account + ' => Sending Message to ' +
                          contact.jid)

    def new_fingerprints_available(self, chat_control):
        jid = chat_control.contact.jid
        account = chat_control.account
        state = self.get_omemo_state(account)
        if isinstance(chat_control, GroupchatControl):
            room_jid = chat_control.room_jid
            if room_jid in self.groupchat:
                for nick in self.groupchat[room_jid]:
                    real_jid = self.groupchat[room_jid][nick]
                    fingerprints = state.store. \
                        getNewFingerprints(real_jid)
                    if fingerprints:
                        self.show_fingerprint_window(
                            chat_control, fingerprints)
        elif not isinstance(chat_control, GroupchatControl):
            fingerprints = state.store.getNewFingerprints(jid)
            if fingerprints:
                self.show_fingerprint_window(
                    chat_control, fingerprints)

    def show_fingerprint_window(self, chat_control, fingerprints=None):
        contact = chat_control.contact
        account = chat_control.account
        state = self.get_omemo_state(account)
        transient = chat_control.parent_win.window
        if 'dialog' not in self.windowinstances:
            if isinstance(chat_control, GroupchatControl):
                self.windowinstances['dialog'] = \
                    FingerprintWindow(self, contact, transient,
                                      self.windowinstances, groupchat=True)
            else:
                self.windowinstances['dialog'] = \
                    FingerprintWindow(self, contact, transient,
                                      self.windowinstances)
            self.windowinstances['dialog'].show_all()
            if fingerprints:
                log.debug(account +
                          ' => Showing Fingerprint Prompt for ' +
                          contact.jid)
                state.store.setShownFingerprints(fingerprints)
        else:
            self.windowinstances['dialog'].update_context_list()
            if fingerprints:
                state.store.setShownFingerprints(fingerprints)

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

    def message_received(self, conn, obj, callback):
        if obj.encrypted:
            return
        if isinstance(obj, MessageReceivedEvent):
            self._message_received(obj)
        elif isinstance(obj, MamMessageReceivedEvent):
            self._mam_message_received(obj)
        if obj.encrypted == 'OMEMO':
            callback(obj)

    def _mam_message_received(self, msg):
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
                msg.encrypted = 'drop'
                return

            self.print_msg_to_log(msg.msg_)

            msg.msgtxt = plaintext
            msg.encrypted = self.encryption_name
            return

        elif msg.msg_.getTag('body'):
            account = msg.conn.name

            from_jid = str(msg.msg_.getAttr('from'))
            from_jid = gajim.get_jid_without_resource(from_jid)

            state = self.get_omemo_state(account)
            encryption = gajim.config.get_per('contacts', from_jid, 'encryption')

            if encryption == 'OMEMO':
                msg.msgtxt = '**Unencrypted** ' + msg.msgtxt

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
        account = msg.conn.name
        if account in self.disabled_accounts:
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
                            msg.encrypted = 'drop'
                            return
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
                    msg.encrypted = 'drop'
            else:
                msg_dict['sender_jid'] = gajim. \
                    get_jid_without_resource(from_jid)
                plaintext = state.decrypt_msg(msg_dict)

            if not plaintext:
                msg.encrypted = 'drop'
                return

            msg.msgtxt = plaintext
            # Gajim bug: there must be a body or the message
            # gets dropped from history
            msg.stanza.setBody(plaintext)
            msg.encrypted = self.encryption_name

        elif msg.stanza.getTag('body'):
            account = msg.conn.name

            from_jid = str(msg.stanza.getFrom())
            jid = gajim.get_jid_without_resource(from_jid)
            state = self.get_omemo_state(account)
            encryption = gajim.config.get_per('contacts', jid, 'encryption')

            if encryption == 'OMEMO':
                msg.msgtxt = '**Unencrypted** ' + msg.msgtxt
                msg.stanza.setBody(msg.msgtxt)

                ctrl = gajim.interface.msg_win_mgr.get_control(jid, account)
                if ctrl:
                    self.plain_warning(ctrl)

    def room_memberlist_received(self, event):
        account = event.conn.name
        if account in self.disabled_accounts:
            return
        log.debug('Room %s Memberlist received: %s',
                  event.fjid, event.users_dict)
        room = event.fjid

        if room not in self.groupchat:
            self.groupchat[room] = {}

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

    def gc_config_changed_received(self, event):
        account = event.conn.name
        room = event.room_jid
        if account in self.disabled_accounts:
            return
        if '172' in event.status_code:
            if room not in self.groupchat:
                self.groupchat[room] = self.temp_groupchat[room]
        log.debug('CONFIG CHANGE')
        log.debug(event.room_jid)
        log.debug(event.status_code)

    def _gc_encrypt_message(self, conn, event, callback):
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
            if not event.msg_iq.getTag('body'):
                return
            state = self.get_omemo_state(account)
            full_jid = str(event.msg_iq.getAttr('to'))
            to_jid = gajim.get_jid_without_resource(full_jid)

            plaintext = event.msg_iq.getBody()
            msg_dict = state.create_gc_msg(
                gajim.get_jid_from_account(account),
                to_jid,
                plaintext.encode('utf8'))
            if not msg_dict:
                return True

            self.cleanup_stanza(event)

            self.gc_message[msg_dict['payload']] = plaintext
            encrypted_node = OmemoMessage(msg_dict)

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

            self.print_msg_to_log(event.msg_iq)

            callback(event)
        except Exception as e:
            log.debug(e)
            return

    def _encrypt_message(self, conn, event, callback):
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

            plaintext = event.msg_iq.getBody().encode('utf8')

            msg_dict = state.create_msg(
                gajim.get_jid_from_account(account), to_jid, plaintext)
            if not msg_dict:
                return True

            encrypted_node = OmemoMessage(msg_dict)
            self.cleanup_stanza(event)

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
            event.xhtml = None
            event.encrypted = self.encryption_name
            callback(event)
        except Exception as e:
            log.debug(e)

    @staticmethod
    def cleanup_stanza(obj):
        ''' We make sure only allowed tags are in the stanza '''
        stanza = nbxmpp.Message(
            to=obj.msg_iq.getTo(),
            typ=obj.msg_iq.getType())
        stanza.setThread(obj.msg_iq.getThread())
        for tag, ns in ALLOWED_TAGS:
            node = obj.msg_iq.getTag(tag, namespace=ns)
            if node:
                stanza.addChild(node=node)
        obj.msg_iq = stanza

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
        if not devices_list:
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
            # TODO

        return True

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
            ctrl = gajim.interface.msg_win_mgr.get_control(
                recipient_id, account)
            if ctrl:
                self.new_fingerprints_available(ctrl)

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
            if not devices_list:
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

    @staticmethod
    def plain_warning(chat_control):
        chat_control.print_conversation_line(
            'Received plaintext message! ' +
            'Your next message will still be encrypted!', 'status', '', None)

    @staticmethod
    def no_trusted_fingerprints_warning(chat_control):
        msg = "To send an encrypted message, you have to " \
              "first trust the fingerprint of your contact!"
        chat_control.print_conversation_line(msg, 'status', '', None)

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
