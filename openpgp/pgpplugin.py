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
from pathlib import Path

from gi.repository import Gtk
from gi.repository import Gdk
from nbxmpp.namespaces import Namespace
from nbxmpp import JID

from gajim.common import app
from gajim.common import ged
from gajim.common import configpaths
from gajim.common.const import CSSPriority

from gajim.gui.dialogs import ErrorDialog

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from openpgp.modules.util import ENCRYPTION_NAME
try:
    from openpgp.modules import openpgp
except ImportError as e:
    ERROR_MSG = str(e)
else:
    ERROR_MSG = None

log = logging.getLogger('gajim.p.openpgp')


class OpenPGPPlugin(GajimPlugin):
    def init(self):
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            self.config_dialog = None
            return

        self.events_handlers = {
            'signed-in': (ged.PRECORE, self.signed_in),
            }

        self.modules = [openpgp]

        self.encryption_name = ENCRYPTION_NAME
        self.config_dialog = None
        self.gui_extension_points = {
            'encrypt' + self.encryption_name: (self._encrypt_message, None),
            'send_message' + self.encryption_name: (
                self._before_sendmessage, None),
            'encryption_dialog' + self.encryption_name: (
                self.on_encryption_button_clicked, None),
            'encryption_state' + self.encryption_name: (
                self.encryption_state, None),
            'update_caps': (self._update_caps, None),
            }

        self.connections = {}

        self.plugin = self
        self.announced = []
        self.own_key = None
        self.pgp_instances = {}
        self._create_paths()
        self._load_css()

    def _load_css(self):
        path = Path(__file__).parent / 'gtk' / 'style.css'
        try:
            with path.open('r') as f:
                css = f.read()
        except Exception as exc:
            log.error('Error loading css: %s', exc)
            return

        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(bytes(css.encode('utf-8')))
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),
                                                     provider,
                                                     CSSPriority.DEFAULT_THEME)
        except Exception:
            log.exception('Error loading application css')

    @staticmethod
    def _create_paths():
        keyring_path = Path(configpaths.get('MY_DATA')) / 'openpgp'
        if not keyring_path.exists():
            keyring_path.mkdir()

    def signed_in(self, event):
        account = event.conn.name
        con = app.connections[account]
        if con.get_module('OpenPGP').secret_key_available:
            log.info('%s => Publish keylist and public key after sign in',
                     account)
            con.get_module('OpenPGP').request_keylist()
            con.get_module('OpenPGP').set_public_key()

    def activate(self):
        for account in app.connections:
            con = app.connections[account]
            con.get_module('Caps').update_caps()
            if app.account_is_connected(account):
                if con.get_module('OpenPGP').secret_key_available:
                    log.info('%s => Publish keylist and public key '
                             'after plugin activation', account)
                    con.get_module('OpenPGP').request_keylist()
                    con.get_module('OpenPGP').set_public_key()

    def deactivate(self):
        pass

    @staticmethod
    def _update_caps(_account, features):
        features.append('%s+notify' % Namespace.OPENPGP_PK)

    def activate_encryption(self, chat_control):
        account = chat_control.account
        jid = chat_control.contact.jid
        con = app.connections[account]
        if con.get_module('OpenPGP').secret_key_available:
            keys = app.connections[account].get_module('OpenPGP').get_keys(
                jid, only_trusted=False)
            if not keys:
                con.get_module('OpenPGP').request_keylist(JID.from_string(jid))
            return True

        from openpgp.gtk.wizard import KeyWizard
        KeyWizard(self, account, chat_control)
        return False

    @staticmethod
    def encryption_state(_chat_control, state):
        state['authenticated'] = True
        state['visible'] = True

    @staticmethod
    def on_encryption_button_clicked(chat_control):
        account = chat_control.account
        jid = chat_control.contact.jid

        from openpgp.gtk.key import KeyDialog
        KeyDialog(account, jid, app.window)

    def _before_sendmessage(self, chat_control):
        account = chat_control.account
        jid = chat_control.contact.jid
        con = app.connections[account]

        if not con.get_module('OpenPGP').secret_key_available:
            from openpgp.gtk.wizard import KeyWizard
            KeyWizard(self, account, chat_control)
            return

        keys = con.get_module('OpenPGP').get_keys(jid)
        if not keys:
            ErrorDialog(
                _('Not Trusted'),
                _('There was no trusted and active key found'))
            chat_control.sendmessage = False

    @staticmethod
    def _encrypt_message(con, obj, callback):
        if not con.get_module('OpenPGP').secret_key_available:
            return
        con.get_module('OpenPGP').encrypt_message(obj, callback)
