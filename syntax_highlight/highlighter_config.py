import logging

from pygments.lexers import get_lexer_by_name
from pygments.lexers import get_all_lexers
from pygments.styles import get_all_styles
from pygments.util import ClassNotFound

from syntax_highlight.types import PLUGIN_INTERNAL_NONE_LEXER_ID

log = logging.getLogger('gajim.p.syntax_highlight')
PLUGIN_INTERNAL_NONE_LEXER = ('None (monospace only)',
                              PLUGIN_INTERNAL_NONE_LEXER_ID)


class HighlighterConfig:
    def __init__(self, plugin_config):
        self._plugin_config = plugin_config

        self._lexer_list = self._create_lexer_list()
        self._style_list = []
        for style in get_all_styles():
            self._style_list.append(style)
        self._style_list.sort()

        self._default_lexer = None
        self.set_default_lexer(self._plugin_config['default_lexer'])

    @staticmethod
    def _create_lexer_list():
        # The list we create here contains the plain text name and the lexer's
        # id string
        lexers = []

        # Iteration over get_all_lexers() seems to be broken somehow
        # Workaround
        all_lexers = get_all_lexers()
        for lexer in all_lexers:
            # We don't want to add lexers that we cant identify by name later
            if lexer[1] is not None and lexer[1]:
                lexers.append((lexer[0], lexer[1][0]))
        lexers.sort()

        # Insert our internal 'none' type at top of the list
        lexers.insert(0, PLUGIN_INTERNAL_NONE_LEXER)
        return lexers

    @staticmethod
    def get_lexer_by_name(name):
        lexer = None
        try:
            lexer = get_lexer_by_name(name)
        except ClassNotFound:
            pass
        return lexer

    def get_lexer_with_fallback(self, language):
        lexer = self.get_lexer_by_name(language)
        if lexer is None:
            log.info('Falling back to default lexer for %s.',
                     self.get_default_lexer_name())
            lexer = self._default_lexer[1]
        return lexer

    def set_default_lexer(self, name):
        if name != PLUGIN_INTERNAL_NONE_LEXER_ID:
            lexer = get_lexer_by_name(name)

            if lexer is None and self._default_lexer is None:
                log.error('Failed to get default lexer by name.'
                          'Falling back to simply using the first lexer '
                          'in the list.')
                lexer = self._lexer_list[0]
                name = lexer[0]
                self._default_lexer = (name, lexer)
            if lexer is None and self._default_lexer is not None:
                log.info('Failed to get default lexer by name, keeping '
                         'previous setting (lexer = %s).',
                         self._default_lexer[0])
                name = self._default_lexer[0]
            else:
                self._default_lexer = (name, lexer)
        else:
            self._default_lexer = PLUGIN_INTERNAL_NONE_LEXER

        self._plugin_config['default_lexer'] = name

    def get_default_lexer(self):
        return self._default_lexer[1]

    def get_default_lexer_name(self):
        return self._default_lexer[0]

    def get_lexer_list(self):
        return self._lexer_list

    def get_styles_list(self):
        return self._style_list
