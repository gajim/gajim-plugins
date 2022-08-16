from gi.repository import GObject
from gi.repository import Gtk

from gajim.gui.settings import SettingsDialog
from gajim.gui.settings import SpinSetting
from gajim.gui.const import Setting
from gajim.gui.const import SettingType

from gajim.plugins.plugins_i18n import _


class MessageBoxSizeConfigDialog(SettingsDialog):
    def __init__(self, plugin, parent):

        self.plugin = plugin
        settings = [
            Setting('PreviewSizeSpinSetting', _('Height in pixels'),
                    SettingType.VALUE, self.plugin.config['HEIGHT'],
                    callback=self.on_setting, data='HEIGHT',
                    desc=_('Size of message input in pixels'),
                    props={'range_': (20, 200)}),
            ]

        SettingsDialog.__init__(self, parent, _('Message Box Size Configuration'),
                                Gtk.DialogFlags.MODAL, settings, None,
                                extend=[('PreviewSizeSpinSetting',
                                         SizeSpinSetting)])

    def on_setting(self, value, data):
        self.plugin.config[data] = value
        self.plugin.set_input_height(value)


class SizeSpinSetting(SpinSetting):

    __gproperties__ = {
        "setting-value": (int, 'Size', '', 20, 200, 20,
                          GObject.ParamFlags.READWRITE), }

    def __init__(self, *args, **kwargs):
        SpinSetting.__init__(self, *args, **kwargs)
