# -*- coding: utf-8 -*-

## Copyright (C) 2010 Philippe Normand <phil@base-art.net>
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

import dbus
from common import gajim
from common import ged
from common import dbus_support
import gui_interface
from plugins import GajimPlugin
from plugins.helpers import log_calls, log

GNOME_STATUS = [u'online', u'invisible', u'dnd', u'idle']
PRESENCE_INTERFACE = "org.gnome.SessionManager.Presence"

class GnomeSessionManagerPlugin(GajimPlugin):

    @log_calls('GnomeSessionManagerPlugin')
    def init(self):
        self.config_dialog = None
        self.events_handlers = {}

    @log_calls('GnomeSessionManagerPlugin')
    def activate(self):
        if not dbus_support.supported:
            return

        self.bus = dbus_support.session_bus.SessionBus()
        try:
            self.session_presence = self.bus.get_object("org.gnome.SessionManager",
                                                        "/org/gnome/SessionManager/Presence")
        except:
            gajim.log.debug("GNOME SessionManager D-Bus service not found")
            return

        self.active = True
        gajim.ged.register_event_handler('our-show', ged.POSTGUI,
                                         self.on_our_status)
        self.bus.add_signal_receiver(self.gnome_presence_changed,
                                     "StatusChanged", PRESENCE_INTERFACE)

    @log_calls('GnomeSessionManagerPlugin')
    def deactivate(self):
        if not dbus_support.supported or not self.active:
            return

        self.active = False
        self.bus.remove_signal_receiver(self.gnome_presence_changed, "StatusChanged",
                                        dbus_interface=PRESENCE_INTERFACE)
        gajim.ged.remove_event_handler('our-show', ged.POSTGUI, self.on_our_status)


    def gnome_presence_changed(self, status, *args, **kw):
        if not gajim.interface.remote_ctrl:
            try:
                import remote_control
                gajim.interface.remote_ctrl = remote_control.Remote()
            except:
                return
        remote_gajim = gajim.interface.remote_ctrl.signal_object
        gajim_status = GNOME_STATUS[status]
        accounts = remote_gajim.list_accounts()
        for account in accounts:
            message = remote_gajim.get_status_message(account)
            remote_gajim.change_status(gajim_status, message, account)

    def on_our_status(self, network_event):
        try:
            gnome_status = GNOME_STATUS.index(network_event.show)
        except ValueError:
            print "GNOME SessionManager doesn't support %r status" % network_event.show
        else:
            self.session_presence.SetStatus(dbus.UInt32(gnome_status),
                                            dbus_interface=PRESENCE_INTERFACE)
