# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the PGP Gajim Plugin.
#
# PGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# PGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import os
import time
import threading

import nbxmpp
from nbxmpp.namespaces import Namespace
from nbxmpp.protocol import Message
from nbxmpp.structs import EncryptionData
from nbxmpp.structs import StanzaHandler
from gi.repository import GLib

from gajim.common import app
from gajim.common.const import Trust
from gajim.common.events import MessageNotSent
from gajim.common.structs import OutgoingMessage
from gajim.common.modules.base import BaseModule

from gajim.plugins.plugins_i18n import _

from pgp.backend.python_gnupg import PGP
from pgp.modules.events import PGPFileEncryptionError
from pgp.modules.events import PGPNotTrusted
from pgp.modules.util import prepare_stanza
from pgp.backend.store import KeyStore
from pgp.exceptions import SignError
from pgp.exceptions import KeyMismatch
from pgp.exceptions import NoKeyIdFound


# Module name
name = 'PGPLegacy'
zeroconf = True
ENCRYPTION_NAME = 'PGP'

ALLOWED_TAGS = [
    ('request', Namespace.RECEIPTS),
    ('active', Namespace.CHATSTATES),
    ('gone', Namespace.CHATSTATES),
    ('inactive', Namespace.CHATSTATES),
    ('paused', Namespace.CHATSTATES),
    ('composing', Namespace.CHATSTATES),
    ('markable', Namespace.CHATMARKERS),
    ('no-store', Namespace.HINTS),
    ('store', Namespace.HINTS),
    ('no-copy', Namespace.HINTS),
    ('no-permanent-store', Namespace.HINTS),
    ('replace', Namespace.CORRECT),
    ('thread', None),
    ('reply', Namespace.REPLY),
    ('fallback', Namespace.FALLBACK),
    ('origin-id', Namespace.SID),
    ('reactions', Namespace.REACTIONS),
]


