# -*- coding: utf-8 -*-
#
# Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright 2015 Daniel Gultsch <daniel@cgultsch.de>
#
# This file is part of Gajim-OMEMO plugin.
#
# The Gajim-OMEMO plugin is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Gajim-OMEMO is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# the Gajim-OMEMO plugin.  If not, see <http://www.gnu.org/licenses/>.
#

import binascii
import logging
import os
import gobject
import gtk
import message_control

# pylint: disable=import-error
import gtkgui_helpers
from common import gajim
from dialogs import YesNoDialog
from plugins.gui import GajimPluginConfigDialog
from axolotl.state.sessionrecord import SessionRecord
from common import configpaths
# pylint: enable=import-error

from .qrcode.main import QRCode

log = logging.getLogger('gajim.plugin_system.omemo')

UNDECIDED = 2
TRUSTED = 1
UNTRUSTED = 0


class OmemoButton(gtk.Button):
    def __init__(self, plugin, chat_control, ui, enabled):
        super(OmemoButton, self).__init__(label=None, stock=None)
        self.chat_control = chat_control

        self.set_property('relief', gtk.RELIEF_NONE)
        self.set_property('can-focus', False)
        self.set_sensitive(True)

        icon = gtk.image_new_from_file(
            plugin.local_file_path('omemo16x16.png'))
        self.set_image(icon)
        self.set_tooltip_text('OMEMO Encryption')

        self.connect('clicked', self.on_click)

        self.menu = OmemoMenu(ui, enabled)

    def on_click(self, widget):
        """
        Popup omemo menu
        """
        gtkgui_helpers.popup_emoticons_under_button(
            self.menu, widget, self.chat_control.parent_win)

    def set_omemo_state(self, state):
        self.menu.set_omemo_state(state)


class OmemoMenu(gtk.Menu):
    def __init__(self, ui, enabled):
        super(OmemoMenu, self).__init__()
        self.ui = ui

        self.item_omemo_state = gtk.CheckMenuItem('Activate OMEMO')
        self.item_omemo_state.set_active(enabled)
        self.item_omemo_state.connect('activate', self.on_toggle_omemo)
        self.append(self.item_omemo_state)

        item = gtk.ImageMenuItem('Fingerprints')
        icon = gtk.image_new_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION,
                                        gtk.ICON_SIZE_MENU)
        item.set_image(icon)
        item.connect('activate', self.on_open_fingerprint_window)
        self.append(item)

        self.show_all()

    def on_toggle_omemo(self, widget):
        self.ui.set_omemo_state(widget.get_active())

    def on_open_fingerprint_window(self, widget):
        self.ui.show_fingerprint_window()

    def set_omemo_state(self, state):
        self.item_omemo_state.handler_block_by_func(self.on_toggle_omemo)
        self.item_omemo_state.set_active(state)
        self.item_omemo_state.handler_unblock_by_func(self.on_toggle_omemo)


