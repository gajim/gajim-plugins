# This file is part of Birthday Reminder.
#
# Birthday Reminder is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Birthday Reminder is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Birthday Reminder.  If not, see <http://www.gnu.org/licenses/>.

import os
import json
import datetime
import logging

from gi.repository import GLib

from gajim.common import configpaths
from gajim.common import app
from gajim.common import ged

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _


log = logging.getLogger('gajim.plugin_system.birthday')

TITLE = _('%s has birthday today')
TEXT = _('Send him a message')


class BirthDayPlugin(GajimPlugin):
    def init(self):
        self.config_dialog = None
        self.description = ('Birthday reminder plugin')
        self.events_handlers = {
            'vcard-received': (ged.GUI2, self._vcard_received)}

        self.timeout_id = None
        self._timeout_id_start = None

        self.showed_accounts = []

        self._birthdays = {}
        self._load_birthdays()

    def activate(self):
        self._timeout_id_start = GLib.timeout_add_seconds(
            5, self._check_birthdays_at_start)
        self._timeout_id = GLib.timeout_add_seconds(
            86400, self._check_birthdays)

    def deactivate(self):
        if self._timeout_id is not None:
            GLib.source_remove(self.timeout_id)
        if self._timeout_id_start is not None:
            GLib.source_remove(self._timeout_id_start)

    def _load_birthdays(self):
        path = os.path.join(configpaths.get('MY_DATA'), 'birthdays.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
                if content:
                    self._birthdays = json.loads(content)

    def _store_birthdays(self):
        path = os.path.join(configpaths.get('MY_DATA'), 'birthdays.json')
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(self._birthdays, file)

    def _vcard_received(self, event):
        birthday = event.vcard_dict.get('BDAY')
        if not birthday:
            if event.jid in self._birthdays:
                del self._birthdays[event.jid]
                log.info('Received empty birthday: %s', event.jid)
        else:
            try:
                year, month, day = birthday.split('-')
                year = int(year)
                month = int(month)
                day = int(day)
            except Exception:
                log.warning('Invalid date: %s', birthday)
                if event.jid in self._birthdays:
                    del self._birthdays[event.jid]
            else:
                self._birthdays[event.jid] = (year, month, day)
                log.info('Received birthday: %s %s',
                         event.jid, (year, month, day))
        self._store_birthdays()

    def _check_birthdays_at_start(self):
        self._check_birthdays()

    def _check_birthdays(self):
        log.info('Check birthdays...')
        today = datetime.date.today()
        for jid, birthdate in self._birthdays.items():
            year, month, day = birthdate
            if today.month == month and today.day == day:
                account, contact = self._find_contact(jid)
                if contact is None:
                    if jid in self._birthdays:
                        del self._birthdays[jid]
                        self._store_birthdays()
                        continue
                else:
                    log.info('Issue notification for %s', jid)
                    nick = contact.get_shown_name() or jid
                    app.notification.popup(
                        'reminder',
                        jid,
                        account,
                        icon_name='trophy-gold',
                        title=TITLE % GLib.markup_escape_text(nick),
                        text=TEXT)

        return True

    @staticmethod
    def _find_contact(jid):
        accounts = app.contacts.get_accounts()
        for account in accounts:
            contact = app.contacts.get_contacts(account, jid)
            if contact is not None:
                return account, contact[0]
