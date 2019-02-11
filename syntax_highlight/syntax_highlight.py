import logging
import re
from enum import Enum, IntEnum, unique

from gi.repository import Gtk, Gdk
from gi.repository.Gtk import TextSearchFlags
from gi.repository.Pango import FontDescription

from gajim.plugins.helpers import log_calls, log
from gajim.plugins import GajimPlugin
from gajim.plugins.gui import GajimPluginConfigDialog


class MatchType(Enum):
    INLINE      = 0
    MULTILINE   = 1
    TEXT        = 2

@unique
class LineBreakOptions(IntEnum):
    NEVER       = 0
    ALWAYS      = 1
    MULTILINE   = 2

@unique
class CodeMarkerOptions(IntEnum):
    AS_COMMENT  = 0
    HIDE        = 1

PYGMENTS_MISSING = 'You are missing Python-Pygments.'
ERROR_MSG = ''

log = logging.getLogger('gajim.plugin_system.syntax_highlight')
DEFAULT_LEXER = "python"

# Only on multi-line code blocks:
DEFAULT_LINE_BREAK = LineBreakOptions.MULTILINE

DEFAULT_STYLE = "default"

DEFAULT_FONT = "Monospace 10"

DEFAULT_BGCOLOR = "#ccc"
DEFAULT_OVERRIDE_BGCOLOR = False

DEFAULT_CODE_MARKER_SETTING = CodeMarkerOptions.AS_COMMENT

try:
    import pygments
    from pygments.lexers import get_lexer_by_name, get_all_lexers
    from pygments.styles import get_all_styles
    from .gtkformatter import GTKFormatter
except Exception as exception:
    log.error("Import Error: %s.", exception)
    ERROR_MSG = PYGMENTS_MISSING


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



