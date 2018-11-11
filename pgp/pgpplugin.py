'''
Copyright 2017 Philipp Hörist <philipp@hoerist.com>

This file is part of Gajim.

Gajim is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; version 3 only.

Gajim is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Gajim. If not, see <http://www.gnu.org/licenses/>.
'''

import os
import logging
import time
import threading
import queue

import nbxmpp
from gi.repository import GLib

from gajim.common import app
from gajim.common.connection_handlers_events import MessageNotSentEvent
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from gajim.gtk.dialogs import ErrorDialog
from gajim.gtk.dialogs import InformationDialog
from gajim.gtk.dialogs import YesNoDialog

log = logging.getLogger('gajim.plugin_system.oldpgp')

ERROR_MSG = ''
if not app.is_installed('GPG'):
    if os.name == 'nt':
        ERROR_MSG = _('Please install GnuPG / Gpg4win')
    else:
        ERROR_MSG = _('Please install python-gnupg and PGP')

ALLOWED_TAGS = [('request', nbxmpp.NS_RECEIPTS),
                ('active', nbxmpp.NS_CHATSTATES),
                ('gone', nbxmpp.NS_CHATSTATES),
                ('inactive', nbxmpp.NS_CHATSTATES),
                ('paused', nbxmpp.NS_CHATSTATES),
                ('composing', nbxmpp.NS_CHATSTATES),
                ('no-store', nbxmpp.NS_MSG_HINTS),
                ('store', nbxmpp.NS_MSG_HINTS),
                ('no-copy', nbxmpp.NS_MSG_HINTS),
                ('no-permanent-store', nbxmpp.NS_MSG_HINTS),
                ('replace', nbxmpp.NS_CORRECT),
                ('origin-id', nbxmpp.NS_SID),
                ]


