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
from __future__ import annotations

from typing import Any, cast

import logging
from functools import partial

from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk

from nbxmpp.protocol import JID

from gajim.common import app
from gajim.common import types

from gajim.gui.message_actions_box import MessageActionsBox
from gajim.gui.message_input import MessageInputTextView

from gajim.plugins import GajimPlugin
from gajim.plugins.gajimplugin import GajimPluginConfig
from gajim.plugins.plugins_i18n import _

from length_notifier.config_dialog import LengthNotifierConfigDialog

log = logging.getLogger('gajim.p.length_notifier')


class LengthNotifierPlugin(GajimPlugin):
    def init(self) -> None:
        self.description = _('Highlights the chat window’s message input if '
                             'a specified message length is exceeded.')

        self.config_dialog = partial(LengthNotifierConfigDialog, self)

        self.gui_extension_points = {
            'message_actions_box': (self._connect, None),
            'switch_contact': (self._on_switch_contact, None)
        }

        self.config_default_values = {
            'MESSAGE_WARNING_LENGTH': (
                140,
                'Message length at which the highlight is shown'),
            'WARNING_COLOR': (
                'rgb(240, 220, 60)',
                'Highlight color for the message input'),
            'JIDS': (
                [''],
                'Enable the plugin for selected XMPP addresses '
                'only (comma separated)')
            }

        self._message_action_box = None
        self._actions_box_widget = None
        self._counter = None
        self._contact = None

    def activate(self) -> None:
        if self._counter is not None and self._contact is not None:
            self._counter.update_contact(self._contact)

    def deactivate(self) -> None:
        assert self._counter is not None
        self._counter.destroy()
        del self._counter

    def _create_counter(self) -> None:
        assert self._message_action_box is not None
        assert self._actions_box_widget is not None
        self._counter = Counter(self._message_action_box.msg_textview,
                                self.config)
        self._actions_box_widget.pack_end(self._counter, False, False, 0)

    def _connect(self,
                 message_actions_box: MessageActionsBox,
                 gtk_box: Gtk.Box
                 ) -> None:

        self._message_action_box = message_actions_box
        self._actions_box_widget = gtk_box
        self._create_counter()

    def _on_switch_contact(self, contact: types.ChatContactT) -> None:
        if self._counter is None:
            return

        self._contact = contact
        self._counter.update_contact(contact)

    def update(self):
        assert self._counter is not None
        if self._contact is not None:
            self._counter.update_config(self.config)


class Counter(Gtk.Label):
    def __init__(self,
                 message_input: MessageInputTextView,
                 config: GajimPluginConfig
                 ) -> None:

        Gtk.Label.__init__(self)
        self.set_tooltip_text(_('Number of typed characters'))
        self.get_style_context().add_class('dim-label')

        self._config = config

        self._contact = None

        self._max_length = None
        self._color = None
        self._inverted_color = None

        self._textview = message_input
        self._textbuffer = self._textview.get_buffer()
        self._signal_id = self._textbuffer.connect('changed', self._update)
        self._provider = None

        self._parse_config()
        self._set_css()

        self.connect('destroy', self._on_destroy)

    def _on_destroy(self, _widget: Counter) -> None:
        self._context.remove_class('length-warning')
        assert self._textbuffer is not None
        assert self._signal_id is not None
        if GObject.signal_handler_is_connected(
                self._textbuffer, self._signal_id):
            self._textbuffer.disconnect(self._signal_id)
        app.check_finalize(self)

    def _parse_config(self) -> None:
        self._max_length = cast(int, self._config['MESSAGE_WARNING_LENGTH'])

        self._color = cast(str, self._config['WARNING_COLOR'])
        rgba = Gdk.RGBA()
        rgba.parse(self._color)
        red = int(255 - rgba.red * 255)
        green = int(255 - rgba.green * 255)
        blue = int(255 - rgba.blue * 255)
        self._inverted_color = f'rgb({red}, {green}, {blue})'

    def _set_css(self) -> None:
        self._context = self._textview.get_style_context()
        if self._provider is not None:
            self._context.remove_provider(self._provider)
        css = '''
        .length-warning > * {
            color: %s;
            background-color: %s;
        }
        ''' % (self._inverted_color, self._color)
        self._provider = Gtk.CssProvider()
        self._provider.load_from_data(bytes(css.encode()))
        self._context.add_provider(
            self._provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def _set_count(self, count: int) -> None:
        self.set_label(str(count))

    def _update(self, *args: Any) -> bool:
        if self._contact is None:
            return False

        enable = self._jid_allowed(self._contact.jid)
        if enable:
            self.show()
        else:
            self.hide()

        assert self._max_length is not None
        if self._textview.has_text and enable:
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
            self._set_count(0)
            self._context.remove_class('length-warning')
        return False

    def _jid_allowed(self, current_jid: JID) -> bool:
        jids = cast(str, self._config['JIDS'])
        if not len(jids):
            # Not restricted to any JIDs
            return True

        allowed_jids = jids.split(',')
        for allowed_jid in allowed_jids:
            try:
                address = JID.from_string(allowed_jid.strip())
            except Exception as error:
                log.error('Error parsing JID: %s (%s)' % (error, allowed_jid))
                continue
            if address.is_domain:
                if current_jid.domain == address:
                    log.debug('Show counter for Domain %s' % address)
                    return True
            if current_jid == address:
                log.debug('Show counter for JID %s' % address)
                return True
        return False

    def update_config(self, config: GajimPluginConfig) -> None:
        self._config = config
        self.reset()
        self._update()

    def update_contact(self, contact: types.ChatContactT) -> None:
        self._contact = contact
        self._update()

    def reset(self) -> None:
        self._context.remove_class('length-warning')
        self._parse_config()
        self._set_css()
