# Copyright (C) 2010-2011 Yves Fischer <yvesf AT xapek.org>
# Copyright (C) 2011 Yann Leboulanger <asterix AT lagaule.org>
#
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

import os
import logging
from functools import partial

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib

from gi.repository import Pango

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from latex.latex_renderer import LatexRenderer
from latex.config_dialog import LatexPluginConfiguration
from latex.util import try_run

log = logging.getLogger('gajim.p.latex')


class LatexPlugin(GajimPlugin):
    def init(self):
        self.description = _(
            'Render LaTeX markup for $$foobar$$ sourrounded LaTeX equations.')
        self.config_dialog = partial(LatexPluginConfiguration, self)

        self.config_default_values = {
            'png_dpi': ('108', '')
        }
        self.gui_extension_points = {
            'chat_control_base': (
                self._connect_chat_control_base,
                self._disconnect_chat_control_base)
        }

        self._test_activatable()
        self._timeout_id = None
        self._last_eol_offset = -1

    def _connect_chat_control_base(self, chat_control):
        d = {}
        tv = chat_control.conv_textview.tv
        tb = tv.get_buffer()

        self._latex_tag = Gtk.TextTag.new('latex')
        self._latex_tag.set_property('foreground', 'blue')
        self._latex_tag.set_property('underline', Pango.Underline.SINGLE)
        d['tag_id'] = self._latex_tag.connect('event', self._textview_event_after)
        tb.get_tag_table().add(self._latex_tag)

        d['h_id'] = tb.connect('changed', self._textbuffer_live_latex_expander)
        chat_control.latexs_expander_plugin_data = d

        return True

    def _disconnect_chat_control_base(self, chat_control):
        d = chat_control.latexs_expander_plugin_data
        tv = chat_control.conv_textview.tv

        tv.get_buffer().disconnect(d['h_id'])
        self._latex_tag.disconnect(d['tag_id'])

    def _test_activatable(self):
        """
        performs very simple checks (check if executable is in PATH)
        """
        self.available_text = ''
        exitcode = try_run(['latex', '-version'], None)
        if exitcode != 0:
            latex_available = False
        else:
            latex_available = True

        exitcode = try_run(['dvipng', '--version'], None)
        if exitcode != 0:
            dvipng_available = False
        else:
            dvipng_available = True

        exitcode = try_run(['convert', '-version'], None)
        if exitcode != 0:
            imagemagick_available = False
        else:
            imagemagick_available = True

        pkgs = ''

        if not latex_available:
            if os.name == 'nt':
                pkgs = 'MikTex'
            else:
                pkgs = 'texlive-latex-base'
            self.available_text = _('LaTeX is not available')
            self.activatable = False

        if not dvipng_available and not imagemagick_available:
            if os.name == 'nt':
                if not pkgs:
                    pkgs = 'MikTex'
            else:
                if pkgs:
                    pkgs += _(' and ')
                pkgs += '%s or %s' % ('dvipng', 'ImageMagick')
            if self.available_text:
                self.available_text += ' and '
            self.available_text += _('dvipng and Imagemagick are not available')

        if self.available_text:
            self.activatable = False
            self.available_text += _('. Install %s') % pkgs

    def _textview_event_after(self, tag, widget, event, iter_):
        """
        start rendering if clicked on a link
        """
        if tag.get_property('name') != 'latex' or \
        event.type != Gdk.EventType.BUTTON_PRESS:
            return
        dollar_start, _iter_start = iter_.backward_search(
            '$$',
            Gtk.TextSearchFlags.TEXT_ONLY, None)
        _iter_end, dollar_end = iter_.forward_search(
            '$$',
            Gtk.TextSearchFlags.TEXT_ONLY, None)
        LatexRenderer(dollar_start, dollar_end, widget, self.config['png_dpi'])

    def _textbuffer_live_latex_expander(self, tb):
        """
        called when conversation text widget changes
        """
        def _split_list(list_):
            newlist = []
            for i in range(0, len(list_)-1, 2):
                newlist.append([ list_[i], list_[i+1], ])
            return newlist

        def _detect_tags(tb, start_it=None, end_it=None):
            self._timeout_id = None
            if not end_it:
                end_it = tb.get_end_iter()
            if not start_it:
                eol_tag = tb.get_tag_table().lookup('eol')
                start_it = end_it.copy()
                start_it.backward_to_tag_toggle(eol_tag)
            points = []
            tuple_found = start_it.forward_search(
                '$$',
                Gtk.TextSearchFlags.TEXT_ONLY, None)
            while tuple_found is not None:
                points.append(tuple_found)
                tuple_found = tuple_found[1].forward_search(
                    '$$',
                    Gtk.TextSearchFlags.TEXT_ONLY, None)

            for pair in _split_list(points):
                tb.apply_tag_by_name('latex', pair[0][1], pair[1][0])

        end_iter = tb.get_end_iter()
        eol_tag = tb.get_tag_table().lookup('eol')
        it = end_iter.copy()
        it.backward_to_tag_toggle(eol_tag)
        if it.get_offset() == self._last_eol_offset:
            if self._timeout_id:
                GLib.source_remove(self._timeout_id)
            self._timeout_id = GLib.timeout_add(100, _detect_tags, tb, it, end_iter)
        else:
            if self._timeout_id:
                GLib.source_remove(self._timeout_id)
                it1 = it.copy()
                it1.backward_char()
                it1.backward_to_tag_toggle(eol_tag)
                _detect_tags(tb, it1, it)
            self._last_eol_offset = it.get_offset()
