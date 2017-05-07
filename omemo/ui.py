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
from enum import IntEnum, unique

from gi.repository import Gtk, GdkPixbuf, Gdk
from axolotl.state.sessionrecord import SessionRecord

log = logging.getLogger('gajim.plugin_system.omemo')

PILLOW = False
try:
    import qrcode
    PILLOW = True
except Exception as e:
    log.exception('Error:')
    log.error('python-qrcode or dependencies of it, are not available')

from common import gajim
from common import configpaths
from dialogs import YesNoDialog
from plugins.gui import GajimPluginConfigDialog


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

        self.fpr_model = self.B.get_object('fingerprint_store')
        self.device_model = self.B.get_object('deviceid_store')

        self.fpr_view = self.B.get_object('fingerprint_view')

        self.disabled_acc_store = self.B.get_object('disabled_account_store')
        self.account_store = self.B.get_object('account_store')

        self.active_acc_view = self.B.get_object('active_accounts_view')
        self.disabled_acc_view = self.B.get_object('disabled_accounts_view')

        vbox = self.get_content_area()
        vbox.pack_start(self.B.get_object('notebook1'), True, True, 0)

        self.B.connect_signals(self)

        self.plugin_active = False

    def on_run(self):
        for plugin in gajim.plugin_manager.active_plugins:
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
        for account in sorted(gajim.contacts.get_accounts()):
            if account not in self.disabled_accounts and \
                    not self.is_in_accountstore(account):
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
            configpaths.gajimpaths['MY_DATA'], file_name)

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

    def delfpr_button_clicked(self, button, *args):
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]

        state = self.plugin.get_omemo_state(account)

        mod, paths = self.fpr_view.get_selection().get_selected_rows()

        def on_yes(checked):
            record = state.store.loadSession(jid, deviceid)
            identity_key = record.getSessionState().getRemoteIdentityKey()

            state.store.deleteSession(jid, deviceid)
            state.store.deleteIdentity(jid, identity_key)
            self.update_context_list()

        for path in paths:
            it = mod.get_iter(path)
            jid, fpr, deviceid = mod.get(it, 1, 3, 4)
            fpr = fpr[31:-12]

            YesNoDialog(
                'Delete Fingerprint?',
                'Do you want to delete the '
                'fingerprint of <b>{}</b> on your account <b>{}</b>?'
                '\n\n<tt>{}</tt>'.format(jid, account, fpr),
                on_response_yes=on_yes, transient_for=self)

    def trust_button_clicked_cb(self, button, *args):
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]

        state = self.plugin.get_omemo_state(account)

        mod, paths = self.fpr_view.get_selection().get_selected_rows()

        def on_yes(checked, identity_key):
            state.store.setTrust(identity_key, State.TRUSTED)
            try:
                if self.plugin.ui_list[account]:
                    self.plugin.ui_list[account][jid]. \
                        refresh_auth_lock_icon()
            except:
                log.debug('UI not available')
            self.update_context_list()

        def on_no(identity_key):
            state.store.setTrust(identity_key, State.UNTRUSTED)
            try:
                if jid in self.plugin.ui_list[account]:
                    self.plugin.ui_list[account][jid]. \
                        refresh_auth_lock_icon()
            except:
                log.debug('UI not available')
            self.update_context_list()

        for path in paths:
            it = mod.get_iter(path)
            jid, fpr, deviceid = mod.get(it, 1, 3, 4)
            fpr = fpr[31:-12]

            record = state.store.loadSession(jid, deviceid)
            identity_key = record.getSessionState().getRemoteIdentityKey()

            YesNoDialog(
                'Trust / Revoke Fingerprint?',
                'Do you want to trust the fingerprint of <b>{}</b> '
                'on your account <b>{}</b>?\n\n'
                '<tt>{}</tt>'.format(jid, account, fpr),
                on_response_yes=(on_yes, identity_key),
                on_response_no=(on_no, identity_key),
                transient_for=self)

    def cleardevice_button_clicked_cb(self, button, *args):
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]
        self.plugin.clear_device_list(account)
        self.update_context_list()

    def refresh_button_clicked_cb(self, button, *args):
        self.update_context_list()

    def fpr_button_pressed_cb(self, tw, event):
        if event.button == 3:
            pthinfo = tw.get_path_at_pos(int(event.x), int(event.y))

            if pthinfo is None:
                # only show the popup when we right clicked on list content
                # ie. don't show it when we click at empty rows
                return False

            # if the row under the mouse is already selected, we keep the
            # selection, otherwise we only select the new item
            keep_selection = tw.get_selection().path_is_selected(pthinfo[0])

            pop = self.B.get_object('fprclipboard_menu')
            pop.popup(None, None, None, None, event.button, event.time)

            # keep_selection=True -> no further processing of click event
            # keep_selection=False-> further processing -> GTK usually selects
            #   the item below the cursor
            return keep_selection

    def clipboard_button_cb(self, menuitem):
        mod, paths = self.fpr_view.get_selection().get_selected_rows()

        fprs = []
        for path in paths:
            it = mod.get_iter(path)
            jid, fpr = mod.get(it, 1, 3)
            fprs.append('%s: %s' % (jid, fpr[31:-12]))
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text('\n'.join(fprs), -1)

    def update_context_list(self):
        self.fpr_model.clear()
        self.device_model.clear()
        self.qrcode = self.B.get_object('qrcode')
        self.qrinfo = self.B.get_object('qrinfo')
        if len(self.account_store) == 0:
            self.B.get_object('ID').set_markup('')
            self.B.get_object('fingerprint_label').set_markup('')
            self.B.get_object('trust_button').set_sensitive(False)
            self.B.get_object('delfprbutton').set_sensitive(False)
            self.B.get_object('refresh').set_sensitive(False)
            self.B.get_object('cleardevice_button').set_sensitive(False)
            self.B.get_object('qrcode').clear()
            return
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]

        # Set buttons active
        self.B.get_object('trust_button').set_sensitive(True)
        self.B.get_object('delfprbutton').set_sensitive(True)
        self.B.get_object('refresh').set_sensitive(True)
        if account == 'Local':
            self.B.get_object('cleardevice_button').set_sensitive(False)
        else:
            self.B.get_object('cleardevice_button').set_sensitive(True)

        # Set FPR Label and DeviceID
        state = self.plugin.get_omemo_state(account)
        deviceid = state.own_device_id
        self.B.get_object('ID').set_markup('<tt>%s</tt>' % deviceid)

        ownfpr = binascii.hexlify(state.store.getIdentityKeyPair()
                                  .getPublicKey().serialize()).decode('utf-8')
        human_ownfpr = human_hash(ownfpr[2:])
        self.B.get_object('fingerprint_label').set_markup('<tt>%s</tt>'
                                                          % human_ownfpr)

        # Set Fingerprint List
        trust_str = {0: 'False', 1: 'True', 2: 'Undecided'}
        session_db = state.store.getAllSessions()

        for item in session_db:
            color = {0: '#FF0040',  # red
                     1: '#2EFE2E',  # green
                     2: '#FF8000'}  # orange

            _id, jid, deviceid, record, active = item

            active = bool(active)

            identity_key = SessionRecord(serialized=record). \
                getSessionState().getRemoteIdentityKey()
            fpr = binascii.hexlify(
                identity_key.getPublicKey().serialize()).decode('utf-8')
            fpr = human_hash(fpr[2:])

            trust = state.store.isTrustedIdentity(jid, identity_key)

            if not active:
                color[trust] = '#585858'  # grey

            self.fpr_model.append(
                (_id, jid, trust_str[trust],
                 '<tt><span foreground="{}">{}</span></tt>'.
                 format(color[trust], fpr),
                 deviceid))

        # Set Device ID List
        for item in state.own_devices:
            self.device_model.append([item])

        # Set QR Verification Code
        if PILLOW:
            path = self.get_qrcode(
                gajim.get_jid_from_account(account), deviceid, ownfpr[2:])
            self.qrcode.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file(path))
            self.qrinfo.hide()
        else:
            self.qrinfo.show()


