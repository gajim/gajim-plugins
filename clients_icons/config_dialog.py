# This file is part of Gajim.
#
# Gajim is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

from gi.repository import Gtk

from gajim.common import app

from gajim.gtk.settings import SettingsDialog
from gajim.gtk.const import Setting
from gajim.gtk.const import SettingKind
from gajim.gtk.const import SettingType

from gajim.plugins.plugins_i18n import _


class ClientsIconsConfigDialog(SettingsDialog):
    def __init__(self, plugin, parent):

        icon_position = [
            ('0', _('Before Avatar')),
            ('1', _('After Status Icon'))]

        self.plugin = plugin
        settings = [
            Setting(SettingKind.SWITCH, _('Show Icons in Contact List'),
                    SettingType.VALUE, self.plugin.config['show_in_roster'],
                    callback=self._on_setting, data='show_in_roster'),

            Setting(SettingKind.SWITCH, _('Show Icons in Tooltip'),
                    SettingType.VALUE, self.plugin.config['show_in_tooltip'],
                    callback=self._on_setting, data='show_in_tooltip'),

            Setting(SettingKind.SWITCH, _('Show Icon for Unknown Clients'),
                    SettingType.VALUE, self.plugin.config['show_unknown_icon'],
                    callback=self._on_setting, data='show_unknown_icon'),

            Setting(SettingKind.SWITCH, _('Show Icon for Transports'),
                    SettingType.VALUE, self.plugin.config['show_facebook'],
                    desc=_('Icons for facebook.com and vk.com'),
                    callback=self._on_setting, data='show_facebook'),

            Setting(SettingKind.COMBO, _('Icon Position'),
                    SettingType.VALUE, self.plugin.config['pos_in_list'],
                    callback=self._on_setting, data='pos_in_list',
                    props={'combo_items': icon_position}),
            ]

        SettingsDialog.__init__(self, parent, _('Clients Icons Configuration'),
                                Gtk.DialogFlags.MODAL, settings, None)

    def _on_setting(self, value, data):
        self.plugin.config[data] = value
        self._redraw_all()

    def _redraw_all(self):
        self.plugin.deactivate()
        self.plugin.activate()
        for gc_control in app.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.disconnect_from_groupchat_control(gc_control)
        for gc_control in app.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.connect_with_groupchat_control(gc_control)