class OldPGPPlugin(GajimPlugin):

    def init(self):
        self.description = _('PGP encryption as per XEP-0027')
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            return
        self.config_dialog = None
        self.encryption_name = 'PGP'
        self.allow_zeroconf = True
        self.gui_extension_points = {
            'encrypt' + self.encryption_name: (self._encrypt_message, None),
            'decrypt': (self._message_received, None),
            'send_message' + self.encryption_name: (
                self._before_sendmessage, None),
            'encryption_dialog' + self.encryption_name: (
                self.on_encryption_button_clicked, None),
            'encryption_state' + self.encryption_name: (
                self.encryption_state, None)}

        self.decrypt_queue = queue.Queue()
        self.thread = None

    def get_gpg(self, account):
        return app.connections[account].gpg

    def activate(self):
        pass

    def deactivate(self):
        pass

    @staticmethod
    def activate_encryption(chat_control):
        return True

    @staticmethod
    def encryption_state(chat_control, state):
        key_id = chat_control.contact.keyID
        account = chat_control.account
        authenticated, _ = check_state(key_id, account)
        state['visible'] = True
        state['authenticated'] = authenticated

    @staticmethod
    def on_encryption_button_clicked(chat_control):
        account = chat_control.account
        key_id = chat_control.contact.keyID
        transient = chat_control.parent_win.window
        authenticated, info = check_state(key_id, account)
        InformationDialog(authenticated, info, transient)

    @staticmethod
    def _before_sendmessage(chat_control):
        account = chat_control.account
        if not chat_control.contact.keyID:
            ErrorDialog(
                _('No OpenPGP key assigned'),
                _('No OpenPGP key is assigned to this contact. So you cannot '
                  'encrypt messages with OpenPGP.'))
            chat_control.sendmessage = False
        elif not app.config.get_per('accounts', account, 'keyid'):
            ErrorDialog(
                _('No OpenPGP key assigned'),
                _('No OpenPGP key is assigned to your account. So you cannot '
                  'encrypt messages with OpenPGP.'))
            chat_control.sendmessage = False

    @staticmethod
    def _get_info_message():
        msg = '[This message is *encrypted* (See :XEP:`27`]'
        lang = os.getenv('LANG')
        if lang is not None and not lang.startswith('en'):
            # we're not english: one in locale and one en
            msg = _('[This message is *encrypted* (See :XEP:`27`]') + \
                    ' (' + msg + ')'
        return msg

    def _message_received(self, conn, obj, callback):
        if obj.encrypted:
            # Another Plugin already decrypted the message
            return
        account = conn.name
        if obj.name == 'message-received':
            enc_tag = obj.stanza.getTag('x', namespace=nbxmpp.NS_ENCRYPTED)
        elif obj.name == 'mam-message-received':
            # Compatibility for Gajim 1.0.3
            if hasattr(obj, 'message'):
                message = obj.message
            else:
                message = obj.msg_
            enc_tag = message.getTag('x', namespace=nbxmpp.NS_ENCRYPTED)
        else:
            return
        if enc_tag:
            encmsg = enc_tag.getData()
            key_id = app.config.get_per('accounts', account, 'keyid')
            if key_id:
                obj.encrypted = self.encryption_name
                self.add_additional_data(obj.additional_data)
                self.decrypt_queue.put([encmsg, key_id, obj, conn, callback])
                if not self.thread:
                    self.thread = threading.Thread(target=self.worker)
                    self.thread.start()
                return

    def worker(self):
        while True:
            try:
                item = self.decrypt_queue.get(block=False)
                encmsg, key_id, obj, conn, callback = item
                account = conn.name
                decmsg = self.get_gpg(account).decrypt(encmsg, key_id)
                decmsg = conn.connection.Dispatcher. \
                    replace_non_character(decmsg)
                # \x00 chars are not allowed in C (so in GTK)
                msg = decmsg.replace('\x00', '')
                obj.msgtxt = msg
                GLib.idle_add(callback, obj)
            except queue.Empty:
                self.thread = None
                break

    def _encrypt_message(self, conn, obj, callback):
        account = conn.name
        if not obj.message:
            # We only encrypt the actual message
            self._finished_encrypt(obj, callback=callback)
            return

        if obj.keyID == 'UNKNOWN':
            error = _('Neither the remote presence is signed, nor a key was '
                      'assigned.')
        elif obj.keyID.endswith('MISMATCH'):
            error = _('The contact\'s key (%s) does not match the key assigned '
                      'in Gajim.' % obj.keyID[:8])
        else:
            my_key_id = app.config.get_per('accounts', account, 'keyid')
            key_list = [obj.keyID, my_key_id]

            def _on_encrypted(output):
                msgenc, error = output
                if error.startswith('NOT_TRUSTED'):
                    def on_yes(checked):
                        if checked:
                            obj.conn.gpg.always_trust.append(obj.keyID)
                        app.thread_interface(
                            self.get_gpg(account).encrypt,
                            [obj.message, key_list, True],
                            _on_encrypted, [])

                    def on_no():
                        self._finished_encrypt(
                            obj, msgenc=msgenc, error=error, conn=conn)

                    YesNoDialog(
                        _('Untrusted OpenPGP key'),
                        _('The OpenPGP key used to encrypt this chat is not '
                          'trusted. Do you really want to encrypt this '
                          'message?'),
                        checktext=_('_Do not ask me again'),
                        on_response_yes=on_yes,
                        on_response_no=on_no)
                else:
                    self._finished_encrypt(
                        obj, msgenc=msgenc, error=error, conn=conn,
                        callback=callback)
            app.thread_interface(
                self.get_gpg(account).encrypt,
                [obj.message, key_list, False],
                _on_encrypted, [])
            return
        self._finished_encrypt(conn, obj, error=error)

    def _finished_encrypt(self, obj, msgenc=None, error=None,
                          conn=None, callback=None):
        if error:
            log.error('python-gnupg error: %s', error)
            app.nec.push_incoming_event(
                MessageNotSentEvent(
                    None, conn=conn, jid=obj.jid, message=obj.message,
                    error=error, time_=time.time(), session=obj.session))
            return

        self.cleanup_stanza(obj)

        if msgenc:
            obj.msg_iq.setBody(self._get_info_message())
            obj.msg_iq.setTag(
                'x', namespace=nbxmpp.NS_ENCRYPTED).setData(msgenc)
            eme_node = nbxmpp.Node('encryption',
                                   attrs={'xmlns': nbxmpp.NS_EME,
                                          'namespace': nbxmpp.NS_ENCRYPTED})
            obj.msg_iq.addChild(node=eme_node)

            # Set xhtml to None so it doesnt get logged
            obj.xhtml = None
            obj.encrypted = self.encryption_name
            self.add_additional_data(obj.additional_data)
            print_msg_to_log(obj.msg_iq)

        callback(obj)

    def encrypt_file(self, file, account, callback):
        thread = threading.Thread(target=self._encrypt_file_thread,
                                  args=(file, account, callback))
        thread.daemon = True
        thread.start()

    def _encrypt_file_thread(self, file, account, callback):
        my_key_id = app.config.get_per('accounts', account, 'keyid')
        key_list = [file.contact.keyID, my_key_id]

        encrypted = self.get_gpg(account).encrypt_file(file.get_data(), key_list)
        if not encrypted:
            GLib.idle_add(self._on_file_encryption_error, file, encrypted.status)
            return

        file.encrypted = True
        file.size = len(encrypted.data)
        file.path += '.pgp'
        file.data = encrypted.data
        if file.event.isSet():
            return
        GLib.idle_add(callback, file)

    @staticmethod
    def _on_file_encryption_error(file, error):
        ErrorDialog(_('Error'), error)

    @staticmethod
    def cleanup_stanza(obj):
        ''' We make sure only allowed tags are in the stanza '''
        stanza = nbxmpp.Message(
            to=obj.msg_iq.getTo(),
            typ=obj.msg_iq.getType())
        stanza.setID(obj.stanza_id)
        stanza.setThread(obj.msg_iq.getThread())
        for tag, ns in ALLOWED_TAGS:
            node = obj.msg_iq.getTag(tag, namespace=ns)
            if node:
                stanza.addChild(node=node)
        obj.msg_iq = stanza

    def add_additional_data(self, data):
        data['encrypted'] = {'name': self.encryption_name}


def print_msg_to_log(stanza):
    """ Prints a stanza in a fancy way to the log """
    stanzastr = '\n' + stanza.__str__(fancy=True) + '\n'
    stanzastr = stanzastr[0:-1]
    log.debug('\n' + '-'*15 + stanzastr + '-'*15)


def check_state(key_id, account):
    error = None
    if key_id.endswith('MISMATCH'):
        verification_status = _('''Contact's identity NOT verified''')
        info = _('The contact\'s key (%s) <b>does not match</b> the key '
                 'assigned in Gajim.') % key_id[:8]
    elif not key_id:
        # No key assigned nor a key is used by remote contact
        verification_status = _('No OpenPGP key assigned')
        info = _('No OpenPGP key is assigned to this contact. So you cannot'
                 ' encrypt messages.')
    else:
        error = app.connections[account].gpg.encrypt('test', [key_id])[1]
        if error:
            verification_status = _('''Contact's identity NOT verified''')
            info = _('OpenPGP key is assigned to this contact, but <b>you '
                     'do not trust their key</b>, so message <b>cannot</b> be '
                     'encrypted. Use your OpenPGP client to trust their key.')
        else:
            verification_status = _('''Contact's identity verified''')
            info = _('OpenPGP Key is assigned to this contact, and you '
                     'trust their key, so messages will be encrypted.')
    return (verification_status, info)