class FingerprintWindow(Gtk.Dialog):
    def __init__(self, plugin, contact, parent, windowinstances,
                 groupchat=False):
        self.groupchat = groupchat
        self.contact = contact
        self.windowinstances = windowinstances
        self.account = self.contact.account.name
        self.plugin = plugin
        self.omemostate = self.plugin.get_omemo_state(self.account)
        self.own_jid = gajim.get_jid_from_account(self.account)
        Gtk.Dialog.__init__(self,
                            title=('Fingerprints for %s') % contact.jid,
                            parent=parent,
                            flags=Gtk.DialogFlags.DESTROY_WITH_PARENT)
        close_button = self.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        close_button.connect('clicked', self.on_close_button_clicked)
        self.connect('delete-event', self.on_window_delete)

        self.GTK_BUILDER_FILE_PATH = \
            self.plugin.local_file_path('fpr_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.add_from_file(self.GTK_BUILDER_FILE_PATH)
        self.xml.set_translation_domain('gajim_plugins')

        self.fpr_model = self.xml.get_object('fingerprint_store')

        self.fpr_view = self.xml.get_object('fingerprint_view')
        self.fpr_view_own = self.xml.get_object('fingerprint_view_own')

        self.notebook = self.xml.get_object('notebook1')
        vbox = self.get_content_area()
        vbox.pack_start(self.notebook, True, True, 0)

        self.xml.connect_signals(self)

        # Set own Fingerprint Label
        ownfpr = binascii.hexlify(self.omemostate.store.getIdentityKeyPair()
                                  .getPublicKey().serialize()).decode('utf-8')
        ownfpr = human_hash(ownfpr[2:])
        self.xml.get_object('fingerprint_label_own').set_markup('<tt>%s</tt>'
                                                                % ownfpr)
        self.update_context_list()

        self.show_all()

    def on_close_button_clicked(self, widget):
        del self.windowinstances['dialog']
        self.hide()

    def on_window_delete(self, widget, event):
        del self.windowinstances['dialog']
        self.hide()

    def trust_button_clicked_cb(self, button, *args):
        state = self.omemostate

        if self.notebook.get_current_page() == 1:
            mod, paths = self.fpr_view_own.get_selection().get_selected_rows()
        else:
            mod, paths = self.fpr_view.get_selection().get_selected_rows()

        def on_yes(checked, identity_key):
            state.store.setTrust(identity_key, State.TRUSTED)
            self.update_context_list()

        def on_no(identity_key):
            state.store.setTrust(identity_key, State.UNTRUSTED)
            self.update_context_list()

        for path in paths:
            it = mod.get_iter(path)
            jid, fpr, deviceid = mod.get(it, 1, 3, 4)
            fpr = fpr[31:-12]

            record = state.store.loadSession(jid, deviceid)
            identity_key = record.getSessionState().getRemoteIdentityKey()

            YesNoDialog(
                'Trust / Revoke Fingerprint?',
                'Do you want to trust the fingerprint of <b>{}</b> '
                'on your account <b>{}</b>?\n\n'
                '<tt>{}</tt>'.format(jid, self.account, fpr),
                on_response_yes=(on_yes, identity_key),
                on_response_no=(on_no, identity_key),
                transient_for=self)

    def fpr_button_pressed_cb(self, tw, event):
        if event.button == 3:
            pthinfo = tw.get_path_at_pos(int(event.x), int(event.y))

            if pthinfo is None:
                # only show the popup when we right clicked on list content
                # ie. don't show it when we click at empty rows
                return False

            # if the row under the mouse is already selected, we keep the
            # selection, otherwise we only select the new item
            keep_selection = tw.get_selection().path_is_selected(pthinfo[0])

            pop = self.xml.get_object('fprclipboard_menu')
            pop.popup(None, None, None, None, event.button, event.time)

            # keep_selection=True -> no further processing of click event
            # keep_selection=False-> further processing -> GTK usually selects
            #   the item below the cursor
            return keep_selection

    def clipboard_button_cb(self, menuitem):
        if self.notebook.get_current_page() == 1:
            mod, paths = self.fpr_view_own.get_selection().get_selected_rows()
        else:
            mod, paths = self.fpr_view.get_selection().get_selected_rows()

        fprs = []
        for path in paths:
            it = mod.get_iter(path)
            jid, fpr = mod.get(it, 1, 3)
            fprs.append('%s: %s' % (jid, fpr[31:-12]))
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text('\n'.join(fprs), -1)

    def update_context_list(self, *args):
        self.fpr_model.clear()
        state = self.omemostate

        if self.notebook.get_current_page() == 1:
            contact_jid = self.own_jid
        else:
            contact_jid = self.contact.jid

        trust_str = {0: 'False', 1: 'True', 2: 'Undecided'}
        if self.groupchat and self.notebook.get_current_page() == 0:
            contact_jids = []
            for nick in self.plugin.groupchat[contact_jid]:
                real_jid = self.plugin.groupchat[contact_jid][nick]
                if real_jid == self.own_jid:
                    continue
                contact_jids.append(real_jid)
            session_db = state.store.getSessionsFromJids(contact_jids)
        else:
            session_db = state.store.getSessionsFromJid(contact_jid)

        for item in session_db:
            color = {0: '#FF0040',  # red
                     1: '#2EFE2E',  # green
                     2: '#FF8000'}  # orange

            _id, jid, deviceid, record, active = item

            active = bool(active)

            identity_key = SessionRecord(serialized=record). \
                getSessionState().getRemoteIdentityKey()
            fpr = binascii.hexlify(identity_key.getPublicKey().serialize()).decode('utf-8')
            fpr = human_hash(fpr[2:])

            trust = state.store.isTrustedIdentity(jid, identity_key)

            if not active:
                color[trust] = '#585858'  # grey

            self.fpr_model.append(
                (_id, jid, trust_str[trust],
                 '<tt><span foreground="{}">{}</span></tt>'.
                 format(color[trust], fpr),
                 deviceid))


def human_hash(fpr):
    fpr = fpr.upper()
    fplen = len(fpr)
    wordsize = fplen // 8
    buf = ''
    for w in range(0, fplen, wordsize):
        buf += '{0} '.format(fpr[w:w + wordsize])
    return buf.rstrip()
