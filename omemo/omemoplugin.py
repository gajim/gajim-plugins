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
import binascii
import threading
from enum import IntEnum, unique

from gi.repository import GLib

from gajim import dialogs
from gajim.common import app, ged
from gajim.common.pep import SUPPORTED_PERSONAL_USER_EVENTS
from gajim.plugins import GajimPlugin
from gajim.groupchat_control import GroupchatControl

from omemo.xmpp import DevicelistPEP

CRYPTOGRAPHY_MISSING = 'You are missing Python-Cryptography'
AXOLOTL_MISSING = 'You are missing Python-Axolotl or use an outdated version'
PROTOBUF_MISSING = 'OMEMO cant import Google Protobuf, you can find help in ' \
                   'the GitHub Wiki'
ERROR_MSG = ''


log = logging.getLogger('gajim.plugin_system.omemo')

try:
    from omemo import file_crypto
except Exception as error:
    log.exception(error)
    ERROR_MSG = CRYPTOGRAPHY_MISSING

try:
    import google.protobuf
except Exception as error:
    log.error(error)
    ERROR_MSG = PROTOBUF_MISSING

try:
    import axolotl
except Exception as error:
    log.error(error)
    ERROR_MSG = AXOLOTL_MISSING

if not ERROR_MSG:
    try:
        from omemo.omemo_connection import OMEMOConnection
        from omemo.ui import OMEMOConfigDialog, FingerprintWindow
    except Exception as error:
        log.error(error)
        ERROR_MSG = 'Error: %s' % error

# pylint: disable=no-init
# pylint: disable=attribute-defined-outside-init


@unique
class UserMessages(IntEnum):
    QUERY_DEVICES = 0
    NO_FINGERPRINTS = 1


