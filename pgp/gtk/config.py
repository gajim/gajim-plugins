# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the PGP Gajim Plugin.
#
# PGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# PGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

from pathlib import Path

from gi.repository import Gtk
from gi.repository import Gdk

from gajim.common import app

from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _

from pgp.gtk.key import ChooseGPGKeyDialog


class PGPConfigDialog(Gtk.ApplicationWindow):
    def __init__(self, plugin, parent):
        Gtk.ApplicationWindow.__init__(self)
        self.set_application(app.app)
        self.set_show_menubar(False)
        self.set_title(_('PGP Configuration'))
        self.set_transient_for(parent)
        self.set_resizable(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_destroy_with_parent(True)

        ui_path = Path(__file__).parent
        self._ui = get_builder(ui_path.resolve() / 'config.ui')

        self.add(self._ui.config_box)

        self._ui.connect_signals(self)

        self._plugin = plugin

        for account in app.connections.keys():
            page = Page(plugin, account)
            self._ui.stack.add_titled(page,
                                      account,
                                      app.get_account_label(account))

        self.show_all()


class Page(Gtk.Box):
    def __init__(self, plugin, account):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

        self._con = app.connections[account]
        self._plugin = plugin
        self._label = Gtk.Label()
        self._button = Gtk.Button(label=_('Assign Key'))
        self._button.connect('clicked', self._on_assign)

        self._load_key()
        self.add(self._label)
        self.add(self._button)
        self.show_all()

    def _on_assign(self, _button):
        backend = self._con.get_module('PGPLegacy').pgp_backend
        secret_keys = backend.get_keys(secret=True)
        dialog = ChooseGPGKeyDialog(secret_keys, self.get_toplevel())
        dialog.connect('response', self._on_response)

    def _load_key(self):
        key_data = self._con.get_module('PGPLegacy').get_own_key_data()
        if key_data is None:
            self._set_key(None)
        else:
            self._set_key((key_data['key_id'], key_data['key_user']))

    def _on_response(self, dialog, response):
        if response != Gtk.ResponseType.OK:
            return

        if dialog.selected_key is None:
            self._con.get_module('PGPLegacy').set_own_key_data(None)
            self._set_key(None)
        else:
            self._con.get_module('PGPLegacy').set_own_key_data(
                dialog.selected_key)
            self._set_key(dialog.selected_key)

    def _set_key(self, key_data):
        if key_data is None:
            self._label.set_text(_('No key assigned'))
        else:
            key_id, key_user = key_data
            self._label.set_text('%s %s' % (key_id, key_user))