class Ui(object):
    def __init__(self, plugin, chat_control, enabled, state):
        self.contact = chat_control.contact
        self.chat_control = chat_control
        self.plugin = plugin
        self.state = state
        self.account = self.contact.account.name
        self.windowinstances = {}

        self.groupchat = False
        if chat_control.type_id == message_control.TYPE_GC:
            self.groupchat = True
            self.omemo_capable = False
            self.room = self.chat_control.room_jid

        self.display_omemo_state()
        self.refresh_auth_lock_icon()

        self.omemobutton = OmemoButton(plugin, chat_control, self, enabled)

        self.actions_hbox = chat_control.xml.get_object('actions_hbox')
        send_button = chat_control.xml.get_object('send_button')
        send_button_pos = self.actions_hbox.child_get_property(send_button,
                                                               'position')
        self.actions_hbox.add_with_properties(self.omemobutton, 'position',
                                              send_button_pos - 2,
                                              'expand', False)
        self.omemobutton.show_all()

        # add a OMEMO entry to the context/advanced menu
        self.chat_control.omemo_orig_prepare_context_menu = \
            self.chat_control.prepare_context_menu

        def omemo_prepare_context_menu(hide_buttonbar_items=False):
            menu = self.chat_control. \
                omemo_orig_prepare_context_menu(hide_buttonbar_items)
            submenu = OmemoMenu(self, self.encryption_active())

            item = gtk.ImageMenuItem('OMEMO Encryption')
            icon_path = plugin.local_file_path('omemo16x16.png')
            item.set_image(gtk.image_new_from_file(icon_path))
            item.set_submenu(submenu)

            if self.groupchat:
                item.set_sensitive(self.omemo_capable)

            # at index 8 is the separator after the esession encryption entry
            menu.insert(item, 8)
            return menu
        self.chat_control.prepare_context_menu = omemo_prepare_context_menu

        # Hook into Send Button so we can check Stuff before sending
        self.chat_control.orig_send_message = \
            self.chat_control.send_message

        def omemo_send_message(message, keyID='', chatstate=None, xhtml=None,
                               process_commands=True, attention=False):
            self.new_fingerprints_available()
            if self.encryption_active() and \
                    self.plugin.are_keys_missing(self.account,
                                                 self.contact.jid):

                log.debug(self.account + ' => No Trusted Fingerprints for ' +
                          self.contact.jid)
                self.no_trusted_fingerprints_warning()
            else:
                self.chat_control.orig_send_message(message, keyID, chatstate,
                                                    xhtml, process_commands,
                                                    attention)
                log.debug(self.account + ' => Sending Message to ' +
                          self.contact.jid)

        def omemo_send_gc_message(message, xhtml=None, process_commands=True):
            self.new_fingerprints_available()
            if self.encryption_active():
                missing = True
                own_jid = gajim.get_jid_from_account(self.account)
                for nick in self.plugin.groupchat[self.room]:
                    real_jid = self.plugin.groupchat[self.room][nick]
                    if real_jid == own_jid:
                        continue
                    if not self.plugin.are_keys_missing(self.account,
                                                        real_jid):
                        missing = False
                if missing:
                    log.debug(self.account +
                              ' => No Trusted Fingerprints for ' +
                              self.room)
                    self.no_trusted_fingerprints_warning()
                else:
                    self.chat_control.orig_send_message(message, xhtml,
                                                        process_commands)
                    log.debug(self.account + ' => Sending Message to ' +
                              self.room)
            else:
                self.chat_control.orig_send_message(message, xhtml,
                                                    process_commands)
                log.debug(self.account + ' => Sending Message to ' +
                          self.room)

        if self.groupchat:
            self.chat_control.send_message = omemo_send_gc_message
        else:
            self.chat_control.send_message = omemo_send_message

    def set_omemo_state(self, enabled):
        """
        Enable or disable OMEMO for this window's contact and update the
        window ui accordingly
        """
        if enabled:
            log.debug(self.contact.account.name + ' => Enable OMEMO for ' +
                      self.contact.jid)
            self.plugin.omemo_enable_for(self.contact.jid,
                                         self.contact.account.name)
            self.refresh_auth_lock_icon()
        else:
            log.debug(self.contact.account.name + ' => Disable OMEMO for ' +
                      self.contact.jid)
            self.plugin.omemo_disable_for(self.contact.jid,
                                          self.contact.account.name)
            self.refresh_auth_lock_icon()

        self.omemobutton.set_omemo_state(enabled)
        self.display_omemo_state()

    def sensitive(self, value):
        self.omemobutton.set_sensitive(value)
        self.omemo_capable = value
        if value:
            self.chat_control.prepare_context_menu

    def encryption_active(self):
        return self.state.encryption.is_active(self.contact.jid)

    def activate_omemo(self):
        if not self.encryption_active():
            self.set_omemo_state(True)

    def new_fingerprints_available(self):
        jid = self.contact.jid
        if self.groupchat and self.room in self.plugin.groupchat:
            for nick in self.plugin.groupchat[self.room]:
                real_jid = self.plugin.groupchat[self.room][nick]
                fingerprints = self.state.store. \
                    getNewFingerprints(real_jid)
                if fingerprints:
                    self.show_fingerprint_window(fingerprints)
        elif not self.groupchat:
            fingerprints = self.state.store.getNewFingerprints(jid)
            if fingerprints:
                self.show_fingerprint_window(fingerprints)

    def show_fingerprint_window(self, fingerprints=None):
        if 'dialog' not in self.windowinstances:
            if self.groupchat:
                self.windowinstances['dialog'] = \
                    FingerprintWindow(self.plugin, self.contact,
                                      self.chat_control.parent_win.window,
                                      self.windowinstances, groupchat=True)
            else:
                self.windowinstances['dialog'] = \
                    FingerprintWindow(self.plugin, self.contact,
                                      self.chat_control.parent_win.window,
                                      self.windowinstances)
            self.windowinstances['dialog'].show_all()
            if fingerprints:
                log.debug(self.account +
                          ' => Showing Fingerprint Prompt for ' +
                          self.contact.jid)
                self.state.store.setShownFingerprints(fingerprints)
        else:
            self.windowinstances['dialog'].update_context_list()
            if fingerprints:
                self.state.store.setShownFingerprints(fingerprints)

    def plain_warning(self):
        self.chat_control.print_conversation_line(
            'Received plaintext message! ' +
            'Your next message will still be encrypted!', 'status', '', None)

    def display_omemo_state(self):
        if self.encryption_active():
            msg = u'OMEMO encryption enabled'
        else:
            msg = u'OMEMO encryption disabled'
        self.chat_control.print_conversation_line(msg, 'status', '', None)

    def no_trusted_fingerprints_warning(self):
        msg = "To send an encrypted message, you have to " \
              "first trust the fingerprint of your contact!"
        self.chat_control.print_conversation_line(msg, 'status', '', None)

    def refresh_auth_lock_icon(self):
        if self.groupchat:
            return
        if self.encryption_active():
            if self.state.getUndecidedFingerprints(self.contact.jid):
                self.chat_control._show_lock_image(True, 'OMEMO', True, True,
                                                   False)
            else:
                self.chat_control._show_lock_image(True, 'OMEMO', True, True,
                                                   True)
        else:
            self.chat_control._show_lock_image(False, 'OMEMO', False, True,
                                               False)

    def removeUi(self):
        self.actions_hbox.remove(self.omemobutton)
        self.chat_control.prepare_context_menu = \
            self.chat_control.omemo_orig_prepare_context_menu
        self.chat_control.send_message = self.chat_control.orig_send_message


