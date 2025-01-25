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

import logging
import os
import sys
from functools import partial

from packaging.version import Version as V

from gajim.common import app
from gajim.common import ged
from gajim.gtk.dialogs import ConfirmationCheckDialog
from gajim.gtk.dialogs import DialogButton
from gajim.gtk.dialogs import SimpleDialog
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from pgp.exceptions import KeyMismatch
from pgp.gtk.config import PGPConfigDialog
from pgp.gtk.key import KeyDialog
from pgp.modules.util import find_gpg

ENCRYPTION_NAME = "PGP"

log = logging.getLogger("gajim.p.pgplegacy")

ERROR = False
try:
    import gnupg
except ImportError:
    ERROR = True
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
        ERROR = True

ERROR_MSG = None
BINARY = find_gpg()
log.info("Found GPG executable: %s", BINARY)

if BINARY is None or ERROR:
    if os.name == "nt":
        ERROR_MSG = _("Please install GnuPG / Gpg4win")
    else:
        ERROR_MSG = _("Please install python-gnupg and gnupg")
else:
    from pgp.backend.python_gnupg import PGP
    from pgp.modules import pgp_legacy


class PGPPlugin(GajimPlugin):

    def init(self):
        # pylint: disable=attribute-defined-outside-init
        self.description = _("PGP encryption as per XEP-0027")
        if ERROR_MSG:
            self.activatable = False
            self.config_dialog = None
            self.available_text = ERROR_MSG
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

        self.modules = [pgp_legacy]

        self.events_handlers = {
            "pgp-not-trusted": (ged.PRECORE, self._on_not_trusted),
            "pgp-file-encryption-error": (ged.PRECORE, self._on_file_encryption_error),
        }

        encoding = "utf8" if sys.platform == "linux" else None
        self._pgp = PGP(BINARY, encoding=encoding)

    @staticmethod
    def get_pgp_module(account):
        return app.get_client(account).get_module("PGPLegacy")

    def activate(self):
        pass

    def deactivate(self):
        pass

    @staticmethod
    def activate_encryption(_chat_control):
        return True

    @staticmethod
    def _encryption_state(_chat_control, state):
        state["visible"] = True
        state["authenticated"] = True

    def _on_encryption_dialog(self, chat_control):
        account = chat_control.account
        jid = chat_control.contact.jid
        transient = app.window
        KeyDialog(self, account, jid, transient)

    def _on_send_presence(self, account, presence):
        status = presence.getStatus()
        self.get_pgp_module(account).sign_presence(presence, status)

    @staticmethod
    def _on_not_trusted(event):
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

    @staticmethod
    def _before_sendmessage(chat_control):
        account = chat_control.account
        jid = chat_control.contact.jid

        client = app.get_client(account)
        try:
            valid = client.get_module("PGPLegacy").has_valid_key_assigned(jid)
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
        elif client.get_module("PGPLegacy").get_own_key_data() is None:
            SimpleDialog(
                _("No OpenPGP key assigned"),
                _("No OpenPGP key is assigned to your account."),
            )
            chat_control.sendmessage = False

    def _encrypt_message(self, conn, event, callback):
        account = conn.name
        self.get_pgp_module(account).encrypt_message(conn, event, callback)

    def encrypt_file(self, file, account, callback):
        self.get_pgp_module(account).encrypt_file(file, callback)

    @staticmethod
    def _on_file_encryption_error(event):
        SimpleDialog(_("Error"), event.error)
