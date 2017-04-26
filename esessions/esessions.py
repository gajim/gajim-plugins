# -*- coding: utf-8 -*-

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

import dialogs
import gtkgui_helpers

from common import gajim
from common.connection_handlers_events import (
    FailedDecryptEvent, MamMessageReceivedEvent)
from plugins import GajimPlugin

log = logging.getLogger('gajim.plugin_system.esessions')

ERROR_MSG = ''
if not gajim.HAVE_PYCRYPTO:
    ERROR_MSG = 'Please install pycrypto'


class ESessionsPlugin(GajimPlugin):

    def init(self):
        """ Init """
        if ERROR_MSG:
            # self.activatable = False
            self.available_text = ERROR_MSG
        self.config_dialog = None
        self.encryption_name = 'ESessions'
        self.config_dialog = None
        self.gui_extension_points = {
            'decrypt': (self._message_received, None),
            'encrypt' + self.encryption_name: (self._encrypt_message, None),
            'send_message' + self.encryption_name: (
                self._before_sendmessage, None),
            'encryption_dialog' + self.encryption_name: (
                self.encryption_dialog, None),
            'encryption_state' + self.encryption_name: (
                self.encryption_state, None),
            'typing' + self.encryption_name: (
                self.typing, None)}

    def activate(self):
        pass

    def deactivate(self):
        pass

    @staticmethod
    def activate_encryption(chat_control):
        contact = chat_control.contact
        useable = contact.supports(nbxmpp.NS_ESESSION)
        if useable:
            chat_control.activate_esessions()
        return bool(useable)

    @staticmethod
    def encryption_dialog(chat_control):
        ESessionInfoWindow(chat_control.session,
                           chat_control.parent_win.window)

    @staticmethod
    def encryption_state(chat_control, state):
        session = chat_control.session
        if not session:
            return
        authenticated = chat_control.session.verified_identity
        state['authenticated'] = session and authenticated
        state['visible'] = True

    @staticmethod
    def typing(chat_control):
        contact = chat_control.contact
        enabled = chat_control.session.enable_encryption
        if contact.supports(nbxmpp.NS_ESESSION):
            if not (chat_control.session and enabled):
                if not chat_control.no_autonegotiation:
                    chat_control.activate_esessions()

    @staticmethod
    def _before_sendmessage(chat_control):
        enabled = chat_control.session.enable_encryption
        if not (chat_control.session and enabled):
            dialogs.ErrorDialog(
                _('No Session'),
                _('You have no valid Session with that contact.'))
            chat_control.sendmessage = False

    def _message_received(self, conn, obj, callback):
        if obj.encrypted:
            # Another Plugin already decrypted the message
            return
        if isinstance(obj, MamMessageReceivedEvent):
            # Esessions doesnt support MAM Messages
            return
        if obj.forwarded:
            # Esessions cant decrypt Carbon Copys
            return
        if obj.stanza.getTag('feature', namespace=nbxmpp.NS_FEATURE):
            if gajim.HAVE_PYCRYPTO:
                feature = obj.stanza.getTag(name='feature',
                                            namespace=nbxmpp.NS_FEATURE)
                form = nbxmpp.DataForm(node=feature.getTag('x'))
                if not form:
                    return

                if not form.getField('FORM_TYPE'):
                    return

                if form['FORM_TYPE'] == 'urn:xmpp:ssn':
                    obj.session.handle_negotiation(form)
                else:
                    reply = obj.stanza.buildReply()
                    reply.setType('error')
                    reply.addChild(feature)
                    err = nbxmpp.ErrorNode('service-unavailable', typ='cancel')
                    reply.addChild(node=err)
                    conn.connection.send(reply)
            return

        if obj.stanza.getTag('init', namespace=nbxmpp.NS_ESESSION_INIT):
            init = obj.stanza.getTag(name='init',
                                     namespace=nbxmpp.NS_ESESSION_INIT)
            form = nbxmpp.DataForm(node=init.getTag('x'))

            obj.session.handle_negotiation(form)
            return

        encrypted = obj.stanza.getTag(
            'c', namespace=nbxmpp.NS_STANZA_CRYPTO)
        if encrypted:
            try:
                obj.stanza = obj.session.decrypt_stanza(obj.stanza)
                obj.msgtxt = obj.stanza.getBody()
                obj.encrypted = 'ESessions'
                callback(obj)
            except Exception:
                gajim.nec.push_incoming_event(
                    FailedDecryptEvent(None, conn=conn, msg_obj=obj))
                return

    def _encrypt_message(self, conn, obj, callback):
        if obj.session.enable_encryption:
            obj.msg_iq = obj.session.encrypt_stanza(obj.msg_iq)
            obj.msg_iq.addChild(name='private', namespace=nbxmpp.NS_CARBONS)
            obj.msg_iq.addChild(name='no-permanent-store',
                                namespace=nbxmpp.NS_MSG_HINTS)
            obj.msg_iq.addChild(name='no-copy',
                                namespace=nbxmpp.NS_MSG_HINTS)
            eme_node = nbxmpp.Node('encryption',
                                   attrs={'xmlns': nbxmpp.NS_EME,
                                          'name': 'ESessions',
                                          'namespace': nbxmpp.NS_STANZA_CRYPTO})
            obj.msg_iq.addChild(node=eme_node)
        callback(obj)


