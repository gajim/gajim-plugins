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

from gajim.gui.settings import SettingsDialog
from gajim.gui.settings import SettingKind
from gajim.gui.const import Setting
from gajim.gui.const import SettingType

from gajim.plugins.plugins_i18n import _


class NowListenConfigDialog(SettingsDialog):
    def __init__(self, plugin, parent):

        self.plugin = plugin
        settings = [
            Setting(SettingKind.ENTRY,
                    _('Format string'),
                    SettingType.VALUE,
                    self.plugin.config['format_string'],
                    callback=self.on_setting, data='format_string')
            ]

        SettingsDialog.__init__(self, parent, _('Now Listen Configuration'),
                                Gtk.DialogFlags.MODAL, settings, None)

    def on_setting(self, value, data):
        self.plugin.config[data] = value
