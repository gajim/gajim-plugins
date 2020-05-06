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

from functools import partial

from gajim.common import app
from gajim.common import ged

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from triggers.gtk.config import ConfigDialog


class Triggers(GajimPlugin):
    def init(self):
        self.description = _('Configure Gajim’s behaviour with triggers '
                             'for each contact')
        self.config_dialog = partial(ConfigDialog, self)
        self.config_default_values = {}

        self.events_handlers = {
            'notification': (ged.PREGUI, self._on_notification),
            'decrypted-message-received': (ged.PREGUI2,
                                           self._on_message_received),
            'gc-message-received': (ged.PREGUI2, self._on_gc_message_received),
            'presence-received': (ged.PREGUI, self._on_presence_received),
        }

    def _check_rule_recipients(self, obj, rule):
        rule_recipients = [t.strip() for t in rule['recipients'].split(',')]
        if rule['recipient_type'] == 'groupchat':
            if obj.jid in rule_recipients:
                return True
            return False
        if (rule['recipient_type'] == 'contact' and obj.jid not in
                rule_recipients):
            return False
        contact = app.contacts.get_first_contact_from_jid(
            obj.conn.name, obj.jid)
        if not contact:  # PM?
            return False
        contact_groups = contact.groups
        group_found = False
        for group in contact_groups:
            if group in rule_recipients:
                group_found = True
                break
        if rule['recipient_type'] == 'group' and not group_found:
            return False

        return True

    def _check_rule_status(self, obj, rule):
        rule_statuses = rule['status'].split()
        our_status = app.connections[obj.conn.name].status
        if rule['status'] != 'all' and our_status not in rule_statuses:
            return False

        return True

    def _check_rule_tab_opened(self, obj, rule):
        if rule['tab_opened'] == 'both':
            return True
        tab_opened = False
        if app.interface.msg_win_mgr.get_control(obj.jid, obj.conn.name):
            tab_opened = True
        if tab_opened and rule['tab_opened'] == 'no':
            return False
        elif not tab_opened and rule['tab_opened'] == 'yes':
            return False

        return True

    def _check_rule_has_focus(self, obj, rule):
        if rule['has_focus'] == 'both':
            return True
        if rule['tab_opened'] == 'no':
            # Does not apply in this case
            return True
        ctrl = app.interface.msg_win_mgr.get_control(obj.jid, obj.conn.name)
        if not ctrl:
            # Does not apply in this case
            return True
        has_focus = ctrl.parent_win.window.has_focus()
        if has_focus and rule['has_focus'] == 'no':
            return False
        elif not has_focus and rule['has_focus'] == 'yes':
            return False

        return True

    def _check_rule_all(self, event, obj, rule):
        # Check notification type
        if rule['event'] != event:
            return False

        # notification type is ok. Now check recipient
        if not self._check_rule_recipients(obj, rule):
            return False

        # recipient is ok. Now check our status
        if not self._check_rule_status(obj, rule):
            return False

        # our_status is ok. Now check opened chat window
        if not self._check_rule_tab_opened(obj, rule):
            return False

        # tab_opened is ok. Now check opened chat window
        if not self._check_rule_has_focus(obj, rule):
            return False

        # All is ok
        return True

    def _check_rule_apply_notification(self, obj, rule):
        # Check notification type
        notif_type = ''
        if obj.notif_type in ('msg', 'gc-msg'):
            notif_type = 'message_received'
        elif obj.notif_type == 'pres':
            if obj.base_event.old_show < 2 and obj.base_event.new_show > 1:
                notif_type = 'contact_connected'
            elif obj.base_event.old_show > 1 and obj.base_event.new_show < 2:
                notif_type = 'contact_disconnected'
            else:
                notif_type = 'contact_status_change'

        return self._check_rule_all(notif_type, obj, rule)

    def _check_rule_apply_msg_received(self, obj, rule):
        return self._check_rule_all('message_received', obj, rule)

    def _check_rule_apply_connected(self, obj, rule):
        return self._check_rule_all('contact_connected', obj, rule)

    def _check_rule_apply_disconnected(self, obj, rule):
        return self._check_rule_all('contact_disconnected', obj, rule)

    def _check_rule_apply_status_changed(self, obj, rule):
        return self._check_rule_all('contact_status_change', obj, rule)

    def _apply_rule_notification(self, obj, rule):
        if rule['sound'] == 'no':
            obj.do_sound = False
        elif rule['sound'] == 'yes':
            obj.do_sound = True
            obj.sound_event = ''
            obj.sound_file = rule['sound_file']

        if rule['popup'] == 'no' or obj.control_focused:
            obj.do_popup = False
        elif rule['popup'] == 'yes':
            obj.do_popup = True

        if rule['run_command']:
            obj.do_command = True
            obj.command = rule['command']
        else:
            obj.do_command = False

        if rule['systray'] == 'no':
            obj.show_in_notification_area = False
        elif rule['systray'] == 'yes':
            obj.show_in_notification_area = True

        if rule['roster'] == 'no':
            obj.show_in_roster = False
        elif rule['roster'] == 'yes':
            obj.show_in_roster = True

    def _apply_rule_message_received(self, obj, rule):
        if rule['auto_open'] == 'no':
            obj.popup = False
        elif rule['auto_open'] == 'yes':
            obj.popup = True

    def _apply_rule_presence_received(self, obj, rule):
        if rule['auto_open'] == 'no':
            obj.popup = False
        elif rule['auto_open'] == 'yes':
            obj.popup = True

    def _check_all(self, obj, check_func, apply_func):
        # check rules in order
        rules_num = [int(i) for i in self.config.keys()]
        rules_num.sort()
        to_remove = []
        for num in rules_num:
            rule = self.config[str(num)]
            if check_func(obj, rule):
                apply_func(obj, rule)
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

    def _on_notification(self, obj):
        self._check_all(obj, self._check_rule_apply_notification,
                        self._apply_rule_notification)

    def _on_message_received(self, obj):
        self._check_all(obj, self._check_rule_apply_msg_received,
                        self._apply_rule_message_received)

    def _on_gc_message_received(self, obj):
        self._check_all(obj, self._check_rule_apply_msg_received,
                        self._apply_rule_message_received)

    def _on_presence_received(self, obj):
        if obj.old_show < 2 and obj.new_show > 1:
            check_func = self._check_rule_apply_connected
        elif obj.old_show > 1 and obj.new_show < 2:
            check_func = self._check_rule_apply_disconnected
        else:
            check_func = self._check_rule_apply_status_changed
        self._check_all(obj, check_func, self._apply_rule_presence_received)
