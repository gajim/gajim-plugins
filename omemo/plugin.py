# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
# Copyright (C) 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright (C) 2015 Daniel Gultsch <daniel@cgultsch.de>
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
import binascii
import threading
from enum import IntEnum, unique
from pathlib import Path

from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Gdk

from nbxmpp.namespaces import Namespace

from gajim.common import app, ged

from gajim.gui.dialogs import ErrorDialog

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

AXOLOTL_MISSING = 'You are missing Python3-Axolotl or use an outdated version'
PROTOBUF_MISSING = "OMEMO can't import Google Protobuf, you can find help in " \
                   "the GitLab Wiki"
ERROR_MSG = ''


log = logging.getLogger('gajim.p.omemo')
if log.getEffectiveLevel() == logging.DEBUG:
    log_axolotl = logging.getLogger('axolotl')
    log_axolotl.setLevel(logging.DEBUG)
    log_axolotl.addHandler(logging.StreamHandler())
    log_axolotl.propagate = False

try:
    import google.protobuf
except Exception as error:
    log.error(error)
    ERROR_MSG = PROTOBUF_MISSING

try:
    import axolotl
except Exception as error:
    log.error(error)
    ERROR_MSG = AXOLOTL_MISSING

if not ERROR_MSG:
    try:
        from omemo.modules import omemo
        from omemo.gtk.key import KeyDialog
        from omemo.gtk.config import OMEMOConfigDialog
        from omemo.backend.aes import aes_encrypt_file
    except Exception as error:
        log.error(error)
        ERROR_MSG = 'Error: %s' % error


@unique
class UserMessages(IntEnum):
    QUERY_DEVICES = 0
    NO_FINGERPRINTS = 1
    UNDECIDED_FINGERPRINTS = 2


