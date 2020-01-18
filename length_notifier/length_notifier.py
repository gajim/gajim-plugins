# -*- coding: utf-8 -*-

# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
#

'''
Message length notifier plugin.

:author: Mateusz Biliński <mateusz@bilinski.it>
:since: 1st June 2008
:copyright: Copyright (2008) Mateusz Biliński <mateusz@bilinski.it>
:license: GPL
'''
import logging
from functools import partial

from gi.repository import Gtk

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from length_notifier.config_dialog import LengthNotifierConfigDialog

log = logging.getLogger('gajim.p.length_notifier')


class LengthNotifierPlugin(GajimPlugin):
    def init(self):
        self.description = _('Highlights the chat window’s message input if '
                             'a specified message length is exceeded.')

        self.config_dialog = partial(LengthNotifierConfigDialog, self)

        self.gui_extension_points = {
            'chat_control_base': (
                self._on_connect_chat_control,
                self._on_disconnect_chat_control
            )
        }

        self.config_default_values = {
            'MESSAGE_WARNING_LENGTH': (
                140,
                'Message length at which the highlight is shown'),
            'WARNING_COLOR': (
                'rgb(240, 220, 60)',
                'Highlight color for the message input'),
            'JIDS': (
                [],
                'Enable the plugin for selected XMPP addresses '
                'only (comma separated)')
            }

        self._counters = {}

    def _on_connect_chat_control(self, chat_control):
        jid = chat_control.contact.jid
        if self._check_jid(jid):
            counter = Counter(chat_control, self.config)
            self._counters[chat_control.control_id] = counter
            actions_hbox = chat_control.xml.get_object('hbox')
            actions_hbox.pack_start(counter, False, False, 0)
            counter.show()

    def _on_disconnect_chat_control(self, chat_control):
        counter = self._counters.get(chat_control.control_id)
        if counter is not None:
            counter.destroy()
            self._counters.pop(chat_control.control_id, None)

    def _check_jid(self, jid):
        allowed_jids = []
        if len(self.config['JIDS']) > 0:
            allowed_jids = self.config['JIDS'].split(',')

        jid_allowed = jid in allowed_jids or not self.config['JIDS']
        if not jid_allowed:
            log.debug('No counter for JID %s' % jid)
        return jid_allowed

    def update_settings(self):
        for counter in self._counters.values():
            counter.update_settings(self.config)


class Counter(Gtk.Label):
    def __init__(self, chat_control, config):
        Gtk.Label.__init__(self)
        self._control = chat_control
        self._max_length = config['MESSAGE_WARNING_LENGTH']
        self._color = config['WARNING_COLOR']

        self.set_tooltip_text(_('Number of typed characters'))
        self.get_style_context().add_class('dim-label')

        self._textview = self._control.msg_textview
        self._textbuffer = self._textview.get_buffer()
        self._textbuffer.connect('changed', self._text_changed)
        self._provider = None

        self._set_count('0')
        self._set_css()

    def _set_css(self):
        self._context = self._textview.get_style_context()
        if self._provider is not None:
            self._context.remove_provider(self._provider)
        css = '''
        .length-warning > * {
            background-color: %s;
        }
        ''' % self._color
        self._provider = Gtk.CssProvider()
        self._provider.load_from_data(bytes(css.encode()))
        self._context.add_provider(
            self._provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def _text_changed(self, *args):
        if self._textview.has_text():
            text = self._textbuffer.get_text(
                self._textbuffer.get_start_iter(),
                self._textbuffer.get_end_iter(),
                True)
            len_text = len(text)
            self._set_count(len_text)
            if len_text > self._max_length:
                self._context.add_class('length-warning')
            else:
                self._context.remove_class('length-warning')
        else:
            self._set_count('0')
            self._context.remove_class('length-warning')

    def _set_count(self, count):
        self.set_label(str(count))

    def update_settings(self, new_config):
        self._max_length = new_config['MESSAGE_WARNING_LENGTH']
        self._color = new_config['WARNING_COLOR']
        self._set_css()
        self._text_changed()
