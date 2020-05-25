# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

from gi.repository import GObject
from gi.repository import Gtk

from gajim.gtk.settings import SettingsDialog
from gajim.gtk.settings import SpinSetting
from gajim.gtk.const import Setting
from gajim.gtk.const import SettingType

from gajim.plugins.plugins_i18n import _


class LatexPluginConfiguration(SettingsDialog):
    def __init__(self, plugin, parent):
        self.plugin = plugin

        settings = [
            Setting('LatexDPISpinSetting', _('PNG DPI'),
                    SettingType.VALUE, int(self.plugin.config['png_dpi']),
                    callback=self.on_setting, data='png_dpi',
                    desc=_('Scale of the rendered PNG file'),
                    props={'range_': (72, 300)}),
        ]

        SettingsDialog.__init__(self, parent, _('Latex Configuration'),
                                Gtk.DialogFlags.MODAL, settings, None,
                                extend=[('LatexDPISpinSetting',
                                         DPISpinSetting)])

    def on_setting(self, value, data):
        self.plugin.config[data] = value

class DPISpinSetting(SpinSetting):

    __gproperties__ = {
        "setting-value": (int, 'Size', '', 72, 300, 108,
                          GObject.ParamFlags.READWRITE), }

    def __init__(self, *args, **kwargs):
        SpinSetting.__init__(self, *args, **kwargs)
