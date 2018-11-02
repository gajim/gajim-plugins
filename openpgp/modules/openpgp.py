# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim.  If not, see <http://www.gnu.org/licenses/>.

# XEP-0373: OpenPGP for XMPP

import time
import logging
from pathlib import Path
from base64 import b64decode, b64encode

from nbxmpp import Node, isResultNode

from gajim.common import app
from gajim.common import configpaths
from gajim.common.connection_handlers_events import MessageNotSentEvent

from openpgp.modules import util
from openpgp.modules.util import ENCRYPTION_NAME
from openpgp.modules.util import add_additional_data
from openpgp.modules.util import NS_OPENPGP_PUBLIC_KEYS
from openpgp.modules.util import NS_OPENPGP
from openpgp.modules.util import Key
from openpgp.modules.util import Trust
from openpgp.modules.util import DecryptionFailed
from openpgp.backend.sql import Storage
from openpgp.backend.pygpg import PGPContext


log = logging.getLogger('gajim.plugin_system.openpgp')


# Module name
name = ENCRYPTION_NAME
zeroconf = False


class KeyData:
    '''
    Holds all data related to a certain key
    '''
    def __init__(self, contact_data):
        self._contact_data = contact_data
        self.fingerprint = None
        self.active = False
        self._trust = Trust.UNKNOWN
        self.timestamp = None
        self.comment = None
        self.has_pubkey = False

    @property
    def trust(self):
        return self._trust

    @trust.setter
    def trust(self, value):
        if value not in (Trust.NOT_TRUSTED,
                         Trust.UNKNOWN,
                         Trust.BLIND,
                         Trust.VERIFIED):
            raise ValueError('Trust value not allowed: %s' % value)
        self._trust = value
        self._contact_data.set_trust(self.fingerprint, self._trust)

    @classmethod
    def from_key(cls, contact_data, key, trust):
        keydata = cls(contact_data)
        keydata.fingerprint = key.fingerprint
        keydata.timestamp = key.date
        keydata.active = True
        keydata._trust = trust
        return keydata

    @classmethod
    def from_row(cls, contact_data, row):
        keydata = cls(contact_data)
        keydata.fingerprint = row.fingerprint
        keydata.timestamp = row.timestamp
        keydata.comment = row.comment
        keydata._trust = row.trust
        keydata.active = row.active
        return keydata

    def delete(self):
        self._contact_data.delete_key(self.fingerprint)


class ContactData:
    '''
    Holds all data related to a contact
    '''
    def __init__(self, jid, storage, pgp):
        self.jid = jid
        self._key_store = {}
        self._storage = storage
        self._pgp = pgp

    @property
    def userid(self):
        if self.jid is None:
            raise ValueError('JID not set')
        return 'xmpp:%s' % self.jid

    @property
    def default_trust(self):
        for key in self._key_store.values():
            if key.trust in (Trust.NOT_TRUSTED, Trust.BLIND):
                return Trust.UNKNOWN
        return Trust.BLIND

    def db_values(self):
        for key in self._key_store.values():
            yield (self.jid,
                   key.fingerprint,
                   key.active,
                   key.trust,
                   key.timestamp,
                   key.comment)

    def add_from_key(self, key):
        try:
            keydata = self._key_store[key.fingerprint]
        except KeyError:
            keydata = KeyData.from_key(self, key, self.default_trust)
            self._key_store[key.fingerprint] = keydata
            log.info('Add from key: %s %s', self.jid, keydata.fingerprint)
        return keydata

    def add_from_db(self, row):
        try:
            keydata = self._key_store[row.fingerprint]
        except KeyError:
            keydata = KeyData.from_row(self, row)
            self._key_store[row.fingerprint] = keydata
            log.info('Add from row: %s %s', self.jid, row.fingerprint)
        return keydata

    def process_keylist(self, keylist):
        log.info('Process keylist: %s %s', self.jid, keylist)

        if keylist is None:
            for keydata in self._key_store.values():
                keydata.active = False
            self._storage.save_contact(self.db_values())
            return []

        missing_pub_keys = []
        fingerprints = set([key.fingerprint for key in keylist])
        if fingerprints == self._key_store.keys():
            log.info('No updates found')
            for key in self._key_store.values():
                if not key.has_pubkey:
                    missing_pub_keys.append(key.fingerprint)
            return missing_pub_keys

        for keydata in self._key_store.values():
            keydata.active = False

        for key in keylist:
            try:
                keydata = self._key_store[key.fingerprint]
                keydata.active = True
                if not keydata.has_pubkey:
                    missing_pub_keys.append(keydata.fingerprint)
            except KeyError:
                keydata = self.add_from_key(key)
                missing_pub_keys.append(keydata.fingerprint)

        self._storage.save_contact(self.db_values())
        return missing_pub_keys

    def set_public_key(self, fingerprint):
        try:
            keydata = self._key_store[fingerprint]
        except KeyError:
            log.warning('Set public key on unknown fingerprint: %s %s',
                        self.jid, fingerprint)
        else:
            keydata.has_pubkey = True
        log.info('Set public key: %s %s', self.jid, fingerprint)

    def get_keys(self, only_trusted=True):
        keys = list(self._key_store.values())
        if not only_trusted:
            return keys
        return [k for k in keys if k.active and k.trust in (Trust.VERIFIED,
                                                            Trust.BLIND)]

    def get_key(self, fingerprint):
        return self._key_store.get(fingerprint, None)

    def set_trust(self, fingerprint, trust):
        self._storage.set_trust(self.jid, fingerprint, trust)

    def delete_key(self, fingerprint):
        self._storage.delete_key(self.jid, fingerprint)
        self._pgp.delete_key(fingerprint)
        del self._key_store[fingerprint]


