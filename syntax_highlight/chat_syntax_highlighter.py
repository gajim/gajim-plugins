import logging
import re
import pygments
from pygments.token import Comment
from pygments.styles import get_style_by_name

from gi.repository import Gtk
from gi.repository import Gdk

from gajim.plugins.plugins_i18n import _

from syntax_highlight.gtkformatter import GTKFormatter
from syntax_highlight.types import MatchType
from syntax_highlight.types import LineBreakOptions
from syntax_highlight.types import CodeMarkerOptions
from syntax_highlight.types import PLUGIN_INTERNAL_NONE_LEXER_ID

log = logging.getLogger('gajim.p.syntax_highlight')


class ChatSyntaxHighlighter:
    def __init__(self, plugin_config, highlighter_config, chat_control):
        self.textview = chat_control.conv_textview
        self._plugin_config = plugin_config
        self._highlighter_config = highlighter_config
        self._chat_control = chat_control
        self._chat_control.msg_textview.connect(
            'populate-popup', self._on_msg_textview_populate_popup)

    def update_config(self, plugin_config):
        self._plugin_config = plugin_config

    def _on_msg_textview_populate_popup(self, _textview, menu):
        item = Gtk.MenuItem.new_with_mnemonic(_('_Paste as Code'))
        menu.append(item)
        id_ = item.connect('activate', self._paste_as_code)
        self._chat_control.handlers[id_] = item

        item = Gtk.MenuItem.new_with_mnemonic(_('Paste as Code _Block'))
        menu.append(item)
        id_ = item.connect('activate', self._paste_as_code_block)
        self._chat_control.handlers[id_] = item

        menu.show_all()

    @staticmethod
    def _get_clipboard_text():
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        return clipboard.wait_for_text()

    def _insert_paste(self, text):
        self._chat_control.msg_textview.remove_placeholder()
        message_buffer = self._chat_control.msg_textview.get_buffer()
        message_buffer.insert_at_cursor(text)

    def _paste_as_code(self, _item):
        text = self._get_clipboard_text()
        self._insert_paste(f'`{text}`')

    def _paste_as_code_block(self, _item):
        text = self._get_clipboard_text()
        self._insert_paste(f'```\n{text}\n```')

    @staticmethod
    def _hide_code_markup(buf, start, end):
        tag = buf.get_tag_table().lookup('hide_code_markup')
        if tag is None:
            tag = Gtk.TextTag.new('hide_code_markup')
            tag.set_property('invisible', True)
            buf.get_tag_table().add(tag)

        buf.apply_tag_by_name('hide_code_markup', start, end)

    def _check_line_break(self, is_multiline):
        line_break = self._plugin_config['line_break'].value
        return (line_break == LineBreakOptions.ALWAYS) \
            or (is_multiline and line_break == LineBreakOptions.MULTILINE)

    def _format_code(self, buf, s_tag, s_code, e_tag, e_code, language):
        style = self._plugin_config['style']
        if self._plugin_config['code_marker'] == CodeMarkerOptions.HIDE:
            self._hide_code_markup(buf, s_tag, s_code)
            self._hide_code_markup(buf, e_code, e_tag)
        else:
            comment_tag = GTKFormatter.create_tag_for_token(
                Comment, get_style_by_name(style))
            buf.get_tag_table().add(comment_tag)
            buf.apply_tag(comment_tag, s_tag, s_code)
            buf.apply_tag(comment_tag, e_tag, e_code)

        code = s_code.get_text(e_code)
        log.debug('full text to encode: %s.', code)

        start_mark = buf.create_mark(None, s_code, False)

        lexer = None

        if language is None:
            lexer = self._highlighter_config.get_default_lexer()
            log.info('No Language specified. '
                     'Falling back to default lexer: %s.',
                     self._highlighter_config.get_default_lexer_name())
        else:
            log.debug('Using lexer for %s.', str(language))
            lexer = self._highlighter_config.get_lexer_with_fallback(language)

        if lexer is None:
            iterator = buf.get_iter_at_mark(start_mark)
            buf.insert(iterator, '\n')
        elif lexer != PLUGIN_INTERNAL_NONE_LEXER_ID:
            tokens = pygments.lex(code, lexer)

            formatter = GTKFormatter(style=style, start_mark=start_mark)
            pygments.format(tokens, formatter, buf)

    @staticmethod
    def _find_multiline_matches(text):
        start = None
        matches = []
        # Less strict, allow prefixed whitespaces:
        # for i in re.finditer(r'(?:^|\n)[ |\t]*(```)\S*[ |\t]*(?:\n|$)',
        #     text, re.DOTALL):
        for i in re.finditer(r'(?:^|\n)(```)\S*(?:\n|$)', text, re.DOTALL):
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

    @staticmethod
    def _find_inline_matches(text):
        """
        Inline code is highlighted if the start marker is precedded by a start
        of line, a whitespace character or either of the other span markers
        defined in XEP-0393.
        The same applies mirrored to the end marker.
        """
        return [(i.start(1), i.end(1), i.group(1)) for i in
                re.finditer(r'(?:^|\s|\*|~|_)(`((?!`).+?)`)(?:\s|\*|~|_|$)',
                            text)]

    @staticmethod
    def _merge_match_groups(real_text, inline_matches, multiline_matches):
        it_inline = iter(inline_matches)
        it_multi = iter(multiline_matches)
        length = len(real_text)

        # Just to get cleaner code below...
        def _get_next(iterator):
            return next(iterator, (length, length, ''))

        # In order to simplify the process, we use the 'length' here.
        cur_inline = _get_next(it_inline)
        cur_multi = _get_next(it_multi)

        pos = 0

        # This will contain tuples with parts of the input and its
        # classification
        parts = []
        while pos < length:
            log.debug('-> in: %s', str(cur_inline))
            log.debug('-> mu: %s', str(cur_multi))

            # selected = (start, end, type)
            if cur_inline[0] < cur_multi[0]:
                selected = (cur_inline[0], cur_inline[1], MatchType.INLINE)
            elif cur_multi[0] < length:
                selected = (cur_multi[0], cur_multi[1], MatchType.MULTILINE)
            else:
                selected = (pos, length, MatchType.TEXT)
            log.debug('--> select: %s', str(selected))

            # Handle plain text string parts (and unforseen errors...)
            if pos < selected[0]:
                end = selected[0] if selected[0] != pos else selected[1]
                parts.append((real_text[pos:end], MatchType.TEXT))
                pos = selected[0]
            elif pos > selected[0]:
                log.error('Should not happen, position > found match.')

            # Cut out and append selected text segment
            parts.append((real_text[selected[0]:selected[1]], selected[2]))
            pos = selected[1]

            # Depending on the match type, we have to forward the iterators.
            # Also, forward the other one, if regions overlap or we took over.
            if selected[2] == MatchType.INLINE:
                if cur_multi[0] < cur_inline[1]:
                    cur_multi = _get_next(it_multi)
                cur_inline = _get_next(it_inline)
            elif selected[2] == MatchType.MULTILINE:
                if cur_inline[0] < cur_multi[1]:
                    cur_inline = _get_next(it_inline)
                cur_multi = _get_next(it_multi)

        return parts

    def process_text(self, real_text, other_tags, _graphics, iter_,
                     _additional):
        def _fix_newline(char, marker_len_no_newline, force=False):
            fixed = (marker_len_no_newline, '')
            if char == '\n':
                fixed = (marker_len_no_newline + 1, '')
            elif force:
                fixed = (marker_len_no_newline + 1, '\n')
            return fixed

        buf = self.textview.tv.get_buffer()

        # First, try to find inline or multiline code snippets
        inline_matches = self._find_inline_matches(real_text)
        multiline_matches = self._find_multiline_matches(real_text)

        if not inline_matches and not multiline_matches:
            log.debug('Stopping early, since there is no code block in it...')
            return

        iterator = iter_ if iter_ is not None else buf.get_end_iter()

        # Create a start marker with left gravity before inserting text.
        start_mark = buf.create_mark('SHP_start', iterator, True)
        end_mark = buf.create_mark('SHP_end', iterator, False)

        insert_newline_for_multiline = self._check_line_break(True)
        insert_newline_for_inline = self._check_line_break(False)

        split_text = self._merge_match_groups(
            real_text, inline_matches, multiline_matches)

        buf.begin_user_action()

        for num, (text_to_insert, match_type) in enumerate(split_text):
            language = None
            end_of_message = num == (len(split_text) - 1)

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
                    front = _fix_newline(
                        text_to_insert[0],
                        3 + language_len,
                        insert_newline_for_multiline)
                    back = _fix_newline(
                        text_to_insert[-1],
                        3,
                        insert_newline_for_multiline and not end_of_message)
                else:
                    front = _fix_newline(
                        text_to_insert[0],
                        1,
                        insert_newline_for_inline)
                    back = _fix_newline(
                        text_to_insert[-1],
                        1,
                        insert_newline_for_inline and not end_of_message)

                marker_widths = (front[0], back[0])
                text_to_insert = ''.join([front[1], text_to_insert, back[1]])

                # Insertion invalidates iterator, let's use our start mark...
                self._insert_and_format_code(
                    buf, text_to_insert, language, marker_widths, start_mark,
                    end_mark, other_tags)

            iterator = buf.get_iter_at_mark(end_mark)
            # The current end of the buffer's contents is the start for the
            # next iteration
            buf.move_mark(start_mark, iterator)

        buf.delete_mark(start_mark)
        buf.delete_mark(end_mark)

        buf.end_user_action()

        # We have to make sure this is the last thing we do (i.e. no calls to
        # the other textview methods no more from here on), because the
        # print_special_text method is resetting the plugin_modified variable.
        self.textview.plugin_modified = True

    def _insert_and_format_code(self, buf, insert_text, language, marker,
                                start_mark, end_mark, other_tags=None):

        start_iter = buf.get_iter_at_mark(start_mark)

        if other_tags:
            buf.insert_with_tags_by_name(start_iter, insert_text, *other_tags)
        else:
            buf.insert(start_iter, insert_text)

        tag_start = buf.get_iter_at_mark(start_mark)
        tag_end = buf.get_iter_at_mark(end_mark)
        s_code = tag_start.copy()
        e_code = tag_end.copy()
        s_code.forward_chars(marker[0])
        e_code.backward_chars(marker[1])

        log.debug('full text between tags: %s.', tag_start.get_text(tag_end))

        self._format_code(buf, tag_start, s_code, tag_end, e_code, language)

        self.textview.plugin_modified = True

        # Set general code block format
        tag = Gtk.TextTag.new()
        bg_color = self._plugin_config['bgcolor']
        if self._plugin_config['bgcolor_override']:
            tag.set_property('background', bg_color)
            tag.set_property('paragraph-background', bg_color)
        tag.set_property('font', self._plugin_config['font'])
        buf.get_tag_table().add(tag)
        buf.apply_tag(tag, tag_start, tag_end)
