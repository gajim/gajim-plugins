# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
# Copyright (C) 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
#
# This file is part of OMEMO Gajim Plugin.
#
# OMEMO Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import logging
import time
from collections import defaultdict

from nbxmpp.structs import OMEMOBundle
from nbxmpp.structs import OMEMOMessage

from axolotl.ecc.djbec import DjbECPublicKey
from axolotl.identitykey import IdentityKey

from axolotl.protocol.prekeywhispermessage import PreKeyWhisperMessage
from axolotl.protocol.whispermessage import WhisperMessage
from axolotl.sessionbuilder import SessionBuilder
from axolotl.sessioncipher import SessionCipher
from axolotl.state.prekeybundle import PreKeyBundle
from axolotl.util.keyhelper import KeyHelper
from axolotl.duplicatemessagexception import DuplicateMessageException

from omemo.backend.aes import aes_decrypt, aes_encrypt
from omemo.backend.devices import DeviceManager
from omemo.backend.devices import NoDevicesFound
from omemo.backend.liteaxolotlstore import LiteAxolotlStore
from omemo.backend.util import get_fingerprint
from omemo.backend.util import DEFAULT_PREKEY_AMOUNT
from omemo.backend.util import MIN_PREKEY_AMOUNT
from omemo.backend.util import SPK_CYCLE_TIME
from omemo.backend.util import SPK_ARCHIVE_TIME


log = logging.getLogger('gajim.plugin_system.omemo')