class ChatSyntaxHighlighter:
    def hide_code_markup(self, buf, start, end):
        tag = buf.get_tag_table().lookup('hide_code_markup')
        if tag is None:
            tag = Gtk.TextTag.new('hide_code_markup')
            tag.set_property('invisible', True)
            buf.get_tag_table().add(tag)

        buf.apply_tag_by_name('hide_code_markup', start, end)

    def check_line_break(self, is_multiline):
        line_break = self.config.get_line_break_action()

        return (line_break == LineBreakOptions.ALWAYS) \
                or (is_multiline and line_break == LineBreakOptions.MULTILINE)


    def format_code(self, buf, s_tag, s_code, e_tag, e_code, language):
        style = self.config.get_style_name()
        if self.config.get_code_marker_setting() == CodeMarkerOptions.HIDE:
            self.hide_code_markup(buf, s_tag, s_code)
            self.hide_code_markup(buf, e_code, e_tag)
        else:
            comment_tag = GTKFormatter.create_tag_for_token(
                    pygments.token.Comment,
                    pygments.styles.get_style_by_name(style))
            buf.get_tag_table().add(comment_tag)
            buf.apply_tag(comment_tag, s_tag, s_code)
            buf.apply_tag(comment_tag, e_tag, e_code)

        code = s_code.get_text(e_code)
        log.debug("full text to encode: %s.", code)


        start_mark  = buf.create_mark(None, s_code, False)

        lexer = None

        if language is None:
            lexer = self.config.get_default_lexer()
            log.info("No Language specified. Falling back to default lexer: %s.",
                    self.config.get_default_lexer_name())
        else:
            log.debug("Using lexer for %s.", str(language))
            lexer = self.config.get_lexer_with_fallback(language)

        if lexer is None:
            iterator = buf.get_iter_at_mark(start_mark)
            buf.insert(iterator, '\n')
        else:
            tokens = pygments.lex(code, lexer)

            formatter = GTKFormatter(style=style, start_mark=start_mark)
            pygments.format(tokens, formatter, buf)

    def find_multiline_matches(self, text):
        start = None
        matches = []
        for i in re.finditer(r'\n?```(?:\S*\n)?', text, re.DOTALL):
            if start is None:
                start = i
            elif re.match(r'^\n```', i.group(0)) is not None:
                matches.append(
                        (start.start(), i.end(), text[start.start():i.end()]))
                start = None
            else:
                # not an end...
                continue
        return matches

    def find_inline_matches(self, text):
        return [(i.start(), i.end(), i.group(0)) for i in \
                re.finditer(r'(?<!`)`(?!`|\n).+(?<!`)`', text)]

    def merge_match_groups(self, real_text, inline_matches, multiline_matches):
        it_inline = iter(inline_matches)
        it_multi  = iter(multiline_matches)
        length    = len(real_text)

        # Just to get cleaner code below...
        def get_next(iterator):
            return next(iterator, (length, length, ""))

        # In order to simplify the process, we use the 'length' here.
        cur_inline = get_next(it_inline)
        cur_multi  = get_next(it_multi)

        pos = 0

        # This will contain tuples with parts of the input and its classification
        parts  = []
        while pos < length:
            log.debug("-> in: %s", str(cur_inline))
            log.debug("-> mu: %s", str(cur_multi))

            # selected = (start, end, type)
            selected = (cur_inline[0], cur_inline[1], MatchType.INLINE) \
                    if cur_inline[0] < cur_multi[0] \
                    else (cur_multi[0], cur_multi[1], MatchType.MULTILINE) \
                        if cur_multi[0] < length \
                        else (pos, length, MatchType.TEXT)
            log.debug("--> select: %s", str(selected))

            # Handle plain text string parts (and unforseen errors...)
            if pos < selected[0]:
                end = selected[0] if selected[0] != pos else selected[1]
                parts.append((real_text[pos:end], MatchType.TEXT))
                pos = selected[0]
            elif pos > selected[0]:
                log.error("Should not happen, position > found match.")

            # Cut out and append selected text segment
            parts.append((real_text[selected[0]:selected[1]], selected[2]))
            pos = selected[1]

            # Depending on the match type, we have to forward the iterators.
            # Also, forward the other one, if regions overlap or we took over...
            if selected[2] == MatchType.INLINE:
                if cur_multi[0] < cur_inline[1]:
                    cur_multi = get_next(it_multi)
                cur_inline = get_next(it_inline)
            elif selected[2] == MatchType.MULTILINE:
                if cur_inline[0] < cur_multi[1]:
                    cur_inline = get_next(it_inline)
                cur_multi = get_next(it_multi)

        return parts

    def process_text(self, real_text, other_tags, _graphics, iter_,
            _additional):
        def fix_newline(char, marker_len_no_newline, force=False):
            fixed = (marker_len_no_newline, '')
            if char == '\n':
                fixed = (marker_len_no_newline + 1, '')
            elif force:
                fixed = (marker_len_no_newline + 1, '\n')
            return fixed


        buf = self.textview.tv.get_buffer()

        # first, try to find inline or multiline code snippets
        inline_matches      = self.find_inline_matches(real_text)
        multiline_matches   = self.find_multiline_matches(real_text)

        if not inline_matches and not multiline_matches:
            log.debug("Stopping early, since there is no code block in it....")
            return

        iterator   = iter_ if iter_ is not None else buf.get_end_iter()

        # Create a start marker with left gravity before inserting text.
        start_mark = buf.create_mark("SHP_start", iterator, True)
        end_mark   = buf.create_mark("SHP_end", iterator, False)

        insert_newline_for_multiline    = self.check_line_break(True)
        insert_newline_for_inline       = self.check_line_break(False)

        split_text = self.merge_match_groups(
                real_text, inline_matches, multiline_matches)

        buf.begin_user_action()

        for num, (text_to_insert, match_type) in enumerate(split_text):
            marker          = [("", 0), ("", 0)]
            language        = None
            end_of_message  = num == (len(split_text) - 1)

            if match_type == MatchType.TEXT:
                self.textview.detect_and_print_special_text(
                        text_to_insert, other_tags, graphics=_graphics,
                        iter_=iterator, additional_data=_additional)
            else:
                if match_type == MatchType.MULTILINE:
                    language_match = re.search(
                            '\n*```([^\n]*)\n', text_to_insert, re.DOTALL)
                    language = None if language_match is None \
                            else language_match.group(1)
                    language_len = 0 if language is None else len(language)

                    # We account the language word width for the front marker
                    front = fix_newline(text_to_insert[0],  3 + language_len,
                            insert_newline_for_multiline)
                    back  = fix_newline(text_to_insert[-1], 3,
                            insert_newline_for_multiline and not end_of_message)
                else:
                    front = fix_newline(text_to_insert[0],  1,
                            insert_newline_for_inline)
                    back  = fix_newline(text_to_insert[-1], 1,
                            insert_newline_for_inline and not end_of_message)

                marker_widths = (front[0], back[0])
                text_to_insert = ''.join([front[1], text_to_insert, back[1]])

                # insertion invalidates iterator, let's use our start mark...
                self.insert_and_format_code(buf, text_to_insert, language,
                        marker_widths, start_mark, other_tags)

            iterator = buf.get_iter_at_mark(end_mark)
            # the current end of the buffer's contents is the start for the
            # next iteration
            buf.move_mark(start_mark, iterator)

        buf.delete_mark(start_mark)
        buf.delete_mark(end_mark)

        buf.end_user_action()

        # We have to make sure this is the last thing we do (i.e. no calls to
        # the other textview methods no more from here on), because the
        # print_special_text method is resetting the plugin_modified variable...
        self.textview.plugin_modified = True

    def insert_and_format_code(self, buf, insert_text, language, marker, start_mark, other_tags=None):
        start_iter  = buf.get_iter_at_mark(start_mark)

        if other_tags:
            buf.insert_with_tags_by_name(start_iter, insert_text,
                    *other_tags)
        else:
            buf.insert(start_iter, insert_text)

        start_iter  = buf.get_iter_at_mark(start_mark)
        tag_start   = start_iter
        tag_end     = buf.get_end_iter()
        s_code      = start_iter.copy()
        e_code      = tag_end.copy()
        s_code.forward_chars(marker[0])
        e_code.backward_chars(marker[1])

        log.debug("full text between tags: %s.", tag_start.get_text(tag_end))

        self.format_code(buf, tag_start, s_code, tag_end, e_code, language)

        self.textview.plugin_modified = True

        # Set general code block format
        tag = Gtk.TextTag.new()
        if self.config.is_bgcolor_override_enabled():
            tag.set_property('background', self.config.get_bgcolor())
            tag.set_property('paragraph-background', self.config.get_bgcolor())
        tag.set_property('font', self.config.get_font())
        buf.get_tag_table().add(tag)
        buf.apply_tag(tag, start_iter, buf.get_end_iter())

    def __init__(self, config, textview):
        self.last_end_mark  = None
        self.config         = config
        self.textview       = textview

