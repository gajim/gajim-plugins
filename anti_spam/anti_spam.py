# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim.  If not, see <http://www.gnu.org/licenses/>.

"""
:author: Yann Leboulanger <asterix@lagaule.org>
:since: 16 August 2012
:copyright: Copyright (2012) Yann Leboulanger <asterix@lagaule.org>
:license: GPLv3
"""

from functools import partial

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from anti_spam.config_dialog import AntiSpamConfigDialog
from anti_spam.modules import anti_spam


class AntiSpamPlugin(GajimPlugin):
    def init(self) -> None:
        self.description = _(
            "Allows you to block various kinds of incoming "
            "messages (Spam, XHTML formatting, etc.)"
        )
        self.config_dialog = partial(AntiSpamConfigDialog, self)
        self.config_default_values = {
            "disable_xhtml_muc": (False, ""),
            "disable_xhtml_pm": (False, ""),
            "block_subscription_requests": (False, ""),
            "msgtxt_limit": (0, ""),
            "msgtxt_question": ("12 x 12 = ?", ""),
            "msgtxt_answer": ("", ""),
            "antispam_for_conference": (False, ""),
            "block_domains": ("", ""),
            "whitelist": ([], ""),
        }
        self.gui_extension_points = {}
        self.modules = [anti_spam]
