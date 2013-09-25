# -*- coding: utf-8 -*-
##

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls
import sys
import os
import traceback
import threading
from cStringIO import StringIO

have_pygments = True
try:
    from pygments import highlight
    from pygments.lexers import PythonConsoleLexer
    from pygments.formatters import TerminalFormatter
    test = PythonConsoleLexer.name

except ImportError:
    have_pygments = False
import catcher

class ColoredTracebackPlugin(GajimPlugin):

    @log_calls('ColoredTracebackPlugin')
    def init(self):
        self.config_dialog = None  # ColoredTracebackPluginConfigDialog(self)
        if not have_pygments:
            self.available_text = _('Pygments are not available. '
                'Install python-pygments.')
            self.activatable = False

    @log_calls('ColoredTracebackPlugin')
    def activate(self):
        # gdb/kdm etc if we use startx this is not True
        if os.name == 'nt' or sys.stderr.isatty():
            self._exception_in_progress = threading.Lock()
            self._excepthook_save = sys.excepthook
            sys.excepthook = self._info

    @log_calls('ColoredTracebackPlugin')
    def deactivate(self):
        sys.excepthook = self._excepthook_save

    def _info(self, type_, value, tb):
        if not self._exception_in_progress.acquire(False):
            # Exceptions have piled up, so we use the default exception
            # handler for such exceptions
            self._excepthook_save(type_, value, tb)
            return
        trace = StringIO()
        traceback.print_exception(type_, value, tb, None, trace)

        print highlight(trace.getvalue(), PythonConsoleLexer(),
            TerminalFormatter())
        self._exception_in_progress.release()
