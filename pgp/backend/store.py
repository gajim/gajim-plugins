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

from __future__ import annotations

from typing import Any

import json
import logging
from collections.abc import Callable
from pathlib import Path

from nbxmpp import JID

from gajim.common import configpaths

CURRENT_STORE_VERSION = 3


class KeyResolveError(Exception):
    pass


class KeyStore:
    def __init__(
        self,
        account: str,
        own_jid: JID,
        log: logging.LoggerAdapter[Any],
        list_keys_func: Callable[..., list[str]],
    ) -> None:
        self._list_keys_func = list_keys_func
        self._log = log
        self._account = account

        own_bare_jid = own_jid.bare
        path = Path(configpaths.get("PLUGINS_DATA")) / "pgplegacy" / own_bare_jid
        if not path.exists():
            path.mkdir(parents=True)

        self._store_path = path / "store"
        if self._store_path.exists():
            # having store v2 or higher
            with self._store_path.open("r") as file:
                try:
                    self._store = json.load(file)
                except Exception:
                    log.exception("Could not load config")
                    self._store = self._empty_store()
                    self._save_store()

        else:
            # having store v1 or fresh install
            self._store = self._empty_store()
            self._save_store()

    @staticmethod
    def _empty_store() -> dict[str, Any]:
        return {
            "_version": CURRENT_STORE_VERSION,
            "own_key_data": None,
            "contact_key_data": {},
        }

    def _save_store(self) -> None:
        with self._store_path.open("w") as file:
            json.dump(self._store, file)

    def _get_dict_key(self, jid: str) -> str:
        return "%s-%s" % (self._account, jid)

    def _resolve_short_id(self, short_id: str, has_secret: bool = False) -> str:
        fingerprints = self._list_keys_func(secret=has_secret, keys=[short_id])
        if len(fingerprints) == 1:
            return fingerprints[0]
        elif len(fingerprints) > 1:
            self._log.critical(
                "Key collision during migration. Key ID is %s. Removing binding...",
                repr(short_id),
            )
        else:
            self._log.warning(
                "Key %s was not found during migration. Removing binding...",
                repr(short_id),
            )
        raise KeyResolveError

    def set_own_key_data(self, key_data: tuple[str, str] | None) -> None:
        self._set_own_key_data_nosync(key_data)
        self._save_store()

    def _set_own_key_data_nosync(self, key_data: tuple[str, str] | None) -> None:
        if key_data is None:
            self._store["own_key_data"] = None
        else:
            self._store["own_key_data"] = {
                "key_id": key_data[0],
                "key_user": key_data[1],
            }

    def get_own_key_data(self) -> dict[str, str] | None:
        return self._store["own_key_data"]

    def get_contact_key_data(self, jid: str) -> dict[str, str] | None:
        key_ids = self._store["contact_key_data"]
        dict_key = self._get_dict_key(jid)
        return key_ids.get(dict_key)

    def set_contact_key_data(self, jid: str, key_data: tuple[str, str] | None) -> None:
        self._set_contact_key_data_nosync(jid, key_data)
        self._save_store()

    def _set_contact_key_data_nosync(
        self, jid: str, key_data: tuple[str, str] | None
    ) -> None:
        key_ids = self._store["contact_key_data"]
        dict_key = self._get_dict_key(jid)
        if key_data is None:
            key_ids[dict_key] = None
        else:
            key_ids[dict_key] = {"key_id": key_data[0], "key_user": key_data[1]}