class SyntaxHighlighterConfig:
    def _create_lexer_list(self):
        self.lexers = []

        # Iteration over get_all_lexers() seems to be broken somehow. Workarround
        all_lexers = get_all_lexers()
        for lexer in all_lexers:
            # We don't want to add lexers that we cant identify by name later
            if lexer[1] is not None and lexer[1]:
                self.lexers.append((lexer[0], lexer[1][0]))
        self.lexers.sort()
        return self.lexers

    def get_lexer_by_name(self, name):
        lexer = None
        try:
            lexer = get_lexer_by_name(name)
        except:
            pass
        return lexer

    def get_lexer_with_fallback(self, language):
        lexer = self.get_lexer_by_name(language)
        if lexer is None:
            log.info("Falling back to default lexer for %s.",
                    self.get_default_lexer_name())
            lexer = self.default_lexer[1]
        return lexer

    def set_font(self, font):
        if font is None or font == "":
            font = DEFAULT_FONT
        self.config['font'] = font

    def set_style(self, style):
        if style is None or style == "":
            style = DEFAULT_STYLE
        self.config['style'] = style

    def set_line_break_action(self, option):
        if isinstance(option, int):
            option = LineBreakOptions(option)
        self.config['line_break'] = option

    def set_default_lexer(self, name):
        lexer = get_lexer_by_name(name)

        if lexer is None and self.default_lexer is None:
            log.error("Failed to get default lexer by name."\
                    "Falling back to simply using the first in the list.")
            lexer = self.lexer_list[0]
            name  = lexer[0]
            self.default_lexer = (name, lexer)
        if lexer is None and self.default_lexer is not None:
            log.info("Failed to get default lexer by name, keeping previous"\
                    "setting (lexer = %s).", self.default_lexer[0])
            name = self.default_lexer[0]
        else:
            self.default_lexer = (name, lexer)

        self.config['default_lexer'] = name

    def set_bgcolor_override_enabled(self, state):
        self.config['bgcolor_override'] = state

    def set_bgcolor(self, color):
        if isinstance(color, Gdk.Color):
            color = color.to_string()
        self.config['bgcolor'] = color

    def set_code_marker_setting(self, option):
        if isinstance(option, int):
            option = CodeMarkerOptions(option)
        self.config['code_marker'] = option

    def get_default_lexer(self):
        return self.default_lexer[1]

    def get_default_lexer_name(self):
        return self.default_lexer[0]

    def get_lexer_list(self):
        return self.lexer_list

    def get_line_break_action(self):
        # return int only

        action = DEFAULT_LINE_BREAK.value
        if 'line_break' in self.config:
            # in case of legacy settings...
            if isinstance(self.config['line_break'], int):
                action = self.config['line_break']
            else:
                action = self.config['line_break'].value
        return action

    def get_font(self):
        return DEFAULT_FONT \
                if 'font' not in self.config \
                else self.config['font']

    def get_style_name(self):
        return DEFAULT_STYLE \
                if 'style' not in self.config \
                else self.config['style']

    def is_bgcolor_override_enabled(self):
        return DEFAULT_OVERRIDE_BGCOLOR \
                if 'bgcolor_override' not in self.config \
                else self.config['bgcolor_override']

    def get_bgcolor(self):
        return DEFAULT_BGCOLOR \
                if 'bgcolor' not in self.config \
                else self.config['bgcolor']

    def get_code_marker_setting(self):
        return DEFAULT_CODE_MARKER_SETTING \
                if 'code_marker' not in self.config \
                else self.config['code_marker']

    def get_styles_list(self):
        return self.style_list

    def __init__(self, config, default_lexer_name):
        self.lexer_list     = self._create_lexer_list()
        self.style_list     = [s for s in get_all_styles()]
        self.default_lexer  = None
        self.config         = config

        self.style_list.sort()

        self.set_default_lexer(default_lexer_name \
                if not 'default_lexer' in self.config \
                    or self.config['default_lexer'] is None \
                else self.config['default_lexer'])

