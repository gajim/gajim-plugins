# -*- coding: utf-8 -*-

## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##

'''
Block some incoming messages

:author: Yann Leboulanger <asterix@lagaule.org>
:since: 16 August 2012
:copyright: Copyright (2012) Yann Leboulanger <asterix@lagaule.org>
:license: GPLv3
'''

from gi.repository import Gtk
import nbxmpp
from gajim.common import app, ged

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log, log_calls
from gajim.plugins.gui import GajimPluginConfigDialog

class AntiSpamPlugin(GajimPlugin):

    @log_calls('AntiSpamPlugin')
    def init(self):
        self.description = _('Allows to block some kind of incoming messages')
        self.config_dialog = AntiSpamPluginConfigDialog(self)

        self.gui_extension_points = {
        }

        self.events_handlers = {
            'atom-entry-received': (ged.POSTCORE,
                self._nec_atom_entry_received),
            'message-received': (ged.PRECORE,
                self._nec_message_received_received),
            'decrypted-message-received': (ged.PRECORE,
                self._nec_decrypted_message_received_received),
            'subscribe-presence-received': (ged.POSTCORE,
                self._nec_subscribe_presence_received),
            'message-outgoing': (ged.OUT_PRECORE,
                self._nec_message_outgoing)
        }

        self.config_default_values = {
            'block_pubsub_messages': (False, 'If True, Gajim will block incoming messages from pubsub.'),
            'disable_xhtml_muc': (False, ''),
            'disable_xhtml_pm': (False, ''),
            'block_subscription_requests': (False, ''),
            'msgtxt_limit': (-1, ''),
            'msgtxt_question': ('Please answer: 12 x 12 =', ''),
            'msgtxt_answer': ('', ''),
            'antispam_for_conference': (False, ''),
            'conference_white_list': ([], ''), # conference private chat jid's
        }

        # List of outgoing jid's
        # Needs to avoid chat of two anti spam plugins
        # Contain all jid's where are you initiate a chat
        self.outgoing_jids = []

    @log_calls('AntiSpamPlugin')
    def _nec_atom_entry_received(self, obj):
        if self.config['block_pubsub_messages']:
            log.info('discarding pubdubd message')
            return True

    @log_calls('AntiSpamPlugin')
    def _nec_message_received_received(self, obj):
        if self.config['disable_xhtml_muc'] and obj.mtype == 'groupchat':
            self.remove_xhtml(obj)
        if self.config['disable_xhtml_pm'] and obj.gc_control and \
        obj.resource and obj.mtype == 'chat':
            self.remove_xhtml(obj)
        return False

    @log_calls('AntiSpamPlugin')
    def _nec_decrypted_message_received_received(self, obj):
        if not obj.msgtxt:
            return False
        if self._nec_decrypted_message_received_question(obj):
            return True
        limit = self.config['msgtxt_limit']
        if limit > -1 and len(obj.msgtxt) > limit:
            return True
        return False

    @log_calls('AntiSpamPlugin')
    def _nec_subscribe_presence_received(self, obj):
        if self.config['block_subscription_requests'] and \
        not app.contacts.get_contacts(obj.conn.name, obj.jid):
            log.info('discarding subscription request from %s' % obj.jid)
            return True

    @log_calls('AntiSpamPlugin')
    def _nec_decrypted_message_received_question(self, obj):
        if obj.mtype != 'chat' and obj.mtype != 'normal':
            return False

        tjid = obj.jid if obj.mtype == 'normal' else obj.fjid
        if tjid in self.outgoing_jids:
            return False
        
        answer = self.config['msgtxt_answer']
        if len(answer) == 0:
            return False
        block_conference = self.config['antispam_for_conference']
        is_conference = app.contacts.is_gc_contact(obj.conn.name, obj.fjid)
        if not block_conference and is_conference:
            return False
        jid = obj.jid if not is_conference else obj.fjid
        # If we receive conference privat message or direct message from unknown user than
        # anti spam question will send in background mode, without any notification for us
        # There are two methods to see who wrote you and not passed filter:
        #     1. Using XML console
        #     2. Running Gajim with log info messages and see logs (probably gajim.log file)
        if is_conference or not app.contacts.get_contacts(obj.conn.name, jid):
            if not self.contain_answer(obj.msgtxt, answer):
                if is_conference and jid in self.config['conference_white_list']:
                    return False
                self.send_question(obj, jid)
                return True
            else:
                if is_conference and jid not in self.config['conference_white_list']:
                    self.config['conference_white_list'].append(jid)
                    # Need to save because 'append' method does not implement __setitem__ method
                    self.config.save()
        return False

    @log_calls('AntiSpamPlugin')
    def _nec_message_outgoing(self, obj):
        if obj.type_ != 'chat' and obj.type_ != 'normal':
            return
        
        if isinstance(obj.jid, list):
            for i in obj.jid:
                if i not in self.outgoing_jids:
                    self.outgoing_jids.append(i)
        else:
            if obj.jid not in self.outgoing_jids:
                self.outgoing_jids.append(obj.jid)
               
    def send_question(self, obj, jid):
        if obj.mtype != 'chat' and obj.mtype != 'normal':
            log.info('Anti_spam wrong message type: %s', obj.mtype)
            return

        # only for 'chat' messages
        if obj.receipt_request_tag and obj.mtype == 'chat':
            receipt = nbxmpp.Message(to=obj.fjid, typ='chat')
            receipt.setTag('received', namespace='urn:xmpp:receipts', attrs={'id': obj.id_})
            if obj.thread_id:
                receipt.setThread(obj.thread_id)
            app.connections[obj.conn.name].connection.send(receipt, now=True)
        question = self.config['msgtxt_question']
        log.info('Anti_spam enabled for %s, question: %s', jid, question)
        message = _('Antispam enabled. Please answer the question. The message must only ' + \
                    'contain the answer. (Messages sent before the correct answer, will be lost): ') \
                    + question

        if obj.mtype == 'chat':
            stanza = nbxmpp.Message(to=jid, body=message, typ=obj.mtype)
        else: # for 'normal' type
            stanza = nbxmpp.Message(to=jid, body=message, subject='Antispam enabled', typ=obj.mtype)

        app.connections[obj.conn.name].connection.send(stanza, now=True)

    def contain_answer(self, msg, answer):
        return answer in msg.split('\n')
	
    def remove_xhtml(self, obj):
        html_node = obj.stanza.getTag('html')
        if html_node:
            obj.stanza.delChild(html_node)


class AntiSpamPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
            ['anti_spam_config_vbox'])
        self.config_vbox = self.xml.get_object('anti_spam_config_vbox')
        self.get_child().pack_start(self.config_vbox, True, True, 0)

        self.block_pubsub_messages_checkbutton = self.xml.get_object(
            'block_pubsub_messages_checkbutton')

        self.xml.connect_signals(self)

    def on_run(self):
        self.block_pubsub_messages_checkbutton.set_active(self.plugin.config[
            'block_pubsub_messages'])
        widget = self.xml.get_object('disable_xhtml_muc_checkbutton')
        widget.set_active(self.plugin.config['disable_xhtml_muc'])
        widget = self.xml.get_object('disable_xhtml_pm_checkbutton')
        widget.set_active(self.plugin.config['disable_xhtml_pm'])
        widget = self.xml.get_object('block_subscription_requests_checkbutton')
        widget.set_active(self.plugin.config['block_subscription_requests'])
        widget = self.xml.get_object('message_size_limit_entry')
        widget.set_text(str(self.plugin.config['msgtxt_limit']))
        widget = self.xml.get_object('antispam_question')
        widget.set_text(str(self.plugin.config['msgtxt_question']))
        widget = self.xml.get_object('antispam_answer')
        widget.set_text(str(self.plugin.config['msgtxt_answer']))
        widget = self.xml.get_object('antispam_for_conference')
        widget.set_active(self.plugin.config['antispam_for_conference'])

    def on_block_pubsub_messages_checkbutton_toggled(self, button):
        self.plugin.config['block_pubsub_messages'] = button.get_active()

    def on_disable_xhtml_muc_checkbutton_toggled(self, button):
        self.plugin.config['disable_xhtml_muc'] = button.get_active()

    def on_disable_xhtml_pm_checkbutton_toggled(self, button):
        self.plugin.config['disable_xhtml_pm'] = button.get_active()

    def on_block_subscription_requests_checkbutton_toggled(self, button):
        self.plugin.config['block_subscription_requests'] = button.get_active()

    def on_message_size_limit_entry_changed(self, entry):
        try:
            self.plugin.config['msgtxt_limit'] = int(entry.get_text())
        except Exception:
            pass
			
    def on_message_question_entry_changed(self, entry):
        try:
            self.plugin.config['msgtxt_question'] = entry.get_text()
        except Exception:
            pass
			
    def on_message_answer_entry_changed(self, entry):
        try:
            self.plugin.config['msgtxt_answer'] = entry.get_text()
        except Exception:
            pass

    def on_antispam_for_conference_checkbutton_toggled(self, button):
        self.plugin.config['antispam_for_conference'] = button.get_active()
			
