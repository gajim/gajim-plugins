import logging
import pygments

from gi.repository import Gtk, Gdk
from gi.repository.Pango import FontDescription


from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.helpers import log_calls, log


from .gtkformatter import GTKFormatter
from .types import MatchType, LineBreakOptions, CodeMarkerOptions

log = logging.getLogger('gajim.plugin_system.syntax_highlight')

class SyntaxHighlighterPluginConfiguration(GajimPluginConfigDialog):
    @log_calls('SyntaxHighlighterPluginConfiguration')
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['mainBox', 'line_break_selection', 'code_marker_selection',
                    'preview_textbuffer'])
        box = self.xml.get_object('mainBox')
        self.get_child().pack_start(box, False, False, 0)
        self.result_label = self.xml.get_object('result_label')

        self.liststore = Gtk.ListStore(str)

        self.default_lexer_combobox = self.xml.get_object('default_lexer_combobox')
        self.default_lexer_combobox.set_property("model", self.liststore)

        self.style_liststore = Gtk.ListStore(str)
        self.style_combobox = self.xml.get_object('style_combobox')
        self.style_combobox.set_property("model", self.style_liststore)

        self.bg_color_checkbox    = self.xml.get_object('bg_color_checkbutton')
        self.bg_color_colorbutton = self.xml.get_object('bg_color_colorbutton')

        self.line_break_combobox  = self.xml.get_object('line_break_combobox')

        self.code_marker_combobox = self.xml.get_object('code_marker_combobox')

        self.preview_textview     = self.xml.get_object('preview_textview')
        self.preview_textview.get_buffer().connect("insert-text", self.on_preview_text_inserted)
        self.preview_textview.set_size_request(-1, 130)

        self.font_button          = self.xml.get_object('font_button')

        self.xml.connect_signals(self)
        self.default_lexer_id   = 0
        self.style_id           = 0

    def set_config(self, config):
        self.config     = config
        self.lexers     = self.config.get_lexer_list()
        self.styles     = self.config.get_styles_list()
        default_lexer   = self.config.get_default_lexer_name()
        default_style   = self.config.get_style_name()

        for i, lexer in enumerate(self.lexers):
            self.liststore.append([lexer[0]])
            if lexer[1] == default_lexer:
                self.default_lexer_id = i

        for i, style in enumerate(self.styles):
            self.style_liststore.append([style])
            if style == default_style:
                self.style_id = i
        self.update_preview()

    def lexer_changed(self, _widget):
        new = self.default_lexer_combobox.get_active()
        if new != self.default_lexer_id:
            self.default_lexer_id = new
            self.config.set_default_lexer(self.lexers[self.default_lexer_id][1])
            self.update_preview()

    def line_break_changed(self, _widget):
        new = LineBreakOptions(self.line_break_combobox.get_active())
        if new != self.config.get_line_break_action():
            self.config.set_line_break_action(new)
            self.update_preview()

    def code_marker_changed(self, _widget):
        new = CodeMarkerOptions(self.code_marker_combobox.get_active())
        if new != self.config.get_code_marker_setting():
            self.config.set_code_marker_setting(new)

    def bg_color_enabled(self, _widget):
        new = self.bg_color_checkbox.get_active()
        if new != self.config.is_bgcolor_override_enabled():
            bg_override_enabled = new
            self.config.set_bgcolor_override_enabled(bg_override_enabled)
            self.bg_color_colorbutton.set_sensitive(bg_override_enabled)
            self.update_preview()

    def bg_color_changed(self, _widget):
        new = self.bg_color_colorbutton.get_color()
        if new != self.config.get_bgcolor():
            self.config.set_bgcolor(new)
            self.update_preview()

    def style_changed(self, _widget):
        new = self.style_combobox.get_active()
        if new != self.style_id:
            self.style_id = new
            self.config.set_style(self.styles[self.style_id])
            self.update_preview()

    def font_changed(self, _widget):
        new = self.font_button.get_font()
        if new != self.config.get_font():
            self.config.set_font(new)
            self.update_preview()

    def update_preview(self):
        self.format_preview_text()

    def on_preview_text_inserted(self, _buf, _iterator, text, length, *_args):
        if (length == 1 and re.match(r'\s', text)) or length > 1:
            self.format_preview_text()

    def format_preview_text(self):
        buf = self.preview_textview.get_buffer()
        start_iter = buf.get_start_iter()
        start_mark = buf.create_mark(None, start_iter, True)
        buf.remove_all_tags(start_iter, buf.get_end_iter())

        formatter = GTKFormatter(
                style=self.config.get_style_name(),
                start_mark=start_mark)

        code    = start_iter.get_text(buf.get_end_iter())
        lexer   = self.config.get_default_lexer()
        tokens  = pygments.lex(code, lexer)

        pygments.format(tokens, formatter, buf)

        buf.delete_mark(start_mark)

        self.preview_textview.override_font(
                FontDescription.from_string(self.config.get_font()))

        color = Gdk.RGBA()
        if color.parse(self.config.get_bgcolor()):
            self.preview_textview.override_background_color(
                    Gtk.StateFlags.NORMAL, color)

    def on_run(self):
        self.default_lexer_combobox.set_active(self.default_lexer_id)
        self.line_break_combobox.set_active(self.config.get_line_break_action())
        self.code_marker_combobox.set_active(self.config.get_code_marker_setting())
        self.style_combobox.set_active(self.style_id)

        self.font_button.set_font(self.config.get_font())

        bg_override_enabled = self.config.is_bgcolor_override_enabled()
        self.bg_color_checkbox.set_active(bg_override_enabled)

        self.bg_color_colorbutton.set_sensitive(bg_override_enabled)

        parsed, color = Gdk.Color.parse(self.config.get_bgcolor())
        if parsed:
            self.bg_color_colorbutton.set_color(color)


