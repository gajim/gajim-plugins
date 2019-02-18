import logging
import sys

if sys.version_info >= (3, 4):
    from importlib.util import find_spec as find_module
else:
    from importlib import find_loader as find_module


from gajim.plugins.helpers import log_calls, log
from gajim.plugins import GajimPlugin

from .types import MatchType, LineBreakOptions, CodeMarkerOptions, \
                    PLUGIN_INTERNAL_NONE_LEXER_ID

log = logging.getLogger('gajim.plugin_system.syntax_highlight')

def try_loading_pygments():
    success = find_module('pygments') is not None
    if success:
        try:
            from .chat_syntax_highlighter import ChatSyntaxHighlighter
            from .plugin_config_dialog import SyntaxHighlighterPluginConfiguration
            from .plugin_config import SyntaxHighlighterConfig
            global SyntaxHighlighterPluginConfiguration, ChatSyntaxHighlighter, \
                SyntaxHighlighterConfig
            success = True
            log.debug("pygments loaded.")
        except Exception as exception:
            log.error("Import Error: %s.", exception)
            success = False

    return success

PYGMENTS_MISSING = 'You are missing Python-Pygments.'



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

    def try_init(self):
        """
        Separating this part of the initialization from the init() method
        allows repeating this step again, without reloading the plugin,
        i.e. restarting Gajim for instance.
        Doing so allows resolving the dependency issues without restart :)
        """
        pygments_loaded = try_loading_pygments()
        if not pygments_loaded:
            return False

        self.activatable = True
        self.available_text = None
        self.config_dialog = SyntaxHighlighterPluginConfiguration(self)

        self.conf   = SyntaxHighlighterConfig(self.config)
        # The following initialization requires pygments to be available.
        self.conf.init_pygments()

        self.config_dialog  = SyntaxHighlighterPluginConfiguration(self)
        self.config_dialog.set_config(self.conf)

        self.gui_extension_points = {
                'chat_control_base': (
                        self.on_connect_with_chat_control,
                        self.on_disconnect_from_chat_control
                   ),
                'print_real_text': (self.on_print_real_text, None),
        }
        return True

    @log_calls('SyntaxHighlighterPlugin')
    def init(self):
        self.ccontrol       = {}

        self.config_default_values = {
                'default_lexer'     : (PLUGIN_INTERNAL_NONE_LEXER_ID, ''),
                'line_break'        : (LineBreakOptions.MULTILINE, ''),
                'style'             : ('default', ''),
                'font'              : ('Monospace 10', ''),
                'bgcolor'           : ('#ccc', ''),
                'bgcolor_override'  : (True, ''),
                'code_marker'       : (CodeMarkerOptions.AS_COMMENT, ''),
                'pygments_path'     : (None, ''),
                }

        is_initialized = self.try_init()

        if not is_initialized:
            self.activatable = False
            self.available_text = PYGMENTS_MISSING
            self.config_dialog = None
