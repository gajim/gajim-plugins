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

import gtk
import nbxmpp
from common import gajim, ged

from plugins import GajimPlugin
from plugins.helpers import log, log_calls
from plugins.gui import GajimPluginConfigDialog
from common.connection_handlers_events import MessageOutgoingEvent

class AntiSpamPlugin(GajimPlugin):

    @log_calls('AntiSpamPlugin')
    def init(self):
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
        }

        # Temporary white list
        self.conference_white_list = []

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
        not gajim.contacts.get_contacts(obj.conn.name, obj.jid):
            log.info('discarding subscription request from %s' % obj.jid)
            return True

    @log_calls('AntiSpamPlugin')
    def _nec_decrypted_message_received_question(self, obj):
        if obj.mtype != 'chat':
            return False
        answer = self.config['msgtxt_answer']
        if len(answer) == 0:
            return False
        block_conference = self.config['antispam_for_conference']
        is_conference = gajim.contacts.is_gc_contact(obj.conn.name, obj.fjid)
        if not block_conference and is_conference:
            return False
        jid = obj.jid if not is_conference else obj.fjid
        # If we receive conference privat message or direct message from unknown user than
        # anti spam question will send in background mode, without any notification for us
        # There are two methods to see who wrote you and not passed filter:
        #     1. Using XML console
        #     2. Running Gajim with log info messages and see logs (probably gajim.log file)
        if is_conference or not gajim.contacts.get_contacts(obj.conn.name, jid):
            if obj.msgtxt != answer:
                if is_conference and self.conference_white_list.count(jid) > 0:
                    return False
                self.send_question(obj, jid)
                return True
            else:
                if is_conference and self.conference_white_list.count(jid) == 0:
                    self.conference_white_list.append(jid)
        return False

    def send_question(self, obj, jid):
        question = self.config['msgtxt_question']
        log.info('Anti_spam enabled for %s, question: %s', jid, question)
        message = _('Antispam enabled. Please answer the question: ') + question
        stanza = nbxmpp.Message(to=jid, body=message, typ='chat')
        gajim.connections[obj.conn.name].connection.send(stanza, now=True)
	
    def remove_xhtml(self, obj):
        html_node = obj.stanza.getTag('html')
        if html_node:
            obj.stanza.delChild(html_node)


class AntiSpamPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
            ['anti_spam_config_vbox'])
        self.config_vbox = self.xml.get_object('anti_spam_config_vbox')
        self.child.pack_start(self.config_vbox)

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
			