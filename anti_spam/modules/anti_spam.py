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

from __future__ import annotations

from typing import Any
from typing import cast

from nbxmpp import NodeProcessed
from nbxmpp.protocol import JID
from nbxmpp.protocol import Message
from nbxmpp.protocol import Presence
from nbxmpp.structs import MessageProperties
from nbxmpp.structs import PresenceProperties
from nbxmpp.structs import StanzaHandler

from gajim.common import app
from gajim.common import ged
from gajim.common import types
from gajim.common.events import MessageSent
from gajim.common.modules.base import BaseModule

# Module name
name = 'AntiSpam'
zeroconf = False


class AntiSpam(BaseModule):
    def __init__(self, con: types.Client) -> None:
        BaseModule.__init__(self, con, plugin=True)

        self.handlers = [
            StanzaHandler(name='message',
                          callback=self._message_received,
                          priority=48),
            StanzaHandler(name='presence',
                          callback=self._subscribe_received,
                          typ='subscribe',
                          priority=48),
        ]

        self.register_events([
            ('message-sent', ged.GUI2, self._on_message_sent),
        ])

        for plugin in app.plugin_manager.plugins:
            if plugin.manifest.short_name == 'anti_spam':
                self._config = plugin.config

        self._contacted_jids: set[JID] = set()

    def _on_message_sent(self, event: MessageSent) -> None:
        # We need self._contacted_jids in order to prevent two
        # Anti Spam Plugins from chatting with each other.
        # This set contains JIDs of all outgoing chats.
        self._contacted_jids.add(event.jid)

    def _message_received(self,
                          _con: types.xmppClient,
                          _stanza: Message,
                          properties: MessageProperties
                          ) -> None:
        if properties.is_sent_carbon:
            # Another device already sent a message
            assert properties.jid
            self._contacted_jids.add(properties.jid)
            return

        msg_body = properties.body
        if not msg_body:
            return

        if self._ask_question(properties):
            raise NodeProcessed

        msg_from = properties.jid
        limit = cast(int, self._config['msgtxt_limit'])
        if limit > 0 and len(msg_body) > limit:
            self._log.info('Discarded message from %s: message '
                           'length exceeded' % msg_from)
            raise NodeProcessed

        if self._config['disable_xhtml_muc'] and properties.type.is_groupchat:
            properties.xhtml = None
            self._log.info('Stripped message from %s: message '
                           'contained XHTML' % msg_from)

        if self._config['disable_xhtml_pm'] and properties.is_muc_pm:
            properties.xhtml = None
            self._log.info('Stripped message from %s: message '
                           'contained XHTML' % msg_from)

    def _ask_question(self, properties: MessageProperties) -> bool:
        answer = cast(str, self._config['msgtxt_answer'])
        if len(answer) == 0:
            return False

        is_muc_pm = properties.is_muc_pm
        if is_muc_pm and not self._config['antispam_for_conference']:
            return False

        if (properties.type.value not in ('chat', 'normal') or
                properties.is_mam_message):
            return False

        assert properties.jid
        if is_muc_pm:
            msg_from = properties.jid
        else:
            msg_from = JID.from_string(properties.jid.bare)

        if msg_from in self._contacted_jids:
            return False

        # If we receive a PM or a message from an unknown user, our anti spam
        # question will silently be sent in the background
        whitelist = cast(list[str], self._config['whitelist'])
        if str(msg_from) in whitelist:
            return False

        roster_item = self._con.get_module('Roster').get_item(msg_from)

        if is_muc_pm or roster_item is None:
            assert properties.body
            if answer in properties.body.split('\n'):
                if msg_from not in whitelist:
                    whitelist.append(str(msg_from))
                    # We need to explicitly save, because 'append' does not
                    # implement the __setitem__ method
                    self._config.save()
            else:
                self._send_question(properties, msg_from)
                return True
        return False

    def _send_question(self, properties: MessageProperties, jid: JID) -> None:
        message = 'Anti Spam Question: %s' % self._config['msgtxt_question']
        stanza = Message(to=jid, body=message, typ=properties.type.value)
        self._con.connection.send_stanza(stanza)
        self._log.info('Anti spam question sent to %s', jid)

    def _subscribe_received(self,
                            _con: types.xmppClient,
                            _stanza: Presence,
                            properties: PresenceProperties
                            ) -> None:
        msg_from = properties.jid
        block_sub = self._config['block_subscription_requests']
        roster_item = self._con.get_module('Roster').get_item(msg_from)

        if block_sub and roster_item is None:
            self._con.get_module('Presence').unsubscribed(msg_from)
            self._log.info('Denied subscription request from %s' % msg_from)
            raise NodeProcessed


def get_instance(*args: Any, **kwargs: Any) -> None:
    return AntiSpam(*args, **kwargs), 'AntiSpam'
