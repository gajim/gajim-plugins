# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Quick Replies.
#
# Quick Replies is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Quick Replies is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Quick Replies. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from typing import Any
from typing import TYPE_CHECKING

from pathlib import Path

from gi.repository import Gtk
from gi.repository import Gdk

from gajim.common import app

from gajim.plugins.plugins_i18n import _
from gajim.plugins.helpers import get_builder

if TYPE_CHECKING:
    from ..plugin import QuickRepliesPlugin


class ConfigDialog(Gtk.ApplicationWindow):
    def __init__(self,
                 plugin: QuickRepliesPlugin,
                 transient: Gtk.Window
                 ) -> None:

        Gtk.ApplicationWindow.__init__(self)
        self.set_application(app.app)
        self.set_show_menubar(False)
        self.set_title(_('Quick Replies Configuration'))
        self.set_transient_for(transient)
        self.set_default_size(400, 400)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_modal(True)
        self.set_destroy_with_parent(True)

        ui_path = Path(__file__).parent
        self._ui = get_builder(str(ui_path.resolve() / 'config.ui'))

        self._plugin = plugin

        self.add(self._ui.box)

        self._fill_list()
        self.show_all()

        self._ui.connect_signals(self)
        self.connect('destroy', self._on_destroy)

    def _fill_list(self) -> None:
        for reply in self._plugin.quick_replies:
            self._ui.replies_store.append([reply])

    def _on_reply_edited(self,
                         _renderer: Gtk.CellRendererText,
                         path: str,
                         new_text: str
                         ) -> None:

        iter_ = self._ui.replies_store.get_iter(path)
        self._ui.replies_store.set_value(iter_, 0, new_text)

    def _on_add_clicked(self, _button: Gtk.Button) -> None:
        self._ui.replies_store.append([_('New Quick Reply')])
        row = self._ui.replies_store[-1]
        self._ui.replies_treeview.scroll_to_cell(
            row.path, None, False, 0, 0)
        self._ui.selection.unselect_all()
        self._ui.selection.select_path(row.path)

    def _on_remove_clicked(self, _button: Gtk.Button) -> None:
        model, paths = self._ui.selection.get_selected_rows()
        references: list[Gtk.TreeRowReference] = []
        for path in paths:
            references.append(Gtk.TreeRowReference.new(model, path))

        for ref in references:
            iter_ = model.get_iter(ref.get_path())
            self._ui.replies_store.remove(iter_)

    def _on_destroy(self, *args: Any) -> None:
        replies: list[str] = []
        for row in self._ui.replies_store:
            if row[0] == '':
                continue
            replies.append(row[0])
        self._plugin.set_quick_replies(replies)
