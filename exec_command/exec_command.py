# -*- coding: utf-8 -*-

from plugins import GajimPlugin
from plugins.helpers import log_calls

from common import gajim
from command_system.implementation.execute import *

class ExecCommandPlugin(GajimPlugin):

    @log_calls('ExecCommandPlugin')
    def init(self):
        self.description = _('Add "show"("sh") command to command system. '
            'Execute expression inside a shell, send output.')
        self.config_dialog = None

    @log_calls('ExecCommandPlugin')
    def activate(self):
        Show.enable()

    @log_calls('ExecCommandPlugin')
    def deactivate(self):
        Show.disable()