class OmemoPlugin(GajimPlugin):
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
            'signed-in': (ged.PRECORE, self.signed_in),
            }

        self.config_dialog = OMEMOConfigDialog(self)
        self.gui_extension_points = {
            'hyperlink_handler': (self._file_decryption, None),
            'encrypt' + self.encryption_name: (self._encrypt_message, None),
            'gc_encrypt' + self.encryption_name: (
                self._gc_encrypt_message, None),
            'decrypt': (self._message_received, None),
            'send_message' + self.encryption_name: (
                self.before_sendmessage, None),
            'encryption_dialog' + self.encryption_name: (
                self.on_encryption_button_clicked, None),
            'encryption_state' + self.encryption_name: (
                self.encryption_state, None),
            'update_caps': (self._update_caps, None)}

        SUPPORTED_PERSONAL_USER_EVENTS.append(DevicelistPEP)
        self.disabled_accounts = []
        self.windowinstances = {}
        self.connections = {}

        self.config_default_values = {'DISABLED_ACCOUNTS': ([], ''), }

        for account in self.config['DISABLED_ACCOUNTS']:
            self.disabled_accounts.append(account)

        # add aesgcm:// uri scheme to config
        schemes = app.config.get('uri_schemes')
        if 'aesgcm://' not in schemes.split():
            schemes += ' aesgcm://'
            app.config.set('uri_schemes', schemes)

    def signed_in(self, event):
        """ Method called on SignIn

            Parameters
            ----------
            event : SignedInEvent
        """
        account = event.conn.name
        if account == 'Local':
            return
        if account in self.disabled_accounts:
            return
        if account not in self.connections:
            self.connections[account] = OMEMOConnection(account, self)
            self.connections[account].signed_in(event)

    def activate(self):
        """ Method called when the Plugin is activated in the PluginManager
        """
        for account in app.connections:
            if account == 'Local':
                continue
            if account in self.disabled_accounts:
                continue
            self.connections[account] = OMEMOConnection(account, self)
            self.connections[account].activate()

    def deactivate(self):
        """ Method called when the Plugin is deactivated in the PluginManager
        """
        for account in self.connections:
            if account == 'Local':
                continue
            self.connections[account].deactivate()

    def _update_caps(self, account):
        if account == 'Local':
            return
        if account not in self.connections:
            self.connections[account] = OMEMOConnection(account, self)
        self.connections[account].update_caps(account)

    def activate_encryption(self, chat_control):
        if isinstance(chat_control, GroupchatControl):
            omemo_con = self.connections[chat_control.account]
            if chat_control.room_jid not in omemo_con.groupchat:
                dialogs.ErrorDialog(
                    _('Bad Configuration'),
                    _('To use OMEMO in a Groupchat, the Groupchat should be'
                      ' non-anonymous and members-only.'))
                return False
        return True

    def _message_received(self, conn, obj, callback):
        self.connections[conn.name].message_received(conn, obj, callback)

    def _gc_encrypt_message(self, conn, obj, callback):
        self.connections[conn.name].gc_encrypt_message(conn, obj, callback)

    def _encrypt_message(self, conn, obj, callback):
        self.connections[conn.name].encrypt_message(conn, obj, callback)

    def _file_decryption(self, url, kind, instance, window):
        file_crypto.FileDecryption(self).hyperlink_handler(
            url, kind, instance, window)

    def encrypt_file(self, file, account, callback):
        thread = threading.Thread(target=self._encrypt_file_thread,
                                  args=(file, callback))
        thread.daemon = True
        thread.start()

    @staticmethod
    def _encrypt_file_thread(file, callback, *args, **kwargs):
        encrypted_data, key, iv = file_crypto.encrypt_file(
            file.get_data(full=True))
        file.encrypted = True
        file.size = len(encrypted_data)
        file.user_data = binascii.hexlify(iv + key).decode('utf-8')
        file.data = encrypted_data
        if file.event.isSet():
            return
        GLib.idle_add(callback, file)

    @staticmethod
    def encryption_state(chat_control, state):
        state['visible'] = True
        state['authenticated'] = True

    def on_encryption_button_clicked(self, chat_control):
        self.show_fingerprint_window(chat_control)

    def get_omemo(self, account):
        return self.connections[account].omemo

    def before_sendmessage(self, chat_control):
        account = chat_control.account
        contact = chat_control.contact
        con = self.connections[account]
        self.new_fingerprints_available(chat_control)
        if isinstance(chat_control, GroupchatControl):
            room = chat_control.room_jid
            missing = True
            own_jid = app.get_jid_from_account(account)
            for nick in con.groupchat[room]:
                real_jid = con.groupchat[room][nick]
                if real_jid == own_jid:
                    continue
                if not con.are_keys_missing(real_jid):
                    missing = False
            if missing:
                log.info('%s => No Trusted Fingerprints for %s',
                         account, room)
                self.print_message(chat_control, UserMessages.NO_FINGERPRINTS)
        else:
            # check if we have devices for the contact
            if not self.get_omemo(account).device_list_for(contact.jid):
                con.query_devicelist(contact.jid, True)
                self.print_message(chat_control, UserMessages.QUERY_DEVICES)
                chat_control.sendmessage = False
                return
            # check if bundles are missing for some devices
            if con.are_keys_missing(contact.jid):
                log.info('%s => No Trusted Fingerprints for %s',
                         account, contact.jid)
                self.print_message(chat_control, UserMessages.NO_FINGERPRINTS)
                chat_control.sendmessage = False
            else:
                log.debug('%s => Sending Message to %s',
                          account, contact.jid)

    def new_fingerprints_available(self, chat_control):
        jid = chat_control.contact.jid
        account = chat_control.account
        con = self.connections[account]
        omemo = self.get_omemo(account)
        if isinstance(chat_control, GroupchatControl):
            room_jid = chat_control.room_jid
            if room_jid in con.groupchat:
                for nick in con.groupchat[room_jid]:
                    real_jid = con.groupchat[room_jid][nick]
                    fingerprints = omemo.store. \
                        getNewFingerprints(real_jid)
                    if fingerprints:
                        self.show_fingerprint_window(
                            chat_control, fingerprints)
        elif not isinstance(chat_control, GroupchatControl):
            fingerprints = omemo.store.getNewFingerprints(jid)
            if fingerprints:
                self.show_fingerprint_window(
                    chat_control, fingerprints)

    def show_fingerprint_window(self, chat_control, fingerprints=None):
        contact = chat_control.contact
        account = chat_control.account
        omemo = self.get_omemo(account)
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
                log.debug('%s => Showing Fingerprint Prompt for %s',
                          account, contact.jid)
                omemo.store.setShownFingerprints(fingerprints)
        else:
            self.windowinstances['dialog'].update_context_list()
            if fingerprints:
                omemo.store.setShownFingerprints(fingerprints)

    @staticmethod
    def print_message(chat_control, kind):
        msg = None
        if kind == UserMessages.QUERY_DEVICES:
            msg = _('No devices found. Query in progress...')
        elif kind == UserMessages.NO_FINGERPRINTS:
            msg = _('To send an encrypted message, you have to '
                    'first trust the fingerprint of your contact!')
        if msg is None:
            return
        chat_control.print_conversation_line(msg, 'status', '', None)
