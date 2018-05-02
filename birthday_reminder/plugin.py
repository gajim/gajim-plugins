import os
import glob
import datetime
from xml.dom.minidom import *
from gi.repository import GObject

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.notify import popup

from gajim.common import configpaths
from gajim.common import app
from gajim.common import ged


class BirthDayPlugin(GajimPlugin):

    @log_calls('BirthDayPlugin')
    def init(self):

        self.config_dialog = None
        self.description = ('Birthday reminder plugin')
        self.events_handlers = {
            'roster-received': (ged.GUI2, self.roster_received)}
        configpath = configpaths.ConfigPaths()
        cache_path = configpath.cache_root
        self.vcard_path = os.path.join(cache_path, 'vcards') + os.sep
        self.timeout_id = 0
        self.showed_accounts = []

    def check_birthdays(self, account=None):
        def show_popup(account, jid):
            contact_instances = app.contacts.get_contacts(account, jid)
            contact = app.contacts.get_highest_prio_contact_from_contacts(
                contact_instances)
            if contact:
                nick = GObject.markup_escape_text(contact.get_shown_name())
                try:
                    image = os.path.dirname(__file__) + os.sep + \
                            'birthday_reminder_large.png'
                except:
                    image = None

                popup('Send message', contact.jid, account, type_='',
                    path_to_image=image, title=title, text=text + ' ' + nick)

        accounts = app.contacts.get_accounts()
        vcards = []
        date_dict = {}
        for jid in glob.glob(self.vcard_path + '*@*'):
            if os.path.isfile(jid):
                vcards.append(jid)

        for xmldoc in vcards:
            try:
                xml = parse(xmldoc)
            except:
                pass
            else:
                name = xml.getElementsByTagName('BDAY')
                for node in name:
                    try:
                        data = node.childNodes[0].nodeValue
                        date_dict[xmldoc[len(self.vcard_path):][:-1]] = data
                    except:
                        pass

        today = datetime.date.today()

        for key, value in date_dict.items():
            try:
                convert_date = datetime.datetime.strptime(value, "%Y-%m-%d")
                user_bday = datetime.date(today.year, convert_date.month,
                    convert_date.day)
            except:
                continue

            if user_bday < today:
                user_bday = user_bday.replace(year=today.year+1)

            time_to_bday = abs(user_bday - today)
            title = "BirthDay Reminder"
            text = None

            if time_to_bday.days > 5:
                continue
            if time_to_bday.days == 5:
                text = "5 days before BDay"
            elif time_to_bday.days == 3:
                text = "3 days before BDay"
            elif time_to_bday.days == 1:
                text = "Tomorrow BDay"
            elif time_to_bday.days == 0:
                text = "Today BDay"
            if not text:
                continue
            if account:
                show_popup(account,key)
            else:
                for acct in accounts:
                    show_popup(account, key)
        return True

    @log_calls('BirthDayPlugin')
    def activate(self):
        self.timeout_id = GObject.timeout_add_seconds(24*3600,
            self.check_birthdays)

    @log_calls('BirthDayPlugin')
    def deactivate(self):
        if self.timeout_id > 0:
            GObject.source_remove(self.timeout_id)


    @log_calls('BirthDayPlugin')
    def roster_received(self, obj):
        if obj.conn.name not in self.showed_accounts:
            self.check_birthdays(obj.conn.name)
            self.showed_accounts.append(obj.conn.name)
