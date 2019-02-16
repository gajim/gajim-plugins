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
from axolotl.untrustedidentityexception import UntrustedIdentityException

from axolotl.protocol.prekeywhispermessage import PreKeyWhisperMessage
from axolotl.protocol.whispermessage import WhisperMessage
from axolotl.sessionbuilder import SessionBuilder
from axolotl.sessioncipher import SessionCipher
from axolotl.state.prekeybundle import PreKeyBundle
from axolotl.util.keyhelper import KeyHelper
from axolotl.duplicatemessagexception import DuplicateMessageException

from omemo.backend.aes import aes_decrypt, aes_encrypt
from omemo.backend.liteaxolotlstore import LiteAxolotlStore
from omemo.backend.liteaxolotlstore import DEFAULT_PREKEY_AMOUNT
from omemo.backend.liteaxolotlstore import MIN_PREKEY_AMOUNT
from omemo.backend.liteaxolotlstore import SPK_CYCLE_TIME
from omemo.backend.liteaxolotlstore import SPK_ARCHIVE_TIME


log = logging.getLogger('gajim.plugin_system.omemo')


UNTRUSTED = 0
TRUSTED = 1
UNDECIDED = 2


class OmemoState:
    def __init__(self, own_jid, db_path, account, xmpp_con):
        self.account = account
        self.xmpp_con = xmpp_con
        self._session_ciphers = defaultdict(dict)
        self.own_jid = own_jid
        self.device_ids = {}
        self.own_devices = []

        self.store = LiteAxolotlStore(db_path)
        for jid, device_id in self.store.getActiveDeviceTuples():
            if jid != own_jid:
                self.add_device(jid, device_id)
            else:
                self.add_own_device(device_id)

        log.info('%s => Roster devices after boot: %s',
                 self.account, self.device_ids)
        log.info('%s => Own devices after boot: %s',
                 self.account, self.own_devices)
        log.debug('%s => %s PreKeys available',
                  self.account,
                  self.store.getPreKeyCount())

    def build_session(self, jid, device_id, bundle):
        session = SessionBuilder(self.store, self.store, self.store,
                                 self.store, jid, device_id)

        registration_id = self.store.getLocalRegistrationId()

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

    def set_devices(self, name, devices):
        self.device_ids[name] = devices
        log.info('%s => Saved devices for %s', self.account, name)

    def add_device(self, name, device_id):
        if name not in self.device_ids:
            self.device_ids[name] = [device_id]
        elif device_id not in self.device_ids[name]:
            self.device_ids[name].append(device_id)

    def set_own_devices(self, devices):
        """ Overwrite the current :py:attribute:`OmemoState.own_devices` with
            the given devices.

            Parameters
            ----------
            devices : [int]
                A list of device_ids
        """
        self.own_devices = devices
        log.info('%s => Saved own devices', self.account)

    def add_own_device(self, device_id):
        if device_id not in self.own_devices:
            self.own_devices.append(device_id)

    @property
    def own_device_id(self):
        reg_id = self.store.getLocalRegistrationId()
        assert reg_id is not None, \
            "Requested device_id but there is no generated"

        return (reg_id % 2147483646) + 1

    def own_device_id_published(self):
        """ Return `True` only if own device id was added via
            :py:method:`OmemoState.set_own_devices()`.
        """
        return self.own_device_id in self.own_devices

    @property
    def bundle(self):
        self._check_pre_key_count()

        bundle = {'otpks': []}
        for k in self.store.loadPendingPreKeys():
            key = k.getKeyPair().getPublicKey().serialize()
            bundle['otpks'].append({'key': key, 'id': k.getId()})

        ik_pair = self.store.getIdentityKeyPair()
        bundle['ik'] = ik_pair.getPublicKey().serialize()

        self._cycle_signed_pre_key(ik_pair)

        spk = self.store.loadSignedPreKey(
            self.store.getCurrentSignedPreKeyId())
        bundle['spk_signature'] = spk.getSignature()
        bundle['spk'] = {'key': spk.getKeyPair().getPublicKey().serialize(),
                         'id': spk.getId()}

        return OMEMOBundle(**bundle)

    def decrypt_message(self, omemo_message, jid):
        if omemo_message.sid == self.own_device_id:
            log.info('Received previously sent message by us')
            raise SelfMessage

        try:
            encrypted_key, prekey = omemo_message.keys[self.own_device_id]
        except KeyError:
            log.info('Received message not for our device')
            raise MessageNotForDevice

        try:
            if prekey:
                key = self._process_pre_key_message(
                    jid, omemo_message.sid, encrypted_key)
            else:
                key = self._process_message(
                    jid, omemo_message.sid, encrypted_key)

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
        return result

    def create_msg(self, jid, plaintext):
        encrypted_keys = {}

        devices_list = self.device_list_for(jid)
        if not devices_list:
            log.error('No known devices')
            return

        result = aes_encrypt(plaintext)

        # Encrypt the message key with for each of receivers devices
        for device in devices_list:
            try:
                if self.isTrusted(jid, device) == TRUSTED:
                    cipher = self._get_session_cipher(jid, device)
                    cipher_key = cipher.encrypt(result.key)
                    prekey = isinstance(cipher_key, PreKeyWhisperMessage)
                    encrypted_keys[device] = (cipher_key.serialize(), prekey)
                else:
                    log.debug('Skipped Device because Trust is: %s',
                              self.isTrusted(jid, device))
            except Exception:
                log.warning('Failed to find key for device: %s', device)

        if not encrypted_keys:
            log.error('Encrypted keys empty')
            raise NoValidSessions('Encrypted keys empty')

        my_other_devices = set(self.own_devices) - set({self.own_device_id})
        # Encrypt the message key with for each of our own devices
        for device in my_other_devices:
            try:
                if self.isTrusted(self.own_jid, device) == TRUSTED:
                    cipher = self._get_session_cipher(self.own_jid, device)
                    cipher_key = cipher.encrypt(result.key)
                    prekey = isinstance(cipher_key, PreKeyWhisperMessage)
                    encrypted_keys[device] = (cipher_key.serialize(), prekey)
                else:
                    log.debug('Skipped own Device because Trust is: %s',
                              self.isTrusted(self.own_jid, device))
            except Exception:
                log.warning('Failed to find key for device: %s', device)

        log.debug('Finished encrypting message')
        return OMEMOMessage(sid=self.own_device_id,
                            keys=encrypted_keys,
                            iv=result.iv,
                            payload=result.payload)

    def create_gc_msg(self, from_jid, jid, plaintext):
        encrypted_keys = {}
        room = jid
        encrypted_jids = []

        devices_list = self.device_list_for(jid, True)

        result = aes_encrypt(plaintext)

        for tup in devices_list:
            self._get_session_cipher(tup[0], tup[1])

        # Encrypt the message key with for each of receivers devices
        for nick in self.xmpp_con.groupchat[room]:
            jid_to = self.xmpp_con.groupchat[room][nick]
            if jid_to == self.own_jid:
                continue
            if jid_to in encrypted_jids:  # We already encrypted to this JID
                continue
            if jid_to not in self._session_ciphers:
                continue
            for rid, cipher in self._session_ciphers[jid_to].items():
                try:
                    if self.isTrusted(jid_to, rid) == TRUSTED:
                        cipher_key = cipher.encrypt(result.key)
                        prekey = isinstance(cipher_key, PreKeyWhisperMessage)
                        encrypted_keys[rid] = (cipher_key.serialize(), prekey)
                    else:
                        log.debug('Skipped Device because Trust is: %s',
                                  self.isTrusted(jid_to, rid))
                except Exception:
                    log.exception('ERROR:')
                    log.warning('Failed to find key for device %s', rid)
            encrypted_jids.append(jid_to)

        my_other_devices = set(self.own_devices) - set({self.own_device_id})
        # Encrypt the message key with for each of our own devices
        for dev in my_other_devices:
            try:
                cipher = self._get_session_cipher(from_jid, dev)
                if self.isTrusted(from_jid, dev) == TRUSTED:
                    cipher_key = cipher.encrypt(result.key)
                    prekey = isinstance(cipher_key, PreKeyWhisperMessage)
                    encrypted_keys[dev] = (cipher_key.serialize(), prekey)
                else:
                    log.debug('Skipped own Device because Trust is: %s',
                              self.isTrusted(from_jid, dev))
            except Exception:
                log.exception('ERROR:')
                log.warning('Failed to find key for device: %s', dev)

        if not encrypted_keys:
            log.error('Encrypted keys empty')
            raise NoValidSessions('Encrypted keys empty')

        log.debug('Finished encrypting message')
        return OMEMOMessage(sid=self.own_device_id,
                            keys=encrypted_keys,
                            iv=result.iv,
                            payload=result.payload)

    def device_list_for(self, jid, gc=False):
        """ Return a list of known device ids for the specified jid.
            Parameters
            ----------
            jid : string
                The contacts jid
            gc : bool
                Groupchat Message
        """
        if gc:
            room = jid
            devicelist = []
            for nick in self.xmpp_con.groupchat[room]:
                jid_to = self.xmpp_con.groupchat[room][nick]
                if jid_to == self.own_jid:
                    continue
                try:
                    for device in self.device_ids[jid_to]:
                        devicelist.append((jid_to, device))
                except KeyError:
                    log.warning('no device ids found for %s', jid_to)
                    continue
            return devicelist

        if jid == self.own_jid:
            return set(self.own_devices) - set({self.own_device_id})
        if jid not in self.device_ids:
            return set()
        return set(self.device_ids[jid])

    def isTrusted(self, recipient_id, device_id):
        record = self.store.loadSession(recipient_id, device_id)
        identity_key = record.getSessionState().getRemoteIdentityKey()
        return self.store.isTrustedIdentity(recipient_id, identity_key)

    def getTrustedFingerprints(self, recipient_id):
        inactive = self.store.getInactiveSessionsKeys(recipient_id)
        trusted = self.store.getTrustedFingerprints(recipient_id)
        trusted = set(trusted) - set(inactive)

        return trusted

    def getUndecidedFingerprints(self, recipient_id):
        inactive = self.store.getInactiveSessionsKeys(recipient_id)
        undecided = self.store.getUndecidedFingerprints(recipient_id)
        undecided = set(undecided) - set(inactive)

        return undecided

    def devices_without_sessions(self, jid):
        """ List device_ids for the given jid which have no axolotl session.

            Parameters
            ----------
            jid : string
                The contacts jid

            Returns
            -------
            [int]
                A list of device_ids
        """
        known_devices = self.device_list_for(jid)
        missing_devices = [dev
                           for dev in known_devices
                           if not self.store.containsSession(jid, dev)]
        if missing_devices:
            log.info('%s => Missing device sessions for %s: %s',
                     self.account, jid, missing_devices)
        return missing_devices

    def _get_session_cipher(self, jid, device_id):
        try:
            return self._session_ciphers[jid][device_id]
        except KeyError:
            cipher = SessionCipher(self.store, self.store, self.store,
                                   self.store, jid, device_id)
            self._session_ciphers[jid][device_id] = cipher
            return cipher

    def _process_pre_key_message(self, recipient_id, device_id, key):
        preKeyWhisperMessage = PreKeyWhisperMessage(serialized=key)
        if not preKeyWhisperMessage.getPreKeyId():
            raise Exception('Received PreKeyWhisperMessage '
                            'without PreKey => %s' % recipient_id)
        sessionCipher = self._get_session_cipher(recipient_id, device_id)
        try:
            log.debug('%s => Received PreKeyWhisperMessage from %s',
                      self.account, recipient_id)
            key = sessionCipher.decryptPkmsg(preKeyWhisperMessage)
            # Publish new bundle after PreKey has been used
            # for building a new Session
            self.xmpp_con.set_bundle()
            self.add_device(recipient_id, device_id)
            return key
        except UntrustedIdentityException as error:
            log.info('%s => Received WhisperMessage '
                     'from Untrusted Fingerprint! => %s',
                     self.account, error.getName())

    def _process_message(self, recipient_id, device_id, key):
        whisperMessage = WhisperMessage(serialized=key)
        log.debug('%s => Received WhisperMessage from %s',
                  self.account, recipient_id)
        if self.isTrusted(recipient_id, device_id):
            sessionCipher = self._get_session_cipher(recipient_id, device_id)
            key = sessionCipher.decryptMsg(whisperMessage, textMsg=False)
            self.add_device(recipient_id, device_id)
            return key

        raise Exception('Received WhisperMessage '
                        'from Untrusted Fingerprint! => %s' % recipient_id)

    def _check_pre_key_count(self):
        # Check if enough PreKeys are available
        pre_key_count = self.store.getPreKeyCount()
        if pre_key_count < MIN_PREKEY_AMOUNT:
            missing_count = DEFAULT_PREKEY_AMOUNT - pre_key_count
            self.store.generateNewPreKeys(missing_count)
            log.info('%s => %s PreKeys created', self.account, missing_count)

    def _cycle_signed_pre_key(self, ik_pair):
        # Publish every SPK_CYCLE_TIME a new SignedPreKey
        # Delete all exsiting SignedPreKeys that are older
        # then SPK_ARCHIVE_TIME

        # Check if SignedPreKey exist and create if not
        if not self.store.getCurrentSignedPreKeyId():
            spk = KeyHelper.generateSignedPreKey(
                ik_pair, self.store.getNextSignedPreKeyId())
            self.store.storeSignedPreKey(spk.getId(), spk)
            log.debug('%s => New SignedPreKey created, because none existed',
                      self.account)

        # if SPK_CYCLE_TIME is reached, generate a new SignedPreKey
        now = int(time.time())
        timestamp = self.store.getSignedPreKeyTimestamp(
            self.store.getCurrentSignedPreKeyId())

        if int(timestamp) < now - SPK_CYCLE_TIME:
            spk = KeyHelper.generateSignedPreKey(
                ik_pair, self.store.getNextSignedPreKeyId())
            self.store.storeSignedPreKey(spk.getId(), spk)
            log.debug('%s => Cycled SignedPreKey', self.account)

        # Delete all SignedPreKeys that are older than SPK_ARCHIVE_TIME
        timestamp = now - SPK_ARCHIVE_TIME
        self.store.removeOldSignedPreKeys(timestamp)


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
