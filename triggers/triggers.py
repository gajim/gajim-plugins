# Copyright (C) 2011-2017 Yann Leboulanger <asterix AT lagaule.org>
# Copyright (C) 2022 Philipp Hörist <philipp AT hoerist.com>
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

from __future__ import annotations

from typing import Any
from typing import cast

import logging
import subprocess
from collections.abc import Callable
from functools import partial

from nbxmpp.protocol import JID

from gajim.common import app
from gajim.common import ged
from gajim.common.const import PROPAGATE_EVENT
from gajim.common.const import STOP_EVENT
from gajim.common.events import MessageReceived
from gajim.common.events import Notification
from gajim.common.events import PresenceReceived
from gajim.common.helpers import play_sound_file
from gajim.common.modules.contacts import BareContact
from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from triggers.gtk.config import ConfigDialog
from triggers.util import log_result
from triggers.util import RuleResult

log = logging.getLogger("gajim.p.triggers")

ProcessableEventsT = MessageReceived | Notification | PresenceReceived
RuleT = dict[str, Any]


class Triggers(GajimPlugin):
    def init(self) -> None:
        self.description = _(
            "Configure Gajim’s behaviour with triggers for each contact"
        )
        self.config_dialog = partial(ConfigDialog, self)
        self.config_default_values = {}

        self.events_handlers = {
            "notification": (ged.PREGUI, self._on_notification),
            "message-received": (ged.PREGUI2, self._on_message_received),
            "gc-message-received": (ged.PREGUI2, self._on_message_received),
            # 'presence-received': (ged.PREGUI, self._on_presence_received),
        }

    def _on_notification(self, event: Notification) -> bool:
        log.info("Process %s, %s", event.name, event.type)
        result = self._check_all(
            event, self._check_rule_apply_notification, self._apply_rule
        )
        log.info("Result: %s", result)
        return self._excecute_notification_rules(result, event)

    def _on_message_received(self, event: MessageReceived) -> bool:
        log.info("Process %s", event.name)
        message = event.message
        if message.text is None:
            log.info("Discard event because it has no message text")
            return PROPAGATE_EVENT

        result = self._check_all(
            event, self._check_rule_apply_msg_received, self._apply_rule
        )
        log.info("Result: %s", result)
        return self._excecute_message_rules(result)

    def _on_presence_received(self, event: PresenceReceived) -> None:
        # TODO
        return

        if event.old_show < 2 and event.new_show > 1:
            check_func = self._check_rule_apply_connected
        elif event.old_show > 1 and event.new_show < 2:
            check_func = self._check_rule_apply_disconnected
        else:
            check_func = self._check_rule_apply_status_changed
        self._check_all(event, check_func, self._apply_rule)

    def _check_all(
        self,
        event: ProcessableEventsT,
        check_func: Callable[..., bool],
        apply_func: Callable[..., Any],
    ) -> RuleResult:
        result = RuleResult()

        rules_num = [int(item) for item in self.config]
        rules_num.sort()
        to_remove: list[int] = []
        for num in rules_num:
            rule = cast(RuleT, self.config[str(num)])
            if check_func(event, rule):
                apply_func(result, rule)
                if rule.get("one_shot"):
                    to_remove.append(num)

        decal = 0
        num = 0
        while str(num) in self.config:
            if num + decal in to_remove:
                num2 = num
                while str(num2 + 1) in self.config:
                    copy = self.config[str(num2 + 1)].copy()  # type: ignore
                    self.config[str(num2)] = copy
                    num2 += 1
                del self.config[str(num2)]
                decal += 1
            else:
                num += 1

        return result

    @log_result
    def _check_rule_apply_msg_received(
        self, event: MessageReceived, rule: RuleT
    ) -> bool:
        return self._check_rule_all("message_received", event, rule)

    @log_result
    def _check_rule_apply_connected(self, event: PresenceReceived, rule: RuleT) -> bool:
        return self._check_rule_all("contact_connected", event, rule)

    @log_result
    def _check_rule_apply_disconnected(
        self, event: PresenceReceived, rule: RuleT
    ) -> bool:
        return self._check_rule_all("contact_disconnected", event, rule)

    @log_result
    def _check_rule_apply_status_changed(
        self, event: PresenceReceived, rule: RuleT
    ) -> bool:
        return self._check_rule_all("contact_status_change", event, rule)

    @log_result
    def _check_rule_apply_notification(self, event: Notification, rule: RuleT) -> bool:
        # Check notification type
        notif_type = ""
        if event.type == "incoming-message":
            notif_type = "message_received"
        # if event.type == 'pres':
        #     # TODO:
        #     if (event.base_event.old_show < 2 and
        #             event.base_event.new_show > 1):
        #         notif_type = 'contact_connected'
        #     elif (event.base_event.old_show > 1 and
        #             event.base_event.new_show < 2):
        #         notif_type = 'contact_disconnected'
        #     else:
        #         notif_type = 'contact_status_change'

        return self._check_rule_all(notif_type, event, rule)

    def _check_rule_all(
        self, notif_type: str, event: ProcessableEventsT, rule: RuleT
    ) -> bool:
        # Check notification type
        if rule["event"] != notif_type:
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
        if not self._check_rule_has_focus(event, rule):  # noqa: SIM103
            return False

        # All is ok
        return True

    @log_result
    def _check_rule_recipients(self, event: ProcessableEventsT, rule: RuleT) -> bool:
        assert event.jid is not None
        rule_recipients = [t.strip() for t in rule["recipients"].split(",")]
        if rule["recipient_type"] == "groupchat":
            return event.jid in rule_recipients

        if rule["recipient_type"] == "contact" and event.jid not in rule_recipients:
            return False
        client = app.get_client(event.account)
        contact = client.get_module("Contacts").get_contact(event.jid)

        if contact.is_groupchat:
            return False

        assert isinstance(contact, BareContact)
        if not contact.is_in_roster:
            return False

        group_found = False
        for group in contact.groups:
            if group in rule_recipients:
                group_found = True
                break
        if rule["recipient_type"] == "group" and not group_found:  # noqa: SIM103
            return False

        return True

    @log_result
    def _check_rule_status(self, event: ProcessableEventsT, rule: RuleT) -> bool:
        rule_statuses = rule["status"].split()
        client = app.get_client(event.account)
        if (  # noqa: SIM103
            rule["status"] != "all" and client.status not in rule_statuses
        ):
            return False

        return True

    @log_result
    def _check_rule_tab_opened(self, event: ProcessableEventsT, rule: RuleT) -> bool:
        if rule["tab_opened"] == "both":
            return True
        tab_opened = False
        assert isinstance(event.jid, JID)
        if app.window.chat_exists(event.account, event.jid):
            tab_opened = True
        if tab_opened and rule["tab_opened"] == "no":
            return False
        elif not tab_opened and rule["tab_opened"] == "yes":
            return False

        return True

    @log_result
    def _check_rule_has_focus(self, event: ProcessableEventsT, rule: RuleT) -> bool:
        if rule["has_focus"] == "both":
            return True
        if rule["tab_opened"] == "no":
            # Does not apply in this case
            return True
        assert isinstance(event.jid, JID)
        chat_active = app.window.is_chat_active(event.account, event.jid)
        if chat_active and rule["has_focus"] == "no":
            return False
        elif not chat_active and rule["has_focus"] == "yes":
            return False

        return True

    def _apply_rule(self, result: RuleResult, rule: RuleT) -> None:
        if rule["sound"] == "no":
            result.sound = False
            result.sound_file = None

        elif rule["sound"] == "yes":
            result.sound = False
            result.sound_file = rule["sound_file"]

        if rule["run_command"]:
            result.command = rule["command"]

        if rule["popup"] == "no":
            result.show_notification = False
        elif rule["popup"] == "yes":
            result.show_notification = True

    def _excecute_notification_rules(
        self, result: RuleResult, event: Notification
    ) -> bool:
        if result.sound is False:
            event.sound = None

        if result.sound_file is not None:
            play_sound_file(result.sound_file)

        if result.show_notification is False:
            return STOP_EVENT
        return PROPAGATE_EVENT

    def _excecute_message_rules(self, result: RuleResult) -> bool:
        if result.sound_file is not None:
            play_sound_file(result.sound_file)

        if result.command is not None:
            try:
                subprocess.Popen(f"{result.command} &", shell=True).wait()  # noqa: S602
            except Exception:
                pass

        return PROPAGATE_EVENT
