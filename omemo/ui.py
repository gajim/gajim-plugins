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

import gobject
import gtk

# pylint: disable=import-error
import gtkgui_helpers
from common import gajim
from plugins.gui import GajimPluginConfigDialog
# pylint: enable=import-error

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

        self.display_omemo_state()
        self.refreshAuthLockSymbol()

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

            # at index 8 is the separator after the esession encryption entry
            menu.insert(item, 8)
            return menu
        self.chat_control.prepare_context_menu = omemo_prepare_context_menu

        # Hook into Send Button so we can check Stuff before sending
        self.chat_control.orig_send_message = \
            self.chat_control.send_message

        def omemo_send_message(message, keyID='', chatstate=None, xhtml=None,
                               process_commands=True, attention=False):

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
            self.WarnIfUndecidedFingerprints()  # calls refreshAuthLockSymbol()
        else:
            log.debug(self.contact.account.name + ' => Disable OMEMO for ' +
                      self.contact.jid)
            self.plugin.omemo_disable_for(self.contact)
            self.refreshAuthLockSymbol()

        self.omemobutton.set_omemo_state(enabled)
        self.display_omemo_state()

    def encryption_active(self):
        return self.state.encryption.is_active(self.contact.jid)

    def activate_omemo(self):
        if not self.encryption_active():
            self.set_omemo_state(True)

    def new_fingerprints_available(self):
        fingerprints = self.state.store.getNewFingerprints(self.contact.jid)
        if fingerprints:
            self.show_fingerprint_window(fingerprints)

    def show_fingerprint_window(self, fingerprints=None):
        if 'dialog' not in self.windowinstances:
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

    def WarnIfUndecidedFingerprints(self):
        if self.state.store.identityKeyStore. \
                getUndecidedFingerprints(self.contact.jid):
            msg = "You received a new Fingerprint. " \
                  "Until you make a trust decision you can only " \
                  "receive encrypted Messages from that Device."
            self.chat_control.print_conversation_line(msg, 'status', '', None)
        self.refreshAuthLockSymbol()

    def no_trusted_fingerprints_warning(self):
        msg = "To send an encrypted message, you have to " \
                          "first trust the fingerprint of your contact!"
        self.chat_control.print_conversation_line(msg, 'status', '', None)

    def refreshAuthLockSymbol(self):
        if self.encryption_active():
            if self.state.store.identityKeyStore. \
                    getUndecidedFingerprints(self.contact.jid):
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

        self.fpr_model = gtk.ListStore(gobject.TYPE_INT,
                                       gobject.TYPE_STRING,
                                       gobject.TYPE_STRING,
                                       gobject.TYPE_STRING)

        self.device_model = gtk.ListStore(gobject.TYPE_STRING)

        self.account_store = self.B.get_object('account_store')

        for account in sorted(gajim.contacts.get_accounts()):
            self.account_store.append(row=(account,))

        self.fpr_view = self.B.get_object('fingerprint_view')
        self.fpr_view.set_model(self.fpr_model)
        self.fpr_view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        self.device_view = self.B.get_object('deviceid_view')
        self.device_view.set_model(self.device_model)

        if len(self.account_store) > 0:
            self.B.get_object('account_combobox').set_active(0)

        self.child.pack_start(self.B.get_object('notebook1'))

        self.B.connect_signals(self)

    def on_run(self):
        self.update_context_list()
        self.account_combobox_changed_cb(self.B.get_object('account_combobox'))

    def account_combobox_changed_cb(self, box, *args):
        self.update_context_list()

    def trust_button_clicked_cb(self, button, *args):
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]

        state = self.plugin.get_omemo_state(account)

        mod, paths = self.fpr_view.get_selection().get_selected_rows()

        for path in paths:
            it = mod.get_iter(path)
            _id, user, fpr = mod.get(it, 0, 1, 3)
            fpr = fpr[31:-12]
            dlg = gtk.Dialog('Confirm trusting fingerprint', self,
                             gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                             (gtk.STOCK_YES, gtk.RESPONSE_YES,
                              gtk.STOCK_NO, gtk.RESPONSE_NO))
            l = gtk.Label()
            l.set_markup('Do you want to trust the following '
                         'fingerprint for the contact <b>%s</b> on the account <b>%s</b>?'
                         '\n\n<tt>%s</tt>' % (user, account, fpr))
            l.set_line_wrap(True)
            dlg.vbox.pack_start(l)
            dlg.show_all()

            response = dlg.run()
            if response == gtk.RESPONSE_YES:
                state.store.identityKeyStore.setTrust(_id, TRUSTED)
                try:
                    if self.plugin.ui_list[account]:
                        self.plugin.ui_list[account][user].refreshAuthLockSymbol()
                except:
                    dlg.destroy()
            else:
                if response == gtk.RESPONSE_NO:
                    state.store.identityKeyStore.setTrust(_id, UNTRUSTED)
                    try:
                        if user in self.plugin.ui_list[account]:
                            self.plugin.ui_list[account][user].refreshAuthLockSymbol()
                    except:
                        dlg.destroy()

        self.update_context_list()

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
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]
        state = self.plugin.get_omemo_state(account)

        ownfpr = binascii.hexlify(state.store.getIdentityKeyPair()
                                  .getPublicKey().serialize())
        ownfpr = self.human_hash(ownfpr[2:])
        self.B.get_object('fingerprint_label').set_markup('<tt>%s</tt>'
                                                          % ownfpr)

        fprDB = state.store.identityKeyStore.getAllFingerprints()
        activeSessions = state.store.sessionStore. \
            getAllActiveSessionsKeys()
        for item in fprDB:
            _id, jid, fpr, tr = item
            active = fpr in activeSessions
            fpr = binascii.hexlify(fpr)
            fpr = self.human_hash(fpr[2:])
            if tr == UNTRUSTED:
                if active:
                    self.fpr_model.append((_id, jid, 'False',
                                           '<tt><span foreground="#FF0040">%s</span></tt>' % fpr))
                else:
                    self.fpr_model.append((_id, jid, 'False',
                                           '<tt><span foreground="#585858">%s</span></tt>' % fpr))
            elif tr == TRUSTED:
                if active:
                    self.fpr_model.append((_id, jid, 'True',
                                           '<tt><span foreground="#2EFE2E">%s</span></tt>' % fpr))
                else:
                    self.fpr_model.append((_id, jid, 'True',
                                           '<tt><span foreground="#585858">%s</span></tt>' % fpr))
            else:
                if active:
                    self.fpr_model.append((_id, jid, 'Undecided',
                                           '<tt><span foreground="#FF8000">%s</span></tt>' % fpr))
                else:
                    self.fpr_model.append((_id, jid, 'Undecided',
                                           '<tt><span foreground="#585858">%s</span></tt>' % fpr))

        for item in state.own_devices:
            self.device_model.append([item])

    def human_hash(self, fpr):
        fpr = fpr.upper()
        fplen = len(fpr)
        wordsize = fplen // 8
        buf = ''
        for w in range(0, fplen, wordsize):
            buf += '{0} '.format(fpr[w:w + wordsize])
        return buf.rstrip()