class OMEMOConfigDialog(GajimPluginConfigDialog):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        self.GTK_BUILDER_FILE_PATH = \
            self.plugin.local_file_path('config_dialog.ui')
        self.B = gtk.Builder()
        self.B.set_translation_domain('gajim_plugins')
        self.B.add_from_file(self.GTK_BUILDER_FILE_PATH)

        try:
            self.disabled_accounts = self.plugin.config['DISABLED_ACCOUNTS']
        except KeyError:
            self.plugin.config['DISABLED_ACCOUNTS'] = []
            self.disabled_accounts = self.plugin.config['DISABLED_ACCOUNTS']

        log.debug('Disabled Accounts:')
        log.debug(self.disabled_accounts)

        self.qrcode = self.B.get_object('qrcode')

        self.fpr_model = self.B.get_object('fingerprint_store')
        self.device_model = self.B.get_object('deviceid_store')

        self.fpr_view = self.B.get_object('fingerprint_view')

        self.disabled_acc_store = self.B.get_object('disabled_account_store')
        self.account_store = self.B.get_object('account_store')

        self.active_acc_view = self.B.get_object('active_accounts_view')
        self.disabled_acc_view = self.B.get_object('disabled_accounts_view')

        self.child.pack_start(self.B.get_object('notebook1'))

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

        qr = QRCode(version=None, error_correction=2, box_size=4, border=1)
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
            state.store.setTrust(identity_key, TRUSTED)
            try:
                if self.plugin.ui_list[account]:
                    self.plugin.ui_list[account][jid]. \
                        refresh_auth_lock_icon()
            except:
                log.debug('UI not available')
            self.update_context_list()

        def on_no(identity_key):
            state.store.setTrust(identity_key, UNTRUSTED)
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
            pop.popup(None, None, None, event.button, event.time)

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
            fprs.append('%s: %s' % (jid, fpr[4:-5]))
        gtk.Clipboard().set_text('\n'.join(fprs))
        gtk.Clipboard(selection='PRIMARY').set_text('\n'.join(fprs))

    def update_context_list(self):
        self.fpr_model.clear()
        self.device_model.clear()
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
                                  .getPublicKey().serialize())
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
            fpr = binascii.hexlify(identity_key.getPublicKey().serialize())
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
        path = self.get_qrcode(
            gajim.get_jid_from_account(account), deviceid, ownfpr[2:])
        self.qrcode.set_from_pixbuf(gtk.gdk.pixbuf_new_from_file(path))


class FingerprintWindow(gtk.Dialog):
    def __init__(self, plugin, contact, parent, windowinstances,
                 groupchat=False):
        self.groupchat = groupchat
        self.contact = contact
        self.windowinstances = windowinstances
        self.account = self.contact.account.name
        self.plugin = plugin
        self.omemostate = self.plugin.get_omemo_state(self.account)
        self.own_jid = gajim.get_jid_from_account(self.account)
        gtk.Dialog.__init__(self,
                            title=('Fingerprints for %s') % contact.jid,
                            parent=parent,
                            flags=gtk.DIALOG_DESTROY_WITH_PARENT)
        close_button = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        close_button.connect('clicked', self.on_close_button_clicked)
        self.connect('delete-event', self.on_window_delete)

        self.GTK_BUILDER_FILE_PATH = \
            self.plugin.local_file_path('fpr_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.add_from_file(self.GTK_BUILDER_FILE_PATH)
        self.xml.set_translation_domain('gajim_plugins')

        self.fpr_model = self.xml.get_object('fingerprint_store')

        self.fpr_view = self.xml.get_object('fingerprint_view')
        self.fpr_view_own = self.xml.get_object('fingerprint_view_own')

        self.notebook = self.xml.get_object('notebook1')
        self.child.pack_start(self.notebook)

        self.xml.connect_signals(self)

        # Set own Fingerprint Label
        ownfpr = binascii.hexlify(self.omemostate.store.getIdentityKeyPair()
                                  .getPublicKey().serialize())
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
            state.store.setTrust(identity_key, TRUSTED)
            if not self.groupchat:
                self.plugin.ui_list[self.account][self.contact.jid]. \
                    refresh_auth_lock_icon()
            self.update_context_list()

        def on_no(identity_key):
            state.store.setTrust(identity_key, UNTRUSTED)
            if not self.groupchat:
                self.plugin.ui_list[self.account][self.contact.jid]. \
                    refresh_auth_lock_icon()
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
            pop.popup(None, None, None, event.button, event.time)

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
        gtk.Clipboard().set_text('\n'.join(fprs))
        gtk.Clipboard(selection='PRIMARY').set_text('\n'.join(fprs))

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
            fpr = binascii.hexlify(identity_key.getPublicKey().serialize())
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