class PGPContacts:
    '''
    Holds all contacts available for PGP encryption
    '''
    def __init__(self, pgp, storage):
        self._contacts = {}
        self._storage = storage
        self._pgp = pgp
        self._load_from_storage()
        self._load_from_keyring()

    def _load_from_keyring(self):
        log.info('Load keys from keyring')
        keyring = self._pgp.get_keys()
        for key in keyring:
            log.info('Found: %s %s', key.jid, key.fingerprint)
            self.set_public_key(key.jid, key.fingerprint)

    def _load_from_storage(self):
        log.info('Load contacts from storage')
        rows = self._storage.load_contacts()
        if rows is None:
            return

        for row in rows:
            log.info('Found: %s %s', row.jid, row.fingerprint)
            try:
                contact_data = self._contacts[row.jid]
            except KeyError:
                contact_data = ContactData(row.jid, self._storage, self._pgp)
                contact_data.add_from_db(row)
                self._contacts[row.jid] = contact_data
            else:
                contact_data.add_from_db(row)

    def process_keylist(self, jid, keylist):
        try:
            contact_data = self._contacts[jid]
        except KeyError:
            contact_data = ContactData(jid, self._storage, self._pgp)
            missing_pub_keys = contact_data.process_keylist(keylist)
            self._contacts[jid] = contact_data
        else:
            missing_pub_keys = contact_data.process_keylist(keylist)

        return missing_pub_keys

    def set_public_key(self, jid, fingerprint):
        try:
            contact_data = self._contacts[jid]
        except KeyError:
            log.warning('ContactData not found: %s %s', jid, fingerprint)
        else:
            contact_data.set_public_key(fingerprint)

    def get_keys(self, jid, only_trusted=True):
        try:
            contact_data = self._contacts[jid]
            return contact_data.get_keys(only_trusted=only_trusted)
        except KeyError:
            return []

    def get_trust(self, jid, fingerprint):
        contact_data = self._contacts.get(jid, None)
        if contact_data is None:
            return Trust.UNKNOWN

        key = contact_data.get_key(fingerprint)
        if key is None:
            return Trust.UNKNOWN
        return key.trust