class FingerprintWindow(gtk.Dialog):
    def __init__(self, plugin, contact, parent, windowinstances):
        self.contact = contact
        self.windowinstances = windowinstances
        gtk.Dialog.__init__(self,
                            title=('Fingerprints for %s') % contact.jid,
                            parent=parent,
                            flags=gtk.DIALOG_DESTROY_WITH_PARENT)
        close_button = self.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
        close_button.connect('clicked', self.on_close_button_clicked)
        self.connect('delete-event', self.on_window_delete)
        self.plugin = plugin
        self.GTK_BUILDER_FILE_PATH = \
            self.plugin.local_file_path('fpr_dialog.ui')
        self.B = gtk.Builder()
        self.B.set_translation_domain('gajim_plugins')
        self.B.add_from_file(self.GTK_BUILDER_FILE_PATH)

        self.fpr_model = gtk.ListStore(gobject.TYPE_INT,
                                       gobject.TYPE_STRING,
                                       gobject.TYPE_STRING,
                                       gobject.TYPE_STRING)

        self.fpr_view = self.B.get_object('fingerprint_view')
        self.fpr_view.set_model(self.fpr_model)
        self.fpr_view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        self.fpr_view_own = self.B.get_object('fingerprint_view_own')
        self.fpr_view_own.set_model(self.fpr_model)
        self.fpr_view_own.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        self.notebook = self.B.get_object('notebook1')

        self.child.pack_start(self.notebook)

        self.B.connect_signals(self)

        self.account = self.contact.account.name
        self.omemostate = self.plugin.get_omemo_state(self.account)

        ownfpr = binascii.hexlify(self.omemostate.store.getIdentityKeyPair()
                                  .getPublicKey().serialize())
        ownfpr = self.human_hash(ownfpr[2:])

        self.B.get_object('fingerprint_label_own').set_markup('<tt>%s</tt>'
                                                              % ownfpr)

        self.update_context_list()

    def on_close_button_clicked(self, widget):
        del self.windowinstances['dialog']
        self.hide()

    def on_window_delete(self, widget, event):
        del self.windowinstances['dialog']
        self.hide()

    def trust_button_clicked_cb(self, button, *args):
        if self.notebook.get_current_page() == 1:
            mod, paths = self.fpr_view_own.get_selection().get_selected_rows()
        else:
            mod, paths = self.fpr_view.get_selection().get_selected_rows()

        for path in paths:
            it = mod.get_iter(path)
            _id, user, fpr = mod.get(it, 0, 1, 3)
            fpr = fpr[31:-12]
            dlg = gtk.Dialog('Confirm trusting fingerprint', self,
                             gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                             (gtk.STOCK_YES, gtk.RESPONSE_YES,
                              gtk.STOCK_NO, gtk.RESPONSE_NO))
            l = gtk.Label()
            l.set_markup('Do you want to trust the following '
                         'fingerprint for the contact <b>%s</b> '
                         'on the account <b>%s</b>?'
                         '\n\n<tt>%s</tt>' % (user, self.account, fpr))
            l.set_line_wrap(True)
            dlg.vbox.pack_start(l)
            dlg.show_all()
            response = dlg.run()
            if response == gtk.RESPONSE_YES:
                self.omemostate.store.identityKeyStore.setTrust(_id, TRUSTED)
                self.plugin.ui_list[self.account][self.contact.jid]. \
                    refreshAuthLockSymbol()
                dlg.destroy()
            else:
                if response == gtk.RESPONSE_NO:
                    self.omemostate.store.identityKeyStore.setTrust(_id, UNTRUSTED)
                    self.plugin.ui_list[self.account][self.contact.jid]. \
                        refreshAuthLockSymbol()
            dlg.destroy()

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

        if self.notebook.get_current_page() == 1:
            jid = gajim.get_jid_from_account(self.account)
        else:
            jid = self.contact.jid

        fprDB = self.omemostate.store.identityKeyStore.getFingerprints(jid)
        activeSessions = self.omemostate.store.sessionStore. \
            getActiveSessionsKeys(jid)

        for item in fprDB:
            _id, jid, fpr, tr = item
            active = fpr in activeSessions
            fpr = binascii.hexlify(fpr)
            fpr = self.human_hash(fpr[2:])
            if tr == UNTRUSTED:
                if active:
                    self.fpr_model.append((_id, jid, 'False',
                                           '<tt><span foreground="#FF0040">%s</span></tt>' % fpr))
                else:
                    self.fpr_model.append((_id, jid, 'False',
                                           '<tt><span foreground="#585858">%s</span></tt>' % fpr))
            elif tr == TRUSTED:
                if active:
                    self.fpr_model.append((_id, jid, 'True',
                                           '<tt><span foreground="#2EFE2E">%s</span></tt>' % fpr))
                else:
                    self.fpr_model.append((_id, jid, 'True',
                                           '<tt><span foreground="#585858">%s</span></tt>' % fpr))
            else:
                if active:
                    self.fpr_model.append((_id, jid, 'Undecided',
                                           '<tt><span foreground="#FF8000">%s</span></tt>' % fpr))
                else:
                    self.fpr_model.append((_id, jid, 'Undecided',
                                           '<tt><span foreground="#585858">%s</span></tt>' % fpr))

    def human_hash(self, fpr):
        fpr = fpr.upper()
        fplen = len(fpr)
        wordsize = fplen // 8
        buf = ''
        for w in range(0, fplen, wordsize):
            buf += '{0} '.format(fpr[w:w + wordsize])
        return buf.rstrip()
