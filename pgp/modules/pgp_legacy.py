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

from typing import Any

import os
import time
from collections.abc import Callable

import nbxmpp
from nbxmpp.client import Client as nbxmppClient
from nbxmpp.namespaces import Namespace
from nbxmpp.protocol import Message
from nbxmpp.protocol import Presence
from nbxmpp.structs import EncryptionData
from nbxmpp.structs import MessageProperties
from nbxmpp.structs import PresenceProperties
from nbxmpp.structs import StanzaHandler

from gajim.common import app
from gajim.common.client import Client
from gajim.common.const import Trust
from gajim.common.events import MessageNotSent
from gajim.common.modules.base import BaseModule
from gajim.common.structs import OutgoingMessage
from gajim.plugins.plugins_i18n import _

from pgp.backend.python_gnupg import PGP
from pgp.backend.store import KeyStore
from pgp.exceptions import KeyMismatch
from pgp.exceptions import NoKeyIdFound
from pgp.exceptions import SignError
from pgp.modules.events import PGPNotTrusted
from pgp.modules.util import prepare_stanza

# Module name
name = "PGPLegacy"
ENCRYPTION_NAME = "PGP"

ALLOWED_TAGS = [
    ("request", Namespace.RECEIPTS),
    ("active", Namespace.CHATSTATES),
    ("gone", Namespace.CHATSTATES),
    ("inactive", Namespace.CHATSTATES),
    ("paused", Namespace.CHATSTATES),
    ("composing", Namespace.CHATSTATES),
    ("markable", Namespace.CHATMARKERS),
    ("no-store", Namespace.HINTS),
    ("store", Namespace.HINTS),
    ("no-copy", Namespace.HINTS),
    ("no-permanent-store", Namespace.HINTS),
    ("replace", Namespace.CORRECT),
    ("thread", None),
    ("reply", Namespace.REPLY),
    ("fallback", Namespace.FALLBACK),
    ("origin-id", Namespace.SID),
    ("reactions", Namespace.REACTIONS),
]


