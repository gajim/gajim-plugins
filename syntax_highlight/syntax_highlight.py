import logging
from functools import partial

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from syntax_highlight.types import LineBreakOptions
from syntax_highlight.types import CodeMarkerOptions
from syntax_highlight.types import PLUGIN_INTERNAL_NONE_LEXER_ID

log = logging.getLogger('gajim.p.syntax_highlight')

HAS_PYGMENTS = False
try:
    from syntax_highlight.chat_syntax_highlighter import ChatSyntaxHighlighter
    from syntax_highlight.config_dialog import SyntaxHighlighterPluginConfig
    from syntax_highlight.highlighter_config import HighlighterConfig
    HAS_PYGMENTS = True
except Exception as exception:
    log.error('Could not load pygments: %s', exception)


class SyntaxHighlighterPlugin(GajimPlugin):
    def init(self):
        self.description = _(
            'Source code syntax highlighting in the chat window.\n\n'
            'Markdown-style syntax is supported, i.e. text inbetween '
            '`single backticks` is rendered as inline code.\n'
            '```language\n'
            'selection is possible in multi-line code snippets inbetween '
            'triple-backticks\n'
            'Note the newlines in this case…\n'
            '```\n\n'
            'Changed settings will take effect after re-opening the message '
            'tab/window.')

        self.config_default_values = {
            'default_lexer': (PLUGIN_INTERNAL_NONE_LEXER_ID, ''),
            'line_break': (LineBreakOptions.MULTILINE, ''),
            'style': ('default', ''),
            'font': ('Monospace 10', ''),
            'bgcolor': ('rgb(200, 200, 200)', ''),
            'bgcolor_override': (True, ''),
            'code_marker': (CodeMarkerOptions.AS_COMMENT, ''),
        }

        self.gui_extension_points = {
            'chat_control_base': (
                self._connect_chat_control,
                self._disconnect_chat_control),
            'print_real_text': (self._on_print_real_text, None)
        }

        if not HAS_PYGMENTS:
            self.activatable = False
            self.available_text = _('You are missing python-pygments.')
            self.config_dialog = None

        self._migrate_settings()
        self._highlighters = {}
        self.config_dialog = partial(SyntaxHighlighterPluginConfig, self)
        self.highlighter_config = HighlighterConfig(self.config)

    def _migrate_settings(self):
        line_break = self.config['line_break']
        if isinstance(line_break, int):
            self.config['line_break'] = LineBreakOptions(line_break)

    def _connect_chat_control(self, chat_control):
        highlighter = ChatSyntaxHighlighter(
            self.config, self.highlighter_config, chat_control.conv_textview)
        self._highlighters[chat_control.control_id] = highlighter

    def _disconnect_chat_control(self, chat_control):
        highlighter = self._highlighters.get(chat_control.control_id)
        if highlighter is not None:
            del highlighter
            self._highlighters.pop(chat_control.control_id, None)

    def _on_print_real_text(self, text_view, real_text, other_tags, graphics,
                            iterator, additional):
        for highlighter in self._highlighters.values():
            if highlighter.textview != text_view:
                continue
            highlighter.process_text(
                real_text, other_tags, graphics, iterator, additional)
            return

    def update_highlighters(self):
        for highlighter in self._highlighters.values():
            highlighter.update_config(self.config)
