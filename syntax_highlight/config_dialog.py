import logging
import re
import math
from pathlib import Path
import pygments

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository.Pango import FontDescription
from gi.repository.Pango import Style
from gi.repository.Pango import SCALE

from gajim.common import app

from gajim.plugins.plugins_i18n import _
from gajim.plugins.helpers import get_builder

from syntax_highlight.gtkformatter import GTKFormatter
from syntax_highlight.types import LineBreakOptions
from syntax_highlight.types import CodeMarkerOptions
from syntax_highlight.types import PLUGIN_INTERNAL_NONE_LEXER_ID

log = logging.getLogger('gajim.p.syntax_highlight')

PLUGIN_INTERNAL_NONE_LEXER = ('None (monospace only)',
                              PLUGIN_INTERNAL_NONE_LEXER_ID)


class SyntaxHighlighterPluginConfig(Gtk.ApplicationWindow):
    def __init__(self, plugin, transient):
        Gtk.ApplicationWindow.__init__(self)
        self.set_application(app.app)
        self.set_show_menubar(False)
        self.set_title(_('Syntax Highlighter Configuration'))
        self.set_transient_for(transient)
        self.set_default_size(400, 500)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_modal(True)
        self.set_destroy_with_parent(True)

        ui_path = Path(__file__).parent
        self._ui = get_builder(ui_path.resolve() / 'config_dialog.ui')
        self.add(self._ui.main_box)
        self.show_all()

        self._ui.preview_textview.get_buffer().connect(
            'insert-text', self._on_preview_text_inserted)
        self._ui.connect_signals(self)

        self._lexer_liststore = Gtk.ListStore(str)
        self._ui.default_lexer_combobox.set_model(self._lexer_liststore)

        self._style_liststore = Gtk.ListStore(str)
        self._ui.style_combobox.set_model(self._style_liststore)

        self._plugin = plugin
        self._lexers = plugin.highlighter_config.get_lexer_list()
        self._styles = plugin.highlighter_config.get_styles_list()

        self._provider = None
        self._add_css_provider()

        self._initialize()

    def _initialize(self):
        default_lexer = self._plugin.highlighter_config.get_default_lexer_name()

        for i, lexer in enumerate(self._lexers):
            self._lexer_liststore.append([lexer[0]])
            if lexer[1] == default_lexer:
                self._ui.default_lexer_combobox.set_active(i)

        for i, style in enumerate(self._styles):
            self._style_liststore.append([style])
            if style == self._plugin.config['style']:
                self._ui.style_combobox.set_active(i)

        self._ui.line_break_combobox.set_active(
            self._plugin.config['line_break'].value)
        self._ui.code_marker_combobox.set_active(
            self._plugin.config['code_marker'])
        self._ui.font_button.set_font(self._plugin.config['font'])

        bg_override_enabled = self._plugin.config['bgcolor_override']
        self._ui.bg_color_checkbutton.set_active(bg_override_enabled)
        self._ui.bg_color_colorbutton.set_sensitive(bg_override_enabled)
        color = Gdk.RGBA()
        if color.parse(self._plugin.config['bgcolor']):
            self._ui.bg_color_colorbutton.set_rgba(color)
        self._update_preview()

    def _lexer_changed(self, widget):
        self._plugin.highlighter_config.set_default_lexer(
            self._lexers[widget.get_active()][1])
        self._update_preview()

    def _line_break_changed(self, widget):
        self._plugin.config['line_break'] = LineBreakOptions(
            widget.get_active())
        self._update_preview()

    def _code_marker_changed(self, widget):
        self._plugin.config['code_marker'] = CodeMarkerOptions(
            widget.get_active())

    def _bg_color_enabled(self, widget):
        override_color = widget.get_active()
        self._plugin.config['bgcolor_override'] = override_color
        self._ui.bg_color_colorbutton.set_sensitive(override_color)
        self._update_preview()

    def _bg_color_changed(self, widget):
        color = widget.get_rgba()
        self._plugin.config['bgcolor'] = color.to_string()
        self._update_preview()

    def _style_changed(self, widget):
        style = self._styles[widget.get_active()]
        if style is not None and style != '':
            self._plugin.config['style'] = style
        self._update_preview()

    def _font_changed(self, widget):
        font = widget.get_font()
        if font is not None and font != '':
            self._plugin.config['font'] = font
        self._update_preview()

    def _update_preview(self):
        self._format_preview_text()

    def _on_preview_text_inserted(self, _buf, _iterator, text, length, *_args):
        if (length == 1 and re.match(r'\s', text)) or length > 1:
            self._format_preview_text()

    def _add_css_provider(self):
        self._context = self._ui.preview_textview.get_style_context()
        self._provider = Gtk.CssProvider()
        self._context.add_provider(
            self._provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._context.add_class('syntax-preview')

    def _format_preview_text(self):
        buf = self._ui.preview_textview.get_buffer()
        start_iter = buf.get_start_iter()
        start_mark = buf.create_mark(None, start_iter, True)
        buf.remove_all_tags(start_iter, buf.get_end_iter())

        formatter = GTKFormatter(
            style=self._plugin.config['style'], start_mark=start_mark)

        code = start_iter.get_text(buf.get_end_iter())
        lexer = self._plugin.highlighter_config.get_default_lexer()
        if lexer != PLUGIN_INTERNAL_NONE_LEXER_ID:
            tokens = pygments.lex(code, lexer)
            pygments.format(tokens, formatter, buf)

        buf.delete_mark(start_mark)
        css = self._get_css()
        self._provider.load_from_data(bytes(css.encode()))

    def _get_css(self):
        # Build CSS from Pango.FontDescription
        description = FontDescription.from_string(self._plugin.config['font'])
        size = description.get_size() / SCALE
        style = self._get_string_from_pango_style(description.get_style())
        weight = self._pango_to_css_weight(int(description.get_weight()))
        family = description.get_family()
        font = '%spt %s' % (size, family)

        if self._plugin.config['bgcolor_override']:
            color = self._plugin.config['bgcolor']
        else:
            color = '@theme_base_color'

        css = '''
        .syntax-preview {
            font: %s;
            font-weight: %s;
            font-style: %s;
        }
        .syntax-preview > text {
            background-color: %s;
        }
        ''' % (font, weight, style, color)
        return css

    @staticmethod
    def _pango_to_css_weight(number):
        # Pango allows for weight values between 100 and 1000
        # CSS allows only full hundred numbers like 100, 200 ..
        number = int(number)
        if number < 100:
            return 100
        if number > 900:
            return 900
        return int(math.ceil(number / 100.0)) * 100

    @staticmethod
    def _get_string_from_pango_style(style: Style) -> str:
        if style == Style.NORMAL:
            return 'normal'
        if style == Style.ITALIC:
            return 'italic'
        # Style.OBLIQUE:
        return 'oblique'
