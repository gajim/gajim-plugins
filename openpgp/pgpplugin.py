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

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING

import logging
from collections.abc import Callable
from pathlib import Path

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk
from nbxmpp import JID
from nbxmpp.namespaces import Namespace

from gajim.common import app
from gajim.common import configpaths
from gajim.common import ged
from gajim.common.client import Client
from gajim.common.const import CSSPriority
from gajim.common.events import SignedIn
from gajim.common.structs import OutgoingMessage
from gajim.gtk.alert import InformationAlertDialog
from gajim.gtk.control import ChatControl
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from openpgp.modules.util import ENCRYPTION_NAME

try:
    from openpgp.modules import openpgp
except (ImportError, OSError) as e:
    error_msg = str(e)
else:
    error_msg = None

if TYPE_CHECKING:
    from openpgp.modules.openpgp import OpenPGP

log = logging.getLogger("gajim.p.openpgp")


class OpenPGPPlugin(GajimPlugin):
    def init(self):
        if error_msg:
            self.activatable = False
            self.available_text = error_msg
            self.config_dialog = None
            return

        self.events_handlers = {
            "signed-in": (ged.PRECORE, self._on_signed_in),
        }

        self.modules = [openpgp]  # type: ignore

        self.encryption_name = ENCRYPTION_NAME
        self.config_dialog = None
        self.gui_extension_points = {
            "encrypt" + self.encryption_name: (self._encrypt_message, None),
            "send_message" + self.encryption_name: (self._before_sendmessage, None),
            "encryption_dialog" + self.encryption_name: (
                self._on_encryption_button_clicked,
                None,
            ),
            "encryption_state" + self.encryption_name: (
                self._get_encryption_state,
                None,
            ),
            "update_caps": (self._update_caps, None),
        }

        self._create_paths()
        self._load_css()

    @staticmethod
    def get_openpgp_module(account: str) -> OpenPGP:
        return app.get_client(account).get_module("OpenPGP")  # pyright: ignore

    def _load_css(self) -> None:
        path = Path(__file__).parent / "gtk" / "style.css"
        try:
            with path.open("r") as f:
                css = f.read()
        except Exception as exc:
            log.error("Error loading css: %s", exc)
            return

        display = Gdk.Display.get_default()
        assert display is not None

        try:
            provider = Gtk.CssProvider()
            provider.load_from_bytes(GLib.Bytes.new(css.encode("utf-8")))
            Gtk.StyleContext.add_provider_for_display(
                display, provider, CSSPriority.DEFAULT_THEME
            )
        except Exception:
            log.exception("Error loading application css")

    @staticmethod
    def _create_paths() -> None:
        keyring_path = Path(configpaths.get("MY_DATA")) / "openpgp"
        if not keyring_path.exists():
            keyring_path.mkdir()

    def _on_signed_in(self, event: SignedIn) -> None:
        openpgp = self.get_openpgp_module(event.account)
        if openpgp.secret_key_available:
            log.info(
                "%s => Publish keylist and public key after sign in", event.account
            )
            openpgp.request_keylist()
            openpgp.set_public_key()

    def activate(self) -> None:
        for account in app.settings.get_active_accounts():
            client = app.get_client(account)
            client.get_module("Caps").update_caps()
            if app.account_is_connected(account):
                openpgp = self.get_openpgp_module(account)
                if openpgp.secret_key_available:
                    log.info(
                        "%s => Publish keylist and public key after plugin activation",
                        account,
                    )
                    openpgp.request_keylist()
                    openpgp.set_public_key()

    def deactivate(self) -> None:
        pass

    def activate_encryption(self, chat_control: ChatControl) -> bool:
        account = chat_control.account
        assert chat_control.contact is not None
        jid = chat_control.contact.jid
        openpgp = self.get_openpgp_module(account)
        if openpgp.secret_key_available:
            keys = openpgp.get_keys(jid, only_trusted=False)
            if not keys:
                openpgp.request_keylist(JID.from_string(jid))
            return True

        from openpgp.gtk.wizard import KeyWizard

        KeyWizard(self, account, chat_control)
        return False

    @staticmethod
    def _update_caps(_account: str, features: list[str]) -> None:
        features.append("%s+notify" % Namespace.OPENPGP_PK)

    @staticmethod
    def _get_encryption_state(
        _chat_control: ChatControl, state: dict[str, Any]
    ) -> None:
        state["authenticated"] = True
        state["visible"] = True

    @staticmethod
    def _on_encryption_button_clicked(chat_control: ChatControl) -> None:
        account = chat_control.account
        assert chat_control.contact is not None
        jid = chat_control.contact.jid

        from openpgp.gtk.key import KeyDialog

        KeyDialog(account, jid, app.window)

    def _before_sendmessage(self, chat_control: ChatControl) -> None:
        account = chat_control.account
        assert chat_control.contact is not None
        jid = chat_control.contact.jid
        openpgp = self.get_openpgp_module(account)

        if not openpgp.secret_key_available:
            from openpgp.gtk.wizard import KeyWizard

            KeyWizard(self, account, chat_control)
            return

        keys = openpgp.get_keys(jid)
        if not keys:
            InformationAlertDialog(
                _("Not Trusted"), _("There was no trusted and active key found")
            )
            chat_control.sendmessage = False

    def _encrypt_message(
        self,
        client: Client,
        message: OutgoingMessage,
        callback: Callable[[OutgoingMessage], None],
    ) -> None:
        openpgp = self.get_openpgp_module(client.account)
        if not openpgp.secret_key_available:
            return
        openpgp.encrypt_message(message, callback)
