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

import json
from pathlib import Path

from gajim.common import app
from gajim.common import configpaths

CURRENT_STORE_VERSION = 3


class KeyResolveError(Exception):
    pass


class KeyStore:
    def __init__(self, account, own_jid, log, list_keys_func):
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

            ver = self._store.get("_version", 2)
            if ver > CURRENT_STORE_VERSION:
                raise Exception("Unknown store version! " "Please upgrade pgp plugin.")
            elif ver == 2:
                self._migrate_v2_store()
                self._save_store()
            elif ver != CURRENT_STORE_VERSION:
                # garbled version
                self._store = self._empty_store()
                log.warning("Bad pgp key store version. Initializing new.")
        else:
            # having store v1 or fresh install
            self._store = self._empty_store()
            self._migrate_v1_store()
            self._migrate_v2_store()
            self._save_store()

    @staticmethod
    def _empty_store():
        return {
            "_version": CURRENT_STORE_VERSION,
            "own_key_data": None,
            "contact_key_data": {},
        }

    def _migrate_v1_store(self):
        keys = {}
        attached_keys = app.settings.get_account_setting(
            self._account, "attached_gpg_keys"
        )
        if not attached_keys:
            return
        attached_keys = attached_keys.split()

        for i in range(len(attached_keys) // 2):
            keys[attached_keys[2 * i]] = attached_keys[2 * i + 1]

        for jid, key_id in keys.items():
            self._set_contact_key_data_nosync(jid, (key_id, ""))

        own_key_id = app.settings.get_account_setting(self._account, "keyid")
        own_key_user = app.settings.get_account_setting(self._account, "keyname")
        if own_key_id:
            self._set_own_key_data_nosync((own_key_id, own_key_user))

        attached_keys = app.settings.set_account_setting(
            self._account, "attached_gpg_keys", ""
        )
        self._log.info("Migration from store v1 was successful")

    def _migrate_v2_store(self):
        own_key_data = self.get_own_key_data()
        if own_key_data is not None:
            own_key_id, own_key_user = (
                own_key_data["key_id"],
                own_key_data["key_user"],
            )
            try:
                own_key_fp = self._resolve_short_id(own_key_id, has_secret=True)
                self._set_own_key_data_nosync((own_key_fp, own_key_user))
            except KeyResolveError:
                self._set_own_key_data_nosync(None)

        prune_list = []

        for dict_key, key_data in self._store["contact_key_data"].items():
            try:
                key_data["key_id"] = self._resolve_short_id(key_data["key_id"])
            except KeyResolveError:
                prune_list.append(dict_key)

        for dict_key in prune_list:
            del self._store["contact_key_data"][dict_key]

        self._store["_version"] = CURRENT_STORE_VERSION
        self._log.info("Migration from store v2 was successful")

    def _save_store(self):
        with self._store_path.open("w") as file:
            json.dump(self._store, file)

    def _get_dict_key(self, jid):
        return "%s-%s" % (self._account, jid)

    def _resolve_short_id(self, short_id, has_secret=False):
        candidates = self._list_keys_func(
            secret=has_secret, keys=(short_id,)
        ).fingerprints
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            self._log.critical(
                "Key collision during migration. " "Key ID is %s. Removing binding...",
                repr(short_id),
            )
        else:
            self._log.warning(
                "Key %s was not found during migration. " "Removing binding...",
                repr(short_id),
            )
        raise KeyResolveError

    def set_own_key_data(self, key_data):
        self._set_own_key_data_nosync(key_data)
        self._save_store()

    def _set_own_key_data_nosync(self, key_data):
        if key_data is None:
            self._store["own_key_data"] = None
        else:
            self._store["own_key_data"] = {
                "key_id": key_data[0],
                "key_user": key_data[1],
            }

    def get_own_key_data(self):
        return self._store["own_key_data"]

    def get_contact_key_data(self, jid):
        key_ids = self._store["contact_key_data"]
        dict_key = self._get_dict_key(jid)
        return key_ids.get(dict_key)

    def set_contact_key_data(self, jid, key_data):
        self._set_contact_key_data_nosync(jid, key_data)
        self._save_store()

    def _set_contact_key_data_nosync(self, jid, key_data):
        key_ids = self._store["contact_key_data"]
        dict_key = self._get_dict_key(jid)
        if key_data is None:
            key_ids[dict_key] = None
        else:
            key_ids[dict_key] = {"key_id": key_data[0], "key_user": key_data[1]}
