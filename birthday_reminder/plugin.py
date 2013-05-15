import os
import glob
import datetime
from xml.dom.minidom import *

from plugins import GajimPlugin
from plugins.helpers import log_calls
from notify import popup

from common import configpaths


class BirthDayPlugin(GajimPlugin):

    @log_calls('BirthDayPlugin')
    def init(self):

        self.config_dialog = None
        self.description = ('Birthday reminder plugin')
        configpath = configpaths.ConfigPaths()
        cache_path = configpath.cache_root
        self.vcard_path = os.path.join(cache_path, 'vcards') + os.sep


    @log_calls('BirthDayPlugin')
    def activate(self):

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
                        data =  node.childNodes[0].nodeValue
                        date_dict[xmldoc[len(self.vcard_path):]] = data
                    except: pass

        today = datetime.date.today()

        for key, value in date_dict.iteritems():
            convert_date = datetime.datetime.strptime(value, "%Y-%m-%d")
            user_bday = datetime.date(
                today.year, convert_date.month, convert_date.day)

            if user_bday < today:
                user_bday = user_bday.replace(year=today.year+1)

            time_to_bday = abs(user_bday - today)
            title = "BirthDay Reminder"
            text = None

            if time_to_bday.days > 5:
                continue
            if time_to_bday.days == 5:
                text = "5 days before BDay %s" % key
            elif time_to_bday.days == 3:
                text = "3 days before BDay %s" % key
            elif time_to_bday.days == 1:
                text = "Tommorrow BDay %s" % key
            elif time_to_bday.days == 0:
                text = "Today BDay %s" % key
            if text:
                popup('', key, key, title=title, text=text)

    @log_calls('BirthDayPlugin')
    def deactivate(self):
        pass

