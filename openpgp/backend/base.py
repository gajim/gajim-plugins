# Copyright (C) 2025 Philipp Hörist <philipp AT hoerist.com>
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

from typing import Any
from typing import TYPE_CHECKING

from collections.abc import Sequence
from pathlib import Path

from nbxmpp.protocol import JID

if TYPE_CHECKING:
    from openpgp.modules.key_store import KeyData


class BaseKeyringItem:
    def __init__(self, key: Any) -> None:
        self._key = key
        self._uid = self._get_uid()

    @property
    def is_xmpp_key(self) -> bool:
        try:
            return self.jid is not None
        except Exception:
            return False

    def is_valid(self, jid: JID) -> bool:
        if not self.is_xmpp_key:
            return False
        return jid == self.jid

    def _get_uid(self) -> str | None:
        raise NotImplementedError

    @property
    def fingerprint(self) -> str:
        raise NotImplementedError

    @property
    def uid(self):
        if self._uid is not None:
            return self._uid

    @property
    def jid(self) -> JID | None:
        if self._uid is not None:
            return JID.from_string(self._uid)

    def __hash__(self):
        return hash(self.fingerprint)


class BasePGPBackend:
    def __init__(self, jid: str, gnupghome: Path) -> None:
        raise NotImplementedError

    def generate_key(self) -> None:
        raise NotImplementedError

    def encrypt(
        self, payload: bytes, keys: list[KeyData]
    ) -> tuple[bytes | None, str | None]:
        raise NotImplementedError

    def decrypt(self, payload: bytes) -> tuple[str, str]:
        raise NotImplementedError

    def get_keys(self) -> Sequence[BaseKeyringItem]:
        raise NotImplementedError

    def import_key(self, data: bytes, jid: JID) -> BaseKeyringItem | None:
        raise NotImplementedError

    def get_own_key_details(self) -> tuple[str | None, int | None]:
        raise NotImplementedError

    def export_key(self, fingerprint: str) -> bytes | None:
        raise NotImplementedError

    def delete_key(self, fingerprint: str) -> None:
        raise NotImplementedError
