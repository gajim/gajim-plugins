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

import os
import logging
from collections import namedtuple

import gnupg

from openpgp.modules.util import DecryptionFailed

log = logging.getLogger('gajim.p.openpgp.pygnupg')
if log.getEffectiveLevel() == logging.DEBUG:
    log = logging.getLogger('gnupg')
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.DEBUG)

KeyringItem = namedtuple('KeyringItem', 'jid keyid fingerprint')


class PythonGnuPG(gnupg.GPG):
    def __init__(self, jid, gnupghome):
        gnupg.GPG.__init__(self, gpgbinary='gpg', gnupghome=str(gnupghome))

        self._jid = jid.getBare()
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
            item = self._make_keyring_item(key)
            if item is None:
                continue
            keys.append(self._make_keyring_item(key))
        return keys

    @staticmethod
    def _make_keyring_item(key):
        userid = key['uids'][0]
        if not userid.startswith('xmpp:'):
            log.warning('Incorrect userid: %s found for key, '
                        'key will be ignored', userid)
            return
        jid = userid[5:]
        return KeyringItem(jid, key['keyid'], key['fingerprint'])

    def import_key(self, data, jid):
        log.info('Import key from %s', jid)
        result = super().import_keys(data)
        if not result:
            log.error('Could not import key')
            log.error(result)
            return

        if not self.validate_key(data, str(jid)):
            return None
        key = self.get_key(result.results[0]['fingerprint'])
        return self._make_keyring_item(key[0])

    def validate_key(self, public_key, jid):
        import tempfile
        temppath = os.path.join(tempfile.gettempdir(), 'temp_pubkey')
        with open(temppath, 'wb') as tempfile:
            tempfile.write(public_key)

        result = self.scan_keys(temppath)
        if result:
            key_found = False
            for uid in result.uids:
                if uid.startswith('xmpp:'):
                    if uid[5:] == jid:
                        key_found = True
                    else:
                        log.warning('Found wrong userid in key: %s != %s',
                                    uid[5:], jid)
                        log.debug(result)
                        os.remove(temppath)
                        return False

            if not key_found:
                log.warning('No valid userid found in key')
                log.debug(result)
                os.remove(temppath)
                return False

            log.info('Key validation succesful')
            os.remove(temppath)
            return True

        log.warning('Invalid key data: %s')
        log.debug(result)
        os.remove(temppath)
        return False

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
