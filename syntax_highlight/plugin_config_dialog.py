import re
import pygments

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository.Pango import FontDescription

from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.helpers import get_builder

from syntax_highlight.gtkformatter import GTKFormatter
from syntax_highlight.types import LineBreakOptions
from syntax_highlight.types import CodeMarkerOptions


class SyntaxHighlighterPluginConfiguration(GajimPluginConfigDialog):
    def init(self):
        path = self.plugin.local_file_path('config_dialog.ui')
        self._ui = get_builder(path)
        box = self.get_content_area()
        box.pack_start(self._ui.main_box, True, True, 0)

        self._ui.set_translation_domain('gajim_plugins')

        self.liststore = Gtk.ListStore(str)
        self._ui.default_lexer_combobox.set_model(self.liststore)

        self.style_liststore = Gtk.ListStore(str)
        self._ui.style_combobox.set_model(self.style_liststore)

        self._ui.preview_textview.get_buffer().connect(
            'insert-text', self._on_preview_text_inserted)

        self._ui.connect_signals(self)

        self.default_lexer_id = 0
        self.style_id = 0

    def set_config(self, config):
        self.config = config
        self.lexers = self.config.get_lexer_list()
        self.styles = self.config.get_styles_list()
        default_lexer = self.config.get_default_lexer_name()
        default_style = self.config.get_style_name()

        for i, lexer in enumerate(self.lexers):
            self.liststore.append([lexer[0]])
            if lexer[1] == default_lexer:
                self.default_lexer_id = i

        for i, style in enumerate(self.styles):
            self.style_liststore.append([style])
            if style == default_style:
                self.style_id = i
        self._update_preview()

    def _lexer_changed(self, _widget):
        new = self._ui.default_lexer_combobox.get_active()
        if new != self.default_lexer_id:
            self.default_lexer_id = new
            self.config.set_default_lexer(self.lexers[self.default_lexer_id][1])
            self._update_preview()

    def _line_break_changed(self, _widget):
        new = LineBreakOptions(self._ui.line_break_combobox.get_active())
        if new != self.config.get_line_break_action():
            self.config.set_line_break_action(new)
            self._update_preview()

    def _code_marker_changed(self, _widget):
        new = CodeMarkerOptions(self._ui.code_marker_combobox.get_active())
        if new != self.config.get_code_marker_setting():
            self.config.set_code_marker_setting(new)

    def _bg_color_enabled(self, _widget):
        new = self._ui.bg_color_checkbutton.get_active()
        if new != self.config.is_bgcolor_override_enabled():
            bg_override_enabled = new
            self.config.set_bgcolor_override_enabled(bg_override_enabled)
            self._ui.bg_color_colorbutton.set_sensitive(bg_override_enabled)
            self._update_preview()

    def _bg_color_changed(self, _widget):
        new = self._ui.bg_color_colorbutton.get_rgba()
        if new != self.config.get_bgcolor():
            self.config.set_bgcolor(new)
            self._update_preview()

    def _style_changed(self, _widget):
        new = self._ui.style_combobox.get_active()
        if new != self.style_id:
            self.style_id = new
            self.config.set_style(self.styles[self.style_id])
            self._update_preview()

    def _font_changed(self, _widget):
        new = self._ui.font_button.get_font()
        if new != self.config.get_font():
            self.config.set_font(new)
            self._update_preview()

    def _update_preview(self):
        self._format_preview_text()

    def _on_preview_text_inserted(self, _buf, _iterator, text, length, *_args):
        if (length == 1 and re.match(r'\s', text)) or length > 1:
            self._format_preview_text()

    def _format_preview_text(self):
        buf = self._ui.preview_textview.get_buffer()
        start_iter = buf.get_start_iter()
        start_mark = buf.create_mark(None, start_iter, True)
        buf.remove_all_tags(start_iter, buf.get_end_iter())

        formatter = GTKFormatter(
            style=self.config.get_style_name(), start_mark=start_mark)

        code = start_iter.get_text(buf.get_end_iter())
        lexer = self.config.get_default_lexer()
        if not self.config.is_internal_none_lexer(lexer):
            tokens = pygments.lex(code, lexer)
            pygments.format(tokens, formatter, buf)

        buf.delete_mark(start_mark)

        self._ui.preview_textview.override_font(
            FontDescription.from_string(self.config.get_font()))

        color = Gdk.RGBA()
        if color.parse(self.config.get_bgcolor()):
            self._ui.preview_textview.override_background_color(
                Gtk.StateFlags.NORMAL, color)

    def on_run(self):
        self._ui.default_lexer_combobox.set_active(self.default_lexer_id)
        self._ui.line_break_combobox.set_active(
            self.config.get_line_break_action())
        self._ui.code_marker_combobox.set_active(
            self.config.get_code_marker_setting())
        self._ui.style_combobox.set_active(self.style_id)

        self._ui.font_button.set_font(self.config.get_font())

        bg_override_enabled = self.config.is_bgcolor_override_enabled()
        self._ui.bg_color_checkbutton.set_active(bg_override_enabled)

        self._ui.bg_color_colorbutton.set_sensitive(bg_override_enabled)

        color = Gdk.RGBA()
        if color.parse(self.config.get_bgcolor()):
            self._ui.bg_color_colorbutton.set_rgba(color)
