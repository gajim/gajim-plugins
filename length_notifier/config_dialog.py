# -*- coding: utf-8 -*-
#
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

from gi.repository import GObject
from gi.repository import Gtk

from gajim.gtk.settings import SettingsDialog
from gajim.gtk.settings import SpinSetting
from gajim.gtk.const import Setting
from gajim.gtk.const import SettingKind
from gajim.gtk.const import SettingType

from gajim.plugins.plugins_i18n import _


class LengthNotifierConfigDialog(SettingsDialog):
    def __init__(self, plugin, parent):
        self.plugin = plugin
        settings = [
            Setting('MessageLengthSpinSetting',
                    _('Message Length'),
                    SettingType.VALUE,
                    self.plugin.config['MESSAGE_WARNING_LENGTH'],
                    callback=self._on_setting,
                    data='MESSAGE_WARNING_LENGTH',
                    desc=_('Message length at which the highlight is shown'),
                    props={'range_': (1, 1000)},
                    ),
            Setting(SettingKind.COLOR,
                    _('Color'),
                    SettingType.VALUE,
                    self.plugin.config['WARNING_COLOR'],
                    callback=self._on_setting,
                    data='WARNING_COLOR',
                    desc=_('Highlight color for the message input'),
                    ),
            Setting(SettingKind.ENTRY,
                    _('Selected Addresses'),
                    SettingType.VALUE,
                    self.plugin.config['JIDS'],
                    callback=self._on_setting,
                    data='JIDS',
                    desc=_('Enable the plugin for selected XMPP addresses '
                           'only (comma separated)'),
                    ),
            ]

        SettingsDialog.__init__(self, parent,
                                _('Length Notifier Configuration'),
                                Gtk.DialogFlags.MODAL, settings, None,
                                extend=[('MessageLengthSpinSetting',
                                         SizeSpinSetting)])

    def _on_setting(self, value, data):
        self.plugin.config[data] = value
        self.plugin.update_settings()


class SizeSpinSetting(SpinSetting):

    __gproperties__ = {
        "setting-value": (int, 'Size', '', 1, 1000, 140,
                          GObject.ParamFlags.READWRITE), }

    def __init__(self, *args, **kwargs):
        SpinSetting.__init__(self, *args, **kwargs)