class OmemoPlugin(GajimPlugin):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            self.config_dialog = None
            return
        self.encryption_name = 'OMEMO'
        self.allow_groupchat = True
        self.events_handlers = {
            'omemo-new-fingerprint': (ged.PRECORE, self._on_new_fingerprints),
            'signed-in': (ged.PRECORE, self._on_signed_in),
            'muc-disco-update': (ged.GUI1, self._on_muc_disco_update),
            'room-joined': (ged.GUI1, self._on_muc_joined),
        }
        self.modules = [omemo]
        self.config_dialog = OMEMOConfigDialog(self)
        self.gui_extension_points = {
            'encrypt' + self.encryption_name: (self._encrypt_message, None),
            'gc_encrypt' + self.encryption_name: (
                self._muc_encrypt_message, None),
            'send_message' + self.encryption_name: (
                self._before_sendmessage, None),
            'encryption_dialog' + self.encryption_name: (
                self._on_encryption_button_clicked, None),
            'encryption_state' + self.encryption_name: (
                self._encryption_state, None),
            'update_caps': (self._update_caps, None)}

        self.disabled_accounts = []
        self._windows = {}

        self.config_default_values = {
            'DISABLED_ACCOUNTS': ([], ''),
            'BLIND_TRUST': (True, ''),
            'SHOW_HELP_FINGERPRINTS': (True, ''),
        }

        for account in self.config['DISABLED_ACCOUNTS']:
            self.disabled_accounts.append(account)

        self._load_css()

    def _is_enabled_account(self, account):
        if account in self.disabled_accounts:
            return False
        if account == 'Local':
            return False
        return True

    @staticmethod
    def get_omemo(account):
        return app.connections[account].get_module('OMEMO')

    @staticmethod
    def _load_css():
        path = Path(__file__).parent / 'gtk' / 'style.css'
        try:
            with path.open("r") as file:
                css = file.read()
        except Exception as exc:
            log.error('Error loading css: %s', exc)
            return

        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(bytes(css.encode('utf-8')))
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),
                                                     provider, 610)
        except Exception:
            log.exception('Error loading application css')

    def activate(self):
        """
        Method called when the Plugin is activated in the PluginManager
        """
        for account in app.connections:
            if not self._is_enabled_account(account):
                continue
            self.get_omemo(account).activate()

    def deactivate(self):
        """
        Method called when the Plugin is deactivated in the PluginManager
        """
        for account in app.connections:
            if not self._is_enabled_account(account):
                continue
            self.get_omemo(account).deactivate()

    def _on_signed_in(self, event):
        account = event.conn.name
        if not self._is_enabled_account(account):
            return
        self.get_omemo(account).on_signed_in()

    def _on_muc_disco_update(self, event):
        if not self._is_enabled_account(event.account):
            return
        self.get_omemo(event.account).on_muc_disco_update(event)

    def _on_muc_joined(self, event):
        if not self._is_enabled_account(event.account):
            return
        self.get_omemo(event.account).on_muc_joined(event)

    def _update_caps(self, account, features):
        if not self._is_enabled_account(account):
            return
        features.append('%s+notify' % Namespace.OMEMO_TEMP_DL)

    @staticmethod
    def activate_encryption(chat_control):
        return True

    def _muc_encrypt_message(self, conn, obj, callback):
        account = conn.name
        if not self._is_enabled_account(account):
            return
        self.get_omemo(account).encrypt_message(conn, obj, callback, True)

    def _encrypt_message(self, conn, obj, callback):
        account = conn.name
        if not self._is_enabled_account(account):
            return
        self.get_omemo(account).encrypt_message(conn, obj, callback, False)

    def encrypt_file(self, file, _account, callback):
        thread = threading.Thread(target=self._encrypt_file_thread,
                                  args=(file, callback))
        thread.daemon = True
        thread.start()

    @staticmethod
    def _encrypt_file_thread(file, callback, *args, **kwargs):
        result = aes_encrypt_file(file.get_data())
        file.size = len(result.payload)
        fragment = binascii.hexlify(result.iv + result.key).decode()
        file.set_uri_transform_func(
            lambda uri: 'aesgcm%s#%s' % (uri[5:], fragment))
        file.set_encrypted_data(result.payload)
        GLib.idle_add(callback, file)

    @staticmethod
    def _encryption_state(_chat_control, state):
        state['visible'] = True
        state['authenticated'] = True

    def _on_encryption_button_clicked(self, chat_control):
        self._show_fingerprint_window(chat_control)

    def _before_sendmessage(self, chat_control):
        account = chat_control.account
        if not self._is_enabled_account(account):
            return
        contact = chat_control.contact
        omemo = self.get_omemo(account)
        self.new_fingerprints_available(chat_control)
        if chat_control.is_groupchat:
            room = chat_control.room_jid
            if not omemo.is_omemo_groupchat(room):
                ErrorDialog(
                    _('Bad Configuration'),
                    _('To use OMEMO in a Groupchat, the Groupchat should be'
                      ' non-anonymous and members-only.'))
                chat_control.sendmessage = False
                return

            missing = True
            for jid in omemo.backend.get_muc_members(room):
                if not omemo.are_keys_missing(jid):
                    missing = False
            if missing:
                log.info('%s => No Trusted Fingerprints for %s',
                         account, room)
                self.print_message(chat_control, UserMessages.NO_FINGERPRINTS)
                chat_control.sendmessage = False
        else:
            # check if we have devices for the contact
            if not omemo.backend.get_devices(contact.jid, without_self=True):
                omemo.request_devicelist(contact.jid)
                self.print_message(chat_control, UserMessages.QUERY_DEVICES)
                chat_control.sendmessage = False
                return
            # check if bundles are missing for some devices
            if omemo.backend.storage.hasUndecidedFingerprints(contact.jid):
                log.info('%s => Undecided Fingerprints for %s',
                         account, contact.jid)
                self.print_message(chat_control, UserMessages.UNDECIDED_FINGERPRINTS)
                chat_control.sendmessage = False
            else:
                log.debug('%s => Sending Message to %s',
                          account, contact.jid)

    def _on_new_fingerprints(self, event):
        self.new_fingerprints_available(event.chat_control)

    def new_fingerprints_available(self, chat_control):
        jid = chat_control.contact.jid
        account = chat_control.account
        omemo = self.get_omemo(account)
        if chat_control.is_groupchat:
            for jid_ in omemo.backend.get_muc_members(chat_control.room_jid,
                                                      without_self=False):
                fingerprints = omemo.backend.storage.getNewFingerprints(jid_)
                if fingerprints:
                    self._show_fingerprint_window(
                        chat_control, fingerprints)
                    break
        else:
            fingerprints = omemo.backend.storage.getNewFingerprints(jid)
            if fingerprints:
                self._show_fingerprint_window(
                    chat_control, fingerprints)

    def _show_fingerprint_window(self, chat_control, fingerprints=None):
        contact = chat_control.contact
        account = chat_control.account
        omemo = self.get_omemo(account)

        if 'dialog' not in self._windows:
            self._windows['dialog'] = \
                KeyDialog(self, contact, app.window,
                          self._windows, groupchat=chat_control.is_groupchat)
            if fingerprints:
                log.debug('%s => Showing Fingerprint Prompt for %s',
                          account, contact.jid)
                omemo.backend.storage.setShownFingerprints(fingerprints)
        else:
            self._windows['dialog'].present()
            self._windows['dialog'].update()
            if fingerprints:
                omemo.backend.storage.setShownFingerprints(fingerprints)

    @staticmethod
    def print_message(chat_control, kind):
        msg = None
        if kind == UserMessages.QUERY_DEVICES:
            msg = _('No devices found. Query in progress...')
        elif kind == UserMessages.NO_FINGERPRINTS:
            msg = _('To send an encrypted message, you have to '
                    'first trust the fingerprint of your contact!')
        elif kind == UserMessages.UNDECIDED_FINGERPRINTS:
            msg = _('You have undecided fingerprints')
        if msg is None:
            return
        chat_control.add_info_message(msg)
