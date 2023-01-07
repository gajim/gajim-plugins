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
from typing import cast
from typing import TYPE_CHECKING

from gi.repository import Gtk

from gajim.gtk.settings import SettingsDialog
from gajim.gtk.const import Setting
from gajim.gtk.const import SettingKind
from gajim.gtk.const import SettingType

from gajim.plugins.plugins_i18n import _

if TYPE_CHECKING:
    from .anti_spam import AntiSpamPlugin


class AntiSpamConfigDialog(SettingsDialog):
    def __init__(self, plugin: AntiSpamPlugin, parent: Gtk.Window) -> None:
        self.plugin = plugin
        msgtxt_limit = cast(int, self.plugin.config['msgtxt_limit'])
        max_length = '' if msgtxt_limit == 0 else msgtxt_limit

        settings = [
            Setting(SettingKind.ENTRY,
                    _('Limit Message Length'),
                    SettingType.VALUE,
                    str(max_length),
                    callback=self._on_length_setting,
                    data='msgtxt_limit',
                    desc=_('Limits maximum message length (leave empty to '
                           'disable)')),
            Setting(SettingKind.SWITCH,
                    _('Deny Subscription Requests'),
                    SettingType.VALUE,
                    self.plugin.config['block_subscription_requests'],
                    callback=self._on_setting,
                    data='block_subscription_requests'),
            Setting(SettingKind.SWITCH,
                    _('Disable XHTML for Group Chats'),
                    SettingType.VALUE,
                    self.plugin.config['disable_xhtml_muc'],
                    callback=self._on_setting,
                    data='disable_xhtml_muc',
                    desc=_('Removes XHTML formatting from group chat '
                           'messages')),
            Setting(SettingKind.SWITCH,
                    _('Disable XHTML for PMs'),
                    SettingType.VALUE,
                    self.plugin.config['disable_xhtml_pm'],
                    callback=self._on_setting,
                    data='disable_xhtml_pm',
                    desc=_('Removes XHTML formatting from private messages '
                           'in group chats')),
            Setting(SettingKind.ENTRY,
                    _('Anti Spam Question'),
                    SettingType.VALUE,
                    self.plugin.config['msgtxt_question'],
                    callback=self._on_setting,
                    data='msgtxt_question',
                    desc=_('Question has to be answered in order to '
                           'contact you')),
            Setting(SettingKind.ENTRY,
                    _('Anti Spam Answer'),
                    SettingType.VALUE,
                    self.plugin.config['msgtxt_answer'],
                    callback=self._on_setting,
                    data='msgtxt_answer',
                    desc=_('Correct answer to your Anti Spam Question '
                           '(leave empty to disable question)')),
            Setting(SettingKind.SWITCH,
                    _('Anti Spam Question in Group Chats'),
                    SettingType.VALUE,
                    self.plugin.config['antispam_for_conference'],
                    callback=self._on_setting,
                    data='antispam_for_conference',
                    desc=_('Enables anti spam question for private messages '
                           'in group chats')),
            ]

        SettingsDialog.__init__(self,
                                parent,
                                _('Anti Spam Configuration'),
                                Gtk.DialogFlags.MODAL,
                                settings,
                                '')

    def _on_setting(self, value: Any, data: Any) -> None:
        self.plugin.config[data] = value

    def _on_length_setting(self, value: str, data: str) -> None:
        try:
            self.plugin.config[data] = int(value)
        except ValueError:
            self.plugin.config[data] = 0
