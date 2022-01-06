# Copyright (C) 2011-2017 Yann Leboulanger <asterix AT lagaule.org>
#
# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import annotations

from typing import Optional

from dataclasses import dataclass
from dataclasses import asdict
from functools import partial

from gajim.common import app
from gajim.common import ged
from gajim.common.events import ApplicationEvent
from gajim.common.events import Notification
from gajim.common.helpers import exec_command
from gajim.common.helpers import play_sound_file

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from triggers.gtk.config import ConfigDialog


@dataclass
class ExtendedEvent(Notification):
    origin: Optional[ApplicationEvent] = None
    show_notification: bool = True
    command: Optional[str] = None
    sound_file: Optional[str] = None

    @classmethod
    def from_event(cls, event) -> ExtendedEvent:
        attr_dict = asdict(event)
        attr_dict.pop('name')
        return cls(**attr_dict, origin=event)


class Triggers(GajimPlugin):
    def init(self):
        self.description = _(
            'Configure Gajim’s behaviour with triggers for each contact')
        self.config_dialog = partial(ConfigDialog, self)
        self.config_default_values = {}

        self.events_handlers = {
            'notification': (ged.PREGUI, self._on_notification),
            'message-received': (ged.PREGUI2, self._on_message_received),
            'gc-message-received': (ged.PREGUI2, self._on_message_received),
            'presence-received': (ged.PREGUI, self._on_presence_received),
        }

    def _excecute(self, event) -> bool:
        if event.command is not None:
            # Used by Triggers plugin
            try:
                exec_command(event.command, use_shell=True)
            except Exception:
                pass

        if event.sound_file is not None:
            play_sound_file(event.sound_file)

        if not event.show_notification:
            # This aborts the event excecution
            return True
        return False

    def _on_notification(self, event: Notification) -> bool:
        extended_event = ExtendedEvent.from_event(event)
        self._check_all(extended_event,
                        self._check_rule_apply_notification,
                        self._apply_rule)
        return self._excecute(extended_event)

    def _on_message_received(self, event: Notification) -> bool:
        extended_event = ExtendedEvent.from_event(event)
        self._check_all(extended_event,
                        self._check_rule_apply_msg_received,
                        self._apply_rule)
        return self._excecute(extended_event)

    def _on_presence_received(self, event):
        # TODO
        return

        if event.old_show < 2 and event.new_show > 1:
            check_func = self._check_rule_apply_connected
        elif event.old_show > 1 and event.new_show < 2:
            check_func = self._check_rule_apply_disconnected
        else:
            check_func = self._check_rule_apply_status_changed
        self._check_all(event, check_func, self._apply_rule)

    def _check_all(self, event, check_func, apply_func):
        # check rules in order
        rules_num = [int(item) for item in self.config.keys()]
        rules_num.sort()
        to_remove = []
        for num in rules_num:
            rule = self.config[str(num)]
            if check_func(event, rule):
                apply_func(event, rule)
                if 'one_shot' in rule and rule['one_shot']:
                    to_remove.append(num)
                # Should we stop after first valid rule ?
                # break

        decal = 0
        num = 0
        while str(num) in self.config:
            if num + decal in to_remove:
                num2 = num
                while str(num2 + 1) in self.config:
                    self.config[str(num2)] = self.config[str(num2 + 1)].copy()
                    num2 += 1
                del self.config[str(num2)]
                decal += 1
            else:
                num += 1

    def _check_rule_apply_msg_received(self, event, rule):
        return self._check_rule_all('message_received', event, rule)

    def _check_rule_apply_connected(self, event, rule):
        return self._check_rule_all('contact_connected', event, rule)

    def _check_rule_apply_disconnected(self, event, rule):
        return self._check_rule_all('contact_disconnected', event, rule)

    def _check_rule_apply_status_changed(self, event, rule):
        return self._check_rule_all('contact_status_change', event, rule)

    def _check_rule_apply_notification(self, event, rule):
        # Check notification type
        notif_type = ''
        if event.notif_type == 'incoming-message':
            notif_type = 'message_received'
        if event.notif_type == 'pres':
            # TODO:
            if (event.base_event.old_show < 2 and
                    event.base_event.new_show > 1):
                notif_type = 'contact_connected'
            elif (event.base_event.old_show > 1 and
                    event.base_event.new_show < 2):
                notif_type = 'contact_disconnected'
            else:
                notif_type = 'contact_status_change'

        return self._check_rule_all(notif_type, event, rule)

    def _check_rule_all(self, notif_type, event, rule):
        # Check notification type
        if rule['event'] != notif_type:
            return False

        # notification type is ok. Now check recipient
        if not self._check_rule_recipients(event, rule):
            return False

        # recipient is ok. Now check our status
        if not self._check_rule_status(event, rule):
            return False

        # our_status is ok. Now check opened chat window
        if not self._check_rule_tab_opened(event, rule):
            return False

        # tab_opened is ok. Now check opened chat window
        if not self._check_rule_has_focus(event, rule):
            return False

        # All is ok
        return True

    def _check_rule_recipients(self, event, rule):
        rule_recipients = [t.strip() for t in rule['recipients'].split(',')]
        if rule['recipient_type'] == 'groupchat':
            if event.jid in rule_recipients:
                return True
            return False
        if (rule['recipient_type'] == 'contact' and event.jid not in
                rule_recipients):
            return False
        client = app.get_client(event.account)
        contact = client.get_module('Contacts').get_contact(event.jid)

        group_found = False
        for group in contact.groups:
            if group in rule_recipients:
                group_found = True
                break
        if rule['recipient_type'] == 'group' and not group_found:
            return False

        return True

    def _check_rule_status(self, event, rule):
        rule_statuses = rule['status'].split()
        our_status = app.connections[event.account].status
        if rule['status'] != 'all' and our_status not in rule_statuses:
            return False

        return True

    def _check_rule_tab_opened(self, event, rule):
        if rule['tab_opened'] == 'both':
            return True
        tab_opened = False
        if app.window.get_control(event.account, event.jid):
            tab_opened = True
        if tab_opened and rule['tab_opened'] == 'no':
            return False
        elif not tab_opened and rule['tab_opened'] == 'yes':
            return False

        return True

    def _check_rule_has_focus(self, event, rule):
        if rule['has_focus'] == 'both':
            return True
        if rule['tab_opened'] == 'no':
            # Does not apply in this case
            return True
        ctrl = app.window.get_control(event.account, event.jid)
        if not ctrl:
            # Does not apply in this case
            return True
        has_focus = ctrl.has_focus()
        if has_focus and rule['has_focus'] == 'no':
            return False
        elif not has_focus and rule['has_focus'] == 'yes':
            return False

        return True

    def _apply_rule(self, event, rule):
        if rule['sound'] == 'no':
            event.origin.sound = None
            event.sound_file = None

        elif rule['sound'] == 'yes':
            event.origin.sound = None
            event.sound_file = rule['sound_file']

        if rule['run_command']:
            event.command = rule['command']

        if rule['popup'] == 'no':
            event.show_notification = False
        elif rule['popup'] == 'yes':
            event.show_notification = True
