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

from gajim.common import app
from gajim.plugins.plugins_i18n import _
from gajim.plugins.helpers import get_builder


class KeyDialog(Gtk.Dialog):
    def __init__(self, plugin, account, jid, transient):
        super().__init__(title=_('Assign key for %s') % jid,
                         destroy_with_parent=True)

        self.set_transient_for(transient)
        self.set_resizable(True)
        self.set_default_size(500, 300)

        self._plugin = plugin
        self._jid = jid
        self._con = app.connections[account]

        self._label = Gtk.Label()

        self._assign_button = Gtk.Button(label='assign')
        self._assign_button.connect('clicked', self._choose_key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add(self._label)
        box.add(self._assign_button)

        area = self.get_content_area()
        area.pack_start(box, True, True, 0)

        self._load_key()
        self.show_all()

    def _choose_key(self, *args):
        backend = self._con.get_module('PGPLegacy').pgp_backend
        dialog = ChooseGPGKeyDialog(backend.get_keys(), self)
        dialog.connect('response', self._on_response)

    def _load_key(self):
        key_data = self._con.get_module('PGPLegacy').get_contact_key_data(
            self._jid)
        if key_data is None:
            self._set_key(None)
        else:
            self._set_key(key_data.values())

    def _on_response(self, dialog, response):
        if response != Gtk.ResponseType.OK:
            return

        if dialog.selected_key is None:
            self._con.get_module('PGPLegacy').set_contact_key_data(
                self._jid, None)
            self._set_key(None)
        else:
            self._con.get_module('PGPLegacy').set_contact_key_data(
                self._jid, dialog.selected_key)
            self._set_key(dialog.selected_key)

    def _set_key(self, key_data):
        if key_data is None:
            self._label.set_text(_('No key assigned'))
        else:
            key_id, key_user = key_data
            self._label.set_text('%s %s' % (key_id, key_user))


class ChooseGPGKeyDialog(Gtk.Dialog):
    def __init__(self, secret_keys, transient_for):
        Gtk.Dialog.__init__(self,
                            title=_('Assign PGP Key'),
                            transient_for=transient_for)

        secret_keys[_('None')] = _('None')

        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self.set_resizable(True)
        self.set_default_size(500, 300)

        self.add_button(_('OK'), Gtk.ResponseType.OK)
        self.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)

        self._selected_key = None

        ui_path = Path(__file__).parent
        self._ui = get_builder(ui_path.resolve() / 'choose_key.ui')

        self._ui.keys_treeview = self._ui.keys_treeview

        model = self._ui.keys_treeview.get_model()
        model.set_sort_func(1, self._sort)

        model = self._ui.keys_treeview.get_model()
        for key_id in secret_keys.keys():
            model.append((key_id, secret_keys[key_id]))

        self.get_content_area().add(self._ui.box)

        self._ui.connect_signals(self)

        self.connect_after('response', self._on_response)

        self.show_all()

    @property
    def selected_key(self):
        return self._selected_key

    @staticmethod
    def _sort(model, iter1, iter2, _data):
        value1 = model[iter1][1]
        value2 = model[iter2][1]
        if value1 == _('None'):
            return -1
        if value2 == _('None'):
            return 1
        if value1 < value2:
            return -1
        return 1

    def _on_response(self, _dialog, _response):
        self.destroy()

    def _on_row_changed(self, treeview):
        selection = treeview.get_selection()
        model, iter_ = selection.get_selected()
        if iter_ is None:
            self._selected_key = None
        else:
            key_id, key_user = model[iter_][0], model[iter_][1]
            if key_id == _('None'):
                self._selected_key = None
            else:
                self._selected_key = key_id, key_user
