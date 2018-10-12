# -*- coding: utf-8 -*-

'''
Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
Copyright 2015 Daniel Gultsch <daniel@cgultsch.de>
Copyright 2016 Philipp Hörist <philipp@hoerist.com>

This file is part of Gajim-OMEMO plugin.

The Gajim-OMEMO plugin is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

Gajim-OMEMO is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
A PARTICULAR PURPOSE.  See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
the Gajim-OMEMO plugin.  If not, see <http://www.gnu.org/licenses/>.
'''

import binascii
import logging
import os
import textwrap
from enum import IntEnum, unique

from gi.repository import Gtk, GdkPixbuf, Gdk
from axolotl.state.sessionrecord import SessionRecord

log = logging.getLogger('gajim.plugin_system.omemo')

PILLOW = False
try:
    import qrcode
    PILLOW = True
except ImportError as error:
    log.debug(error)
    log.error('python-qrcode or dependencies of it are not available')

from gajim.common import app
from gajim.common import configpaths
from gajim.dialogs import YesNoDialog
from gajim.plugins.gui import GajimPluginConfigDialog

# Since Gajim 1.1.0 _() has to be imported
try:
    from gajim.common.i18n import _
except ImportError:
    pass

@unique
class State(IntEnum):
    UNTRUSTED = 0
    TRUSTED = 1
    UNDECIDED = 2