class ESessionInfoWindow:
    """
    Class for displaying information about a XEP-0116 encrypted session
    """
    def __init__(self, session, transient_for=None):
        self.session = session

        self.xml = gtkgui_helpers.get_gtk_builder('esession_info_window.ui')
        self.xml.connect_signals(self)

        self.security_image = self.xml.get_object('security_image')
        self.verify_now_button = self.xml.get_object('verify_now_button')
        self.button_label = self.xml.get_object('verification_status_label')
        self.window = self.xml.get_object('esession_info_window')
        self.update_info()
        self.window.set_transient_for(transient_for)

        self.window.show_all()

    def get_sas(self):
        sas = ''
        if hasattr(self.session, 'sas'):
            sas = self.session.sas
        return sas

    def update_info(self):

        labeltext = _(
            '''Your chat session with <b>%(jid)s</b> is encrypted.\n\n
            This session's Short Authentication String is <b>%(sas)s</b>.
            ''') % {'jid': self.session.jid, 'sas': self.get_sas()}

        if self.session.verified_identity:
            labeltext += '\n\n' + _(
                '''You have already verified this contact's identity.''')
            security_image = 'security-high'
            if self.session.control:
                self.session.control.set_lock_image()

            verification_status = _('''Contact's identity verified''')
            self.window.set_title(verification_status)
            self.xml.get_object('verification_status_label').set_markup(
                '<b><span size="x-large">%s</span></b>' % verification_status)

            self.xml.get_object('dialog-action_area1').set_no_show_all(True)
            self.button_label.set_text(_('Verify again…'))
        else:
            if self.session.control:
                self.session.control.set_lock_image()
            labeltext += '\n\n' + _(
                '''To be certain that <b>only</b> the expected person can read
                your messages or send you messages, you need to verify their
                identity by clicking the button below.''')
            security_image = 'security-low'

            verification_status = _('''Contact's identity NOT verified''')
            self.window.set_title(verification_status)
            self.xml.get_object('verification_status_label').set_markup(
                '<b><span size="x-large">%s</span></b>' % verification_status)

            self.button_label.set_text(_('Verify…'))

        path = gtkgui_helpers.get_icon_path(security_image, 32)
        self.security_image.set_from_file(path)

        self.xml.get_object('info_display').set_markup(labeltext)

    def on_close_button_clicked(self, widget):
        self.window.destroy()

    def on_verify_now_button_clicked(self, widget):
        pritext = _('''Have you verified the contact's identity?''')
        sectext = _('''
            To prevent talking to an unknown person, you should
            speak to <b>%(jid)s</b> directly (in person or on the phone)
            and verify that they see the same Short Authentication String (SAS)
            as you.\n\n
            This session's Short Authentication String is <b>%(sas)s</b>.
            ''') % {'jid': self.session.jid, 'sas': self.get_sas()}
        sectext += '\n\n' + _(
            'Did you talk to the remote contact and verify the SAS?')

        def on_yes(checked):
            self.session._verified_srs_cb()
            self.session.verified_identity = True
            self.update_info()

        def on_no():
            self.session._unverified_srs_cb()
            self.session.verified_identity = False
            self.update_info()

        dialogs.YesNoDialog(pritext, sectext,
                            on_response_yes=on_yes,
                            on_response_no=on_no,
                            transient_for=self.window)
