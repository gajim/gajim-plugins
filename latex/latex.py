# -*- coding: utf-8 -*-
#
## plugins/latex/latex.py
##
## Copyright (C) 2010-2011 Yves Fischer <yvesf AT xapek.org>
## Copyright (C) 2011 Yann Leboulanger <asterix AT lagaule.org>
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##


from threading import Thread
import os
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import Pango
from gi.repository import GObject
from tempfile import mkstemp, mkdtemp
import random
from subprocess import Popen, PIPE

from gajim.common import app
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log, log_calls
from gajim.plugins.gui import GajimPluginConfigDialog

Gdk.threads_init()

def latex_template(code):
    return '''\\documentclass[12pt]{article}
\\usepackage[dvips]{graphicx}
\\usepackage{amsmath}
\\usepackage{amssymb}
\\pagestyle{empty}
\\begin{document}
\\begin{large}
\\begin{gather*}
%s
\\end{gather*}
\\end{large}
\\end{document}''' % (code)

def write_latex(filename, str_):
    texstr = latex_template(str_)

    file_ = open(filename, "w+")
    file_.write(texstr)
    file_.flush()
    file_.close()

def popen_nt_friendly(command, directory):
    if os.name == 'nt':
        # CREATE_NO_WINDOW
        return Popen(command, creationflags=0x08000000, cwd=directory,
            stdout=PIPE)
    else:
        return Popen(command, cwd=directory, stdout=PIPE)

def try_run(argv, directory):
    try:
        p = popen_nt_friendly(argv, directory)
        out = p.communicate()[0]
        log.info(out)
        return p.wait()
    except Exception as e:
        return _('Error executing "%(command)s": %(error)s') % {
            'command': " ".join(argv),
            'error': str(e)}

BLACKLIST = ['\def', '\\let', '\\futurelet', '\\newcommand', '\\renewcomment',
   '\\else', '\\fi', '\\write', '\\input', '\\include', '\\chardef',
   '\\catcode', '\\makeatletter', '\\noexpand', '\\toksdef', '\\every',
   '\\errhelp', '\\errorstopmode', '\\scrollmode', '\\nonstopmode',
   '\\batchmode', '\\read', '\\csname', '\\newhelp', '\\relax', '\\afterground',
   '\\afterassignment', '\\expandafter', '\\noexpand', '\\special', '\\command',
   '\\loop', '\\repeat', '\\toks', '\\output', '\\line', '\\mathcode', '\\name',
   '\\item', '\\section', '\\mbox', '\\DeclareRobustCommand', '\\[', '\\]'
]