class SyntaxHighlighterPlugin(GajimPlugin):

    @log_calls('SyntaxHighlighterPlugin')
    def on_connect_with_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid     = chat_control.contact.jid
        if account not in self.ccontrol:
            self.ccontrol[account] = {}
        self.ccontrol[account][jid] = ChatSyntaxHighlighter(
                self.conf, chat_control.conv_textview)

    @log_calls('SyntaxHighlighterPlugin')
    def on_disconnect_from_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid = chat_control.contact.jid
        del self.ccontrol[account][jid]

    @log_calls('SyntaxHighlighterPlugin')
    def on_print_real_text(self, text_view, real_text, other_tags, graphics,
            iterator, additional):
        account = text_view.account
        for jid in self.ccontrol[account]:
            if self.ccontrol[account][jid].textview != text_view:
                continue
            self.ccontrol[account][jid].process_text(
                real_text, other_tags, graphics, iterator, additional)
            return


    @log_calls('SyntaxHighlighterPlugin')
    def init(self):
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            self.config_dialog = None
            return


        self.conf   = SyntaxHighlighterConfig(self.config, DEFAULT_LEXER)

        self.ccontrol       = {}
        self.config_dialog  = SyntaxHighlighterPluginConfiguration(self)
        self.config_default_values = {
                'default_lexer': (DEFAULT_LEXER, "Default Lexer"),
                'line_break': (DEFAULT_LINE_BREAK, "Add line break")
            }
        self.config_dialog.set_config(self.conf)

        self.gui_extension_points = {
                'chat_control_base': (
                        self.on_connect_with_chat_control,
                        self.on_disconnect_from_chat_control
                   ),
                'print_real_text': (self.on_print_real_text, None),
        }
