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

from __future__ import annotations

import logging
from collections.abc import Iterator

from nbxmpp.protocol import JID
from nbxmpp.structs import PGPKeyMetadata

from openpgp.backend.base import BasePGPBackend
from openpgp.backend.sql import ContactRow
from openpgp.backend.sql import Storage
from openpgp.modules.util import Trust

log = logging.getLogger("gajim.p.openpgp.store")


class KeyData:
    """
    Holds all data related to a certain key
    """

    def __init__(
        self,
        contact_data: ContactData,
        fingerprint: str,
        active: bool,
        trust: Trust,
        timestamp: float,
    ):
        self._contact_data = contact_data
        self.fingerprint = fingerprint
        self.active = active
        self._trust = trust
        self.timestamp = timestamp
        self.comment = None
        self.has_pubkey = False

    @property
    def trust(self) -> Trust:
        return self._trust

    @trust.setter
    def trust(self, value: Trust) -> None:
        if value not in (Trust.NOT_TRUSTED, Trust.UNKNOWN, Trust.BLIND, Trust.VERIFIED):
            raise ValueError("Trust value not allowed: %s" % value)

        self._trust = value
        self._contact_data.set_trust(self.fingerprint, self._trust)

    def delete(self):
        self._contact_data.delete_key(self.fingerprint)


class ContactData:
    """
    Holds all data related to a contact
    """

    def __init__(self, jid: JID, storage: Storage, pgp: BasePGPBackend) -> None:
        self.jid = jid
        self._key_store: dict[str, KeyData] = {}
        self._storage = storage
        self._pgp = pgp

    @property
    def userid(self):
        if self.jid is None:
            raise ValueError("JID not set")
        return "xmpp:%s" % self.jid

    @property
    def default_trust(self) -> Trust:
        for key in self._key_store.values():
            if key.trust in (Trust.NOT_TRUSTED, Trust.BLIND):
                return Trust.UNKNOWN
        return Trust.BLIND

    def db_values(self) -> Iterator[tuple[JID, str, bool, Trust, float]]:
        for key in self._key_store.values():
            yield (
                self.jid,
                key.fingerprint,
                key.active,
                key.trust,
                key.timestamp,
            )

    def add_from_key(self, key: PGPKeyMetadata) -> KeyData:
        try:
            keydata = self._key_store[key.fingerprint]
        except KeyError:
            keydata = KeyData(
                self,
                key.fingerprint,
                True,
                self.default_trust,
                key.date,
            )
            self._key_store[key.fingerprint] = keydata
            log.info("Add from key: %s %s", self.jid, keydata.fingerprint)
        return keydata

    def add_from_db(self, row: ContactRow) -> KeyData:
        try:
            keydata = self._key_store[row.fingerprint]
        except KeyError:
            keydata = KeyData(
                self,
                row.fingerprint,
                row.active,
                row.trust,
                row.timestamp,
            )
            self._key_store[row.fingerprint] = keydata
            log.info("Add from row: %s %s", self.jid, row.fingerprint)
        return keydata

    def process_keylist(self, keylist: list[PGPKeyMetadata] | None) -> list[str]:
        log.info("Process keylist: %s %s", self.jid, keylist)

        if keylist is None:
            for keydata in self._key_store.values():
                keydata.active = False
            self._storage.save_contact(self.db_values())
            return []

        missing_pub_keys: list[str] = []
        fingerprints = {key.fingerprint for key in keylist}
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

    def set_public_key(self, fingerprint: str) -> None:
        try:
            keydata = self._key_store[fingerprint]
        except KeyError:
            log.warning(
                "Set public key on unknown fingerprint: %s %s", self.jid, fingerprint
            )
        else:
            keydata.has_pubkey = True
        log.info("Set public key: %s %s", self.jid, fingerprint)

    def get_keys(self, only_trusted: bool = True) -> list[KeyData]:
        keys = list(self._key_store.values())
        if not only_trusted:
            return keys
        return [
            k for k in keys if k.active and k.trust in (Trust.VERIFIED, Trust.BLIND)
        ]

    def get_key(self, fingerprint: str) -> KeyData | None:
        return self._key_store.get(fingerprint, None)

    def set_trust(self, fingerprint: str, trust: Trust) -> None:
        self._storage.set_trust(self.jid, fingerprint, trust)

    def delete_key(self, fingerprint: str) -> None:
        self._storage.delete_key(self.jid, fingerprint)
        self._pgp.delete_key(fingerprint)
        del self._key_store[fingerprint]


class PGPContacts:
    """
    Holds all contacts available for PGP encryption
    """

    def __init__(self, pgp: BasePGPBackend, storage: Storage) -> None:
        self._contacts: dict[JID, ContactData] = {}
        self._storage = storage
        self._pgp = pgp
        self._load_from_storage()
        self._load_from_keyring()

    def _load_from_keyring(self):
        log.info("Load keys from keyring")
        keyring = self._pgp.get_keys()
        for key in keyring:
            log.info("Found: %s %s", key.jid, key.fingerprint)
            assert key.jid is not None
            self.set_public_key(key.jid, key.fingerprint)

    def _load_from_storage(self):
        log.info("Load contacts from storage")
        rows = self._storage.load_contacts()
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

    def process_keylist(
        self, jid: JID, keylist: list[PGPKeyMetadata] | None
    ) -> list[str]:
        try:
            contact_data = self._contacts[jid]
        except KeyError:
            contact_data = ContactData(jid, self._storage, self._pgp)
            missing_pub_keys = contact_data.process_keylist(keylist)
            self._contacts[jid] = contact_data
        else:
            missing_pub_keys = contact_data.process_keylist(keylist)

        return missing_pub_keys

    def set_public_key(self, jid: JID, fingerprint: str) -> None:
        try:
            contact_data = self._contacts[jid]
        except KeyError:
            log.warning("ContactData not found: %s %s", jid, fingerprint)
        else:
            contact_data.set_public_key(fingerprint)

    def get_keys(self, jid: JID, only_trusted: bool = True) -> list[KeyData]:
        try:
            contact_data = self._contacts[jid]
            return contact_data.get_keys(only_trusted=only_trusted)
        except KeyError:
            return []

    def get_trust(self, jid: JID, fingerprint: str) -> Trust:
        contact_data = self._contacts.get(jid, None)
        if contact_data is None:
            return Trust.UNKNOWN

        key = contact_data.get_key(fingerprint)
        if key is None:
            return Trust.UNKNOWN
        return key.trust
