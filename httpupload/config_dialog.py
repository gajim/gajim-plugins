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

from gi.repository import Gtk

from gajim.options_dialog import OptionsDialog
from gajim.common.const import Option, OptionKind, OptionType


class HTTPUploadConfigDialog(OptionsDialog):
    def __init__(self, plugin, parent):
        self.plugin = plugin
        options = [
            Option(OptionKind.SWITCH, _('Enable HTTPS Verification'),
                   OptionType.VALUE, self.plugin.config['verify'],
                   callback=self.on_option, data='verify'),
            ]

        OptionsDialog.__init__(self, parent, _('HTTP Upload Options'),
                               Gtk.DialogFlags.MODAL, options, None)

    def on_option(self, value, data):
        self.plugin.config[data] = value
