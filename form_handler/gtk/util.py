# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Form Handler.
#
# Form Handler is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Form Handler is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Form Handler. If not, see <http://www.gnu.org/licenses/>.

from gi.repository import Gtk


def get_button(label, data, callback):
    button = Gtk.Button(label=label)
    button.connect('clicked', callback, data)
    return button
