# -*- coding: utf-8 -*-
##

import gobject

from plugins import GajimPlugin
from plugins.helpers import log_calls
from common import ged
from common import gajim
from common import helpers
import gtkgui_helpers
import unicodedata

def paragraph_direction_mark(text):
    """
    Determine paragraph writing direction according to
    http://www.unicode.org/reports/tr9/#The_Paragraph_Level

    Returns either Unicode LTR mark or RTL mark.
    """
    for char in text:
        bidi = unicodedata.bidirectional(char)
        if bidi == 'L':
            return u'\u200E'
        elif bidi == 'AL' or bidi == 'R':
            return u'\u200F'

    return u'\u200E'

class ChatstatePlugin(GajimPlugin):

    @log_calls('ChatstatePlugin')
    def init(self):
        self.config_dialog = None  # ChatstatePluginConfigDialog(self)
        self.events_handlers = {'chatstate-received':
                                    (ged.GUI2, self.chatstate_received), }
        self.active = None

    def chatstate_received(self, obj):
        if not self.active:
            return

        contact = gajim.contacts.get_contact_from_full_jid(obj.conn.name,
            obj.fjid)
        if not contact:
            return

        chatstate = obj.chatstate
        if chatstate not in self.chatstates.keys():
            return

        self.model = gajim.interface.roster.model
        child_iters = gajim.interface.roster._get_contact_iter(obj.jid,
            obj.conn.name, contact, self.model)

        name = gobject.markup_escape_text(contact.get_shown_name())
        contact_instances = gajim.contacts.get_contacts(obj.conn.name,
            contact.jid)

        # Show resource counter
        nb_connected_contact = 0
        for c in contact_instances:
            if c.show not in ('error', 'offline'):
                nb_connected_contact += 1
        if nb_connected_contact > 1:
            name += paragraph_direction_mark(unicode(name))
            name += u' (%d)' % nb_connected_contact

        for child_iter in child_iters:
            if chatstate != 'gone':
                color = self.chatstates[chatstate]
                name = '<span foreground="%s">%s</span>' % (color, name)
            if contact.status and gajim.config.get(
            'show_status_msgs_in_roster'):
                status = contact.status.strip()
                if status != '':
                    status = helpers.reduce_chars_newlines(status,
                            max_lines=1)
                    name += '\n<span size="small" style="italic" ' \
                            'foreground="%s">%s</span>' % (self.status_color,
                            gobject.markup_escape_text(status))
            self.model[child_iter][1] = name

    @log_calls('ChatstatePlugin')
    def activate(self):
        color = gtkgui_helpers.get_fade_color(gajim.interface.roster.tree,
            False, False)
        self.status_color = '#%04x%04x%04x' % (color.red, color.green,
            color.blue)
        theme = gajim.config.get('roster_theme')
        self.chatstates = {'active': gajim.config.get('inmsgcolor'),
                            'composing': gajim.config.get_per('themes', theme,
                                         'state_composing_color'),
                            'inactive': gajim.config.get_per('themes', theme,
                                        'state_inactive_color'),
                            'paused': gajim.config.get_per('themes', theme,
                                        'state_paused_color'),
                            'gone': None, }
        self.active = True

    @log_calls('ChatstatePlugin')
    def deactivate(self):
        self.active = False