class LatexRenderer(Thread):
    def __init__(self, iter_start, iter_end, buffer_, widget, png_dpi):
        Thread.__init__(self)

        self.code = iter_start.get_text(iter_end)
        self.mark_name = 'LatexRendererMark%s' % str(random.randint(0,1000))
        self.mark = buffer_.create_mark(self.mark_name, iter_start, True)

        self.buffer_ = buffer_
        self.widget = widget
        self.png_dpi = png_dpi

        # delete code and show message 'processing'
        self.buffer_.delete(iter_start, iter_end)
        # iter_start.forward_char()
        self.buffer_.insert(iter_start, _('Processing LaTeX'))

        self.start() # start background processing

    def run(self):
        try:
            if self.check_code():
                self.show_image()
            else:
                self.show_error(_('There are bad commands!'))
        except Exception:
            self.show_error(_('Error processing LaTeX'))
        finally:
            self.buffer_.delete_mark(self.mark)

    def show_error(self, message):
        """
        String -> TextBuffer
        """
        Gdk.threads_enter()
        iter_mark = self.buffer_.get_iter_at_mark(self.mark)
        iter_end = iter_mark.copy().forward_search(_('Processing LaTeX'),
            Gtk.TextSearchFlags.TEXT_ONLY, None)[1]
        self.buffer_.delete(iter_mark, iter_end)

        pixbuf = self.widget.render_icon(Gtk.STOCK_STOP, Gtk.IconSize.BUTTON)
        self.buffer_.insert_pixbuf(iter_end, pixbuf)
        self.buffer_.insert(iter_end, message)
        Gdk.threads_leave()

    @log_calls('LatexRenderer')
    def show_image(self):
        """
        Latex -> PNG -> TextBuffer
        """

        def fg_str(fmt):
            try:
                return [{'hex' : '+level-colors', 'tex' : '-fg'}[fmt],
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
            self.show_error(_('latex error: %s\n===ORIGINAL CODE====\n%s') % (
                msg, self.code[2:len(self.code)-2]))
            return False

        tmpfile = os.path.join(tmpdir, 'gajim_tex')

        # build latex string
        write_latex(tmpfile + '.tex', self.code[2:len(self.code)-2])

        # convert TeX to dvi
        exitcode = try_run(['latex', '--interaction=nonstopmode',
            tmpfile + '.tex'], tmpdir)

        if exitcode == 0:
            # convert dvi to png
            log.debug('DVI OK')
            exitcode = try_run(['dvipng', '-bg', 'Transparent'] + fg_str('tex')\
                + ['-T', 'tight', '-D', self.png_dpi, tmpfile + '.dvi', '-o',
                tmpfile + '.png'], tmpdir)

            if exitcode:
                # dvipng failed, try convert
                log.debug('dvipng failed, try convert')
                exitcode = try_run(['convert'] + fg_str('hex') + ['-trim',
                    '-density', self.png_dpi, tmpfile + '.dvi',
                    tmpfile + '.png'], tmpdir)

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
            self.show_error(_('Convertion to image failed\n===ORIGINAL CODE===='
                '\n%s') % self.code[2:len(self.code)-2])
            return False

        log.debug('Loading PNG %s' % tmppng)
        try:
            Gdk.threads_enter()
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(tmppng)
            log.debug('png loaded')
            iter_mark = self.buffer_.get_iter_at_mark(self.mark)
            iter_end = iter_mark.copy().forward_search('Processing LaTeX',
                Gtk.TextSearchFlags.TEXT_ONLY, None)[1]
            log.debug('Delete old Text')
            self.buffer_.delete(iter_mark, iter_end)
            log.debug('Insert pixbuf')
            self.buffer_.insert_pixbuf(iter_end, pixbuf)
        except GObject.GError:
            self.show_error(_('Cannot open %s for reading') % tmppng)
            log.debug('Cant open %s for reading' % tmppng)
        finally:
            Gdk.threads_leave()
            os.remove(tmppng)

    def check_code(self):
        for bad_cmd in BLACKLIST:
            if self.code.find(bad_cmd) != -1:
                # Found bad command
                return False
        return True

class LatexPluginConfiguration(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        hbox = self.xml.get_object('vbox1')
        self.get_child().pack_start(hbox, False, False, 0)
        self.result_label = self.xml.get_object('result_label')

        self.xml.connect_signals(self)

    def on_run(self):
        widget = self.xml.get_object('png_dpi_label')
        widget.set_text(str(self.plugin.config['png_dpi']))

    def show_result(self, msg):
        self.result_label.set_text(self.result_label.get_text() + '\n' + msg)

    def on_test_button_clicked(self,widget):
        """
        performs very simple checks (check if executable is in PATH)
        """
        self.show_result(_('Test Latex Binary'))
        exitcode = try_run(['latex', '-version'], None)
        if exitcode != 0:
            self.show_result(_('  No LaTeX binary found in PATH'))
        else:
            self.show_result(_('  OK'))

        self.show_result(_('Test dvipng'))
        exitcode = try_run(['dvipng', '--version'], None)
        if exitcode != 0:
            self.show_result(_('  No dvipng binary found in PATH'))
        else:
            self.show_result(_('  OK'))

        self.show_result(_('Test ImageMagick'))
        exitcode = try_run(['convert', '-version'], None)
        if exitcode != 0:
            self.show_result(_('  No convert binary found in PATH'))
        else:
            self.show_result(_('  OK'))

    def on_png_dpi_label_changed(self, label):
        self.plugin.config['png_dpi'] = label.get_text()

class LatexPlugin(GajimPlugin):
    def init(self):
        self.description = _('Invoke Latex to render $$foobar$$ sourrounded ' \
            'Latex equations. Needs latex and dvipng or ImageMagick.')
        self.config_dialog = LatexPluginConfiguration(self)
        self.config_default_values = {'png_dpi': ('108', '')}

        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control_base,
                self.disconnect_from_chat_control_base)
        }
        self.test_activatable()
        self.timeout_id = None
        self.last_eol_offset = -1

    def test_activatable(self):
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

    def textview_event_after(self, tag, widget, event, iter_):
        """
        start rendering if clicked on a link
        """
        if tag.get_property('name') != 'latex' or \
        event.type != Gdk.EventType.BUTTON_PRESS:
            return
        dollar_start, iter_start = iter_.backward_search('$$',
            Gtk.TextSearchFlags.TEXT_ONLY, None)
        iter_end, dollar_end = iter_.forward_search('$$',
            Gtk.TextSearchFlags.TEXT_ONLY, None)
        LatexRenderer(dollar_start, dollar_end, widget.get_buffer(), widget,
            self.config['png_dpi'])

    def textbuffer_live_latex_expander(self, tb):
        """
        called when conversation text widget changes
        """
        def split_list(list_):
            newlist = []
            for i in range(0, len(list_)-1, 2):
                newlist.append( [ list_[i], list_[i+1], ] )
            return newlist

        def detect_tags(tb, start_it=None, end_it=None):
            self.timeout_id = None 
            if not end_it: 
                end_it = tb.get_end_iter() 
            if not start_it: 
                eol_tag = tb.get_tag_table().lookup('eol') 
                start_it = end_it.copy() 
                start_it.backward_to_tag_toggle(eol_tag)
            points = []
            tuple_found = start_it.forward_search('$$',
                Gtk.TextSearchFlags.TEXT_ONLY, None)
            while tuple_found != None:
                points.append(tuple_found)
                tuple_found = tuple_found[1].forward_search('$$',
                    Gtk.TextSearchFlags.TEXT_ONLY, None)

            for pair in split_list(points):
                tb.apply_tag_by_name('latex', pair[0][1], pair[1][0])

        end_iter = tb.get_end_iter()
        eol_tag = tb.get_tag_table().lookup('eol')
        it = end_iter.copy()
        it.backward_to_tag_toggle(eol_tag)
        if it.get_offset() == self.last_eol_offset:
            if self.timeout_id:
                GObject.source_remove(self.timeout_id)
            self.timeout_id = Geobject.timeout_add(100, detect_tags, traceback, it, end_iter)
        else:
            if self.timeout_id: 
                GObject.source_remove(self.timeout_id) 
                it1 = it.copy() 
                it1.backward_char() 
                it1.backward_to_tag_toggle(eol_tag) 
                detect_tags(traceback, it1, it) 
            self.last_eol_offset = it.get_offset()

    def connect_with_chat_control_base(self, chat_control):
        d = {}
        tv = chat_control.conv_textview.tv
        tb = tv.get_buffer()

        self.latex_tag = Gtk.TextTag.new('latex')
        self.latex_tag.set_property('foreground', 'blue')
        self.latex_tag.set_property('underline', Pango.Underline.SINGLE)
        d['tag_id'] = self.latex_tag.connect('event', self.textview_event_after)
        tb.get_tag_table().add(self.latex_tag)

        d['h_id'] = tb.connect('changed', self.textbuffer_live_latex_expander)
        chat_control.latexs_expander_plugin_data = d

        return True

    def disconnect_from_chat_control_base(self, chat_control):
        d = chat_control.latexs_expander_plugin_data
        tv = chat_control.conv_textview.tv

        tv.get_buffer().disconnect(d['h_id'])
        self.latex_tag.disconnect(d['tag_id'])
