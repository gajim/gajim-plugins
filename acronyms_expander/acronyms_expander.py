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

from __future__ import annotations

import json
import logging
from pathlib import Path
from functools import partial

from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Gtk

from gajim.common import configpaths
from gajim.common import types
from gajim.common.modules.contacts import GroupchatContact

from gajim.gtk.message_input import MessageInputTextView

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from acronyms_expander.acronyms import DEFAULT_DATA
from acronyms_expander.gtk.config import ConfigDialog

log = logging.getLogger('gajim.p.acronyms')


class AcronymsExpanderPlugin(GajimPlugin):
    def init(self) -> None:
        self.description = _('Replaces acronyms (or other strings) '
                             'with given expansions/substitutes.')
        self.config_dialog = partial(ConfigDialog, self)
        self.gui_extension_points = {
            'message_input': (self._connect, None),
            'switch_contact': (self._on_switch_contact, None)
        }
        self._invoker = ' '
        self._replace_in_progress = False

        self._signal_id = None
        self._text_buffer = None
        self._contact = None

        self.acronyms = self._load_acronyms()

    @staticmethod
    def _load_acronyms() -> dict[str, str]:
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
    def _save_acronyms(acronyms: dict[str, str]) -> None:
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

    def set_acronyms(self, acronyms: dict[str, str]) -> None:
        self.acronyms = acronyms
        self._save_acronyms(acronyms)

    def _on_buffer_changed(self,
                           buffer_: Gtk.TextBuffer
                           ) -> None:

        if self._contact is None:
            # If no chat has been activated yet
            return

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
        # word_start_iter = insert_iter.copy()
        result = insert_iter.backward_search(
            self._invoker,
            Gtk.TextSearchFlags.VISIBLE_ONLY,
            None)

        if result is None:
            word_start_iter = buffer_.get_start_iter()
        else:
            _, word_start_iter = result

        # Get last word and cut invoker
        last_word = word_start_iter.get_slice(insert_iter)

        if isinstance(self._contact, GroupchatContact):
            if last_word in self._contact.get_user_nicknames():
                log.info('Groupchat participant has same nick as acronym')
                return

        if self._contact.is_pm_contact:
            if last_word == self._contact.name:
                log.info('Contact name equals acronym')
                return

        substitute = self.acronyms.get(last_word)
        if substitute is None:
            log.debug('%s not an acronym', last_word)
            return

        GLib.idle_add(self._replace_text,
                      buffer_,
                      word_start_iter,
                      insert_iter,
                      substitute)

    def _replace_text(self,
                      buffer_: Gtk.TextBuffer,
                      start: Gtk.TextIter,
                      end: Gtk.TextIter,
                      substitute: str
                      ) -> None:

        self._replace_in_progress = True
        buffer_.delete(start, end)
        buffer_.insert(start, substitute)
        self._replace_in_progress = False

    def _on_switch_contact(self, contact: types.ChatContactT) -> None:
        self._contact = contact

    def _connect(self, message_input: MessageInputTextView) -> None:
        self._text_buffer = message_input.get_buffer()
        self._signal_id = self._text_buffer.connect(
            'changed', self._on_buffer_changed)

    def deactivate(self) -> None:
        assert self._text_buffer is not None
        assert self._signal_id is not None
        if GObject.signal_handler_is_connected(
                self._text_buffer, self._signal_id):
            self._text_buffer.disconnect(self._signal_id)