class OmemoState(DeviceManager):
    def __init__(self, own_jid, db_path, account, xmpp_con):
        self._account = account
        self._own_jid = own_jid
        self._session_ciphers = defaultdict(dict)
        self._storage = LiteAxolotlStore(db_path)

        DeviceManager.__init__(self)

        self.xmpp_con = xmpp_con

        log.info('%s => %s PreKeys available',
                 self._account,
                 self._storage.getPreKeyCount())

    def build_session(self, jid, device_id, bundle):
        session = SessionBuilder(self._storage, self._storage, self._storage,
                                 self._storage, jid, device_id)

        registration_id = self._storage.getLocalRegistrationId()

        prekey = bundle.pick_prekey()
        otpk = DjbECPublicKey(prekey['key'][1:])

        spk = DjbECPublicKey(bundle.spk['key'][1:])
        ik = IdentityKey(DjbECPublicKey(bundle.ik[1:]))

        prekey_bundle = PreKeyBundle(registration_id,
                                     device_id,
                                     prekey['id'],
                                     otpk,
                                     bundle.spk['id'],
                                     spk,
                                     bundle.spk_signature,
                                     ik)

        session.processPreKeyBundle(prekey_bundle)
        return self._get_session_cipher(jid, device_id)

    @property
    def storage(self):
        return self._storage

    @property
    def own_fingerprint(self):
        return get_fingerprint(self._storage.getIdentityKeyPair())

    @property
    def bundle(self):
        self._check_pre_key_count()

        bundle = {'otpks': []}
        for k in self._storage.loadPendingPreKeys():
            key = k.getKeyPair().getPublicKey().serialize()
            bundle['otpks'].append({'key': key, 'id': k.getId()})

        ik_pair = self._storage.getIdentityKeyPair()
        bundle['ik'] = ik_pair.getPublicKey().serialize()

        self._cycle_signed_pre_key(ik_pair)

        spk = self._storage.loadSignedPreKey(
            self._storage.getCurrentSignedPreKeyId())
        bundle['spk_signature'] = spk.getSignature()
        bundle['spk'] = {'key': spk.getKeyPair().getPublicKey().serialize(),
                         'id': spk.getId()}

        return OMEMOBundle(**bundle)

    def decrypt_message(self, omemo_message, jid):
        if omemo_message.sid == self.own_device:
            log.info('Received previously sent message by us')
            raise SelfMessage

        try:
            encrypted_key, prekey = omemo_message.keys[self.own_device]
        except KeyError:
            log.info('Received message not for our device')
            raise MessageNotForDevice

        try:
            if prekey:
                key, fingerprint = self._process_pre_key_message(
                    jid, omemo_message.sid, encrypted_key)
            else:
                key, fingerprint = self._process_message(
                    jid, omemo_message.sid, encrypted_key)

        except SenderNotTrusted:
            log.info('Sender not trusted, ignore message')
            raise

        except DuplicateMessageException:
            log.info('Received duplicated message')
            raise DuplicateMessage

        except Exception as error:
            log.warning(error)
            raise DecryptionFailed

        if omemo_message.payload is None:
            log.debug("Decrypted Key Exchange Message")
            raise KeyExchangeMessage

        result = aes_decrypt(key, omemo_message.iv, omemo_message.payload)
        log.debug("Decrypted Message => %s", result)
        return result, fingerprint

    def _get_whisper_message(self, jid, device, key):
        cipher = self._get_session_cipher(jid, device)
        cipher_key = cipher.encrypt(key)
        prekey = isinstance(cipher_key, PreKeyWhisperMessage)
        return cipher_key.serialize(), prekey

    def encrypt(self, jid, plaintext):
        try:
            devices_for_encryption = self.get_devices_for_encryption(jid)
        except NoDevicesFound:
            log.warning('No devices for encryption found for: %s', jid)
            return

        result = aes_encrypt(plaintext)
        whisper_messages = defaultdict(dict)

        for jid_, device in devices_for_encryption:
            try:
                whisper_messages[jid_][device] = self._get_whisper_message(
                    jid_, device, result.key)
            except Exception:
                log.exception('Failed to encrypt')
                continue

        recipients = set(whisper_messages.keys()) - set([self._own_jid])
        if not recipients:
            log.error('Encrypted keys empty')
            return

        encrypted_keys = {}
        for jid_ in whisper_messages:
            encrypted_keys.update(whisper_messages[jid_])

        log.debug('Finished encrypting message')
        return OMEMOMessage(sid=self.own_device,
                            keys=encrypted_keys,
                            iv=result.iv,
                            payload=result.payload)

    def has_trusted_keys(self, jid):
        inactive = self._storage.getInactiveSessionsKeys(jid)
        trusted = self._storage.getTrustedFingerprints(jid)
        return bool(set(trusted) - set(inactive))

    def devices_without_sessions(self, jid):
        known_devices = self.get_devices(jid, without_self=True)
        missing_devices = [dev
                           for dev in known_devices
                           if not self._storage.containsSession(jid, dev)]
        if missing_devices:
            log.info('%s => Missing device sessions for %s: %s',
                     self._account, jid, missing_devices)
        return missing_devices

    def _get_session_cipher(self, jid, device_id):
        try:
            return self._session_ciphers[jid][device_id]
        except KeyError:
            cipher = SessionCipher(self._storage, self._storage, self._storage,
                                   self._storage, jid, device_id)
            self._session_ciphers[jid][device_id] = cipher
            return cipher

    def _process_pre_key_message(self, jid, device, key):
        pre_key_message = PreKeyWhisperMessage(serialized=key)
        if not pre_key_message.getPreKeyId():
            raise Exception('Received Pre Key Message '
                            'without PreKey => %s' % jid)

        identity_key = pre_key_message.getIdentityKey()
        if self._storage.isUntrustedIdentity(jid, identity_key):
            raise SenderNotTrusted

        session_cipher = self._get_session_cipher(jid, device)

        log.info('%s => Process pre key message from %s',
                 self._account, jid)
        key = session_cipher.decryptPkmsg(pre_key_message)
        fingerprint = get_fingerprint(identity_key)

        self._storage.setIdentityLastSeen(jid, identity_key)

        self.xmpp_con.set_bundle()
        self.add_device(jid, device)
        return key, fingerprint

    def _process_message(self, jid, device, key):
        message = WhisperMessage(serialized=key)
        log.info('%s => Process message from %s', self._account, jid)

        session_cipher = self._get_session_cipher(jid, device)
        key = session_cipher.decryptMsg(message, textMsg=False)

        session_record = self._storage.loadSession(jid, device)
        identity_key = session_record.getSessionState().getRemoteIdentityKey()

        if self._storage.isUntrustedIdentity(jid, identity_key):
            raise SenderNotTrusted

        fingerprint = get_fingerprint(identity_key)
        self._storage.setIdentityLastSeen(jid, identity_key)

        self.add_device(jid, device)

        return key, fingerprint

    def _check_pre_key_count(self):
        # Check if enough PreKeys are available
        pre_key_count = self._storage.getPreKeyCount()
        if pre_key_count < MIN_PREKEY_AMOUNT:
            missing_count = DEFAULT_PREKEY_AMOUNT - pre_key_count
            self._storage.generateNewPreKeys(missing_count)
            log.info('%s => %s PreKeys created', self._account, missing_count)

    def _cycle_signed_pre_key(self, ik_pair):
        # Publish every SPK_CYCLE_TIME a new SignedPreKey
        # Delete all exsiting SignedPreKeys that are older
        # then SPK_ARCHIVE_TIME

        # Check if SignedPreKey exist and create if not
        if not self._storage.getCurrentSignedPreKeyId():
            spk = KeyHelper.generateSignedPreKey(
                ik_pair, self._storage.getNextSignedPreKeyId())
            self._storage.storeSignedPreKey(spk.getId(), spk)
            log.debug('%s => New SignedPreKey created, because none existed',
                      self._account)

        # if SPK_CYCLE_TIME is reached, generate a new SignedPreKey
        now = int(time.time())
        timestamp = self._storage.getSignedPreKeyTimestamp(
            self._storage.getCurrentSignedPreKeyId())

        if int(timestamp) < now - SPK_CYCLE_TIME:
            spk = KeyHelper.generateSignedPreKey(
                ik_pair, self._storage.getNextSignedPreKeyId())
            self._storage.storeSignedPreKey(spk.getId(), spk)
            log.debug('%s => Cycled SignedPreKey', self._account)

        # Delete all SignedPreKeys that are older than SPK_ARCHIVE_TIME
        timestamp = now - SPK_ARCHIVE_TIME
        self._storage.removeOldSignedPreKeys(timestamp)


class NoValidSessions(Exception):
    pass


class SelfMessage(Exception):
    pass


class MessageNotForDevice(Exception):
    pass


class DecryptionFailed(Exception):
    pass


class KeyExchangeMessage(Exception):
    pass


class InvalidMessage(Exception):
    pass


class DuplicateMessage(Exception):
    pass


class SenderNotTrusted(Exception):
    pass
