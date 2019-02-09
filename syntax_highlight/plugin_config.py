from gajim.plugins.helpers import log

from gi.repository import Gdk

from pygments.lexers import get_lexer_by_name, get_all_lexers
from pygments.styles import get_all_styles

from .types import LineBreakOptions, CodeMarkerOptions, \
                    PLUGIN_INTERNAL_NONE_LEXER_ID

class SyntaxHighlighterConfig:
    PLUGIN_INTERNAL_NONE_LEXER=('None (monospace only)', PLUGIN_INTERNAL_NONE_LEXER_ID)

    def _create_lexer_list(self):
        # The list we create here contains the plain text name and the lexer's
        # id string
        lexers = []

        # Iteration over get_all_lexers() seems to be broken somehow. Workarround
        all_lexers = get_all_lexers()
        for lexer in all_lexers:
            # We don't want to add lexers that we cant identify by name later
            if lexer[1] is not None and lexer[1]:
                lexers.append((lexer[0], lexer[1][0]))
        lexers.sort()

        # Insert our internal "none" type at top of the list.
        lexers.insert(0, self.PLUGIN_INTERNAL_NONE_LEXER)
        return lexers

    def is_internal_none_lexer(self, lexer):
        return lexer == PLUGIN_INTERNAL_NONE_LEXER_ID

    def get_internal_none_lexer(self):
        return self.PLUGIN_INTERNAL_NONE_LEXER

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
        if font is not None and font != "":
            self.config['font'] = font

    def set_style(self, style):
        if style is not None and style != "":
            self.config['style'] = style

    def set_line_break_action(self, option):
        if isinstance(option, int):
            option = LineBreakOptions(option)
        self.config['line_break'] = option

    def set_default_lexer(self, name):
        if not self.is_internal_none_lexer(name):
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
        else:
            self.default_lexer = self.PLUGIN_INTERNAL_NONE_LEXER

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

    def set_pygments_path(self, path):
        self.config['pygments_path'] = path

    def get_default_lexer(self):
        return self.default_lexer[1]

    def get_default_lexer_name(self):
        return self.default_lexer[0]

    def get_lexer_list(self):
        return self.lexer_list

    def get_line_break_action(self):
        # return int only
        if isinstance(self.config['line_break'], int):
            # in case of legacy settings, convert.
            action = self.config['line_break']
            self.set_line_break_action(action)
        else:
            action = self.config['line_break'].value

        return action

    def get_pygments_path(self):
        return self.config['pygments_path']

    def get_font(self):
        return self.config['font']

    def get_style_name(self):
        return self.config['style']

    def is_bgcolor_override_enabled(self):
        return self.config['bgcolor_override']

    def get_bgcolor(self):
        return self.config['bgcolor']

    def get_code_marker_setting(self):
        return self.config['code_marker']

    def get_styles_list(self):
        return self.style_list

    def init_pygments(self):
        """
        Initialize all config variables that depend directly on pygments being
        available.
        """
        self.lexer_list     = self._create_lexer_list()
        self.style_list     = [s for s in get_all_styles()]
        self.style_list.sort()
        self.set_default_lexer(self.config['default_lexer'])

    def __init__(self, config):
        self.lexer_list     = []
        self.style_list     = []
        self.config         = config
        self.default_lexer  = None
