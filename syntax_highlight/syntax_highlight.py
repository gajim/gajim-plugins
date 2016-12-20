import logging

import gtk

from plugins.helpers import log_calls, log
from plugins import GajimPlugin
from plugins.gui import GajimPluginConfigDialog

PYGMENTS_MISSING = 'You are missing Python-Pygments.'
ERROR_MSG = ''

log = logging.getLogger('gajim.plugin_system.syntax_highlight')
DEFAULT_LEXER = "python"
DEFAULT_LINE_BREAK = 2 # => Only on multi-line code blocks

try:
    import pygments
    from pygments.lexers import get_lexer_by_name, get_all_lexers
    from .gtkformatter import GTKFormatter
except Exception as e:
    log.error("Import Error: %s.", e)
    ERROR_MSG = PYGMENTS_MISSING


class SyntaxHighlighterPluginConfiguration(GajimPluginConfigDialog):
    @log_calls('SyntaxHighlighterPluginConfiguration')
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1', 'line_break_selection'])
        hbox = self.xml.get_object('vbox1')
        self.child.pack_start(hbox)
        self.result_label = self.xml.get_object('result_label')

        self.liststore = gtk.ListStore(str)

        self.default_lexer_combobox = self.xml.get_object('default_lexer_combobox')
        self.default_lexer_combobox.set_property("model", self.liststore)

        self.line_break_combobox = self.xml.get_object('line_break_combobox')

        self.xml.connect_signals(self)
        self.default_lexer_id = 0

    def set_lexer_list(self, lexers):
        self.lexers = lexers
        default_lexer = self.plugin.config['default_lexer']
        for i, lexer in enumerate(self.lexers):
            self.liststore.append([lexer[0]])
            if lexer[1] == default_lexer:
                self.default_lexer_id = i

    def lexer_changed(self, widget):
        self.default_lexer_id = self.default_lexer_combobox.get_active()
        self.plugin.config['default_lexer'] = self.lexers[self.default_lexer_id][1]

    def line_break_changed(self, widget):
        self.plugin.config['line_break'] = self.line_break_combobox.get_active()

    def on_run(self):
        self.default_lexer_combobox.set_active(self.default_lexer_id)
        self.line_break_combobox.set_active(self.plugin.config['line_break'])

