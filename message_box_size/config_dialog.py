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

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING

from gi.repository import Gtk

from gajim.gtk.const import Setting
from gajim.gtk.const import SettingKind
from gajim.gtk.const import SettingType
from gajim.gtk.settings import SettingsDialog
from gajim.plugins.plugins_i18n import _

if TYPE_CHECKING:
    from .msg_box_size import MsgBoxSizePlugin


class MessageBoxSizeConfigDialog(SettingsDialog):
    def __init__(self, plugin: MsgBoxSizePlugin, parent: Gtk.Window) -> None:

        self.plugin = plugin
        settings = [
            Setting(
                SettingKind.SPIN,
                _("Height in pixels"),
                SettingType.VALUE,
                str(self.plugin.config["HEIGHT"]),
                callback=self._on_setting,
                data="HEIGHT",
                desc=_("Size of message input in pixels"),
                props={"range_": (20, 200, 1)},
            ),
        ]

        SettingsDialog.__init__(
            self,
            parent,
            _("Message Box Size Configuration"),
            Gtk.DialogFlags.MODAL,
            settings,
            "",
        )

    def _on_setting(self, value: Any, data: Any) -> None:
        self.plugin.config[data] = value
        self.plugin.set_input_height(value)
