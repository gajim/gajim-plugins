# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of OMEMO Gajim Plugin.
#
# OMEMO Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.


from gajim.plugins.helpers import get_builder


class ProgressWindow:
    def __init__(self, plugin, window, event):
        self._plugin = plugin
        self._event = event

        path = self._plugin.local_file_path('gtk/progress.ui')
        self._ui = get_builder(path)
        self._ui.progress_dialog.set_transient_for(window)
        self._ui.progressbar.set_text("")
        self._ui.progress_dialog.show_all()

        image_path = self._plugin.local_file_path('omemo.png')
        self._ui.image.set_from_file(image_path)
        self._ui.connect_signals(self)
        self._seen = 0

    def set_text(self, text):
        self._ui.label.set_markup('<big>%s</big>' % text)
        return False

    def update_progress(self, seen, total):
        self._seen += seen
        pct = (self._seen / float(total)) * 100.0
        self._ui.progressbar.set_fraction(self._seen / float(total))
        self._ui.progressbar.set_text(str(int(pct)) + "%")
        return False

    def close_dialog(self, *args):
        self._ui.progress_dialog.destroy()
        return False

    def on_destroy(self, *args):
        self._event.set()
