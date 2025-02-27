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

import logging
from collections.abc import Sequence
from pathlib import Path

import gnupg
from nbxmpp.protocol import JID

from openpgp.backend.base import BaseKeyringItem
from openpgp.backend.base import BasePGPBackend
from openpgp.backend.util import parse_uid
from openpgp.modules.key_store import KeyData
from openpgp.modules.util import DecryptionFailed

log = logging.getLogger("gajim.p.openpgp.pygnupg")
if log.getEffectiveLevel() == logging.DEBUG:
    log = logging.getLogger("gnupg")
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.DEBUG)


class KeyringItem(BaseKeyringItem):
    def __init__(self, key: dict[Any, Any]) -> None:
        self._key = key
        BaseKeyringItem.__init__(self)

    @property
    def keyid(self) -> str:
        return self._key["keyid"]

    def _get_uid(self) -> str | None:
        for uid in self._key["uids"]:
            try:
                return parse_uid(uid)
            except Exception:
                pass

    @property
    def fingerprint(self) -> str:
        return self._key["fingerprint"]


class PythonGnuPG(BasePGPBackend):
    def __init__(self, jid: str, gnupghome: Path) -> None:
        self._gnupg = gnupg.GPG(gpgbinary="gpg", gnupghome=str(gnupghome))
        self._jid = jid
        self._own_fingerprint = None

    @staticmethod
    def _get_key_params(jid: str) -> str:
        """
        Generate --gen-key input
        """

        params = {
            "Key-Type": "RSA",
            "Key-Length": 2048,
            "Name-Real": "xmpp:%s" % jid,
        }

        out = "Key-Type: %s\n" % params.pop("Key-Type")
        for key, val in list(params.items()):
            out += "%s: %s\n" % (key, val)
        out += "%no-protection\n"
        out += "%commit\n"
        return out

    def generate_key(self) -> None:
        self._gnupg.gen_key(self._get_key_params(self._jid))

    def encrypt(
        self, payload: bytes, keys: list[KeyData]
    ) -> tuple[bytes | None, str | None]:
        recipients = [key.fingerprint for key in keys]
        log.info("encrypt to:")
        for fingerprint in recipients:
            log.info(fingerprint)

        result = self._gnupg.encrypt(
            payload,
            recipients,
            armor=False,
            sign=self._own_fingerprint,
            always_trust=True,
        )

        if result.ok:
            error = ""
        else:
            error = result.status

        return result.data, error

    def decrypt(self, payload: bytes) -> tuple[str, str]:
        result = self._gnupg.decrypt(payload, always_trust=True)
        if not result.ok:
            raise DecryptionFailed(result.status)

        assert result.fingerprint is not None
        return result.data.decode("utf8"), result.fingerprint

    def _get_key(self, fingerprint: str) -> gnupg.ListKeys:
        return self._gnupg.list_keys(keys=[fingerprint])

    def get_keys(self) -> Sequence[KeyringItem]:
        result = self._gnupg.list_keys(secret=False)
        keys: list[KeyringItem] = []
        for key in result:
            item = KeyringItem(key)
            if not item.is_xmpp_key:
                log.warning("Invalid key found, deleting key")
                log.warning(key)
                self.delete_key(item.fingerprint)
                continue
            keys.append(item)
        return keys

    def import_key(self, data: bytes, jid: JID) -> KeyringItem | None:
        log.info("Import key from %s", jid)
        result = self._gnupg.import_keys(data)
        if not result:
            log.error("Could not import key")
            log.error(result)
            return

        fpr = result.results[0]["fingerprint"]
        assert fpr is not None

        key = self._get_key(fpr)
        item = KeyringItem(key[0])
        if not item.is_valid(jid):
            log.warning("Invalid key found, deleting key")
            log.warning(key)
            self.delete_key(item.fingerprint)
            return

        return item

    def get_own_key_details(self) -> tuple[str | None, int | None]:
        result = self._gnupg.list_keys(secret=True)
        if not result:
            return None, None

        if len(result) > 1:
            log.error("More than one secret key found")
            return None, None

        self._own_fingerprint = result[0]["fingerprint"]
        return self._own_fingerprint, int(result[0]["date"])

    def export_key(self, fingerprint: str) -> bytes | None:
        key = self._gnupg.export_keys(
            fingerprint, secret=False, armor=False, minimal=True
        )
        assert isinstance(key, bytes | None)
        return key

    def delete_key(self, fingerprint: str) -> None:
        log.info("Delete Key: %s", fingerprint)
        self._gnupg.delete_keys(fingerprint)
