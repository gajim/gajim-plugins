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
from common import ged

from plugins import GajimPlugin
from plugins.helpers import log, log_calls
from plugins.gui import GajimPluginConfigDialog

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
        }

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
