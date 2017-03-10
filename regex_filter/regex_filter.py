# -*- coding: utf-8 -*-

## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##

'''
Regex Filter plugin.

:author: Yann Leboulanger <asterix@lagaule.org>
:since: 23th September 2011
:copyright: Copyright (2011) Yann Leboulanger <asterix@lagaule.org>
:license: GPLv3
'''

import re

from plugins import GajimPlugin
from plugins.helpers import log, log_calls

from common import gajim
from common import ged
from command_system.framework import CommandContainer, command, doc
from command_system.implementation.hosts import *

import ui

class RegexFilterPlugin(GajimPlugin):

    @log_calls('RegexFilterPlugin')
    def init(self):
        self.config_dialog = ui.RegexFilterPluginConfigDialog(self)

        self.events_handlers = {
            'decrypted-message-received': (ged.PREGUI1,
                self._nec_decrypted_message_received),
            'gc-message-received': (ged.PREGUI1, self._nec_gc_message_received),
        }

        self.create_rules()

    @log_calls('RegexFilterPlugin')
    def activate(self):
        FilterCommands.enable()

    @log_calls('RegexFilterPlugin')
    def deactivate(self):
        FilterCommands.disable()

    @log_calls('RegexFilterPlugin')
    def create_rules(self):
        self.rules = {}
        for num, c in self.config.items():
            self.rules[int(num)] = [re.compile(c[0], re.MULTILINE), c[1]]
        self.update_context_list()

    @log_calls('RegexFilterPlugin')
    def add_rule(self, search, replace):
        if self.rules:
            num = max(self.rules.keys()) + 1
        else:
            num = 0
        self.config[str(num)] = [search, replace]
        self.create_rules()

    @log_calls('RegexFilterPlugin')
    def edit_rule(self, num, search, replace):
        self.config[str(num)] = [search, replace]
        self.create_rules()

    @log_calls('RegexFilterPlugin')
    def remove_rule(self, num):
        if num in self.config:
            del self.config[num]
            self.create_rules()
            return True
        return False

    @log_calls('RegexFilterPlugin')
    def get_rules(self):
        return self.config


    @log_calls('RegexFilterPlugin')
    def is_valid_regex(self, string):
        if string.strip():
            try:
                re.compile(string)
                return True
            except re.error:
                None
        return False

    @log_calls('RegexFilterPlugin')
    def _nec_all(self, obj):
        if not obj.msgtxt:
            return
        rules_num = self.rules.keys()
        rules_num.sort()
        for num in rules_num:
            rule = self.rules[num]
            obj.msgtxt = rule[0].sub(rule[1], obj.msgtxt)

    @log_calls('RegexFilterPlugin')
    def _nec_decrypted_message_received(self, obj):
        self._nec_all(obj)

    @log_calls('RegexFilterPlugin')
    def _nec_gc_message_received(self, obj):
        self._nec_all(obj)

    @log_calls('RegexFilterPlugin')
    def update_context_list(self):
        self.config_dialog.rules_model.clear()
        rules_num = self.rules.keys()
        rules_num.sort()
        for num in rules_num:
            rule = self.rules[num]
            self.config_dialog.rules_model.append((num, rule[0].pattern, rule[1]))

class FilterCommands(CommandContainer):
    AUTOMATIC = False
    HOSTS = ChatCommands, PrivateChatCommands, GroupChatCommands

    @command("add_filter", raw=True)
    @doc(_("Add an incoming filter. First argument is the search regex, "
    "second argument is the replace regex."))
    def add_filter(self, search, replace):
        plugin = gajim.plugin_manager.get_active_plugin('regex_filter')
        plugin.add_rule(search, replace)
        return _('Added rule to replace %s by %s' % (search, replace))

    @command("remove_filter", raw=True)
    @doc(_("Remove an incoming filter. Argument is the rule number. "
    "See /list_rules command."))
    def remove_filter(self, num):
        plugin = gajim.plugin_manager.get_active_plugin('regex_filter')
        if plugin.remove_rule(num):
            return _('Rule number %s removed' % num)
        return _('Rule number %s does not exist' % num)

    @command("list_filters")
    @doc(_("List incoming filters."))
    def list_filters(self):
        plugin = gajim.plugin_manager.get_active_plugin('regex_filter')
        rules = plugin.get_rules()
        st = ''
        for num, rule in rules.items():
            st += _('%(num)s: %(search)s -> %(replace)s') % {'num': num,
                'search': rule[0], 'replace': rule[1]} + '\n'
        if st:
            return st[:-1]
        else:
            return _('No rule defined')
