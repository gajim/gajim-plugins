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
from gajim.common.helpers import delay_execution


class KeyStore:
    def __init__(self, account, own_jid, log):
        self._log = log
        self._account = account
        self._store = {
            'own_key_data': None,
            'contact_key_data': {},
        }

        own_bare_jid = own_jid.getBare()
        path = Path(configpaths.get('PLUGINS_DATA')) / 'pgplegacy' / own_bare_jid
        if not path.exists():
            path.mkdir(parents=True)

        self._store_path = path / 'store'
        if self._store_path.exists():
            with self._store_path.open('r') as file:
                try:
                    self._store = json.load(file)
                except Exception:
                    log.exception('Could not load config')

        if not self._store['contact_key_data']:
            self._migrate()

    def _migrate(self):
        keys = {}
        attached_keys = app.config.get_per(
            'accounts', self._account, 'attached_gpg_keys')
        if not attached_keys:
            return
        attached_keys = attached_keys.split()

        for i in range(len(attached_keys) // 2):
            keys[attached_keys[2 * i]] = attached_keys[2 * i + 1]

        for jid, key_id in keys.items():
            self.set_contact_key_data(jid, (key_id, ''))

        own_key_id = app.config.get_per('accounts', self._account, 'keyid')
        own_key_user = app.config.get_per('accounts', self._account, 'keyname')
        if own_key_id:
            self.set_own_key_data((own_key_id, own_key_user))

        attached_keys = app.config.set_per(
            'accounts', self._account, 'attached_gpg_keys', '')
        self._log.info('Migration successful')

    @delay_execution(500)
    def _save_store(self):
        with self._store_path.open('w') as file:
            json.dump(self._store, file)

    def _get_dict_key(self, jid):
        return '%s-%s' % (self._account, jid)

    def set_own_key_data(self, key_data):
        if key_data is None:
            self._store['own_key_data'] = None
        else:
            self._store['own_key_data'] = {
                'key_id': key_data[0],
                'key_user': key_data[1]
            }
        self._save_store()

    def get_own_key_data(self):
        return self._store['own_key_data']

    def get_contact_key_data(self, jid):
        key_ids = self._store['contact_key_data']
        dict_key = self._get_dict_key(jid)
        return key_ids.get(dict_key)

    def set_contact_key_data(self, jid, key_data):
        key_ids = self._store['contact_key_data']
        dict_key = self._get_dict_key(jid)
        if key_data is None:
            self._store['contact_key_data'][dict_key] = None
        else:
            key_ids[dict_key] = {
                'key_id': key_data[0],
                'key_user': key_data[1]
            }
        self._save_store()
