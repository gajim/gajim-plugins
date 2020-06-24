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

from gajim.common import app
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.helpers import get_builder

from omemo.backend.util import get_fingerprint

log = logging.getLogger('gajim.p.omemo')


class OMEMOConfigDialog(GajimPluginConfigDialog):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        path = self.plugin.local_file_path('gtk/config.ui')
        self._ui = get_builder(path)

        image_path = self.plugin.local_file_path('omemo.png')
        self._ui.image.set_from_file(image_path)

        try:
            self.disabled_accounts = self.plugin.config['DISABLED_ACCOUNTS']
        except KeyError:
            self.plugin.config['DISABLED_ACCOUNTS'] = []
            self.disabled_accounts = self.plugin.config['DISABLED_ACCOUNTS']

        box = self.get_content_area()
        box.pack_start(self._ui.notebook1, True, True, 0)

        self._ui.connect_signals(self)

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
        self.update_settings()

    def is_in_accountstore(self, account):
        for row in self._ui.account_store:
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
                self._ui.account_store.append(row=(account,))

    def update_account_combobox(self):
        if self.plugin_active is False:
            return
        if len(self._ui.account_store):
            self._ui.account_combobox.set_active(0)
        else:
            self.account_combobox_changed_cb(self._ui.account_combobox)

    def account_combobox_changed_cb(self, box, *args):
        self.update_context_list()

    def update_disabled_account_view(self):
        self._ui.disabled_account_store.clear()
        for account in self.disabled_accounts:
            self._ui.disabled_account_store.append(row=(account,))

    def activate_accounts_btn_clicked(self, _button, *args):
        selection = self._ui.disabled_accounts_view.get_selection()
        mod, paths = selection.get_selected_rows()
        for path in paths:
            it = mod.get_iter(path)
            account = mod.get(it, 0)
            if account[0] in self.disabled_accounts and \
                    not self.is_in_accountstore(account[0]):
                self._ui.account_store.append(row=(account[0],))
                self.disabled_accounts.remove(account[0])
        self.update_disabled_account_view()
        self.plugin.config['DISABLED_ACCOUNTS'] = self.disabled_accounts
        self.update_account_combobox()

    def disable_accounts_btn_clicked(self, _button, *args):
        selection = self._ui.active_accounts_view.get_selection()
        mod, paths = selection.get_selected_rows()
        for path in paths:
            it = mod.get_iter(path)
            account = mod.get(it, 0)
            if account[0] not in self.disabled_accounts and \
                    self.is_in_accountstore(account[0]):
                self.disabled_accounts.append(account[0])
                self._ui.account_store.remove(it)
        self.update_disabled_account_view()
        self.plugin.config['DISABLED_ACCOUNTS'] = self.disabled_accounts
        self.update_account_combobox()

    def cleardevice_button_clicked_cb(self, button, *args):
        active = self._ui.account_combobox.get_active()
        account = self._ui.account_store[active][0]
        app.connections[account].get_module('OMEMO').clear_devicelist()
        self.update_context_list()

    def refresh_button_clicked_cb(self, button, *args):
        self.update_context_list()

    def _on_blind_trust(self, button):
        self.plugin.config['BLIND_TRUST'] = button.get_active()

    def update_context_list(self):
        self._ui.deviceid_store.clear()

        if not len(self._ui.account_store):
            self._ui.ID.set_markup('')
            self._ui.fingerprint_label.set_markup('')
            self._ui.refresh.set_sensitive(False)
            self._ui.cleardevice_button.set_sensitive(False)
            return
        active = self._ui.account_combobox.get_active()
        account = self._ui.account_store[active][0]

        # Set buttons active
        self._ui.refresh.set_sensitive(True)
        if account == 'Local':
            self._ui.cleardevice_button.set_sensitive(False)
        else:
            self._ui.cleardevice_button.set_sensitive(True)

        # Set FPR Label and DeviceID
        omemo = self.plugin.get_omemo(account)
        self._ui.ID.set_markup('<tt>%s</tt>' % omemo.backend.own_device)

        identity_key = omemo.backend.storage.getIdentityKeyPair()
        fpr = get_fingerprint(identity_key, formatted=True)
        self._ui.fingerprint_label.set_markup('<tt>%s</tt>' % fpr)

        own_jid = app.get_jid_from_account(account)
        # Set Device ID List
        for item in omemo.backend.get_devices(own_jid):
            self._ui.deviceid_store.append([item])

    def update_settings(self):
        self._ui.blind_trust_checkbutton.set_active(
            self.plugin.config['BLIND_TRUST'])