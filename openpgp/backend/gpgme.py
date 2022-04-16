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

from nbxmpp.protocol import JID

import gpg
from gpg.results import ImportResult

from openpgp.modules.util import DecryptionFailed

log = logging.getLogger('gajim.p.openpgp.gpgme')


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

    def _get_uid(self):
        for uid in self._key.uids:
            if uid.uid.startswith('xmpp:'):
                return uid.uid

    @property
    def fingerprint(self):
        return self._key.fpr

    @property
    def uid(self):
        if self._uid is not None:
            return self._uid

    @property
    def jid(self):
        if self._uid is not None:
            return JID.from_string(self._uid[5:])

    def __hash__(self):
        return hash(self.fingerprint)


class GPGME:
    def __init__(self, jid, gnuhome):
        self._jid = jid
        self._context_args = {
            'home_dir': str(gnuhome),
            'offline': True,
            'armor': False,
        }

    def generate_key(self):
        with gpg.Context(**self._context_args) as context:
            result = context.create_key(f'xmpp:{str(self._jid)}',
                                        expires=False,
                                        sign=True,
                                        encrypt=True,
                                        certify=False,
                                        authenticate=False,
                                        passphrase=None,
                                        force=False)

            log.info('Generated new key: %s', result.fpr)

    def get_key(self, fingerprint):
        with gpg.Context(**self._context_args) as context:
            try:
                key = context.get_key(fingerprint)
            except gpg.errors.KeyNotFound as error:
                log.warning('key not found: %s', error.keystr)
                return

            except Exception as error:
                log.warning('get_key() error: %s', error)
                return

        return key

    def get_own_key_details(self):
        with gpg.Context(**self._context_args) as context:
            keys = list(context.keylist(secret=True))
            if not keys:
                return None, None

            key = keys[0]
            for subkey in key.subkeys:
                if subkey.fpr == key.fpr:
                    return subkey.fpr, subkey.timestamp

        return None, None

    def get_keys(self):
        keys = []
        with gpg.Context(**self._context_args) as context:
            for key in context.keylist():
                keyring_item = KeyringItem(key)
                if not keyring_item.is_xmpp_key:
                    log.warning('Key not suited for xmpp: %s', key.fpr)
                    continue

                keys.append(keyring_item)

        return keys

    def export_key(self, fingerprint):
        with gpg.Context(**self._context_args) as context:
            key = context.key_export_minimal(pattern=fingerprint)
        return key

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

    def encrypt(self, plaintext, keys):
        recipients = []
        with gpg.Context(**self._context_args) as context:
            for key in keys:
                key = context.get_key(key.fingerprint)
                if key is not None:
                    recipients.append(key)

        if not recipients:
            return None, 'No keys found to encrypt to'

        with gpg.Context(**self._context_args) as context:
            result = context.encrypt(str(plaintext).encode(),
                                     recipients,
                                     always_trust=True)

        ciphertext, result, _sign_result = result
        return ciphertext, None

    def decrypt(self, ciphertext):
        with gpg.Context(**self._context_args) as context:
            try:
                result = context.decrypt(ciphertext)
            except Exception as error:
                raise DecryptionFailed('Decryption failed: %s' % error)

        plaintext, result, verify_result = result
        plaintext = plaintext.decode()

        fingerprints = [sig.fpr for sig in verify_result.signatures]
        if not fingerprints or len(fingerprints) > 1:
            log.error(result)
            log.error(verify_result)
            raise DecryptionFailed('Verification failed')

        return plaintext, fingerprints[0]

    def import_key(self, data, jid):
        log.info('Import key from %s', jid)
        with gpg.Context(**self._context_args) as context:
            result = context.key_import(data)
            if not isinstance(result, ImportResult) or result.imported != 1:
                log.error('Key import failed: %s', jid)
                log.error(result)
                return

            fingerprint = result.imports[0].fpr
            key = self.get_key(fingerprint)

        return KeyringItem(key)

    def delete_key(self, fingerprint):
        key = self.get_key(fingerprint)
        with gpg.Context(**self._context_args) as context:
            context.op_delete(key, True)
