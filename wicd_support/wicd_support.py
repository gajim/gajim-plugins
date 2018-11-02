import os

from gajim.common import app
from gajim.common import dbus_support

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.plugins_i18n import _


class WicdPlugin(GajimPlugin):
    @log_calls('WicdPlugin')
    def init(self):
        self.description = _(
            'Support for autodetection of network status '
            'for Wicd Network Manager.\nRequires wicd and python-dbus.')
        self.config_dialog = None
        self.test_activatable()

    def test_activatable(self):
        self.available_text = ''
        if os.name == 'nt':
            self.available_text = _('Plugin can\'t be run under Windows.')
            self.activatable = False
            return
        if not dbus_support.supported:
            self.activatable = False
            self.available_text += _('python-dbus is missing! '
                                     'Install python-dbus.')

    @log_calls('WicdPlugin')
    def activate(self):
        try:
            import dbus
            from gajim.common.dbus_support import system_bus

            self.bus = system_bus.bus()

            if 'org.wicd.daemon' not in self.bus.list_names():
                return
            wicd_object = self.bus.get_object('org.wicd.daemon',
                                              '/org/wicd/daemon')
            self.props = dbus.Interface(wicd_object,
                                        'org.freedesktop.DBus.Properties')
            self.bus.add_signal_receiver(self.state_changed,
                                         'StatusChanged',
                                         'org.wicd.daemon',
                                         'org.wicd.daemon',
                                         '/org/wicd/daemon')
        except dbus.DBusException:
            pass

    @log_calls('WicdPlugin')
    def deactivate(self):
        self.bus.remove_signal_receiver(self.state_changed,
                                        'StatusChanged',
                                        'org.wicd.daemon',
                                        'org.wicd.daemon',
                                        '/org/wicd/daemon')

    def state_changed(self, state, _info):
        # Connection state constants
        # NOT_CONNECTED = 0
        # CONNECTING = 1
        # WIRELESS = 2
        # WIRED = 3
        # SUSPENDED = 4
        if state in (2, 3):
            for connection in app.connections.values():
                if app.config.get_per('accounts', connection.name,
                'listen_to_network_manager') and connection.time_to_reconnect:
                    connection._reconnect()
        else:
            for connection in app.connections.values():
                if app.config.get_per('accounts', connection.name,
                'listen_to_network_manager') and connection.connected > 1:
                    connection._disconnectedReconnCB()
