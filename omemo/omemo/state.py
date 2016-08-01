# -*- coding: utf-8 -*-
#
# Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
#
# This file is part of Gajim-OMEMO plugin.
#
# The Gajim-OMEMO plugin is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Gajim-OMEMO is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# the Gajim-OMEMO plugin.  If not, see <http://www.gnu.org/licenses/>.
#

import logging
import time
from base64 import b64encode

from axolotl.ecc.djbec import DjbECPublicKey
from axolotl.identitykey import IdentityKey
from axolotl.duplicatemessagexception import DuplicateMessageException
from axolotl.invalidmessageexception import InvalidMessageException
from axolotl.invalidversionexception import InvalidVersionException
from axolotl.untrustedidentityexception import UntrustedIdentityException
from axolotl.nosessionexception import NoSessionException
from axolotl.protocol.prekeywhispermessage import PreKeyWhisperMessage
from axolotl.protocol.whispermessage import WhisperMessage
from axolotl.sessionbuilder import SessionBuilder
from axolotl.sessioncipher import SessionCipher
from axolotl.state.prekeybundle import PreKeyBundle
from axolotl.util.keyhelper import KeyHelper
from Crypto.Random import get_random_bytes

from .aes_gcm import NoValidSessions, decrypt, encrypt
from .liteaxolotlstore import (LiteAxolotlStore, DEFAULT_PREKEY_AMOUNT,
                               MIN_PREKEY_AMOUNT, SPK_CYCLE_TIME,
                               SPK_ARCHIVE_TIME)

log = logging.getLogger('gajim.plugin_system.omemo')
logAxolotl = logging.getLogger('axolotl')


UNTRUSTED = 0
TRUSTED = 1
UNDECIDED = 2


