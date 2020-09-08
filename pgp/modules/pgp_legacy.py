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
from nbxmpp.structs import StanzaHandler
from gi.repository import GLib

from gajim.common import app
from gajim.common.nec import NetworkEvent
from gajim.common.const import EncryptionData
from gajim.common.modules.base import BaseModule

from gajim.plugins.plugins_i18n import _

from pgp.backend.python_gnupg import PGP
from pgp.modules.util import prepare_stanza
from pgp.backend.store import KeyStore
from pgp.exceptions import SignError
from pgp.exceptions import KeyMismatch
from pgp.exceptions import NoKeyIdFound


# Module name
name = 'PGPLegacy'
zeroconf = True

ALLOWED_TAGS = [('request', Namespace.RECEIPTS),
                ('active', Namespace.CHATSTATES),
                ('gone', Namespace.CHATSTATES),
                ('inactive', Namespace.CHATSTATES),
                ('paused', Namespace.CHATSTATES),
                ('composing', Namespace.CHATSTATES),
                ('no-store', Namespace.HINTS),
                ('store', Namespace.HINTS),
                ('no-copy', Namespace.HINTS),
                ('no-permanent-store', Namespace.HINTS),
                ('replace', Namespace.CORRECT),
                ('origin-id', Namespace.SID),
                ]


class PGPLegacy(BaseModule):
    def __init__(self, con):
        BaseModule.__init__(self, con, plugin=True)

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

        self.own_jid = self._con.get_own_jid()

        self._pgp = PGP()
        self._store = KeyStore(self._account, self.own_jid, self._log,
                               self._pgp.list_keys)
        self._always_trust = []
        self._presence_key_id_store = {}

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
        announced_key_id = self._presence_key_id_store.get(jid)
        if announced_key_id is None:
            return True
        if announced_key_id == key_id:
            return True
        raise KeyMismatch(announced_key_id)

    def _on_presence_received(self, _con, _stanza, properties):
        if properties.signed is None:
            return
        jid = properties.jid.getBare()

        key_id = self._pgp.verify(properties.status, properties.signed)
        self._log.info('Presence from %s was signed with key-id: %s',
                       jid, key_id)
        if key_id is None:
            return

        self._presence_key_id_store[jid] = key_id

        key_data = self.get_contact_key_data(jid)
        if key_data is not None:
            return

        key = self._pgp.get_key(key_id)
        if not key:
            self._log.info('Key-id %s not found in keyring, cant assign to %s',
                           key_id, jid)
            return

        self._log.info('Assign key-id: %s to %s', key_id, jid)
        self.set_contact_key_data(jid, (key_id, key[0]['uids'][0]))

    def _message_received(self, _con, stanza, properties):
        if not properties.is_pgp_legacy or properties.from_muc:
            return

        from_jid = properties.jid.getBare()
        self._log.info('Message received from: %s', from_jid)

        payload = self._pgp.decrypt(properties.pgp_legacy)
        prepare_stanza(stanza, payload)

        properties.encrypted = EncryptionData({'name': 'PGP'})

    def encrypt_message(self, con, event, callback):
        if not event.message:
            callback(event)
            return

        to_jid = app.get_jid_without_resource(event.jid)
        try:
            key_id, own_key_id = self._get_key_ids(to_jid)
        except NoKeyIdFound as error:
            self._log.warning(error)
            return

        always_trust = key_id in self._always_trust
        self._encrypt(con, event, [key_id, own_key_id], callback, always_trust)

    def _encrypt(self, con, event, keys, callback, always_trust):
        result = self._pgp.encrypt(event.message, keys, always_trust)
        encrypted_payload, error = result
        if error:
            self._handle_encrypt_error(con, error, event, keys, callback)
            return

        self._cleanup_stanza(event)
        self._create_pgp_legacy_message(event.stanza, encrypted_payload)

        event.xhtml = None
        event.encrypted = 'PGP'
        event.additional_data['encrypted'] = {'name': 'PGP'}

        callback(event)

    def _handle_encrypt_error(self, con, error, event, keys, callback):
        if error.startswith('NOT_TRUSTED'):
            def on_yes(checked):
                if checked:
                    self._always_trust.append(keys[0])
                self._encrypt(con, event, keys, callback, True)

            def on_no():
                self._raise_message_not_sent(con, event, error)

            app.nec.push_incoming_event(
                NetworkEvent('pgp-not-trusted', on_yes=on_yes, on_no=on_no))

        else:
            self._raise_message_not_sent(con, event, error)

    @staticmethod
    def _raise_message_not_sent(con, event, error):
        session = event.session if hasattr(event, 'session') else None
        app.nec.push_incoming_event(
            NetworkEvent('message-not-sent',
                         conn=con,
                         jid=event.jid,
                         message=event.message,
                         error=_('Encryption error: %s') % error,
                         time_=time.time(),
                         session=session))

    def _create_pgp_legacy_message(self, stanza, payload):
        stanza.setBody(self._get_info_message())
        stanza.setTag('x', namespace=Namespace.ENCRYPTED).setData(payload)
        eme_node = nbxmpp.Node('encryption',
                               attrs={'xmlns': Namespace.EME,
                                      'namespace': Namespace.ENCRYPTED})
        stanza.addChild(node=eme_node)

    def sign_presence(self, presence, status):
        key_data = self.get_own_key_data()
        if key_data is None:
            self._log.warning('No own key id found, cant sign presence')
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
        msg = '[This message is *encrypted* (See :XEP:`27`]'
        lang = os.getenv('LANG')
        if lang is not None and not lang.startswith('en'):
            # we're not english: one in locale and one en
            msg = _('[This message is *encrypted* (See :XEP:`27`]') + \
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
    def _cleanup_stanza(obj):
        ''' We make sure only allowed tags are in the stanza '''
        stanza = nbxmpp.Message(
            to=obj.stanza.getTo(),
            typ=obj.stanza.getType())
        stanza.setID(obj.stanza.getID())
        stanza.setThread(obj.stanza.getThread())
        for tag, ns in ALLOWED_TAGS:
            node = obj.stanza.getTag(tag, namespace=ns)
            if node:
                stanza.addChild(node=node)
        obj.stanza = stanza

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

        encrypted = self._pgp.encrypt_file(file.get_data(),
                                           [key_id, own_key_id])
        if not encrypted:
            GLib.idle_add(self._on_file_encryption_error, encrypted.status)
            return

        file.size = len(encrypted.data)
        file.set_uri_transform_func(lambda uri: '%s.pgp' % uri)
        file.set_encrypted_data(encrypted.data)
        GLib.idle_add(callback, file)

    @staticmethod
    def _on_file_encryption_error(error):
        app.nec.push_incoming_event(
            NetworkEvent('pgp-file-encryption-error', error=error))

def get_instance(*args, **kwargs):
    return PGPLegacy(*args, **kwargs), 'PGPLegacy'
