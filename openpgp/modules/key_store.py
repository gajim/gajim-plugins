# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the OpenPGP Gajim Plugin.
#
# OpenPGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OpenPGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OpenPGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import logging

from openpgp.modules.util import Trust

log = logging.getLogger("gajim.p.openpgp.store")


class KeyData:
    """
    Holds all data related to a certain key
    """

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
        if value not in (Trust.NOT_TRUSTED, Trust.UNKNOWN, Trust.BLIND, Trust.VERIFIED):
            raise ValueError("Trust value not allowed: %s" % value)
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
    """
    Holds all data related to a contact
    """

    def __init__(self, jid, storage, pgp):
        self.jid = jid
        self._key_store = {}
        self._storage = storage
        self._pgp = pgp

    @property
    def userid(self):
        if self.jid is None:
            raise ValueError("JID not set")
        return "xmpp:%s" % self.jid

    @property
    def default_trust(self):
        for key in self._key_store.values():
            if key.trust in (Trust.NOT_TRUSTED, Trust.BLIND):
                return Trust.UNKNOWN
        return Trust.BLIND

    def db_values(self):
        for key in self._key_store.values():
            yield (
                self.jid,
                key.fingerprint,
                key.active,
                key.trust,
                key.timestamp,
                key.comment,
            )

    def add_from_key(self, key):
        try:
            keydata = self._key_store[key.fingerprint]
        except KeyError:
            keydata = KeyData.from_key(self, key, self.default_trust)
            self._key_store[key.fingerprint] = keydata
            log.info("Add from key: %s %s", self.jid, keydata.fingerprint)
        return keydata

    def add_from_db(self, row):
        try:
            keydata = self._key_store[row.fingerprint]
        except KeyError:
            keydata = KeyData.from_row(self, row)
            self._key_store[row.fingerprint] = keydata
            log.info("Add from row: %s %s", self.jid, row.fingerprint)
        return keydata

    def process_keylist(self, keylist):
        log.info("Process keylist: %s %s", self.jid, keylist)

        if keylist is None:
            for keydata in self._key_store.values():
                keydata.active = False
            self._storage.save_contact(self.db_values())
            return []

        missing_pub_keys = []
        fingerprints = set([key.fingerprint for key in keylist])
        if fingerprints == self._key_store.keys():
            log.info("No updates found")
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
            log.warning(
                "Set public key on unknown fingerprint: %s %s", self.jid, fingerprint
            )
        else:
            keydata.has_pubkey = True
        log.info("Set public key: %s %s", self.jid, fingerprint)

    def get_keys(self, only_trusted=True):
        keys = list(self._key_store.values())
        if not only_trusted:
            return keys
        return [
            k for k in keys if k.active and k.trust in (Trust.VERIFIED, Trust.BLIND)
        ]

    def get_key(self, fingerprint):
        return self._key_store.get(fingerprint, None)

    def set_trust(self, fingerprint, trust):
        self._storage.set_trust(self.jid, fingerprint, trust)

    def delete_key(self, fingerprint):
        self._storage.delete_key(self.jid, fingerprint)
        self._pgp.delete_key(fingerprint)
        del self._key_store[fingerprint]


class PGPContacts:
    """
    Holds all contacts available for PGP encryption
    """

    def __init__(self, pgp, storage):
        self._contacts = {}
        self._storage = storage
        self._pgp = pgp
        self._load_from_storage()
        self._load_from_keyring()

    def _load_from_keyring(self):
        log.info("Load keys from keyring")
        keyring = self._pgp.get_keys()
        for key in keyring:
            log.info("Found: %s %s", key.jid, key.fingerprint)
            self.set_public_key(key.jid, key.fingerprint)

    def _load_from_storage(self):
        log.info("Load contacts from storage")
        rows = self._storage.load_contacts()
        if rows is None:
            return

        for row in rows:
            log.info("Found: %s %s", row.jid, row.fingerprint)
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
            log.warning("ContactData not found: %s %s", jid, fingerprint)
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