class OMEMOConfigDialog(GajimPluginConfigDialog):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        self.GTK_BUILDER_FILE_PATH = \
            self.plugin.local_file_path('config_dialog.ui')
        self.B = Gtk.Builder()
        self.B.set_translation_domain('gajim_plugins')
        self.B.add_from_file(self.GTK_BUILDER_FILE_PATH)

        try:
            self.disabled_accounts = self.plugin.config['DISABLED_ACCOUNTS']
        except KeyError:
            self.plugin.config['DISABLED_ACCOUNTS'] = []
            self.disabled_accounts = self.plugin.config['DISABLED_ACCOUNTS']

        log.debug('Disabled Accounts:')
        log.debug(self.disabled_accounts)

        self.device_model = self.B.get_object('deviceid_store')

        self.disabled_acc_store = self.B.get_object('disabled_account_store')
        self.account_store = self.B.get_object('account_store')

        self.active_acc_view = self.B.get_object('active_accounts_view')
        self.disabled_acc_view = self.B.get_object('disabled_accounts_view')

        box = self.get_content_area()
        box.pack_start(self.B.get_object('notebook1'), True, True, 0)

        self.B.connect_signals(self)

        self.plugin_active = False

    def on_run(self):
        for plugin in app.plugin_manager.active_plugins:
            log.debug(type(plugin))
            if type(plugin).__name__ == 'OmemoPlugin':
                self.plugin_active = True
                break
        self.update_account_store()
        self.update_account_combobox()
        self.update_disabled_account_view()

    def is_in_accountstore(self, account):
        for row in self.account_store:
            if row[0] == account:
                return True
        return False

    def update_account_store(self):
        for account in sorted(app.contacts.get_accounts()):
            if account in self.disabled_accounts:
                continue
            if account == 'Local':
                continue
            if not self.is_in_accountstore(account):
                self.account_store.append(row=(account,))

    def update_account_combobox(self):
        if self.plugin_active is False:
            return
        if len(self.account_store) > 0:
            self.B.get_object('account_combobox').set_active(0)
        else:
            self.account_combobox_changed_cb(
                self.B.get_object('account_combobox'))

    def account_combobox_changed_cb(self, box, *args):
        self.update_context_list()

    def get_qrcode(self, jid, sid, fingerprint):
        file_name = 'omemo_{}.png'.format(jid)
        path = os.path.join(
            configpaths.get('MY_DATA'), file_name)

        ver_string = 'xmpp:{}?omemo-sid-{}={}'.format(jid, sid, fingerprint)
        log.debug('Verification String: ' + ver_string)

        if os.path.exists(path):
            return path

        qr = qrcode.QRCode(version=None, error_correction=2, box_size=4, border=1)
        qr.add_data(ver_string)
        qr.make(fit=True)
        img = qr.make_image()
        img.save(path)
        return path

    def update_disabled_account_view(self):
        self.disabled_acc_store.clear()
        for account in self.disabled_accounts:
            self.disabled_acc_store.append(row=(account,))

    def activate_accounts_btn_clicked(self, button, *args):
        mod, paths = self.disabled_acc_view.get_selection().get_selected_rows()
        for path in paths:
            it = mod.get_iter(path)
            account = mod.get(it, 0)
            if account[0] in self.disabled_accounts and \
                    not self.is_in_accountstore(account[0]):
                self.account_store.append(row=(account[0],))
                self.disabled_accounts.remove(account[0])
        self.update_disabled_account_view()
        self.plugin.config['DISABLED_ACCOUNTS'] = self.disabled_accounts
        self.update_account_combobox()

    def disable_accounts_btn_clicked(self, button, *args):
        mod, paths = self.active_acc_view.get_selection().get_selected_rows()
        for path in paths:
            it = mod.get_iter(path)
            account = mod.get(it, 0)
            if account[0] not in self.disabled_accounts and \
                    self.is_in_accountstore(account[0]):
                self.disabled_accounts.append(account[0])
                self.account_store.remove(it)
        self.update_disabled_account_view()
        self.plugin.config['DISABLED_ACCOUNTS'] = self.disabled_accounts
        self.update_account_combobox()

    def cleardevice_button_clicked_cb(self, button, *args):
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]
        self.plugin.connections[account].clear_device_list()
        self.update_context_list()

    def refresh_button_clicked_cb(self, button, *args):
        self.update_context_list()

    def update_context_list(self):
        self.device_model.clear()
        self.qrcode = self.B.get_object('qrcode')
        self.qrinfo = self.B.get_object('qrinfo')
        if len(self.account_store) == 0:
            self.B.get_object('ID').set_markup('')
            self.B.get_object('fingerprint_label').set_markup('')
            self.B.get_object('refresh').set_sensitive(False)
            self.B.get_object('cleardevice_button').set_sensitive(False)
            self.B.get_object('qrcode').clear()
            return
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]

        # Set buttons active
        self.B.get_object('refresh').set_sensitive(True)
        if account == 'Local':
            self.B.get_object('cleardevice_button').set_sensitive(False)
        else:
            self.B.get_object('cleardevice_button').set_sensitive(True)

        # Set FPR Label and DeviceID
        state = self.plugin.get_omemo(account)
        deviceid = state.own_device_id
        self.B.get_object('ID').set_markup('<tt>%s</tt>' % deviceid)

        ownfpr = binascii.hexlify(state.store.getIdentityKeyPair()
                                  .getPublicKey().serialize()).decode('utf-8')
        human_ownfpr = self.human_hash(ownfpr[2:])
        self.B.get_object('fingerprint_label').set_markup('<tt>%s</tt>'
                                                          % human_ownfpr)

        # Set Device ID List
        for item in state.own_devices:
            self.device_model.append([item])

        # Set QR Verification Code
        if PILLOW:
            path = self.get_qrcode(
                app.get_jid_from_account(account), deviceid, ownfpr[2:])
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            self.qrcode.set_from_pixbuf(pixbuf)
            self.qrcode.show()
            self.qrinfo.set_revealed(False)
        else:
            self.qrinfo.set_revealed(True)
            self.qrcode.hide()

    def human_hash(self, fpr):
        fpr = fpr.upper()
        fplen = len(fpr)
        wordsize = fplen // 8
        buf = ''
        for w in range(0, fplen, wordsize):
            buf += '{0} '.format(fpr[w:w + wordsize])
        buf = textwrap.fill(buf, width=36)
        return buf.rstrip()
