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
import sys
import time
from pathlib import Path

from nbxmpp import Node
from nbxmpp import StanzaMalformed
from nbxmpp.errors import MalformedStanzaError
from nbxmpp.errors import StanzaError
from nbxmpp.exceptions import StanzaDecrypted
from nbxmpp.modules.openpgp import create_message_stanza
from nbxmpp.modules.openpgp import create_signcrypt_node
from nbxmpp.modules.openpgp import parse_signcrypt
from nbxmpp.modules.openpgp import PGPKeyMetadata
from nbxmpp.namespaces import Namespace
from nbxmpp.structs import EncryptionData
from nbxmpp.structs import MessageProperties
from nbxmpp.structs import StanzaHandler

from gajim.common import app
from gajim.common import configpaths
from gajim.common.events import MessageNotSent
from gajim.common.modules.base import BaseModule
from gajim.common.modules.util import event_node
from gajim.common.structs import OutgoingMessage

from openpgp.backend.sql import Storage
from openpgp.modules.key_store import PGPContacts
from openpgp.modules.util import DecryptionFailed
from openpgp.modules.util import ENCRYPTION_NAME
from openpgp.modules.util import Key
from openpgp.modules.util import NOT_ENCRYPTED_TAGS
from openpgp.modules.util import prepare_stanza
from openpgp.modules.util import Trust

if sys.platform == "win32":
    from openpgp.backend.pygpg import PythonGnuPG as PGPBackend
else:
    from openpgp.backend.gpgme import GPGME as PGPBackend


log = logging.getLogger("gajim.p.openpgp")


# Module name
name = ENCRYPTION_NAME
zeroconf = False


