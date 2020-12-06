#
# This file is part of the TicTacToe plugin for Gajim.
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

from gi.repository import GObject
from gi.repository import Gtk

from gajim.gui.settings import SettingsDialog
from gajim.gui.settings import SpinSetting
from gajim.gui.const import Setting
from gajim.gui.const import SettingType

from gajim.plugins.plugins_i18n import _


class TicTacToeConfigDialog(SettingsDialog):
    def __init__(self, plugin, parent):

        self.plugin = plugin
        settings = [
            Setting('BoardSizeSpinSetting', _('Board Size'),
                    SettingType.VALUE, self.plugin.config['board_size'],
                    callback=self.on_setting, data='board_size',
                    desc=_('Size of the board'),
                    props={'range_': (3, 10)})]

        SettingsDialog.__init__(self, parent, _('TicTacToe Configuration'),
                                Gtk.DialogFlags.MODAL, settings, None,
                                extend=[
                                   ('BoardSizeSpinSetting', SizeSpinSetting)])

    def on_setting(self, value, data):
        self.plugin.config[data] = value


class SizeSpinSetting(SpinSetting):

    __gproperties__ = {
        "setting-value": (int, 'Size', '', 3, 10, 3,
                          GObject.ParamFlags.READWRITE), }

    def __init__(self, *args, **kwargs):
        SpinSetting.__init__(self, *args, **kwargs)
