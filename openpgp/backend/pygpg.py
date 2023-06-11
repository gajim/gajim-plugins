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

import gnupg
from nbxmpp.protocol import JID

from openpgp.backend.util import parse_uid
from openpgp.modules.util import DecryptionFailed


log = logging.getLogger('gajim.p.openpgp.pygnupg')
if log.getEffectiveLevel() == logging.DEBUG:
    log = logging.getLogger('gnupg')
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.DEBUG)


class KeyringItem:
    def __init__(self, key):
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

    @property
    def keyid(self) -> str:
        return self._key['keyid']

    def _get_uid(self) -> str | None:
        for uid in self._key['uids']:
            try:
                return parse_uid(uid)
            except Exception:
                pass

    @property
    def fingerprint(self):
        return self._key['fingerprint']

    @property
    def uid(self):
        if self._uid is not None:
            return self._uid

    @property
    def jid(self):
        if self._uid is not None:
            return JID.from_string(self._uid)

    def __hash__(self):
        return hash(self.fingerprint)


class PythonGnuPG(gnupg.GPG):
    def __init__(self, jid, gnupghome):
        gnupg.GPG.__init__(self, gpgbinary='gpg', gnupghome=str(gnupghome))

        self._jid = jid.bare
        self._own_fingerprint = None

    @staticmethod
    def _get_key_params(jid):
        '''
        Generate --gen-key input
        '''

        params = {
            'Key-Type': 'RSA',
            'Key-Length': 2048,
            'Name-Real': 'xmpp:%s' % jid,
        }

        out = 'Key-Type: %s\n' % params.pop('Key-Type')
        for key, val in list(params.items()):
            out += '%s: %s\n' % (key, val)
        out += '%no-protection\n'
        out += '%commit\n'
        return out

    def generate_key(self):
        super().gen_key(self._get_key_params(self._jid))

    def encrypt(self, payload, keys):
        recipients = [key.fingerprint for key in keys]
        log.info('encrypt to:')
        for fingerprint in recipients:
            log.info(fingerprint)

        result = super().encrypt(str(payload).encode('utf8'),
                                 recipients,
                                 armor=False,
                                 sign=self._own_fingerprint,
                                 always_trust=True)

        if result.ok:
            error = ''
        else:
            error = result.status

        return result.data, error

    def decrypt(self, payload):
        result = super().decrypt(payload, always_trust=True)
        if not result.ok:
            raise DecryptionFailed(result.status)

        return result.data.decode('utf8'), result.fingerprint

    def get_key(self, fingerprint):
        return super().list_keys(keys=[fingerprint])

    def get_keys(self, secret=False):
        result = super().list_keys(secret=secret)
        keys = []
        for key in result:
            item = KeyringItem(key)
            if not item.is_xmpp_key:
                log.warning('Invalid key found, deleting key')
                log.warning(key)
                self.delete_key(item.fingerprint)
                continue
            keys.append(item)
        return keys

    def import_key(self, data, jid):
        log.info('Import key from %s', jid)
        result = super().import_keys(data)
        if not result:
            log.error('Could not import key')
            log.error(result)
            return

        key = self.get_key(result.results[0]['fingerprint'])
        item = KeyringItem(key[0])
        if not item.is_valid(jid):
            log.warning('Invalid key found, deleting key')
            log.warning(key)
            self.delete_key(item.fingerprint)
            return

        return item

    def get_own_key_details(self):
        result = super().list_keys(secret=True)
        if not result:
            return None, None

        if len(result) > 1:
            log.error('More than one secret key found')
            return None, None

        self._own_fingerprint = result[0]['fingerprint']
        return self._own_fingerprint, int(result[0]['date'])

    def export_key(self, fingerprint):
        key = super().export_keys(
            fingerprint, secret=False, armor=False, minimal=True)
        return key

    def delete_key(self, fingerprint):
        log.info('Delete Key: %s', fingerprint)
        super().delete_keys(fingerprint)
