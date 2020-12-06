# -*- coding: utf-8 -*-
#
# Copyright (C) 2017 Philipp Hörist <philipp AT hoerist.com>
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

from gajim.gui.settings import SettingsDialog
from gajim.gui.settings import SpinSetting
from gajim.gui.const import Setting
from gajim.gui.const import SettingKind
from gajim.gui.const import SettingType

from gajim.plugins.plugins_i18n import _


class UrlImagePreviewConfigDialog(SettingsDialog):
    def __init__(self, plugin, parent):

        sizes = [('262144', '256 KiB'),
                 ('524288', '512 KiB'),
                 ('1048576', '1 MiB'),
                 ('5242880', '5 MiB'),
                 ('10485760', '10 MiB')]

        actions = [
            ('open', _('Open')),
            ('save_as', _('Save as')),
            ('open_folder', _('Open Folder')),
            ('copy_link_location', _('Copy Link Location')),
            ('open_link_in_browser', _('Open Link in Browser'))]

        self.plugin = plugin
        settings = [
            Setting('PreviewSizeSpinSetting', _('Preview Size'),
                    SettingType.VALUE, self.plugin.config['PREVIEW_SIZE'],
                    callback=self.on_setting, data='PREVIEW_SIZE',
                    desc=_('Size of preview image'),
                    props={'range_': (100, 1000)}),

            Setting(SettingKind.COMBO, _('File Size'),
                    SettingType.VALUE, self.plugin.config['MAX_FILE_SIZE'],
                    callback=self.on_setting, data='MAX_FILE_SIZE',
                    desc=_('Maximum file size for preview generation'),
                    props={'combo_items': sizes}),

            Setting(SettingKind.SWITCH, _('Preview all Image URLs'),
                    SettingType.VALUE, self.plugin.config['ALLOW_ALL_IMAGES'],
                    callback=self.on_setting, data='ALLOW_ALL_IMAGES',
                    desc=_('Generate preview for any URL containing images '
                           '(may be unsafe)')),

            Setting(SettingKind.COMBO, _('Left Click'),
                    SettingType.VALUE, self.plugin.config['LEFTCLICK_ACTION'],
                    callback=self.on_setting, data='LEFTCLICK_ACTION',
                    desc=_('Action when left clicking a preview'),
                    props={'combo_items': actions}),

            Setting(SettingKind.SWITCH, _('HTTPS Verification'),
                    SettingType.VALUE, self.plugin.config['VERIFY'],
                    desc=_('Whether to check for a valid certificate'),
                    callback=self.on_setting, data='VERIFY'),
            ]

        SettingsDialog.__init__(self, parent, _('UrlImagePreview Configuration'),
                                Gtk.DialogFlags.MODAL, settings, None,
                                extend=[('PreviewSizeSpinSetting',
                                         SizeSpinSetting)])

    def on_setting(self, value, data):
        self.plugin.config[data] = value


class SizeSpinSetting(SpinSetting):

    __gproperties__ = {
        "setting-value": (int, 'Size', '', 100, 1000, 300,
                          GObject.ParamFlags.READWRITE), }

    def __init__(self, *args, **kwargs):
        SpinSetting.__init__(self, *args, **kwargs)
