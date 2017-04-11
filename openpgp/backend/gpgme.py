# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

# XEP-0373: OpenPGP for XMPP


import io
from collections import namedtuple
import logging

import gpg

from gajim.common import app

KeyringItem = namedtuple('KeyringItem',
                         'type keyid userid fingerprint')

log = logging.getLogger('gajim.plugin_system.openpgp.pgpme')


class PGPContext():
    def __init__(self, jid, gnuhome):
        self.context = gpg.Context(home_dir=str(gnuhome))
        # self.create_new_key()
    #    self.get_key_by_name()
    #    self.get_key_by_fingerprint()
        self.export_public_key()

    def create_new_key(self):
        parms = """<GnupgKeyParms format="internal">
        Key-Type: RSA
        Key-Length: 2048
        Subkey-Type: RSA
        Subkey-Length: 2048
        Name-Real: Joe Tester
        Name-Comment: with stupid passphrase
        Name-Email: test@example.org
        Passphrase: Crypt0R0cks
        Expire-Date: 2020-12-31
        </GnupgKeyParms>
        """

        with self.context as c:
            c.set_engine_info(gpg.constants.PROTOCOL_OpenPGP, None, app.gajimpaths['MY_DATA'])
            c.set_progress_cb(gpg.callbacks.progress_stdout)
            c.op_genkey(parms, None, None)
            print("Generated key with fingerprint {0}.".format(
                c.op_genkey_result().fpr))

    def get_all_keys(self):
        c = gpg.Context()
        for key in c.keylist():
            user = key.uids[0]
            print("Keys for %s (%s):" % (user.name, user.email))
            for subkey in key.subkeys:
                features = []
                if subkey.can_authenticate:
                    features.append('auth')
                if subkey.can_certify:
                    features.append('cert')
                if subkey.can_encrypt:
                    features.append('encrypt')
                if subkey.can_sign:
                    features.append('sign')
                print('  %s %s' % (subkey.fpr, ','.join(features)))

    def get_key_by_name(self):
        c = gpg.Context()
        for key in c.keylist('john'):
            print(key.subkeys[0].fpr)

    def get_key_by_fingerprint(self):
        c = gpg.Context()
        fingerprint = 'key fingerprint to search for'
        try:
            key = c.get_key(fingerprint)
            print('%s (%s)' % (key.uids[0].name, key.uids[0].email))
        except gpg.errors.KeyNotFound:
            print("No key for fingerprint '%s'." % fingerprint)

    def get_secret_key(self):
        '''
        Key(can_authenticate=1,
            can_certify=1,
            can_encrypt=1,
            can_sign=1,
            chain_id=None,
            disabled=0,
            expired=0,
            fpr='7ECE1F88BAFCA37F168E1556A4DBDD1BA55FE3CE',
            invalid=0,
            is_qualified=0,
            issuer_name=None,
            issuer_serial=None,
            keylist_mode=1,
            last_update=0,
            origin=0,
            owner_trust=5,
            protocol=0,
            revoked=0,
            secret=1,
            subkeys=[
                SubKey(can_authenticate=1,
                       can_certify=1,
                       can_encrypt=1,
                       can_sign=1,
                       card_number=None
                       curve=None,
                       disabled=0,
                       expired=0,
                       expires=0,
                       fpr='7ECE1F88BAFCA37F168E1556A4DBDD1BA55FE3CE',
                       invalid=0,
                       is_cardkey=0,
                       is_de_vs=1,
                       is_qualified=0,
                       keygrip='15BECB77301E4810ABB9CA6A9391158E575DABEC',
                       keyid='A4DBDD1BA55FE3CE',
                       length=2048,
                       pubkey_algo=1,
                       revoked=0,
                       secret=1,
                       timestamp=1525006759)],
            uids=[
                UID(address=None,
                    comment='',
                    email='',
                    invalid=0,
                    last_update=0,
                    name='xmpp:philw@jabber.at',
                    origin=0,
                    revoked=0,
                    signatures=[],
                    tofu=[],
                    uid='xmpp:philw@jabber.at',
                    validity=5)])
        '''
        for key in self.context.keylist(secret=True):
            break
        return key.fpr, key.fpr[-16:]

    def get_keys(self, secret=False):
        keys = []
        for key in self.context.keylist():
            for uid in key.uids:
                if uid.uid.startswith('xmpp:'):
                    keys.append((key, uid.uid[5:]))
                    break
        return keys

    def export_public_key(self):
        # print(dir(self.context))
        result = self.context.key_export_minimal()
        print(result)

    def encrypt_decrypt_files(self):
        c = gpg.Context()
        recipient = c.get_key("fingerprint of recipient's key")

        # Encrypt
        with open('foo.txt', 'r') as input_file:
            with open('foo.txt.gpg', 'wb') as output_file:
                c.encrypt([recipient], 0, input_file, output_file)

        # Decrypt
        with open('foo.txt.gpg', 'rb') as input_file:
            with open('foo2.txt', 'w') as output_file:
                c.decrypt(input_file, output_file)

    def encrypt(self):
        c = gpg.Context()
        recipient = c.get_key("fingerprint of recipient's key")

        plaintext_string = u'plain text data'
        plaintext_bytes = io.BytesIO(plaintext_string.encode('utf8'))
        encrypted_bytes = io.BytesIO()
        c.encrypt([recipient], 0, plaintext_bytes, encrypted_bytes)

    def decrypt(self):
        c = gpg.Context()
        decrypted_bytes = io.BytesIO()
        c.decrypt(encrypted_bytes, decrypted_bytes)
        decrypted_string = decrypted_bytes.getvalue().decode('utf8')
