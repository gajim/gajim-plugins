# -*- coding: utf-8 -*-
##

import gtk
import gobject
import pango

from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from common import ged
from common import gajim
from common import helpers
import gtkgui_helpers


class ChatstatePlugin(GajimPlugin):

    @log_calls('ChatstatePlugin')
    def init(self):
        self.config_dialog = None#ChatstatePluginConfigDialog(self)
        self.events_handlers = {'raw-message-received' :
                                    (ged.POSTCORE, self.raw_pres_received),}
        self.chatstates = ('active', 'composing', 'gone', 'inactive', 'paused')
        self.active = None


    def raw_pres_received(self, event_object):
        if not self.active:
            return
        jid = str(event_object.xmpp_msg.getFrom())
        account = event_object.account
        contact = gajim.contacts.get_contact_from_full_jid(account, jid)
        if not contact:
            return

        for chatstate in self.chatstates:
            state = event_object.xmpp_msg.getTag(chatstate)
            if state:
                break
        if not state:
            return

        self.model = gajim.interface.roster.model
        child_iters = gajim.interface.roster._get_contact_iter(
                jid.split('/')[0], account, contact, self.model)

        for child_iter in child_iters:
            name = gobject.markup_escape_text(contact.get_shown_name())
            theme = gajim.config.get('roster_theme')
            color = None
            if chatstate == 'composing':
                color = gajim.config.get_per('themes', theme,
                                'state_composing_color')
            elif chatstate == 'inactive':
                color = gajim.config.get_per('themes', theme,
                                'state_inactive_color')
            elif chatstate == 'gone':
                color = gajim.config.get_per('themes', theme,
                                'state_gone_color')
            elif chatstate == 'paused':
                color = gajim.config.get_per('themes', theme,
                                'state_paused_color')
            elif chatstate == 'active':
                color = gajim.config.get('inmsgcolor')

            name = '<span foreground="%s">%s</span>' % (
                    color, name)
            if contact.status and gajim.config.get('show_status_msgs_in_roster'):
                status = contact.status.strip()
                if status != '':
                    status = helpers.reduce_chars_newlines(status,
                            max_lines = 1)
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