class OmemoState:
    def __init__(self, own_jid, connection, account, plugin):
        """ Instantiates an OmemoState object.

            :param connection: an :py:class:`sqlite3.Connection`
        """
        self.account = account
        self.plugin = plugin
        self.session_ciphers = {}
        self.own_jid = own_jid
        self.device_ids = {}
        self.own_devices = []
        self.store = LiteAxolotlStore(connection)
        self.encryption = self.store.encryptionStore
        for jid, device_id in self.store.getActiveDeviceTuples():
            if jid != own_jid:
                self.add_device(jid, device_id)
            else:
                self.add_own_device(device_id)

        log.info(self.account + ' => Roster devices after boot:' +
                 str(self.device_ids))
        log.info(self.account + ' => Own devices after boot:' +
                 str(self.own_devices))
        log.debug(self.account + ' => ' +
                  str(self.store.preKeyStore.getPreKeyCount()) +
                  ' PreKeys available')

    def build_session(self, recipient_id, device_id, bundle_dict):
        sessionBuilder = SessionBuilder(self.store, self.store, self.store,
                                        self.store, recipient_id, device_id)

        registration_id = self.store.getLocalRegistrationId()

        preKeyPublic = DjbECPublicKey(bundle_dict['preKeyPublic'][1:])

        signedPreKeyPublic = DjbECPublicKey(bundle_dict['signedPreKeyPublic'][
            1:])
        identityKey = IdentityKey(DjbECPublicKey(bundle_dict['identityKey'][
            1:]))

        prekey_bundle = PreKeyBundle(
            registration_id, device_id, bundle_dict['preKeyId'], preKeyPublic,
            bundle_dict['signedPreKeyId'], signedPreKeyPublic,
            bundle_dict['signedPreKeySignature'], identityKey)

        sessionBuilder.processPreKeyBundle(prekey_bundle)
        return self.get_session_cipher(recipient_id, device_id)

    def set_devices(self, name, devices):
        """ Return a an.

            Parameters
            ----------
            jid : string
                The contacts jid

            devices: [int]
                A list of devices
        """

        self.device_ids[name] = devices
        log.info(self.account + ' => Saved devices for ' + name)

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
        log.info(self.account + ' => Saved own devices')

    def add_own_device(self, device_id):
        if device_id not in self.own_devices:
            self.own_devices.append(device_id)

    @property
    def own_device_id(self):
        reg_id = self.store.getLocalRegistrationId()
        assert reg_id is not None, \
            "Requested device_id but there is no generated"

        return ((reg_id % 2147483646) + 1)

    def own_device_id_published(self):
        """ Return `True` only if own device id was added via
            :py:method:`OmemoState.set_own_devices()`.
        """
        return self.own_device_id in self.own_devices

    @property
    def bundle(self):
        self.checkPreKeyAmount()
        prekeys = [
            (k.getId(), b64encode(k.getKeyPair().getPublicKey().serialize()))
            for k in self.store.loadPreKeys()
        ]

        identityKeyPair = self.store.getIdentityKeyPair()

        self.cycleSignedPreKey(identityKeyPair)

        signedPreKey = self.store.loadSignedPreKey(
            self.store.getCurrentSignedPreKeyId())

        result = {
            'signedPreKeyId': signedPreKey.getId(),
            'signedPreKeyPublic':
            b64encode(signedPreKey.getKeyPair().getPublicKey().serialize()),
            'signedPreKeySignature': b64encode(signedPreKey.getSignature()),
            'identityKey':
            b64encode(identityKeyPair.getPublicKey().serialize()),
            'prekeys': prekeys
        }
        return result

    def decrypt_msg(self, msg_dict):
        own_id = self.own_device_id
        if own_id not in msg_dict['keys']:
            log.warn('OMEMO message does not contain our device key')
            return

        iv = msg_dict['iv']
        sid = msg_dict['sid']
        sender_jid = msg_dict['sender_jid']
        payload = msg_dict['payload']

        encrypted_key = msg_dict['keys'][own_id]

        try:
            key = self.handlePreKeyWhisperMessage(sender_jid, sid,
                                                  encrypted_key)
        except (InvalidVersionException, InvalidMessageException):
            try:
                key = self.handleWhisperMessage(sender_jid, sid, encrypted_key)
            except (NoSessionException, InvalidMessageException) as e:
                log.error('No Session found ' + e.message)
                log.error('sender_jid =>  ' + str(sender_jid) + ' sid =>' +
                          str(sid))
                return
            except (DuplicateMessageException) as e:
                log.error('Duplicate message found ' + str(e.args))
                log.error('sender_jid => ' + str(sender_jid) +
                          ' sid => ' + str(sid))
                return

        except (DuplicateMessageException) as e:
            log.error('Duplicate message found ' + e.message)
            log.error('sender_jid => ' + str(sender_jid) +
                      ' sid => ' + str(sid))
            return

        result = unicode(decrypt(key, iv, payload))

        if self.own_jid == sender_jid:
            self.add_own_device(sid)
        else:
            self.add_device(sender_jid, sid)

        log.debug("Decrypted Message => " + result)
        return result

    def create_msg(self, from_jid, jid, plaintext):
        key = get_random_bytes(16)
        iv = get_random_bytes(16)
        encrypted_keys = {}

        devices_list = self.device_list_for(jid)
        if len(devices_list) == 0:
            log.error('No known devices')
            return

        for dev in devices_list:
            self.get_session_cipher(jid, dev)
        session_ciphers = self.session_ciphers[jid]
        if not session_ciphers:
            log.warn('No session ciphers for ' + jid)
            return

        # Encrypt the message key with for each of receivers devices
        for rid, cipher in session_ciphers.items():
            try:
                if self.isTrusted(cipher) == TRUSTED:
                    encrypted_keys[rid] = cipher.encrypt(key).serialize()
                else:
                    log.debug('Skipped Device because Trust is: ' +
                              str(self.isTrusted(cipher)))
            except:
                log.warn('Failed to find key for device ' + str(rid))

        if len(encrypted_keys) == 0:
            log_msg = 'Encrypted keys empty'
            log.error(log_msg)
            raise NoValidSessions(log_msg)

        my_other_devices = set(self.own_devices) - set({self.own_device_id})
        # Encrypt the message key with for each of our own devices
        for dev in my_other_devices:
            cipher = self.get_session_cipher(from_jid, dev)
            if self.isTrusted(cipher) == TRUSTED:
                encrypted_keys[dev] = cipher.encrypt(key).serialize()
            else:
                log.debug('Skipped own Device because Trust is: ' +
                          str(self.isTrusted(cipher)))

        payload = encrypt(key, iv, plaintext)

        result = {'sid': self.own_device_id,
                  'keys': encrypted_keys,
                  'jid': jid,
                  'iv': iv,
                  'payload': payload}

        log.debug('Finished encrypting message')
        return result

    def isTrusted(self, cipher):
        self.cipher = cipher
        self.state = self.cipher.sessionStore. \
            loadSession(self.cipher.recipientId, self.cipher.deviceId). \
            getSessionState()
        self.key = self.state.getRemoteIdentityKey()
        return self.store.identityKeyStore. \
            isTrustedIdentity(self.cipher.recipientId, self.key)

    def getTrustedFingerprints(self, recipient_id):
        log.debug('Inactive fingerprints')
        log.debug(self.store.getInactiveSessionsKeys(recipient_id))
        log.debug('trusted fingerprints')
        log.debug(self.store.getTrustedFingerprints(recipient_id))

        inactive = self.store.getInactiveSessionsKeys(recipient_id)
        trusted = self.store.getTrustedFingerprints(recipient_id)
        trusted = set(trusted) - set(inactive)

        log.debug('trusted active fingerprints')
        log.debug(trusted)

        return trusted

    def device_list_for(self, jid):
        """ Return a list of known device ids for the specified jid.

            Parameters
            ----------
            jid : string
                The contacts jid
        """
        if jid == self.own_jid:
            return set(self.own_devices) - set({self.own_device_id})
        if jid not in self.device_ids:
            return set()
        return set(self.device_ids[jid])

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
            log.info(self.account + ' => Missing device sessions for ' +
                     jid + ': ' + str(missing_devices))
        return missing_devices

    def get_session_cipher(self, jid, device_id):
        if jid not in self.session_ciphers:
            self.session_ciphers[jid] = {}

        if device_id not in self.session_ciphers[jid]:
            cipher = SessionCipher(self.store, self.store, self.store,
                                   self.store, jid, device_id)
            self.session_ciphers[jid][device_id] = cipher

        return self.session_ciphers[jid][device_id]

    def handlePreKeyWhisperMessage(self, recipient_id, device_id, key):
        preKeyWhisperMessage = PreKeyWhisperMessage(serialized=key)
        sessionCipher = self.get_session_cipher(recipient_id, device_id)
        try:
            log.debug(self.account +
                      " => Received PreKeyWhisperMessage from " +
                      recipient_id)
            key = sessionCipher.decryptPkmsg(preKeyWhisperMessage)
            # Publish new bundle after PreKey has been used
            # for building a new Session
            self.plugin.publish_bundle(self.account)
            return key
        except UntrustedIdentityException as e:
            log.info(self.account + " => Received WhisperMessage " +
                     "from Untrusted Fingerprint! => " + e.getName())

    def handleWhisperMessage(self, recipient_id, device_id, key):
        whisperMessage = WhisperMessage(serialized=key)
        sessionCipher = self.get_session_cipher(recipient_id, device_id)
        log.debug(self.account + " => Received WhisperMessage from " +
                  recipient_id)
        if self.isTrusted(sessionCipher) >= TRUSTED:
            key = sessionCipher.decryptMsg(whisperMessage)
            return key
        else:
            raise Exception("Received WhisperMessage "
                            "from Untrusted Fingerprint! => " + recipient_id)

    def checkPreKeyAmount(self):
        # Check if enough PreKeys are available
        preKeyCount = self.store.preKeyStore.getPreKeyCount()
        if preKeyCount < MIN_PREKEY_AMOUNT:
            newKeys = DEFAULT_PREKEY_AMOUNT - preKeyCount
            self.store.preKeyStore.generateNewPreKeys(newKeys)
            log.info(self.account + ' => ' + str(newKeys) +
                     ' PreKeys created')

    def cycleSignedPreKey(self, identityKeyPair):
        # Publish every SPK_CYCLE_TIME a new SignedPreKey
        # Delete all exsiting SignedPreKeys that are older
        # then SPK_ARCHIVE_TIME

        # Check if SignedPreKey exist and create if not
        if not self.store.getCurrentSignedPreKeyId():
            signedPreKey = KeyHelper.generateSignedPreKey(
                identityKeyPair, self.store.getNextSignedPreKeyId())
            self.store.storeSignedPreKey(signedPreKey.getId(), signedPreKey)
            log.debug(self.account +
                      ' => New SignedPreKey created, because none existed')

        # if SPK_CYCLE_TIME is reached, generate a new SignedPreKey
        now = int(time.time())
        timestamp = self.store.getSignedPreKeyTimestamp(
            self.store.getCurrentSignedPreKeyId())

        if int(timestamp) < now - SPK_CYCLE_TIME:
            signedPreKey = KeyHelper.generateSignedPreKey(
                identityKeyPair, self.store.getNextSignedPreKeyId())
            self.store.storeSignedPreKey(signedPreKey.getId(), signedPreKey)
            log.debug(self.account + ' => Cycled SignedPreKey')

        # Delete all SignedPreKeys that are older than SPK_ARCHIVE_TIME
        timestamp = now - SPK_ARCHIVE_TIME
        self.store.removeOldSignedPreKeys(timestamp)
