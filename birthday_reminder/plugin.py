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

import json
import datetime
import logging
from pathlib import Path

from gi.repository import GLib

from gajim.common import configpaths
from gajim.common import app
from gajim.common import ged
from gajim.common.events import Notification

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _


log = logging.getLogger('gajim.p.birthday')

TITLE = _('Birthday Reminder')
TEXT = _('Send your best wishes to %s')


class BirthDayPlugin(GajimPlugin):
    def init(self):
        self.config_dialog = None
        self.description = _('Checks vCards of your contacts for upcoming '
                             'birthdays and reminds you on that day.')
        self.events_handlers = {
            'vcard-received': (ged.GUI2, self._vcard_received)
        }

        self._timeout_id = None
        self._timeout_id_start = None

        self.showed_accounts = []

        self._birthdays = {}
        self._load_birthdays()

    def activate(self):
        self._timeout_id_start = GLib.timeout_add_seconds(
            5, self._check_birthdays_at_start)
        self._timeout_id = GLib.timeout_add_seconds(
            86400, self._check_birthdays)  # 24h

    def deactivate(self):
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
        if self._timeout_id_start is not None:
            GLib.source_remove(self._timeout_id_start)

    def _load_birthdays(self):
        data_path = Path(configpaths.get('PLUGINS_DATA'))
        path = data_path / 'birthday_reminder' / 'birthdays.json'
        if not path.exists():
            return
        with path.open('r') as file:
            content = file.read()
            if content:
                self._birthdays = json.loads(content)

    def _store_birthdays(self):
        data_path = Path(configpaths.get('PLUGINS_DATA'))
        path = data_path / 'birthday_reminder'
        if not path.exists():
            path.mkdir(parents=True)

        filepath = path / 'birthdays.json'
        with filepath.open('w') as file:
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
                    name = GLib.markup_escape_text(contact.name)
                    app.ged.raise_event(
                        Notification(account=account,
                                     jid=jid,
                                     type='reminder',
                                     title=TITLE,
                                     text=TEXT % name,
                                     icon_name='trophy-gold'))
        return True

    @staticmethod
    def _find_contact(jid):
        accounts = app.settings.get_active_accounts()
        for account in accounts:
            client = app.get_client(account)
            item = client.get_module('Roster').get_item(jid)
            if item is not None:
                contact = client.get_module('Contacts').get_contact(jid)
                return account, contact
        return None, None