class PGPLegacy(BaseModule):
    def __init__(self, client):
        BaseModule.__init__(self, client, plugin=True)

        self.handlers = [
            StanzaHandler(name='message',
                          callback=self._message_received,
                          ns=Namespace.ENCRYPTED,
                          priority=9),
            StanzaHandler(name='presence',
                          callback=self._on_presence_received,
                          ns=Namespace.SIGNED,
                          priority=48),
        ]

        self.own_jid = self._client.get_own_jid()

        self._pgp = PGP()
        self._store = KeyStore(self._account, self.own_jid, self._log,
                               self._pgp.list_keys)
        self._always_trust = []
        self._presence_fingerprint_store = {}

    @property
    def pgp_backend(self):
        return self._pgp

    def set_own_key_data(self, *args, **kwargs):
        return self._store.set_own_key_data(*args, **kwargs)

    def get_own_key_data(self, *args, **kwargs):
        return self._store.get_own_key_data(*args, **kwargs)

    def set_contact_key_data(self, *args, **kwargs):
        return self._store.set_contact_key_data(*args, **kwargs)

    def get_contact_key_data(self, *args, **kwargs):
        return self._store.get_contact_key_data(*args, **kwargs)

    def has_valid_key_assigned(self, jid):
        key_data = self.get_contact_key_data(jid)
        if key_data is None:
            return False
        key_id = key_data['key_id']

        announced_fingerprint = self._presence_fingerprint_store.get(jid)
        if announced_fingerprint is None:
            return True

        if announced_fingerprint == key_id:
            return True

        raise KeyMismatch(announced_fingerprint)

    def _on_presence_received(self, _con, _stanza, properties):
        if properties.signed is None:
            return
        jid = properties.jid.bare

        fingerprint = self._pgp.verify(properties.status, properties.signed)
        if fingerprint is None:
            self._log.info('Presence from %s was signed but no corresponding '
                           'key was found', jid)
            return

        self._presence_fingerprint_store[jid] = fingerprint
        self._log.info('Presence from %s was verified successfully, '
                       'fingerprint: %s', jid, fingerprint)

        key_data = self.get_contact_key_data(jid)
        if key_data is None:
            self._log.info('No key assigned for contact: %s', jid)
            return

        if key_data['key_id'] != fingerprint:
            self._log.warning('Fingerprint mismatch, '
                              'Presence was signed with fingerprint: %s, '
                              'Assigned key fingerprint: %s',
                              fingerprint, key_data['key_id'])
            return

    def _message_received(self, _con, stanza, properties):
        if not properties.is_pgp_legacy or properties.from_muc:
            return

        remote_jid = properties.remote_jid
        self._log.info('Message received from: %s', remote_jid)

        payload = self._pgp.decrypt(properties.pgp_legacy)
        prepare_stanza(stanza, payload)

        properties.encrypted = EncryptionData(
            protocol=ENCRYPTION_NAME,
            key='Unknown',
            trust=Trust.UNDECIDED
        )

    def encrypt_message(self, con, message: OutgoingMessage, callback):
        if not message.get_text():
            callback(message)
            return

        to_jid = str(message.contact.jid)
        try:
            key_id, own_key_id = self._get_key_ids(to_jid)
        except NoKeyIdFound as error:
            self._log.warning(error)
            return

        always_trust = key_id in self._always_trust
        self._encrypt(con, message, [key_id, own_key_id], callback, always_trust)

    def _encrypt(self, con, message: OutgoingMessage, keys, callback, always_trust: bool):
        result = self._pgp.encrypt(message.get_text(), keys, always_trust)
        encrypted_payload, error = result
        if error:
            self._handle_encrypt_error(con, error, message, keys, callback)
            return

        self._cleanup_stanza(message)
        self._create_pgp_legacy_message(message.get_stanza(), encrypted_payload)

        message.set_encryption(
            EncryptionData(
                protocol=ENCRYPTION_NAME,
                key='Unknown',
                trust=Trust.VERIFIED,
            )
        )

        callback(message)

    def _handle_encrypt_error(self, con, error: str, message: OutgoingMessage, keys, callback):
        if error.startswith('NOT_TRUSTED'):
            def on_yes(checked):
                if checked:
                    self._always_trust.append(keys[0])
                self._encrypt(con, message, keys, callback, True)

            def on_no():
                self._raise_message_not_sent(con, message, error)

            app.ged.raise_event(PGPNotTrusted(on_yes=on_yes, on_no=on_no))

        else:
            self._raise_message_not_sent(con, message, error)

    @staticmethod
    def _raise_message_not_sent(con, message: OutgoingMessage, error: str):
        app.ged.raise_event(
            MessageNotSent(client=con,
                           jid=str(message.contact.jid),
                           message=message.get_text(),
                           error=_('Encryption error: %s') % error,
                           time=time.time()))

    def _create_pgp_legacy_message(self, stanza: Message, payload: str) -> None:
        stanza.setBody(self._get_info_message())
        stanza.setTag('x', namespace=Namespace.ENCRYPTED).setData(payload)
        eme_node = nbxmpp.Node('encryption',
                               attrs={'xmlns': Namespace.EME,
                                      'namespace': Namespace.ENCRYPTED})
        stanza.addChild(node=eme_node)

    def sign_presence(self, presence, status):
        key_data = self.get_own_key_data()
        if key_data is None:
            self._log.warning('No own key id found, can’t sign presence')
            return

        try:
            result = self._pgp.sign(status, key_data['key_id'])
        except SignError as error:
            self._log.warning('Sign Error: %s', error)
            return
        # self._log.debug(self._pgp.sign.cache_info())
        self._log.info('Presence signed')
        presence.setTag(Namespace.SIGNED + ' x').setData(result)

    @staticmethod
    def _get_info_message():
        msg = '[This message is *encrypted* (See :XEP:`27`)]'
        lang = os.getenv('LANG')
        if lang is not None and not lang.startswith('en'):
            # we're not english: one in locale and one en
            msg = _('[This message is *encrypted* (See :XEP:`27`)]') + \
                    ' (' + msg + ')'
        return msg

    def _get_key_ids(self, jid):
        key_data = self.get_contact_key_data(jid)
        if key_data is None:
            raise NoKeyIdFound('No key id found for %s' % jid)
        key_id = key_data['key_id']

        own_key_data = self.get_own_key_data()
        if own_key_data is None:
            raise NoKeyIdFound('Own key id not found')
        own_key_id = own_key_data['key_id']
        return key_id, own_key_id

    @staticmethod
    def _cleanup_stanza(message: OutgoingMessage) -> None:
        ''' We make sure only allowed tags are in the stanza '''
        original_stanza = message.get_stanza()
        stanza = nbxmpp.Message(
            to=original_stanza.getTo(),
            typ=original_stanza.getType())
        stanza.setID(original_stanza.getID())
        stanza.setThread(original_stanza.getThread())
        for tag, ns in ALLOWED_TAGS:
            node = original_stanza.getTag(tag, namespace=ns)
            if node:
                stanza.addChild(node=node)
        message.set_stanza(stanza)

    def encrypt_file(self, file, callback):
        thread = threading.Thread(target=self._encrypt_file_thread,
                                  args=(file, callback))
        thread.daemon = True
        thread.start()

    def _encrypt_file_thread(self, file, callback):
        try:
            key_id, own_key_id = self._get_key_ids(file.contact.jid)
        except NoKeyIdFound as error:
            self._log.warning(error)
            return

        stream = open(file.path, "rb")
        encrypted = self._pgp.encrypt_file(stream,
                                           [key_id, own_key_id])
        stream.close()

        if not encrypted:
            GLib.idle_add(self._on_file_encryption_error, encrypted.status)
            return

        file.size = len(encrypted.data)
        file.set_uri_transform_func(lambda uri: '%s.pgp' % uri)
        file.set_encrypted_data(encrypted.data)
        GLib.idle_add(callback, file)

    @staticmethod
    def _on_file_encryption_error(error):
        app.ged.raise_event(PGPFileEncryptionError(error=error))

def get_instance(*args, **kwargs):
    return PGPLegacy(*args, **kwargs), 'PGPLegacy'
