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
import ui

# pylint: disable=import-error
from common import caps_cache, gajim, ged
from common.pep import SUPPORTED_PERSONAL_USER_EVENTS
from plugins import GajimPlugin
from plugins.helpers import log_calls

from nbxmpp.simplexml import Node


from .ui import Ui
from .xmpp import (
    NS_NOTIFY, NS_OMEMO, BundleInformationAnnouncement, BundleInformationQuery,
    DeviceListAnnouncement, DevicelistQuery, DevicelistPEP, OmemoMessage, successful,
    unpack_device_bundle, unpack_device_list_update, unpack_encrypted)


iq_ids_to_callbacks = {}

AXOLOTL_MISSING = 'Please install python-axolotl.'

NS_HINTS = 'urn:xmpp:hints'

log = logging.getLogger('gajim.plugin_system.omemo')
try:
    from omemo.state import OmemoState
    HAS_AXOLOTL = True
except ImportError:
    log.error(AXOLOTL_MISSING)
    HAS_AXOLOTL = False

DB_DIR = gajim.gajimpaths.data_root


class OmemoPlugin(GajimPlugin):
    # pylint: disable=no-init

    omemo_states = {}

    ui_list = {}

    @log_calls('OmemoPlugin')
    def init(self):
        if not HAS_AXOLOTL:
            self.activatable = False
            self.available_text = _(AXOLOTL_MISSING)
            return
        self.events_handlers = {
            'mam-message-received': (ged.PRECORE, self.mam_message_received),
            'message-received': (ged.PRECORE, self.message_received),
            'pep-received': (ged.PRECORE, self.handle_device_list_update),
            'raw-iq-received': (ged.PRECORE, self.handle_iq_received),
            'signed-in': (ged.PRECORE, self.signed_in),
            'stanza-message-outgoing':
            (ged.PRECORE, self.handle_outgoing_msgs),
        }
        self.config_dialog = ui.OMEMOConfigDialog(self)
        self.gui_extension_points = {'chat_control': (self.connect_ui, None)}
        SUPPORTED_PERSONAL_USER_EVENTS.append(DevicelistPEP)

    @log_calls('OmemoPlugin')
    def get_omemo_state(self, account):
        """ Returns the the OmemoState for specified account. Creates the
            OmemoState if it does not exist yet.
        """
        if account not in self.omemo_states:
            db_path = os.path.join(DB_DIR, 'omemo_' + account + '.db')
            conn = sqlite3.connect(db_path, check_same_thread=False)

            my_jid = gajim.get_jid_from_account(account)

            self.omemo_states[account] = OmemoState(my_jid, conn)
        return self.omemo_states[account]

    @log_calls('OmemoPlugin')
    def signed_in(self, show):
        """
            On sign in announce OMEMO support for each account.
        """
        account = show.conn.name
        self.announce_support(account)

    @log_calls('OmemoPlugin')
    def activate(self):
        if NS_NOTIFY not in gajim.gajim_common_features:
            gajim.gajim_common_features.append(NS_NOTIFY)
        self._compute_caps_hash()

    @log_calls('OmemoPlugin')
    def deactivate(self):
        if NS_NOTIFY in gajim.gajim_common_features:
            gajim.gajim_common_features.remove(NS_NOTIFY)
        self._compute_caps_hash()

    @log_calls('OmemoPlugin')
    def _compute_caps_hash(self):
        for a in gajim.connections:
            gajim.caps_hash[a] = caps_cache.compute_caps_hash(
                [
                    gajim.gajim_identity
                ],
                gajim.gajim_common_features + gajim.gajim_optional_features[a])
            # re-send presence with new hash
            connected = gajim.connections[a].connected
            if connected > 1 and gajim.SHOW_LIST[connected] != 'invisible':
                gajim.connections[a].change_status(gajim.SHOW_LIST[connected],
                                                   gajim.connections[a].status)

    @log_calls('OmemoPlugin')
    def mam_message_received(self, msg):
        if msg.msg_.getTag('encrypted', namespace=NS_OMEMO):
            account = msg.conn.name
            log.debug(account + ' => OMEMO MAM msg received')
            log.debug(msg.msg_)
            state = self.get_omemo_state(account)

            from_jid = str(msg.msg_.getAttr('from'))
            from_jid = gajim.get_jid_without_resource(from_jid)

            msg_dict = unpack_encrypted(msg.msg_.getTag
                                        ('encrypted', namespace=NS_OMEMO))
            msg_dict['sender_jid'] = from_jid
            plaintext = state.decrypt_msg(msg_dict)

            if not plaintext:
                return

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

                try:
                    gui = self.ui_list[account].get(jid, None)
                    if gui and gui.encryption_active():
                        gui.plain_warning()
                except KeyError:
                    log.debug('No Ui present for ' + jid +
                              ', Ui Warning not shown')

    @log_calls('OmemoPlugin')
    def message_received(self, msg):
        if msg.stanza.getTag('encrypted', namespace=NS_OMEMO) and \
                msg.mtype == 'chat':
            account = msg.conn.name
            log.debug(account + ' => OMEMO msg received')

            state = self.get_omemo_state(account)
            if msg.forwarded and msg.sent:
                from_jid = str(msg.stanza.getTo())  # why gajim? why?
                log.debug('message was forwarded doing magic')
            else:
                from_jid = str(msg.stanza.getFrom())

            msg_dict = unpack_encrypted(msg.stanza.getTag
                                        ('encrypted', namespace=NS_OMEMO))
            msg_dict['sender_jid'] = gajim.get_jid_without_resource(from_jid)
            plaintext = state.decrypt_msg(msg_dict)

            if not plaintext:
                return

            msg.msgtxt = plaintext
            # bug? there must be a body or the message gets dropped from history
            msg.stanza.setBody(plaintext)

            contact_jid = gajim.get_jid_without_resource(from_jid)
            if account in self.ui_list and \
                    contact_jid in self.ui_list[account]:
                self.ui_list[account][contact_jid].activate_omemo()
            return False

        elif msg.stanza.getTag('body') and msg.mtype == 'chat':
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

    @log_calls('OmemoPlugin')
    def handle_device_list_update(self, event):
        """ Check if the passed event is a device list update and store the new
            device ids.

            Parameters
            ----------
            event : MessageReceivedEvent

            Returns
            -------
            bool
                True if the given event was a valid device list update event


            See also
            --------
            4.2 Discovering peer support
                http://conversations.im/xeps/multi-end.html#usecases-discovering
        """
        if event.pep_type != 'headline':
            return False

        devices_list = unpack_device_list_update(event.stanza, event.conn.name)
        if len(devices_list) == 0:
            return False
        account_name = event.conn.name
        contact_jid = gajim.get_jid_without_resource(event.fjid)
        state = self.get_omemo_state(account_name)
        my_jid = gajim.get_jid_from_account(account_name)

        if contact_jid == my_jid:
            log.info(account_name + ' => Received own device_list:' + str(
                devices_list))
            state.set_own_devices(devices_list)

            if not state.own_device_id_published() or anydup(
                    state.own_devices):
                # Our own device_id is not in the list, it could be
                # overwritten by some other client?
                # also remove duplicates
                devices_list = list(set(state.own_devices))
                devices_list.append(state.own_device_id)
                self.publish_own_devices_list(account_name, state)
        else:
            log.info(account_name + ' => Received device_list for ' +
                     contact_jid + ':' + str(devices_list))
            state.set_devices(contact_jid, devices_list)
            if (account_name in self.ui_list and
                    contact_jid not in self.ui_list[account_name]):

                chat_control = gajim.interface.msg_win_mgr.get_control(
                    contact_jid, account_name)

                if chat_control is not None:
                    self.connect_ui(chat_control)

        # Look if Device Keys are missing and fetch them
        self.are_keys_missing(account_name, contact_jid)

        return True

    @log_calls('OmemoPlugin')
    def publish_own_devices_list(self, account_name, state):
        devices_list = state.own_devices
        devices_list += [state.own_device_id]

        log.debug(account_name + ' => Publishing own devices_list ' + str(
            devices_list))
        iq = DeviceListAnnouncement(devices_list)
        gajim.connections[account_name].connection.send(iq)
        id_ = str(iq.getAttr('id'))
        iq_ids_to_callbacks[id_] = lambda event: log.debug(event)

    @log_calls('OmemoPlugin')
    def connect_ui(self, chat_control):
        account_name = chat_control.contact.account.name
        contact_jid = chat_control.contact.jid
        if account_name not in self.ui_list:
            self.ui_list[account_name] = {}
        state = self.get_omemo_state(account_name)
        my_jid = gajim.get_jid_from_account(account_name)
        if contact_jid in state.device_ids or contact_jid == my_jid:
            log.debug(account_name + " => Adding OMEMO ui for " + contact_jid)
            omemo_enabled = state.encryption.is_active(contact_jid)
            self.ui_list[account_name][contact_jid] = Ui(self, chat_control,
                                                         omemo_enabled, state)
        else:
            log.warn(account_name + " => No OMEMO dev_keys for " + contact_jid)

    def are_keys_missing(self, account_name, contact_jid):
        """ Used by the ui to set the state of the PreKeyButton. """

        my_jid = gajim.get_jid_from_account(account_name)
        state = self.get_omemo_state(account_name)
        result = 0
        result += len(state.devices_without_sessions(str(contact_jid)))
        result += len(state.own_devices_without_sessions(my_jid))
        if result > 0:
            log.info(account_name + " => Missing keys for " + contact_jid + ": " +
                     str(result))
            log.info('Query keys now ...')
            self.query_prekey(account_name, contact_jid)

    @log_calls('OmemoPlugin')
    def handle_iq_received(self, event):
        global iq_ids_to_callbacks
        id_ = str(event.stanza.getAttr("id"))
        if id_ in iq_ids_to_callbacks:
            try:
                iq_ids_to_callbacks[id_](event.stanza)
            except:
                raise
            finally:
                del iq_ids_to_callbacks[id_]

    @log_calls('OmemoPlugin')
    def query_prekey(self, account_name, contact_jid):
        """ Calls OmemoPlugin.fetch_device_bundle_information() for each own or
            recipient device key missing.
        """
        account = account_name
        state = self.get_omemo_state(account)
        to_jid = contact_jid
        my_jid = gajim.get_jid_from_account(account)
        for device_id in state.devices_without_sessions(to_jid):
            self.fetch_device_bundle_information(account, state, to_jid,
                                                 device_id)

        for device_id in state.own_devices_without_sessions(my_jid):
            self.fetch_device_bundle_information(account, state, my_jid,
                                                 device_id)

    @log_calls('OmemoPlugin')
    def fetch_device_bundle_information(self, account_name, state, jid,
                                        device_id):
        """ Fetch bundle information for specified jid, key, and create axolotl
            session on success.

            Parameters
            ----------
            account_name : str
                The account name
            state : (OmemoState)
                The OmemoState which is missing device bundle information
            jid : str
                The jid to query for bundle information
            device_id : int
                The device_id for which we are missing an axolotl session
        """
        log.debug(account_name + '=> Fetch bundle device ' + str(device_id) +
                  '#' + jid)
        iq = BundleInformationQuery(jid, device_id)
        iq_id = str(iq.getAttr('id'))
        iq_ids_to_callbacks[iq_id] = \
            lambda stanza: self.session_from_prekey_bundle(account_name, state,
                                                           stanza, jid,
                                                           device_id)
        gajim.connections[account_name].connection.send(iq)

    @log_calls('OmemoPlugin')
    def session_from_prekey_bundle(self, account_name, state, stanza,
                                   recipient_id, device_id):
        """ Starts a session when a bundle information announcement is received.


            This method tries to build an axolotl session when a PreKey bundle
            is fetched.

            If a session can not be build it will fail silently but log the a
            warning.

            See also
            --------
            4.3. Announcing bundle information:
                http://conversations.im/xeps/multi-end.html#usecases-announcing

            4.4 Building a session:
                http://conversations.im/xeps/multi-end.html#usecases-building

            Parameters:
            -----------
            account_name : str
                The account name
            state : (OmemoState)
                The OmemoState used
            stanza
                The stanza object received from callback
            recipient_id : str
                           The recipient jid
            device_id : int
                The device_id for which the bundle was queried

        """
        bundle_dict = unpack_device_bundle(stanza, device_id)
        if not bundle_dict:
            log.warn('Failed requesting a bundle')
            return

        if state.build_session(recipient_id, device_id, bundle_dict):
            log.warn(recipient_id + ' => session created')
            # Warn User about new Fingerprints in DB if Chat Window is Open
            if account_name in self.ui_list and \
                    recipient_id in self.ui_list[account_name]:
                self.ui_list[account_name][recipient_id]. \
                    WarnIfUndecidedFingerprints()

    @log_calls('OmemoPlugin')
    def announce_support(self, account):
        """ Announce OMEMO support for an account via PEP.

            In order for other clients/devices to be able to initiate a session
            with gajim, it first has to announce itself by adding its device ID
            to the devicelist PEP node.

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
        log.debug(account + " => Announcing OMEMO support via PEP")
        iq_ids_to_callbacks[id_] = lambda stanza: \
            self.handle_announcement_result(account, stanza)

    @log_calls('OmemoPlugin')
    def handle_announcement_result(self, account, stanza):
        """ Query own device list if announcement was successfull.

            If the OMEMO support announcement was successfull own device
            list is queried.

            Parameters
            ----------
            account : str
                the account name
            stanza
                The stanza object received from callback
        """
        my_jid = gajim.get_jid_from_account(account)
        iq = DevicelistQuery(my_jid)
        if successful(stanza):
            log.debug(account + ' => Publishing bundle was successful')
            gajim.connections[account].connection.send(iq)
            log.debug(account + ' => Querry own Devicelist')
            id_ = str(iq.getAttr("id"))
            iq_ids_to_callbacks[id_] = lambda stanza: \
                self.handle_devicelist_result(account, stanza)
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
            log.debug(account + ' => Devicelistquery was successful')
            devices_list = unpack_device_list_update(stanza, account)
            if len(devices_list) == 0:
                return False
            contact_jid = stanza.getAttr('from')
            if contact_jid == my_jid:
                state.set_own_devices(devices_list)
                if not state.own_device_id_published() or anydup(
                        state.own_devices):
                    # Our own device_id is not in the list, it could be
                    # overwritten by some other client?
                    # also remove duplicates
                    devices_list = list(set(state.own_devices))
                    devices_list.append(state.own_device_id)
                    self.publish_own_devices_list(account, state)
        else:
            log.error(account + ' => Devicelistquery was NOT successful')
            self.publish_own_devices_list(account, state)

    @log_calls('OmemoPlugin')
    def clear_device_list(self, account):
        state = self.get_omemo_state(account)
        devices_list = [state.own_device_id]
        state.set_own_devices(devices_list)

        log.info(account + ' => Clearing devices_list ' + str(devices_list))
        iq = DeviceListAnnouncement(devices_list)
        connection = gajim.connections[account].connection
        if not connection:  # not connected
            return
        connection.send(iq)
        id_ = str(iq.getAttr('id'))
        iq_ids_to_callbacks[id_] = lambda event: log.info(event)

    @log_calls('OmemoPlugin')
    def handle_outgoing_msgs(self, event):
        if not event.msg_iq.getTag('body'):
            return
        plaintext = event.msg_iq.getBody().encode('utf8')
        account = event.conn.name
        state = self.get_omemo_state(account)
        full_jid = str(event.msg_iq.getAttr('to'))
        to_jid = gajim.get_jid_without_resource(full_jid)
        if not state.encryption.is_active(to_jid):
            return False

        if not state.store.identityKeyStore.getTrustedFingerprints(to_jid):
                msg = "To send an encrypted message, you have to " \
                      "first trust the fingerprint of your contact!"
                if account in self.ui_list and \
                        to_jid in self.ui_list[account]:
                    self.ui_list[account][to_jid].chat_control. \
                        print_conversation_line(msg, 'status', '', None)

                return True

        try:
            msg_dict = state.create_msg(
                gajim.get_jid_from_account(account), to_jid, plaintext)
            if not msg_dict:
                return True
            encrypted_node = OmemoMessage(msg_dict)
            event.msg_iq.delChild('body')
            event.msg_iq.addChild(node=encrypted_node)
            store = Node('store', attrs={'xmlns': NS_HINTS})
            event.msg_iq.addChild(node=store)
            log.debug(account + ' => ' + str(event.msg_iq))
        except:
            return True

    @log_calls('OmemoPlugin')
    def omemo_enable_for(self, contact):
        """ Used by the ui to enable omemo for a specified contact """
        account = contact.account.name
        state = self.get_omemo_state(account)
        state.encryption.activate(contact.jid)

    @log_calls('OmemoPlugin')
    def omemo_disable_for(self, contact):
        """ Used by the ui to disable omemo for a specified contact """
        # TODO Migrate this
        account = contact.account.name
        state = self.get_omemo_state(account)
        state.encryption.deactivate(contact.jid)


@log_calls('OmemoPlugin')
def anydup(thelist):
    seen = set()
    for x in thelist:
        if x in seen:
            return True
        seen.add(x)
    return False
