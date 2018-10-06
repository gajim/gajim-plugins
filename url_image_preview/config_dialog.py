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

from gi.repository import GObject
from gi.repository import Gtk

from gajim.options_dialog import OptionsDialog, GenericOption, SpinOption
from gajim.common.const import Option, OptionType, OptionKind

# Since Gajim 1.1.0 _() has to be imported
try:
    from gajim.common.i18n import _
except ImportError:
    pass

class UrlImagePreviewConfigDialog(OptionsDialog):
    def __init__(self, plugin, parent):

        sizes = [('256 KiB', '262144'),
                 ('512 KiB', '524288'),
                 ('1 MiB', '1048576'),
                 ('5 MiB', '5242880'),
                 ('10 MiB', '10485760')]
        actions = [
            (_('Open'), 'open_menuitem'),
            (_('Save as'), 'save_as_menuitem'),
            (_('Copy Link Location'), 'copy_link_location_menuitem'),
            (_('Open Link in Browser'), 'open_link_in_browser_menuitem'),
            (_('Open File in Browser'), 'open_file_in_browser_menuitem')]

        geo_providers = [
            (_('No map preview'), 'no_preview'),
            ('Google Maps', 'Google'),
            ('OpenStreetMap', 'OSM')]

        self.plugin = plugin
        options = [
            Option('PreviewSizeSpinOption', _('Preview size'),
                   OptionType.VALUE, self.plugin.config['PREVIEW_SIZE'],
                   callback=self.on_option, data='PREVIEW_SIZE',
                   props={'range_': (100, 1000)}),

            Option('PreviewComboOption', _('Accepted filesize'),
                   OptionType.VALUE, self.plugin.config['MAX_FILE_SIZE'],
                   callback=self.on_option, data='MAX_FILE_SIZE',
                   props={'items': sizes,
                          'plugin': self.plugin}),

            Option(OptionKind.SWITCH, _('Preview all Image URLs'),
                   OptionType.VALUE, self.plugin.config['ALLOW_ALL_IMAGES'],
                   callback=self.on_option, data='ALLOW_ALL_IMAGES'),

            Option('PreviewComboOption', _('Left click action'),
                   OptionType.VALUE, self.plugin.config['LEFTCLICK_ACTION'],
                   callback=self.on_option, data='LEFTCLICK_ACTION',
                   props={'items': actions,
                          'plugin': self.plugin}),

            Option('PreviewComboOption', _('Map service for preview'),
                   OptionType.VALUE, self.plugin.config['GEO_PREVIEW_PROVIDER'],
                   callback=self.on_option, data='GEO_PREVIEW_PROVIDER',
                   props={'items': geo_providers,
                          'plugin': self.plugin}),

            Option(OptionKind.SWITCH, _('Enable HTTPS Verification'),
                   OptionType.VALUE, self.plugin.config['VERIFY'],
                   callback=self.on_option, data='VERIFY'),
            ]

        OptionsDialog.__init__(self, parent, _('UrlImagePreview Options'),
                               Gtk.DialogFlags.MODAL, options, None,
                               extend=[
                                   ('PreviewComboOption', ComboOption),
                                   ('PreviewSizeSpinOption', SizeSpinOption)])

    def on_option(self, value, data):
        self.plugin.config[data] = value


class SizeSpinOption(SpinOption):

    __gproperties__ = {
        "option-value": (int, 'Size', '', 100, 1000, 300,
                         GObject.ParamFlags.READWRITE), }

    def __init__(self, *args, **kwargs):
        SpinOption.__init__(self, *args, **kwargs)


class ComboOption(GenericOption):

    __gproperties__ = {
        "option-value": (str, 'Value', '', '',
                         GObject.ParamFlags.READWRITE), }

    def __init__(self, *args, items, plugin):
        GenericOption.__init__(self, *args)
        self.plugin = plugin
        self.combo = Gtk.ComboBox()
        text_renderer = Gtk.CellRendererText()
        self.combo.pack_start(text_renderer, True)
        self.combo.add_attribute(text_renderer, 'text', 0)

        self.store = Gtk.ListStore(str, str)
        for item in items:
            self.store.append(item)

        self.combo.set_model(self.store)
        self.combo.set_id_column(1)
        self.combo.set_active_id(str(self.option_value))

        self.combo.connect('changed', self.on_value_change)
        self.combo.set_valign(Gtk.Align.CENTER)

        self.option_box.pack_start(self.combo, True, True, 0)
        self.show_all()

    def on_value_change(self, combo):
        self.set_value(combo.get_active_id())

    def on_row_activated(self):
        pass
