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
        self.description = _('Allows to block some kind of incoming messages')
        self.config_dialog = AntiSpamPluginConfigDialog(self)

        self.gui_extension_points = {
        }

        self.events_handlers = {
            'atom-entry-received': (ged.POSTCORE,
                self._nec_atom_entry_received),
        }

        self.config_default_values = {
            'block_pubsub_messages': (False, 'If True, Gajim will block incoming messages from pubsub.'),
        }

    @log_calls('AntiSpamPlugin')
    def _nec_atom_entry_received(self, obj):
        if self.config['block_pubsub_messages']:
            log.info('discarding pubdubd message')
            return True

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

    def on_block_pubsub_messages_checkbutton_toggled(self, button):
        self.plugin.config['block_pubsub_messages'] = button.get_active()
