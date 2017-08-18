# -*- coding: utf-8 -*-
##

from gi.repository import GObject

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.common import ged
from gajim.common import app
from gajim.common import helpers
from gajim import gtkgui_helpers
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
            return '\u200E'
        elif bidi == 'AL' or bidi == 'R':
            return '\u200F'

    return '\u200E'

class ChatstatePlugin(GajimPlugin):

    @log_calls('ChatstatePlugin')
    def init(self):
        self.description = _('Chat State Notifications in roster.'
'Font color of the contact varies depending on the chat state.\n'
'The plugin does not work if you use custom font color for contacts in roster.\n'
'http://trac.gajim.org/ticket/3628.\nhttp://xmpp.org/extensions/xep-0085.html')
        self.config_dialog = None  # ChatstatePluginConfigDialog(self)
        self.events_handlers = {'chatstate-received':
                                    (ged.GUI2, self.chatstate_received), }
        self.active = None

    def chatstate_received(self, obj):
        if not self.active:
            return

        contact = app.contacts.get_contact_from_full_jid(obj.conn.name,
            obj.fjid)
        if not contact:
            return

        chatstate = obj.chatstate
        if chatstate not in self.chatstates.keys():
            return

        self.model = app.interface.roster.model
        child_iters = app.interface.roster._get_contact_iter(obj.jid,
            obj.conn.name, contact, self.model)

        name = GObject.markup_escape_text(contact.get_shown_name())
        contact_instances = app.contacts.get_contacts(obj.conn.name,
            contact.jid)

        # Show resource counter
        nb_connected_contact = 0
        for c in contact_instances:
            if c.show not in ('error', 'offline'):
                nb_connected_contact += 1
        if nb_connected_contact > 1:
            name += paragraph_direction_mark(name)
            name += ' (%d)' % nb_connected_contact

        for child_iter in child_iters:
            if chatstate != 'gone':
                color = self.chatstates[chatstate]
                name = '<span foreground="%s">%s</span>' % (color, name)
            if contact.status and app.config.get(
            'show_status_msgs_in_roster'):
                status = contact.status.strip()
                if status != '':
                    status = helpers.reduce_chars_newlines(status,
                            max_lines=1)
                    name += '\n<span size="small" style="italic" ' \
                            'foreground="%s">%s</span>' % (self.status_color,
                            GObject.markup_escape_text(status))
            self.model[child_iter][1] = name

    @log_calls('ChatstatePlugin')
    def activate(self):
        color = gtkgui_helpers.get_fade_color(app.interface.roster.tree,
            False, False)
        self.status_color = '#%04x%04x%04x' % (color.red, color.green,
            color.blue)
        theme = app.config.get('roster_theme')
        self.chatstates = {'active': app.config.get('inmsgcolor'),
                            'composing': app.config.get_per('themes', theme,
                                         'state_composing_color'),
                            'inactive': app.config.get_per('themes', theme,
                                        'state_inactive_color'),
                            'paused': app.config.get_per('themes', theme,
                                        'state_paused_color'),
                            'gone': None, }
        self.active = True

    @log_calls('ChatstatePlugin')
    def deactivate(self):
        self.active = False
