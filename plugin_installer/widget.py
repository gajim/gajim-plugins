# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

from enum import IntEnum

from gi.repository import Gtk

from gajim.common.helpers import Observable

from gajim.plugins.plugins_i18n import _
from gajim.plugins.helpers import get_builder

class Column(IntEnum):
    PIXBUF = 0
    NAME = 1
    INSTALLED_VERSION = 2
    VERSION = 3
    INSTALL = 4
    PLUGIN = 5


class AvailablePage(Observable):
    def __init__(self, builder_path, notebook):
        Observable.__init__(self)
        self._ui = get_builder(builder_path)

        self._notebook = notebook
        self._page_num = self._notebook.append_page(
            self._ui.available_plugins_box,
            Gtk.Label.new(_('Available')))

        self._ui.plugin_store.set_sort_column_id(1, Gtk.SortType.ASCENDING)
        self._ui.connect_signals(self)

    def destroy(self):
        self._notebook.remove_page(self._page_num)
        self._notebook = None
        self._ui.plugin_store.clear()
        self._ui.available_plugins_box.destroy()
        self._ui = None
        self._plugin = None
        self.disconnect_signals()

    def show_page(self):
        self._notebook.set_current_page(self._page_num)

    def append_plugins(self, plugins):
        for plugin in plugins:
            self._ui.plugin_store.append(plugin.fields)

        if plugins:
            self._select_first_plugin()

        self._update_install_button()
        self._ui.spinner.stop()
        self._ui.spinner.hide()

    def update_plugin(self, plugin):
        for row in self._ui.plugin_store:
            if row[Column.NAME] == plugin.name:
                row[Column.INSTALLED_VERSION] = str(plugin.version)
                row[Column.INSTALL] = False
                break

    def set_download_in_progress(self, state):
        self._download_in_progress = state
        self._update_install_button()

    def _available_plugin_toggled(self, _cell, path):
        is_active = self._ui.plugin_store[path][Column.INSTALL]
        self._ui.plugin_store[path][Column.INSTALL] = not is_active
        self._update_install_button()

    def _update_install_button(self):
        if self._download_in_progress:
            self._ui.install_plugin_button.set_sensitive(False)
            return

        sensitive = False
        for row in self._ui.plugin_store:
            if row[Column.INSTALL]:
                sensitive = True
                break
        self._ui.install_plugin_button.set_sensitive(sensitive)

    def _on_install_update_clicked(self, _button):
        self._ui.install_plugin_button.set_sensitive(False)

        plugins = []
        for row in self._ui.plugin_store:
            if row[Column.INSTALL]:
                plugins.append(row[Column.PLUGIN])

        self.notify('download-plugins', plugins)

    def _on_plugin_selection_changed(self, selection):
        model, iter_ = selection.get_selected()
        if not iter_:
            self._clear_plugin_info()
        else:
            self._set_plugin_info(model, iter_)

    def _clear_plugin_info(self):
        self._ui.name_label.set_text('')
        self._ui.description_label.set_text('')
        self._ui.version_label.set_text('')
        self._ui.authors_label.set_text('')
        self._ui.homepage_linkbutton.set_text('')
        self._ui.install_plugin_button.set_sensitive(False)

    def _set_plugin_info(self, model, iter_):
        plugin = model[iter_][Column.PLUGIN]
        self._ui.name_label.set_text(plugin.name)
        self._ui.version_label.set_text(str(plugin.version))
        self._ui.authors_label.set_text(plugin.authors)
        homepage = '<a href="%s">%s</a>' % (plugin.homepage, plugin.homepage)
        self._ui.homepage_linkbutton.set_markup(homepage)
        self._ui.description_label.set_text(plugin.description)

    def _select_first_plugin(self):
        selection = self._ui.available_plugins_treeview.get_selection()
        iter_ = self._ui.plugin_store.get_iter_first()
        selection.select_iter(iter_)

        path = self._ui.plugin_store.get_path(iter_)
        self._ui.available_plugins_treeview.scroll_to_cell(path)
