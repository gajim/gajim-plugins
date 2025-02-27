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

from typing import Any
from typing import cast

import logging
from collections.abc import Iterator
from collections.abc import Sequence
from pathlib import Path

import gpg
from gpg.errors import KeyNotFound
from gpg.results import ImportResult
from nbxmpp.protocol import JID

from openpgp.backend.base import BaseKeyringItem
from openpgp.backend.base import BasePGPBackend
from openpgp.backend.gpgme_types import Key
from openpgp.backend.util import parse_uid
from openpgp.modules.key_store import KeyData
from openpgp.modules.util import DecryptionFailed

log = logging.getLogger("gajim.p.openpgp.gpgme")


class KeyringItem(BaseKeyringItem):
    def __init__(self, key: Key) -> None:
        self._key = key
        BaseKeyringItem.__init__(self)

    def _get_uid(self) -> str | None:
        for uid in self._key.uids:
            try:
                return parse_uid(uid.uid)
            except Exception:
                pass

    @property
    def fingerprint(self) -> str:
        return self._key.fpr


class GPGMe(BasePGPBackend):
    def __init__(self, jid: str, gnuhome: Path) -> None:
        self._jid = jid
        self._home_dir = str(gnuhome)

    def _get_context(self) -> gpg.Context:
        return gpg.Context(armor=False, offline=True, home_dir=self._home_dir)

    def generate_key(self) -> None:
        with self._get_context() as context:
            result = context.create_key(
                f"xmpp:{self._jid}",
                algorithm="default",
                expires=False,
                passphrase=None,
                force=False,
            )

            log.info("Generated new key: %s", result.fpr)

    def _get_key(self, fingerprint: str) -> Key | None:
        with self._get_context() as context:
            try:
                return cast(Key, context.get_key(fingerprint))
            except KeyNotFound as error:
                log.warning("key not found: %s", error.keystr)
                return

            except Exception as error:
                log.warning("get_key() error: %s", error)
                return

    def get_own_key_details(self) -> tuple[str | None, int | None]:
        with self._get_context() as context:
            keys = cast(list[Key], list(context.keylist(secret=True)))
            if not keys:
                return None, None

            key = keys[0]
            for subkey in key.subkeys:
                if subkey.fpr == key.fpr:
                    return subkey.fpr, subkey.timestamp

        return None, None

    def get_keys(self) -> Sequence[KeyringItem]:
        keys: list[KeyringItem] = []
        with self._get_context() as context:
            for key in cast(Iterator[Key], context.keylist(secret=False)):
                keyring_item = KeyringItem(key)
                if not keyring_item.is_xmpp_key:
                    log.warning("Key not suited for xmpp: %s", key.fpr)
                    self.delete_key(keyring_item.fingerprint)
                    continue

                keys.append(keyring_item)

        return keys

    def export_key(self, fingerprint: str) -> bytes | None:
        with self._get_context() as context:
            return context.key_export_minimal(pattern=fingerprint)

    # def encrypt_decrypt_files(self):
    #     c = gpg.Context()
    #     recipient = c.get_key("fingerprint of recipient's key")

    #     # Encrypt
    #     with open('foo.txt', 'r') as input_file:
    #         with open('foo.txt.gpg', 'wb') as output_file:
    #             c.encrypt([recipient], 0, input_file, output_file)

    #     # Decrypt
    #     with open('foo.txt.gpg', 'rb') as input_file:
    #         with open('foo2.txt', 'w') as output_file:
    #             c.decrypt(input_file, output_file)

    def encrypt(
        self, payload: bytes, keys: list[KeyData]
    ) -> tuple[bytes | None, str | None]:
        recipients: list[Any] = []
        with self._get_context() as context:
            for key in keys:
                key = cast(Key | None, context.get_key(key.fingerprint))
                if key is not None:
                    recipients.append(key)

        if not recipients:
            return None, "No keys found to encrypt to"

        with self._get_context() as context:
            result = context.encrypt(payload, recipients, always_trust=True)

            ciphertext, result, _sign_result = result
            return ciphertext, None

        raise RuntimeError

    def decrypt(self, payload: bytes) -> tuple[str, str]:
        with self._get_context() as context:
            try:
                result = context.decrypt(payload)
            except Exception as error:
                raise DecryptionFailed("Decryption failed: %s" % error)

            plaintext, result, verify_result = result
            plaintext = plaintext.decode()

            fingerprints = [sig.fpr for sig in verify_result.signatures]
            if not fingerprints or len(fingerprints) > 1:
                log.error(result)
                log.error(verify_result)
                raise DecryptionFailed("Verification failed")

            return plaintext, fingerprints[0]

        raise RuntimeError

    def import_key(self, data: bytes, jid: JID) -> KeyringItem | None:
        log.info("Import key from %s", jid)
        with self._get_context() as context:
            result = context.key_import(data)
            if not isinstance(result, ImportResult) or result.imported != 1:
                log.error("Key import failed: %s", jid)
                log.error(result)
                return

            fingerprint = result.imports[0].fpr
            key = self._get_key(fingerprint)
            item = KeyringItem(key)
            if not item.is_valid(jid):
                log.warning("Invalid key found")
                log.warning(key)
                self.delete_key(item.fingerprint)
                return

        return item

    def delete_key(self, fingerprint: str) -> None:
        log.info("Delete Key: %s", fingerprint)
        key = self._get_key(fingerprint)
        assert key is not None
        with self._get_context() as context:
            context.op_delete(key, True)
