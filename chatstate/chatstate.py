# -*- coding: utf-8 -*-
##

import gobject

from plugins import GajimPlugin
from plugins.helpers import log_calls
from common import ged
from common import gajim
from common import helpers
import gtkgui_helpers


class ChatstatePlugin(GajimPlugin):

    @log_calls('ChatstatePlugin')
    def init(self):
        self.config_dialog = None  # ChatstatePluginConfigDialog(self)
        self.events_handlers = {'chatstate-received':
                                    (ged.GUI2, self.chatstate_received), }
        self.chatstates = ('active', 'composing', 'gone', 'inactive', 'paused')
        self.active = None

    def chatstate_received(self, obj):
        if not self.active:
            return

        contact = gajim.contacts.get_contact_from_full_jid(obj.conn.name,
            obj.fjid)
        if not contact:
            return

        chatstate = obj.chatstate
        if chatstate not in self.chatstates:
            return

        self.model = gajim.interface.roster.model
        child_iters = gajim.interface.roster._get_contact_iter(obj.jid,
            obj.conn.name, contact, self.model)

        for child_iter in child_iters:
            name = gobject.markup_escape_text(contact.get_shown_name())
            theme = gajim.config.get('roster_theme')
            if chatstate != 'gone':
                color = None
                if chatstate == 'composing':
                    color = gajim.config.get_per('themes', theme,
                                    'state_composing_color')
                elif chatstate == 'inactive':
                    color = gajim.config.get_per('themes', theme,
                                    'state_inactive_color')
                elif chatstate == 'paused':
                    color = gajim.config.get_per('themes', theme,
                                    'state_paused_color')
                elif chatstate == 'active':
                    color = gajim.config.get('inmsgcolor')

                name = '<span foreground="%s">%s</span>' % (
                        color, name)

            if contact.status and gajim.config.get(
            'show_status_msgs_in_roster'):
                status = contact.status.strip()
                if status != '':
                    status = helpers.reduce_chars_newlines(status,
                            max_lines=1)
                    color = gtkgui_helpers.get_fade_color(
                            gajim.interface.roster.tree, False, False)
                    colorstring = '#%04x%04x%04x' % (color.red, color.green,
                            color.blue)
                    name += '\n<span size="small" style="italic" ' \
                            'foreground="%s">%s</span>' % (colorstring,
                            gobject.markup_escape_text(status))
            self.model[child_iter][1] = name

    @log_calls('ChatstatePlugin')
    def activate(self):
        self.active = True
        pass

    @log_calls('ChatstatePlugin')
    def deactivate(self):
        self.active = False
        pass