class OpenPGP:
    def __init__(self, con):
        self._con = con
        self._account = con.name

        self.handlers = []

        self.own_jid = self.get_own_jid(stripped=True)

        path = Path(configpaths.get('MY_DATA')) / 'openpgp' / self.own_jid
        if not path.exists():
            path.mkdir(parents=True)

        self._pgp = PGPContext(self.own_jid, path)
        self._storage = Storage(path)
        self._contacts = PGPContacts(self._pgp, self._storage)
        self._fingerprint, self._date = self.get_own_key_details()
        log.info('Own Fingerprint at start: %s', self._fingerprint)

    @property
    def secret_key_available(self):
        return self._fingerprint is not None

    def get_own_jid(self, stripped=False):
        if stripped:
            return self._con.get_own_jid().getStripped()
        return self._con.get_own_jid()

    def get_own_key_details(self):
        self._fingerprint, self._date = self._pgp.get_own_key_details()
        return self._fingerprint, self._date

    def generate_key(self):
        self._pgp.generate_key()

    def publish_key(self):
        log.info('%s => Publish key', self._account)
        key = self._pgp.export_key(self._fingerprint)

        date = time.strftime(
            '%Y-%m-%dT%H:%M:%SZ', time.gmtime(self._date))
        pubkey_node = Node('pubkey', attrs={'xmlns': NS_OPENPGP,
                                            'date': date})
        data = pubkey_node.addChild('data')
        data.addData(b64encode(key).decode('utf8'))
        node = '%s:%s' % (NS_OPENPGP_PUBLIC_KEYS, self._fingerprint)

        self._con.get_module('PubSub').send_pb_publish(
            self.own_jid, node, pubkey_node,
            id_='current', cb=self._public_result)

    def _publish_key_list(self, keylist=None):
        if keylist is None:
            keylist = [Key(self._fingerprint, self._date)]
        log.info('%s => Publish keys list', self._account)
        self._con.get_module('PGPKeylist').send(keylist)

    def _public_result(self, con, stanza):
        if not isResultNode(stanza):
            log.error('%s => Publishing failed: %s',
                      self._account, stanza.getError())

    def _query_public_key(self, jid, fingerprint):
        log.info('%s => Fetch public key %s - %s',
                 self._account, fingerprint, jid)
        node = '%s:%s' % (NS_OPENPGP_PUBLIC_KEYS, fingerprint)
        self._con.get_module('PubSub').send_pb_retrieve(
            jid, node, cb=self._public_key_received, fingerprint=fingerprint)

    def _public_key_received(self, con, stanza, fingerprint):
        if not isResultNode(stanza):
            log.error('%s => Public Key not found: %s',
                      self._account, stanza.getError())
            return
        pubkey = util.unpack_public_key(stanza, fingerprint)
        if pubkey is None:
            log.warning('Invalid public key received:\n%s', stanza)
            return

        jid = stanza.getFrom().getStripped()
        result = self._pgp.import_key(pubkey, jid)
        if result is not None:
            self._contacts.set_public_key(jid, fingerprint)

    def query_key_list(self, jid=None):
        if jid is None:
            jid = self.own_jid
        log.info('%s => Fetch keys list %s', self._account, jid)
        self._con.get_module('PubSub').send_pb_retrieve(
            jid, NS_OPENPGP_PUBLIC_KEYS,
            cb=self._query_key_list_result)

    def _query_key_list_result(self, con, stanza):
        from_jid = stanza.getFrom()
        if from_jid is None:
            from_jid = self.own_jid
        else:
            from_jid = from_jid.getStripped()

        if not isResultNode(stanza):
            log.error('%s => Keys list query failed: %s',
                      self._account, stanza.getError())
            if from_jid == self.own_jid and self._fingerprint is not None:
                self._publish_key_list()
            return

        from_jid = stanza.getFrom()
        if from_jid is None:
            from_jid = self.own_jid
        else:
            from_jid = from_jid.getStripped()

        log.info('Key list query received from %s', from_jid)

        keylist = util.unpack_public_key_list(stanza, from_jid)
        self.key_list_received(keylist, from_jid)

    def key_list_received(self, keylist, from_jid):
        if keylist is None:
            log.warning('Invalid keys list received')
            if from_jid == self.own_jid and self._fingerprint is not None:
                self._publish_key_list()
            return

        if not keylist:
            log.warning('%s => Empty keys list received from %s',
                        self._account, from_jid)
            self._contacts.process_keylist(self.own_jid, keylist)
            if from_jid == self.own_jid and self._fingerprint is not None:
                self._publish_key_list()
            return

        if from_jid == self.own_jid:
            log.info('Received own keys list')
            for key in keylist:
                log.info(key.fingerprint)
            for key in keylist:
                # Check if own fingerprint is published
                if key.fingerprint == self._fingerprint:
                    log.info('Own key found in keys list')
                    return
            log.info('Own key not published')
            if self._fingerprint is not None:
                keylist.append(Key(self._fingerprint, self._date))
                self._publish_key_list(keylist)
            return

        missing_pub_keys = self._contacts.process_keylist(from_jid, keylist)

        for key in keylist:
            log.info(key.fingerprint)

        for fingerprint in missing_pub_keys:
            self._query_public_key(from_jid, fingerprint)

    def decrypt_message(self, obj, callback):
        if obj.encrypted:
            # Another Plugin already decrypted the message
            return

        if obj.name == 'message-received':
            enc_tag = obj.stanza.getTag('openpgp', namespace=NS_OPENPGP)
            jid = obj.jid
        else:
            enc_tag = obj.message.getTag('openpgp', namespace=NS_OPENPGP)
            jid = obj.with_

        if enc_tag is None:
            return

        log.info('Received OpenPGP message from: %s', jid)
        b64encode_payload = enc_tag.getData()
        encrypted_payload = b64decode(b64encode_payload)

        try:
            decrypted_payload, fingerprint = self._pgp.decrypt(
                encrypted_payload)
        except DecryptionFailed as error:
            log.warning(error)
            return

        signcrypt = Node(node=decrypted_payload)

        signcrypt_jid = signcrypt.getTagAttr('to', 'jid')
        if self.own_jid != signcrypt_jid:
            log.warning('signcrypt "to" attr %s != %s',
                        self.own_jid, signcrypt_jid)
            log.debug(signcrypt)
            return

        payload = signcrypt.getTag('payload')

        body = None
        if obj.name == 'message-received':
            obj.stanza.delChild(enc_tag)
            for node in payload.getChildren():
                if node.name == 'body':
                    body = node.getData()
                    obj.stanza.setTagData('body', body)
                else:
                    obj.stanza.addChild(node=node)
        else:
            obj.msg_.delChild(enc_tag)
            for node in payload.getChildren():
                if node.name == 'body':
                    body = node.getData()
                    obj.msg_.setTagData('body', node.getData())
                else:
                    obj.msg_.addChild(node=node)

        if body:
            obj.msgtxt = body

        add_additional_data(obj.additional_data,
                            fingerprint)

        obj.encrypted = ENCRYPTION_NAME
        callback(obj)

    def encrypt_message(self, obj, callback):
        keys = self._contacts.get_keys(obj.jid)
        if not keys:
            # TODO: this should never happen in theory
            log.error('Droping stanza to %s, because we have no key', obj.jid)
            return

        keys += self._contacts.get_keys(self.own_jid)
        keys += [Key(self._fingerprint, None)]

        payload = util.create_signcrypt_node(obj)

        encrypted_payload, error = self._pgp.encrypt(payload, keys)
        if error:
            log.error('Error: %s', error)
            app.nec.push_incoming_event(
                MessageNotSentEvent(
                    None, conn=self._con, jid=obj.jid, message=obj.message,
                    error=error, time_=time.time()))
            return

        util.create_openpgp_message(obj, encrypted_payload)

        add_additional_data(obj.additional_data,
                            self._fingerprint)

        obj.encrypted = ENCRYPTION_NAME
        self.print_msg_to_log(obj.msg_iq)
        callback(obj)

    @staticmethod
    def print_msg_to_log(stanza):
        """ Prints a stanza in a fancy way to the log """
        log.debug('-'*15)
        stanzastr = '\n' + stanza.__str__(fancy=True)
        stanzastr = stanzastr[0:-1]
        log.debug(stanzastr)
        log.debug('-'*15)

    def get_keys(self, jid=None, only_trusted=True):
        if jid is None:
            jid = self.own_jid
        return self._contacts.get_keys(jid, only_trusted=only_trusted)

    def clear_fingerprints(self):
        self._publish_key_list()

    def cleanup(self):
        self._storage.cleanup()
        self._pgp = None
        self._contacts = None


def get_instance(*args, **kwargs):
    return OpenPGP(*args, **kwargs), 'OpenPGP'
