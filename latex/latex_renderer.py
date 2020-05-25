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

import random
import os
import logging
from tempfile import mkstemp
from tempfile import mkdtemp

from gi.repository import Gtk
from gi.repository import GdkPixbuf
from gi.repository import GLib

from gajim.common import app

from gajim.plugins.plugins_i18n import _

from latex.util import try_run
from latex.util import write_latex
from latex.util import BLACKLIST

log = logging.getLogger('gajim.p.latex')


class LatexRenderer:
    def __init__(self, iter_start, iter_end, widget, png_dpi):
        self.widget = widget
        self.buffer = widget.get_buffer()
        self.code = iter_start.get_text(iter_end)
        self.mark_name = 'LatexRendererMark%s' % str(random.randint(0, 1000))
        self.mark = self.buffer.create_mark(self.mark_name, iter_start, True)
        self.png_dpi = str(png_dpi)

        # delete code and show message 'processing'
        self.buffer.delete(iter_start, iter_end)
        self.buffer.insert(iter_start, _('Processing LaTeX'))
        self._start_processing()

    def _start_processing(self):
        try:
            if self._check_code():
                self._show_image()
            else:
                self._show_error(_('There are bad commands!'))
        except Exception as err:
            self._show_error(_('Error processing LaTeX: %s' % err))
        finally:
            self.buffer.delete_mark(self.mark)

    def _check_code(self):
        for bad_cmd in BLACKLIST:
            if self.code.find(bad_cmd) != -1:
                # Found bad command
                return False
        return True

    def _show_error(self, message):
        """
        String -> TextBuffer
        """
        iter_mark = self.buffer.get_iter_at_mark(self.mark)
        iter_end = iter_mark.copy().forward_search(
            _('Processing LaTeX'),
            Gtk.TextSearchFlags.TEXT_ONLY, None)[1]
        self.buffer.delete(iter_mark, iter_end)
        self.buffer.insert(iter_end, message)

    def _show_image(self):
        """
        Latex -> PNG -> TextBuffer
        """

        def _fg_str(fmt):
            try:
                return [
                    {'hex' : '+level-colors', 'tex' : '-fg'}[fmt],
                    app.interface.get_fg_color(fmt)]
            except KeyError:
                # interface may not be available when we test latex at startup
                return []
            except AttributeError:
                # interface may not be available when we test latext at startup
                return {'hex': ['+level-colors', '0x000000'],
                        'tex': ['-fg', 'rgb 0.0 0.0 0.0']}[fmt]

        try:
            tmpdir = mkdtemp(prefix='gajim_tex')
            tmpfd, tmppng = mkstemp(prefix='gajim_tex', suffix='.png')
            os.close(tmpfd)
        except Exception:
            msg = 'Could not create temporary files for Latex plugin'
            log.debug(msg)
            self._show_error(
                _('latex error: %(error)s\n===ORIGINAL CODE====\n'
                  '%(code)s') % {
                      'error': msg,
                      'code': self.code[2:len(self.code)-2]})
            return False

        tmpfile = os.path.join(tmpdir, 'gajim_tex')

        # build latex string
        write_latex(tmpfile + '.tex', self.code[2:len(self.code)-2])

        # convert TeX to dvi
        exitcode = try_run(
            ['latex', '--interaction=nonstopmode', tmpfile + '.tex'], tmpdir)

        if exitcode == 0:
            # convert dvi to png
            log.debug('DVI OK')
            exitcode = try_run(
                ['dvipng', '-bg', 'Transparent'] + _fg_str('tex') + \
                ['-T', 'tight', '-D', self.png_dpi, tmpfile + '.dvi', '-o',
                 tmpfile + '.png'], tmpdir)

            if exitcode:
                # dvipng failed, try convert
                log.debug('dvipng failed, try convert')
                exitcode = try_run(
                    ['convert'] + _fg_str('hex') + \
                    ['-trim', '-density', self.png_dpi,
                     tmpfile + '.dvi', tmpfile + '.png'], tmpdir)

        # remove temp files created by us and TeX
        extensions = ['.tex', '.log', '.aux', '.dvi']
        for ext in extensions:
            try:
                os.remove(tmpfile + ext)
            except Exception:
                pass

        if exitcode == 0:
            log.debug('PNG OK')
            os.rename(tmpfile + '.png', tmppng)
        else:
            log.debug('PNG FAILED')
            os.remove(tmppng)
            os.rmdir(tmpdir)
            self._show_error(
                _('Convertion to image failed\n===ORIGINAL CODE===='
                  '\n%s') % self.code[2:len(self.code)-2])
            return False

        log.debug('Loading PNG %s', tmppng)
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmppng)
            log.debug('png loaded')
            iter_mark = self.buffer.get_iter_at_mark(self.mark)
            iter_end = iter_mark.copy().forward_search(
                _('Processing LaTeX'),
                Gtk.TextSearchFlags.TEXT_ONLY, None)[1]
            log.debug('Delete old Text')
            self.buffer.delete(iter_mark, iter_end)
            log.debug('Insert pixbuf')
            self.buffer.insert_pixbuf(iter_end, pixbuf)
        except GLib.GError:
            self._show_error(_('Cannot open %s for reading') % tmppng)
            log.debug('Cant open %s for reading', tmppng)
        finally:
            os.remove(tmppng)