class OpenPGP(BaseModule):

    _nbxmpp_extends = "OpenPGP"
    _nbxmpp_methods = [
        "set_keylist",
        "request_keylist",
        "set_public_key",
        "request_public_key",
        "set_secret_key",
        "request_secret_key",
    ]

    def __init__(self, client):
        BaseModule.__init__(self, client)

        self.handlers = [
            StanzaHandler(
                name="message",
                callback=self.decrypt_message,
                ns=Namespace.OPENPGP,
                priority=9,
            ),
        ]

        self._register_pubsub_handler(self._keylist_notification_received)

        self.own_jid = self._client.get_own_jid()

        own_bare_jid = self.own_jid.bare
        path = Path(configpaths.get("MY_DATA")) / "openpgp" / own_bare_jid
        if not path.exists():
            path.mkdir(mode=0o700, parents=True)

        self._pgp = PGPBackend(own_bare_jid, path)
        self._storage = Storage(path)
        self._contacts = PGPContacts(self._pgp, self._storage)
        self._fingerprint, self._date = self.get_own_key_details()
        log.info("Own Fingerprint at start: %s", self._fingerprint)

    @property
    def secret_key_available(self):
        return self._fingerprint is not None

    def get_own_key_details(self):
        self._fingerprint, self._date = self._pgp.get_own_key_details()
        return self._fingerprint, self._date

    def generate_key(self):
        self._pgp.generate_key()

    def set_public_key(self):
        log.info("%s => Publish public key", self._account)
        key = self._pgp.export_key(self._fingerprint)
        self._nbxmpp("OpenPGP").set_public_key(key, self._fingerprint, self._date)

    def request_public_key(self, jid, fingerprint):
        log.info("%s => Request public key %s - %s", self._account, fingerprint, jid)
        self._nbxmpp("OpenPGP").request_public_key(
            jid, fingerprint, callback=self._public_key_received, user_data=fingerprint
        )

    def _public_key_received(self, task):
        fingerprint = task.get_user_data()
        try:
            result = task.finish()
        except (StanzaError, MalformedStanzaError) as error:
            log.error("%s => Public Key not found: %s", self._account, error)
            return

        imported_key = self._pgp.import_key(result.key, result.jid)
        if imported_key is not None:
            self._contacts.set_public_key(result.jid, fingerprint)

    def set_keylist(self, keylist=None):
        if keylist is None:
            keylist = [PGPKeyMetadata(None, self._fingerprint, self._date)]
        log.info("%s => Publish keylist", self._account)
        self._nbxmpp("OpenPGP").set_keylist(keylist)

    @event_node(Namespace.OPENPGP_PK)
    def _keylist_notification_received(self, _con, _stanza, properties):
        if properties.pubsub_event.retracted:
            return

        keylist = properties.pubsub_event.data or []

        self._process_keylist(keylist, properties.jid)

    def request_keylist(self, jid=None):
        if jid is None:
            jid = self.own_jid
        log.info("%s => Fetch keylist %s", self._account, jid)

        self._nbxmpp("OpenPGP").request_keylist(
            jid, callback=self._keylist_received, user_data=jid
        )

    def _keylist_received(self, task):
        jid = task.get_user_data()
        try:
            keylist = task.finish()
        except (StanzaError, MalformedStanzaError) as error:
            log.error("%s => Keylist query failed: %s", self._account, error)
            if self.own_jid.bare_match(jid) and self._fingerprint is not None:
                self.set_keylist()
            return

        log.info("Keylist received from %s", jid)
        self._process_keylist(keylist, jid)

    def _process_keylist(self, keylist, from_jid):
        if not keylist:
            log.warning("%s => Empty keylist received from %s", self._account, from_jid)
            self._contacts.process_keylist(self.own_jid, keylist)
            if self.own_jid.bare_match(from_jid) and self._fingerprint is not None:
                self.set_keylist()
            return

        if self.own_jid.bare_match(from_jid):
            log.info("Received own keylist")
            for key in keylist:
                log.info(key.fingerprint)
            for key in keylist:
                # Check if own fingerprint is published
                if key.fingerprint == self._fingerprint:
                    log.info("Own key found in keys list")
                    return
            log.info("Own key not published")
            if self._fingerprint is not None:
                keylist.append(Key(self._fingerprint, self._date))
                self.set_keylist(keylist)
            return

        missing_pub_keys = self._contacts.process_keylist(from_jid, keylist)

        for key in keylist:
            log.info(key.fingerprint)

        for fingerprint in missing_pub_keys:
            self.request_public_key(from_jid, fingerprint)

    def decrypt_message(self, _con, stanza, properties: MessageProperties):
        if not properties.is_openpgp:
            return

        remote_jid = properties.remote_jid
        assert remote_jid is not None

        try:
            payload, fingerprint = self._pgp.decrypt(properties.openpgp)
        except DecryptionFailed as error:
            log.warning(error)
            return

        signcrypt = Node(node=payload)

        try:
            payload, recipients, _timestamp = parse_signcrypt(signcrypt)
        except StanzaMalformed as error:
            log.warning("Decryption failed: %s", error)
            log.warning(payload)
            return

        if not any(map(self.own_jid.bare_match, recipients)):
            log.warning("to attr not valid")
            log.warning(signcrypt)
            return

        keys = self._contacts.get_keys(remote_jid)
        fingerprints = [key.fingerprint for key in keys]
        if fingerprint not in fingerprints:
            log.warning("Invalid fingerprint on message: %s", fingerprint)
            log.warning("Expected: %s", fingerprints)
            return

        log.info("Received OpenPGP message from: %s", properties.jid)
        prepare_stanza(stanza, payload)

        trust = self._contacts.get_trust(remote_jid, fingerprint)

        properties.encrypted = EncryptionData(
            protocol=ENCRYPTION_NAME, key=fingerprint, trust=trust
        )

        raise StanzaDecrypted

    def encrypt_message(self, message: OutgoingMessage, callback):
        remote_jid = message.contact.jid

        keys = self._contacts.get_keys(remote_jid)
        if not keys:
            log.error("Dropping stanza to %s, because we have no key", remote_jid)
            return

        keys += self._contacts.get_keys(self.own_jid)
        keys += [Key(self._fingerprint, None)]

        payload = create_signcrypt_node(
            message.get_stanza(), [remote_jid], NOT_ENCRYPTED_TAGS
        )

        encrypted_payload, error = self._pgp.encrypt(payload, keys)
        if error:
            log.error("Error: %s", error)
            text = message.get_text(with_fallback=False) or ""
            app.ged.raise_event(
                MessageNotSent(
                    client=self._client,
                    jid=str(remote_jid),
                    message=text,
                    error=error,
                    time=time.time(),
                )
            )
            return

        create_message_stanza(
            message.get_stanza(), encrypted_payload, bool(message.get_text())
        )

        message.set_encryption(
            EncryptionData(
                protocol=ENCRYPTION_NAME, key="Unknown", trust=Trust.VERIFIED
            )
        )

        callback(message)

    @staticmethod
    def print_msg_to_log(stanza):
        """Prints a stanza in a fancy way to the log"""
        log.debug("-" * 15)
        stanzastr = "\n" + stanza.__str__(fancy=True)
        stanzastr = stanzastr[0:-1]
        log.debug(stanzastr)
        log.debug("-" * 15)

    def get_keys(self, jid=None, only_trusted=True):
        if jid is None:
            jid = self.own_jid
        return self._contacts.get_keys(jid, only_trusted=only_trusted)

    def clear_fingerprints(self):
        self.set_keylist()

    def cleanup(self):
        self._storage.cleanup()
        self._pgp = None
        self._contacts = None


def get_instance(*args, **kwargs):
    return OpenPGP(*args, **kwargs), "OpenPGP"
