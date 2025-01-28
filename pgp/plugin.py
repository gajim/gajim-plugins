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

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING

import logging
import os
from collections.abc import Callable
from functools import partial

import nbxmpp
from packaging.version import Version as V

from gajim.common import app
from gajim.common import ged
from gajim.common.client import Client
from gajim.common.modules.httpupload import HTTPFileTransfer
from gajim.common.structs import OutgoingMessage
from gajim.gtk.control import ChatControl
from gajim.gtk.dialogs import ConfirmationCheckDialog
from gajim.gtk.dialogs import DialogButton
from gajim.gtk.dialogs import SimpleDialog
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from pgp.exceptions import KeyMismatch
from pgp.gtk.config import PGPConfigDialog
from pgp.gtk.key import KeyDialog
from pgp.modules.events import PGPFileEncryptionError
from pgp.modules.events import PGPNotTrusted
from pgp.modules.util import find_gpg

if TYPE_CHECKING:
    from pgp.modules.pgp_legacy import PGPLegacy


ENCRYPTION_NAME = "PGP"

log = logging.getLogger("gajim.p.pgplegacy")

error = False
try:
    import gnupg
except ImportError:
    error = True
else:
    # We need https://pypi.python.org/pypi/python-gnupg
    # but https://pypi.python.org/pypi/gnupg shares the same package name.
    # It cannot be used as a drop-in replacement.
    # We test with a version check if python-gnupg is installed as it is
    # on a much lower version number than gnupg
    # Also we need at least python-gnupg 0.3.8
    v_gnupg = gnupg.__version__
    if V(v_gnupg) < V("0.3.8") or V(v_gnupg) > V("1.0.0"):
        log.error("We need python-gnupg >= 0.3.8")
        error = True

error_msg = None
BINARY = find_gpg()
log.info("Found GPG executable: %s", BINARY)

if BINARY is None or error:
    if os.name == "nt":
        error_msg = _("Please install GnuPG / Gpg4win")
    else:
        error_msg = _("Please install python-gnupg and gnupg")


class PGPPlugin(GajimPlugin):

    def init(self):
        self.description = _("PGP encryption as per XEP-0027")
        if error_msg:
            self.activatable = False
            self.config_dialog = None
            self.available_text = error_msg
            return

        self.config_dialog = partial(PGPConfigDialog, self)
        self.encryption_name = ENCRYPTION_NAME
        self.allow_zeroconf = True
        self.gui_extension_points = {
            "encrypt" + ENCRYPTION_NAME: (self._encrypt_message, None),
            "send_message" + ENCRYPTION_NAME: (self._before_sendmessage, None),
            "encryption_dialog" + ENCRYPTION_NAME: (self._on_encryption_dialog, None),
            "encryption_state" + ENCRYPTION_NAME: (self._encryption_state, None),
            "send-presence": (self._on_send_presence, None),
        }

        from pgp.modules import pgp_legacy

        self.modules = [pgp_legacy]

        self.events_handlers = {
            "pgp-not-trusted": (ged.PRECORE, self._on_not_trusted),
            "pgp-file-encryption-error": (ged.PRECORE, self._on_file_encryption_error),
        }

    @staticmethod
    def get_pgp_module(account: str) -> PGPLegacy:
        return app.get_client(account).get_module("PGPLegacy")  # pyright: ignore

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def activate_encryption(self, chat_control: ChatControl) -> bool:
        return True

    @staticmethod
    def _encryption_state(_chat_control: ChatControl, state: dict[str, Any]) -> None:
        state["visible"] = True
        state["authenticated"] = True

    def _on_encryption_dialog(self, chat_control: ChatControl):
        account = chat_control.account
        jid = chat_control.contact.jid
        transient = app.window
        KeyDialog(self, account, jid, transient)

    def _on_send_presence(self, account: str, presence: nbxmpp.Presence) -> None:
        status = presence.getStatus()
        self.get_pgp_module(account).sign_presence(presence, status)

    @staticmethod
    def _on_not_trusted(event: PGPNotTrusted) -> None:
        ConfirmationCheckDialog(
            _("Untrusted PGP key"),
            _(
                "The PGP key used to encrypt this chat is not "
                "trusted. Do you really want to encrypt this "
                "message?"
            ),
            _("_Do not ask me again"),
            [
                DialogButton.make("Cancel", text=_("_No"), callback=event.on_no),
                DialogButton.make(
                    "OK", text=_("_Encrypt Anyway"), callback=event.on_yes
                ),
            ],
        ).show()

    def _before_sendmessage(self, chat_control: ChatControl) -> None:
        account = chat_control.account
        jid = str(chat_control.contact.jid)

        pgp = self.get_pgp_module(account)

        try:
            valid = pgp.has_valid_key_assigned(jid)
        except KeyMismatch as announced_key_id:
            SimpleDialog(
                _("PGP Key mismatch"),
                _(
                    "The contact's key (%s) <b>does not match</b> the key "
                    "assigned in Gajim."
                )
                % announced_key_id,
            )
            chat_control.sendmessage = False
            return

        if not valid:
            SimpleDialog(
                _("No OpenPGP key assigned"),
                _("No OpenPGP key is assigned to this contact."),
            )
            chat_control.sendmessage = False
        elif pgp.get_own_key_data() is None:
            SimpleDialog(
                _("No OpenPGP key assigned"),
                _("No OpenPGP key is assigned to your account."),
            )
            chat_control.sendmessage = False

    def _encrypt_message(
        self,
        client: Client,
        event: OutgoingMessage,
        callback: Callable[[OutgoingMessage], None],
    ):
        self.get_pgp_module(client.name).encrypt_message(client, event, callback)

    def encrypt_file(
        self,
        transfer: HTTPFileTransfer,
        account: str,
        callback: Callable[[HTTPFileTransfer], None],
    ):
        self.get_pgp_module(account).encrypt_file(transfer, callback)

    @staticmethod
    def _on_file_encryption_error(event: PGPFileEncryptionError) -> None:
        SimpleDialog(_("Error"), event.error)
