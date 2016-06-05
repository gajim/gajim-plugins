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

import logging

import gtk
from common import gajim
from plugins.gui import GajimPluginConfigDialog
import gobject
import binascii

log = logging.getLogger('gajim.plugin_system.omemo')

TRUSTED = 1
UNTRUSTED = 0


class FingerprintButton(gtk.Button):
    def __init__(self, plugin, contact):
        super(FingerprintButton, self).__init__(label='Fingerprints')
        self.plugin = plugin
        self.contact = contact
        self.connect('clicked', self.on_click)

    def on_click(self, widget):
        dlg = FingerprintWindow(self.plugin, self.contact)
        if dlg.run() == gtk.RESPONSE_CLOSE:
            dlg.destroy()
        else:
            dlg.destroy()


class Checkbox(gtk.CheckButton):
    def __init__(self, plugin, chat_control, ui):
        super(Checkbox, self).__init__(label='OMEMO')
        self.chat_control = chat_control
        self.contact = chat_control.contact
        self.plugin = plugin
        self.connect('clicked', self.on_click)
        self.ui = ui

    def on_click(self, widget):
        enabled = self.get_active()
        if enabled:
            log.info(self.contact.account.name + ' ⇒ Enable OMEMO for ' +
                     self.contact.jid)
            self.plugin.omemo_enable_for(self.contact)
            self.ui.WarnIfUndecidedFingerprints()
            self.chat_control.print_conversation_line(
                u'OMEMO encryption enabled ', 'status', '', None)
        else:
            log.info(self.contact.account.name + ' ⇒ Disable OMEMO for ' +
                     self.contact.jid)
            self.plugin.omemo_disable_for(self.contact)
            self.ui.refreshAuthLockSymbol()
            self.chat_control.print_conversation_line(
                u'OMEMO encryption disabled', 'status', '', None)


def _add_widget(widget, chat_control):
    actions_hbox = chat_control.xml.get_object('actions_hbox')
    send_button = chat_control.xml.get_object('send_button')
    send_button_pos = actions_hbox.child_get_property(send_button, 'position')
    actions_hbox.add_with_properties(widget, 'position', send_button_pos - 2,
                                     'expand', False)
    widget.show_all()


class Ui(object):

    def __init__(self, plugin, chat_control, enabled, state):
        self.contact = chat_control.contact
        self.chat_control = chat_control
        self.checkbox = Checkbox(plugin, chat_control, self)
        self.finger_button = FingerprintButton(plugin, self.contact)
        self.state = state

        if enabled:
            self.checkbox.set_active(True)
        else:
            self.encryption_disable()

        _add_widget(self.checkbox, self.chat_control)
        _add_widget(self.finger_button, self.chat_control)

    def encryption_active(self):
        return self.checkbox.get_active()

    def encryption_disable(self):
        if self.checkbox.get_active():
            self.checkbox.set_active(False)
        else:
            log.info(self.contact.account.name + ' ⇒ Disable OMEMO for ' +
                     self.contact.jid)
            self.refreshAuthLockSymbol()
            self.chat_control.print_conversation_line(
                u'OMEMO encryption disabled', 'status', '', None)

    def activate_omemo(self):
        if not self.checkbox.get_active():
            self.checkbox.set_active(True)

    def plain_warning(self):
        self.chat_control.print_conversation_line(
            'Received plaintext message! ' +
            'Your next message will still be encrypted!', 'status', '', None)

    def WarnIfUndecidedFingerprints(self):
        if self.state.store.identityKeyStore.getUndecidedFingerprints(self.contact.jid):
            msg = "You received a new Fingerprint. " + \
                  "Until you make a trust decision you can only " + \
                  "receive encrypted Messages from that Device."
            self.chat_control.print_conversation_line(msg, 'status', '', None)
        self.refreshAuthLockSymbol()

    def refreshAuthLockSymbol(self):
        if self.encryption_active():
            if self.state.store.identityKeyStore.getUndecidedFingerprints(self.contact.jid):
                self.chat_control._show_lock_image(True, 'OMEMO', True, True,
                                                   False)
            else:
                self.chat_control._show_lock_image(True, 'OMEMO', True, True,
                                                   True)
        else:
            self.chat_control._show_lock_image(False, 'OMEMO', False, True,
                                               False)


class OMEMOConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = \
            self.plugin.local_file_path('config_dialog.ui')
        self.B = gtk.Builder()
        self.B.set_translation_domain('gajim_plugins')
        self.B.add_from_file(self.GTK_BUILDER_FILE_PATH)

        self.fpr_model = gtk.ListStore(gobject.TYPE_INT,
                                       gobject.TYPE_STRING,
                                       gobject.TYPE_STRING,
                                       gobject.TYPE_STRING)

        self.account_store = self.B.get_object('account_store')

        for account in sorted(gajim.contacts.get_accounts()):
            self.account_store.append(row=(account,))

        self.fpr_view = self.B.get_object('fingerprint_view')
        self.fpr_view.set_model(self.fpr_model)
        self.fpr_view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

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
        trust = {None: "Not Set", 0: False, 1: True, 2: "Undecided"}
        self.fpr_model.clear()
        active = self.B.get_object('account_combobox').get_active()
        account = self.account_store[active][0]
        state = self.plugin.get_omemo_state(account)

        ownfpr = binascii.hexlify(state.store.getIdentityKeyPair()
                                  .getPublicKey().serialize())
        ownfpr = self.human_hash(ownfpr[2:])
        self.B.get_object('fingerprint_label').set_markup('<tt>%s</tt>'
                                                          % ownfpr)

        fprDB = state.store.identityKeyStore.getAllFingerprints()
        for item in fprDB:
            _id, jid, fpr, tr = item
            fpr = binascii.hexlify(fpr)
            fpr = self.human_hash(fpr[2:])
            if trust[tr] is False:
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#FF0040">%s</span></tt>' % fpr))
            elif trust[tr] is True:
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#2EFE2E">%s</span></tt>' % fpr))
            elif trust[tr] == "Not Set":
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#FF0040">%s</span></tt>' % fpr))
            elif trust[tr] == "Undecided":
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#FF8000">%s</span></tt>' % fpr))

    def human_hash(self, fpr):
        fpr = fpr.upper()
        fplen = len(fpr)
        wordsize = fplen // 8
        buf = ''
        for w in range(0, fplen, wordsize):
            buf += '{0} '.format(fpr[w:w + wordsize])
        return buf.rstrip()


class FingerprintWindow(gtk.Dialog):
    def __init__(self, plugin, contact, parent=None):
        self.contact = contact
        gtk.Dialog.__init__(self,
                            title=('Fingerprints for %s') % contact.jid,
                            parent=parent,
                            flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                            buttons=(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE))
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

        self.child.pack_start(self.B.get_object('notebook1'))

        self.B.connect_signals(self)

        self.update_context_list()

    def trust_button_clicked_cb(self, button, *args):
        account = self.contact.account.name

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
                self.plugin.ui_list[account][self.contact.jid].refreshAuthLockSymbol()
                dlg.destroy()
            else:
                if response == gtk.RESPONSE_NO:
                    state.store.identityKeyStore.setTrust(_id, UNTRUSTED)
                    self.plugin.ui_list[account][self.contact.jid].refreshAuthLockSymbol()
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
        mod, paths = self.fpr_view.get_selection().get_selected_rows()

        fprs = []
        for path in paths:
            it = mod.get_iter(path)
            jid, fpr = mod.get(it, 1, 3)
            fprs.append('%s: %s' % (jid, fpr[31:-12]))
        gtk.Clipboard().set_text('\n'.join(fprs))
        gtk.Clipboard(selection='PRIMARY').set_text('\n'.join(fprs))

    def update_context_list(self):
        trust = {None: "Not Set", 0: False, 1: True, 2: "Undecided"}
        self.fpr_model.clear()
        state = self.plugin.get_omemo_state(self.contact.account.name)

        ownfpr = binascii.hexlify(state.store.getIdentityKeyPair()
                                  .getPublicKey().serialize())
        ownfpr = self.human_hash(ownfpr[2:])
        self.B.get_object('fingerprint_label').set_markup('<tt>%s</tt>'
                                                          % ownfpr)

        fprDB = state.store.identityKeyStore.getFingerprints(self.contact.jid)
        for item in fprDB:
            _id, jid, fpr, tr = item
            fpr = binascii.hexlify(fpr)
            fpr = self.human_hash(fpr[2:])
            if trust[tr] is False:
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#FF0040">%s</span></tt>' % fpr))
            elif trust[tr] is True:
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#2EFE2E">%s</span></tt>' % fpr))
            elif trust[tr] == "Not Set":
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#FF0040">%s</span></tt>' % fpr))
            elif trust[tr] == "Undecided":
                self.fpr_model.append((_id, jid, trust[tr],
                                       '<tt><span foreground="#FF8000">%s</span></tt>' % fpr))

    def human_hash(self, fpr):
        fpr = fpr.upper()
        fplen = len(fpr)
        wordsize = fplen // 8
        buf = ''
        for w in range(0, fplen, wordsize):
            buf += '{0} '.format(fpr[w:w + wordsize])
        return buf.rstrip()
