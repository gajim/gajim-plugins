# -*- coding: utf-8 -*-

# Copyright (C) 2017 Kyoken, kyoken@kyoken.ninja

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 3
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import os

from plugins import GajimPlugin
from plugins.helpers import log_calls
from common import dbus_support, gajim as app

ERR_MSG = ''

if dbus_support.supported:
    import dbus
    import dbus.service

    class LauncherEntry(dbus.service.Object):
        '''
        https://wiki.ubuntu.com/Unity/LauncherAPI
        '''
        def __init__(self, conn, object_path='/org/gajim/Gajim'):
            dbus.service.Object.__init__(self, conn, object_path)

        @dbus.service.signal('com.canonical.Unity.LauncherEntry',
                             signature='sa{sv}')
        def Update(self, app_uri, properties):
            pass

else:
    ERR_MSG = 'D-Bus Python bindings are missing.'

if os.name == 'nt':
    ERR_MSG = "Plugin can't be run under Windows."


class UbuntuDockPlugin(GajimPlugin):
    @log_calls('UbuntuDockPlugin')
    def init(self):
        self.config_dialog = None
        if ERR_MSG:
            self.available_text = ERR_MSG
            self.activatable = False

    @log_calls('UbuntuDockPlugin')
    def activate(self):
        bus = dbus.SessionBus()
        self.launcher = LauncherEntry(bus)

        app.events.event_added_subscribe(self.update_count)
        app.events.event_removed_subscribe(self.update_count)
        self.active = True

    @log_calls('UbuntuDockPlugin')
    def deactivate(self):
        app.events.event_added_unsubscribe(self.update_count)
        app.events.event_removed_unsubscribe(self.update_count)
        self.active = False

    def update_count(self, *args):
        nb_unread = 0
        for account in app.connections:
            events = [
                'chat', 'normal',
                'file-request', 'file-error', 'file-completed',
                'file-request-error', 'file-send-error', 'file-stopped',
                'printed_chat',
                'printed_marked_gc_msg',
            ]
            if app.config.get('notify_on_all_muc_messages'):
                events.append('printed_gc_msg')
            nb_unread += app.events.get_nb_events(events, account)

        self.launcher.Update('application://gajim.desktop', {
            'count': dbus.Int64(nb_unread),
            'count-visible': bool(nb_unread),
        })
