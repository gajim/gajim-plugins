# Copyright (C) 2008 Mateusz Biliński <mateusz AT bilinski.it>
# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Acronyms Expander.
#
# Acronyms Expander is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Acronyms Expander is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Acronyms Expander. If not, see <http://www.gnu.org/licenses/>.

import json
import logging
from pathlib import Path
from functools import partial

from gi.repository import GLib

from gajim.common import app
from gajim.common import configpaths

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from acronyms_expander.acronyms import DEFAULT_DATA
from acronyms_expander.gtk.config import ConfigDialog

log = logging.getLogger('gajim.p.acronyms')


class AcronymsExpanderPlugin(GajimPlugin):
    def init(self):
        self.description = _('Replaces acronyms (or other strings) '
                             'with given expansions/substitutes.')
        self.config_dialog = partial(ConfigDialog, self)
        self.gui_extension_points = {
            'chat_control_base': (self._connect, self._disconnect)
        }
        self._invoker = ' '
        self._replace_in_progress = False
        self._handler_ids = {}

        self.acronyms = self._load_acronyms()

    @staticmethod
    def _load_acronyms():
        try:
            data_path = Path(configpaths.get('PLUGINS_DATA'))
        except KeyError:
            # PLUGINS_DATA was added in 1.0.99.1
            return DEFAULT_DATA

        path = data_path / 'acronyms' / 'acronyms'
        if not path.exists():
            return DEFAULT_DATA

        with path.open('r') as file:
            acronyms = json.load(file)
        return acronyms

    @staticmethod
    def _save_acronyms(acronyms):
        try:
            data_path = Path(configpaths.get('PLUGINS_DATA'))
        except KeyError:
            # PLUGINS_DATA was added in 1.0.99.1
            return

        path = data_path / 'acronyms'
        if not path.exists():
            path.mkdir(parents=True)

        filepath = path / 'acronyms'
        with filepath.open('w') as file:
            json.dump(acronyms, file)

    def set_acronyms(self, acronyms):
        self.acronyms = acronyms
        self._save_acronyms(acronyms)

    def _on_buffer_changed(self, _textview, buffer_, contact, account):
        if self._replace_in_progress:
            return

        if buffer_.get_char_count() < 2:
            return
        # Get iter at cursor
        insert_iter = buffer_.get_iter_at_mark(buffer_.get_insert())

        if insert_iter.get_offset() < 2:
            # We need at least 2 chars and an invoker
            return

        # Get last char
        insert_iter.backward_char()
        if insert_iter.get_char() != self._invoker:
            log.debug('"%s" not an invoker', insert_iter.get_char())
            return

        # Get to the start of the last word
        word_start_iter = insert_iter.copy()
        word_start_iter.backward_word_start()

        # Get last word and cut invoker
        last_word = word_start_iter.get_slice(insert_iter).strip()

        if contact.is_groupchat:
            nick_list = app.contacts.get_nick_list(account, contact.jid)
            if last_word in nick_list:
                log.info('Groupchat participant has same nick as acronym')
                return

        if contact.is_pm_contact:
            if last_word == contact.get_shown_name():
                log.info('Contact name equals acronym')
                return

        substitute = self.acronyms.get(last_word)
        if substitute is None:
            log.debug('%s not an acronym', last_word)
            return

        # Replace
        word_end_iter = word_start_iter.copy()
        word_end_iter.forward_word_end()
        GLib.idle_add(self._replace_text,
                      buffer_,
                      word_start_iter,
                      word_end_iter,
                      substitute)

    def _replace_text(self, buffer_, start, end, substitute):
        self._replace_in_progress = True
        buffer_.delete(start, end)
        buffer_.insert(start, substitute)
        self._replace_in_progress = False

    def _connect(self, chat_control):
        textview = chat_control.msg_textview
        handler_id = textview.connect('text-changed',
                                      self._on_buffer_changed,
                                      chat_control.contact,
                                      chat_control.account)
        self._handler_ids[id(textview)] = handler_id

    def _disconnect(self, chat_control):
        textview = chat_control.msg_textview
        handler_id = self._handler_ids.get(id(textview))
        if handler_id is not None:
            textview.disconnect(handler_id)
            del self._handler_ids[id(textview)]
