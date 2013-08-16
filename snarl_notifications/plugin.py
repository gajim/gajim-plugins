# -*- coding: utf-8 -*-
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##
'''
Events notifications using Snarl

Fancy events notifications under Windows using Snarl infrastructure.

:note: plugin is at proof-of-concept state.

:author: Yann Leboulanger <asterix@lagaule.org>
:since: 08 April 2012
:copyright: Copyright (2012) Yann Leboulanger <asterix@lagaule.org>
:license: GPL
'''

import pySnarl

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from common import ged
import os.path

class SnarlActionHandler(pySnarl.EventHandler):
    def OnNotificationInvoked(self, uid):
        account, jid, msg_type = uid.split()
        gajim.interface.handle_event(account, jid, msg_type)

class SnarlNotificationsPlugin(GajimPlugin):

    @log_calls('SnarlNotificationsPlugin')
    def init(self):
        self.description = _('Shows events notification using <a href='
            '"http://www.fullphat.net/">Snarl</a> under Windows. '
            'Snarl needs to be installed in system.<br/>'
            '<a href="http://code.google.com/p/pysnarl/">PySnarl bindings</a> '
            'are used.')
        self.config_dialog = None
        self.h = SnarlActionHandler
        self.snarl_win = pySnarl.SnarlApp(
            "pySnarl/Gajim",       # app signature
            "Gajim",               # app title
            os.path.abspath("..\data\pixmaps\gajim.ico"),    # icon
            "",                    # config Tool
            "Gajim will use Snarl to display notifications", # hint
            False,                 # IsDaemon
            self.h,                # event handler
            []                     # classes
        )

        self.events_handlers = {'notification' : (ged.PRECORE, self.notif)}

    @log_calls('SnarlNotificationsPlugin')
    def notif(self, obj):
        if obj.do_popup:
            uid = obj.conn.name + " " + obj.jid + " " + obj.popup_msg_type
            self.snarl_win.notify(
                [],         # actions
                "",         # callbackScript
                "",         # callbackScriptType
                "",         # class
                "",         # defaultCallback
                5,          # duration
                os.path.abspath(obj.popup_image),#r"C:\Documents and Settings\Administrateur\Mes documents\gajim\data\pixmaps\gajim.ico",     # icon
                "",         # mergeUID
                0,          # priority
                "",         # replaceUID
                obj.popup_text,
                obj.popup_title,
                uid,        # UID
                "",         # sound
                -1,         # percent
                0,          # log
                64,         # sensitivity
            )
            obj.do_popup = False