class SyntaxHighlighterPlugin(GajimPlugin):
    def on_change(self, tb):
        """
        called when conversation text widget changes
        """
        end_iter = tb.get_end_iter()
        eol_tag = tb.get_tag_table().lookup('eol')

        def split_list(list_):
            newlist = []
            for i in range(0, len(list_)-1, 2):
                newlist.append( [ list_[i], list_[i+1], ] )
            return newlist

        def get_lexer(language):
            lexer = None
            try:
                lexer = get_lexer_by_name(language)
            except:
                pass
            return lexer

        def get_lexer_with_fallback(language, default_lexer):
            lexer = get_lexer(language)
            if lexer is None:
                log.info("Falling back to default lexer for %s.",
                        str(self.config['default_lexer']))
                lexer = get_lexer_by_name(default_lexer)
            return lexer

        def insert_formatted_code(tb, language, code, mark=None, line_break=False):
            lexer = None

            if language is None:
                log.info("No Language specified. Falling back to default lexer: %s.",
                        str(self.config['default_lexer']))
                lexer = get_lexer(self.config['default_lexer'])
            else:
                log.debug("Using lexer for %s.", str(language))
                lexer = get_lexer_with_fallback(language, self.config['default_lexer'])

            if lexer is None:
                it = tb.get_iter_at_mark(mark)
                tb.insert(it, '\n')
            else:
                tokens = pygments.lex(code, lexer)

                if line_break:
                    log.debug("Inserting newline before code.")
                    it = tb.get_iter_at_mark(mark)
                    tb.insert(it, '\n')
                    it.forward_char()
                    tb.move_mark(mark, it)


                formatter = GTKFormatter(start_mark=mark)
                pygments.format(tokens, formatter, tb)

                endmark = formatter.get_last_mark()
                if line_break and not endmark is None:
                    it = tb.get_iter_at_mark(endmark)
                    tb.insert(it, '\n')
                    log.debug("Inserting newline after code.")

            return tb

        def detect_language(tb, start_mark):
            language = None
            new_start = None
            if not start_mark is None:
                next_chars = None
                lang_iter = tb.get_iter_at_mark(start_mark)
                first_word_end = lang_iter.copy()
                first_word_end.forward_word_end()
                first_word_last_char = first_word_end.get_char()

                next_chars_iter = first_word_end.copy()
                next_chars_iter.forward_chars(2)
                next_chars = first_word_end.get_text(next_chars_iter)
                log.debug("first_word_last_char: %s.", first_word_last_char)
                if first_word_last_char == "@" and next_chars != "@@":
                    language = lang_iter.get_text(first_word_end)
                    log.debug("language: >>%s<<", language)
                    first_word_end.forward_char()
                    new_start = tb.create_mark(None, first_word_end, True)
            return (language, new_start)

        def to_iter(tb, mark):
            return tb.get_iter_at_mark(mark)

        def check_line_break(tb, start, end):
            line_break = False
            if self.config['line_break'] == 1:
                line_break = True
            elif self.config['line_break'] == 2:
                # hackish way to check if this code block contains multiple
                # lines.
                # TODO find better method....
                multiline_test = to_iter(tb, start).copy()
                multiline_test.forward_line()
                line_break = multiline_test.in_range(
                        to_iter(tb, start), to_iter(tb, end))
            return line_break

        def replace_code_block(tb, s_tag, s_code, e_tag, e_code):
            iter_range_full = (tb.get_iter_at_mark(s_tag),
                    tb.get_iter_at_mark(e_tag))

            text_full = iter_range_full[0].get_text(iter_range_full[1])
            log.debug("full text to remove: %s.", text_full)

            tb.begin_user_action()

            language, code_start = detect_language(tb, s_code)
            code_start = s_code if code_start is None else code_start

            line_break = check_line_break(tb, code_start, e_code)

            code = to_iter(tb, code_start).get_text(to_iter(tb, e_code))
            log.debug("full text to encode: %s.", code)

            # Delete code between and including tags
            tb.delete(to_iter(tb, s_tag), to_iter(tb, e_tag))

            insert_formatted_code(tb, language, code, mark=s_tag,
                    line_break=line_break)

            tb.end_user_action()

        def detect_tags(tb, start_it=None, end_it=None):
            if not end_it:
                end_it = tb.get_end_iter()
            if not start_it:
                eol_tag = tb.get_tag_table().lookup('eol')
                start_it = end_it.copy()
                start_it.backward_to_tag_toggle(eol_tag)
            points = []
            tuple_found = start_it.forward_search('@@',
                gtk.TEXT_SEARCH_TEXT_ONLY)
            while tuple_found != None:
                points.append((tb.create_mark(None, tuple_found[0], True),
                        tb.create_mark(None, tuple_found[1], True)))
                tuple_found = tuple_found[1].forward_search('@@',
                    gtk.TEXT_SEARCH_TEXT_ONLY)

            for (s_tag, s_code), (e_code, e_tag) in split_list(points):
                replace_code_block(tb, s_tag, s_code, e_tag, e_code)

        end_iter = tb.get_end_iter()
        eol_tag = tb.get_tag_table().lookup('eol')
        it = end_iter.copy()
        it.backward_to_tag_toggle(eol_tag)

        it1 = it.copy()
        it1.backward_char()
        it1.backward_to_tag_toggle(eol_tag)
        detect_tags(tb, it1, it)

    @log_calls('SyntaxHighlighterPlugin')
    def connect_with_chat_control(self, control):
        control_data = {}
        tv = control.conv_textview.tv

        control_data['connection'] = tv.get_buffer().connect('changed', self.on_change)
        log.debug("connection: %s.", str(control_data['connection']))
        control.syntax_highlighter_plugin_data = control_data

    @log_calls('SyntaxHighlighterPlugin')
    def disconnect_from_chat_control(self, control):
        control_data = control.syntax_highlighter_plugin_data
        tv = control.conv_textview.tv
        log.debug("disconnected: %s.", str(control_data['connection']))
        tv.get_buffer().disconnect(control_data['connection'])

    def create_lexer_list(self):
        self.lexers = []

        # Iteration over get_all_lexers() seems to be broken somehow. Workarround
        all_lexers = get_all_lexers()
        lexer = all_lexers.next()
        while not lexer is None:
            # We don't want to add lexers that we cant identify by name later
            if not lexer[1] is None and len(lexer[1]) > 0:
                self.lexers.append((lexer[0], lexer[1][0]))
            try:
                lexer = all_lexers.next()
            except:
                lexer = None
        self.lexers.sort()
        return self.lexers

    @log_calls('SyntaxHighlighterPlugin')
    def init(self):
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            self.config_dialog = None
            return
        self.config_dialog = SyntaxHighlighterPluginConfiguration(self)
        self.config_default_values = {
                'default_lexer': (DEFAULT_LEXER, "Default Lexer"),
                'line_break': (DEFAULT_LINE_BREAK, "Add line break")
            }
        self.config_dialog.set_lexer_list(self.create_lexer_list())

        self.gui_extension_points = {
                'chat_control_base': (
                        self.connect_with_chat_control,
                        self.disconnect_from_chat_control
                   ),
            }
        self.timeout_id = None
        self.last_eol_offset = -1