class PGPLegacy(BaseModule):
    def __init__(self, client: Client) -> None:
        BaseModule.__init__(self, client, plugin=True)

        self.handlers = [
            StanzaHandler(
                name="message",
                callback=self._message_received,
                ns=Namespace.ENCRYPTED,
                priority=9,
            ),
            StanzaHandler(
                name="presence",
                callback=self._on_presence_received,
                ns=Namespace.SIGNED,
                priority=48,
            ),
        ]

        self.own_jid = self._client.get_own_jid()

        self._pgp = PGP()
        self._store = KeyStore(
            self._account, self.own_jid, self._log, self._pgp.list_keys
        )
        self._always_trust: list[str] = []
        self._presence_fingerprint_store: dict[str, str] = {}

    @property
    def pgp_backend(self) -> PGP:
        return self._pgp

    def set_own_key_data(self, keydata: tuple[str, str] | None) -> None:
        return self._store.set_own_key_data(keydata)

    def get_own_key_data(self) -> dict[str, str] | None:
        return self._store.get_own_key_data()

    def set_contact_key_data(self, jid: str, key_data: tuple[str, str] | None) -> None:
        return self._store.set_contact_key_data(jid, key_data)

    def get_contact_key_data(self, jid: str) -> dict[str, str] | None:
        return self._store.get_contact_key_data(jid)

    def has_valid_key_assigned(self, jid: str) -> bool:
        key_data = self.get_contact_key_data(jid)
        if key_data is None:
            return False
        key_id = key_data["key_id"]

        announced_fingerprint = self._presence_fingerprint_store.get(jid)
        if announced_fingerprint is None:
            return True

        if announced_fingerprint == key_id:
            return True

        raise KeyMismatch(announced_fingerprint)

    def _on_presence_received(
        self, _client: nbxmppClient, _stanza: Presence, properties: PresenceProperties
    ):
        if properties.signed is None:
            return

        assert properties.jid is not None
        jid = properties.jid.bare

        fingerprint = self._pgp.verify(properties.status, properties.signed)
        if fingerprint is None:
            self._log.info(
                "Presence from %s was signed but no corresponding key was found", jid
            )
            return

        self._presence_fingerprint_store[jid] = fingerprint
        self._log.info(
            "Presence from %s was verified successfully, fingerprint: %s",
            jid,
            fingerprint,
        )

        key_data = self.get_contact_key_data(jid)
        if key_data is None:
            self._log.info("No key assigned for contact: %s", jid)
            return

        if key_data["key_id"] != fingerprint:
            self._log.warning(
                "Fingerprint mismatch, "
                "Presence was signed with fingerprint: %s, "
                "Assigned key fingerprint: %s",
                fingerprint,
                key_data["key_id"],
            )
            return

    def _message_received(
        self, _client: nbxmppClient, stanza: Message, properties: MessageProperties
    ) -> None:
        if not properties.is_pgp_legacy or properties.from_muc:
            return

        remote_jid = properties.remote_jid
        self._log.info("Message received from: %s", remote_jid)

        assert properties.pgp_legacy is not None
        payload = self._pgp.decrypt(properties.pgp_legacy)
        prepare_stanza(stanza, payload)

        properties.encrypted = EncryptionData(
            protocol=ENCRYPTION_NAME, key="Unknown", trust=Trust.UNDECIDED
        )

    def encrypt_message(
        self,
        client: Client,
        message: OutgoingMessage,
        callback: Callable[[OutgoingMessage], None],
    ) -> None:
        if not message.get_text():
            callback(message)
            return

        to_jid = str(message.contact.jid)
        try:
            key_id, own_key_id = self._get_key_ids(to_jid)
        except NoKeyIdFound as error:
            self._log.warning(error)
            return

        always_trust = key_id in self._always_trust
        self._encrypt(client, message, [key_id, own_key_id], callback, always_trust)

    def _encrypt(
        self,
        client: Client,
        message: OutgoingMessage,
        recipients: list[str],
        callback: Callable[[OutgoingMessage], None],
        always_trust: bool,
    ) -> None:
        text = message.get_text()
        assert text is not None

        result = self._pgp.encrypt(text, recipients, always_trust)
        encrypted_payload, error = result
        if error:
            self._handle_encrypt_error(client, error, message, recipients, callback)
            return

        self._cleanup_stanza(message)
        self._create_pgp_legacy_message(message.get_stanza(), encrypted_payload)

        message.set_encryption(
            EncryptionData(
                protocol=ENCRYPTION_NAME,
                key="Unknown",
                trust=Trust.VERIFIED,
            )
        )

        callback(message)

    def _handle_encrypt_error(
        self,
        client: Client,
        error: str,
        message: OutgoingMessage,
        recipients: list[str],
        callback: Callable[[OutgoingMessage], None],
    ) -> None:
        if error.startswith("NOT_TRUSTED"):

            def on_yes(checked: bool) -> None:
                if checked:
                    self._always_trust.append(recipients[0])
                self._encrypt(client, message, recipients, callback, True)

            def on_no() -> None:
                self._raise_message_not_sent(client, message, error)

            app.ged.raise_event(PGPNotTrusted(on_yes=on_yes, on_no=on_no))

        else:
            self._raise_message_not_sent(client, message, error)

    @staticmethod
    def _raise_message_not_sent(
        client: Client, message: OutgoingMessage, error: str
    ) -> None:
        text = message.get_text()
        assert text is not None

        app.ged.raise_event(
            MessageNotSent(
                client=client,
                jid=str(message.contact.jid),
                message=text,
                error=_("Encryption error: %s") % error,
                time=time.time(),
            )
        )

    def _create_pgp_legacy_message(self, stanza: Message, payload: str) -> None:
        stanza.setBody(self._get_info_message())
        stanza.setTag("x", namespace=Namespace.ENCRYPTED).setData(payload)
        eme_node = nbxmpp.Node(
            "encryption",
            attrs={"xmlns": Namespace.EME, "namespace": Namespace.ENCRYPTED},
        )
        stanza.addChild(node=eme_node)

    def sign_presence(self, presence: nbxmpp.Presence, status: str) -> None:
        key_data = self.get_own_key_data()
        if key_data is None:
            self._log.warning("No own key id found, can’t sign presence")
            return

        try:
            result = self._pgp.sign(status, key_data["key_id"])
        except SignError as error:
            self._log.warning("Sign Error: %s", error)
            return
        # self._log.debug(self._pgp.sign.cache_info())
        self._log.info("Presence signed")
        presence.setTag(Namespace.SIGNED + " x").setData(result)

    @staticmethod
    def _get_info_message() -> str:
        msg = "[This message is *encrypted* (See :XEP:`27`)]"
        lang = os.getenv("LANG")
        if lang is not None and not lang.startswith("en"):
            # we're not english: one in locale and one en
            msg = _("[This message is *encrypted* (See :XEP:`27`)]") + " (" + msg + ")"
        return msg

    def _get_key_ids(self, jid: str) -> tuple[str, str]:
        key_data = self.get_contact_key_data(jid)
        if key_data is None:
            raise NoKeyIdFound("No key id found for %s" % jid)
        key_id = key_data["key_id"]

        own_key_data = self.get_own_key_data()
        if own_key_data is None:
            raise NoKeyIdFound("Own key id not found")
        own_key_id = own_key_data["key_id"]
        return key_id, own_key_id

    @staticmethod
    def _cleanup_stanza(message: OutgoingMessage) -> None:
        """We make sure only allowed tags are in the stanza"""
        original_stanza = message.get_stanza()
        m_type = original_stanza.getType()
        assert m_type in ("chat", "groupchat", "normal")
        stanza = nbxmpp.Message(to=original_stanza.getTo(), typ=m_type)

        if message_id := original_stanza.getID():
            stanza.setID(message_id)

        if thread := original_stanza.getThread():
            stanza.setThread(thread)

        for tag, ns in ALLOWED_TAGS:
            node = original_stanza.getTag(tag, namespace=ns)
            if node:
                stanza.addChild(node=node)
        message.set_stanza(stanza)


def get_instance(*args: Any, **kwargs: Any) -> tuple[PGPLegacy, str]:
    return PGPLegacy(*args, **kwargs), "PGPLegacy"
