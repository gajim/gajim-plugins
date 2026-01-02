# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Acronyms Expander.
#
# Acronyms Expander is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Acronyms Expander is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Acronyms Expander. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from typing import cast
from typing import TYPE_CHECKING

from pathlib import Path

from gi.repository import Gtk

from gajim.gtk.widgets import GajimAppWindow
from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _

if TYPE_CHECKING:
    from ..acronyms_expander import AcronymsExpanderPlugin


class ConfigBuilder(Gtk.Builder):
    acronyms_store: Gtk.ListStore
    box: Gtk.Box
    acronyms_treeview: Gtk.TreeView
    selection: Gtk.TreeSelection
    acronym_renderer: Gtk.CellRendererText
    sub_renderer: Gtk.CellRendererText
    add_button: Gtk.Button
    remove_button: Gtk.Button


class ConfigDialog(GajimAppWindow):
    def __init__(self, plugin: AcronymsExpanderPlugin, transient: Gtk.Window) -> None:
        GajimAppWindow.__init__(
            self,
            name="AcronymsConfigDialog",
            title=_("Acronyms Configuration"),
            default_width=400,
            default_height=400,
            transient_for=transient,
            modal=True,
        )

        ui_path = Path(__file__).parent
        self._ui = cast(
            ConfigBuilder, get_builder(str(ui_path.resolve() / "config.ui"))
        )

        self._plugin = plugin

        self.set_child(self._ui.box)

        self._fill_list()

        self._connect(self._ui.acronym_renderer, "edited", self._on_acronym_edited)
        self._connect(self._ui.sub_renderer, "edited", self._on_substitute_edited)
        self._connect(self._ui.add_button, "clicked", self._on_add_clicked)
        self._connect(self._ui.remove_button, "clicked", self._on_remove_clicked)
        self._connect(self.window, "close-request", self._on_close_request)

        self.show()

    def _cleanup(self) -> None:
        del self._plugin

    def _fill_list(self) -> None:
        for acronym, substitute in self._plugin.acronyms.items():
            self._ui.acronyms_store.append([acronym, substitute])

    def _on_acronym_edited(
        self, _renderer: Gtk.CellRendererText, path: str, new_text: str
    ) -> None:
        iter_ = self._ui.acronyms_store.get_iter(path)
        self._ui.acronyms_store.set_value(iter_, 0, new_text)

    def _on_substitute_edited(
        self, _renderer: Gtk.CellRendererText, path: str, new_text: str
    ) -> None:
        iter_ = self._ui.acronyms_store.get_iter(path)
        self._ui.acronyms_store.set_value(iter_, 1, new_text)

    def _on_add_clicked(self, _button: Gtk.Button) -> None:
        self._ui.acronyms_store.append(["", ""])
        row = self._ui.acronyms_store[-1]
        self._ui.acronyms_treeview.scroll_to_cell(row.path, None, False, 0, 0)
        self._ui.selection.unselect_all()
        self._ui.selection.select_path(row.path)

    def _on_remove_clicked(self, _button: Gtk.Button) -> None:
        res = self._ui.selection.get_selected_rows()
        if res is None:
            return

        model, paths = res
        references: list[Gtk.TreeRowReference] = []
        for path in paths:
            ref = Gtk.TreeRowReference.new(model, path)
            assert ref is not None
            references.append(ref)

        for ref in references:
            path = ref.get_path()
            assert path is not None
            iter_ = model.get_iter(path)
            self._ui.acronyms_store.remove(iter_)

    def _on_close_request(self, win: Gtk.ApplicationWindow) -> None:
        acronyms: dict[str, str] = {}
        for row in self._ui.acronyms_store:
            acronym, substitute = row
            if not acronym or not substitute:
                continue
            acronyms[acronym] = substitute
        self._plugin.set_acronyms(acronyms)
