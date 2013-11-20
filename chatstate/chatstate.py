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
from nbxmpp.protocol import NS_CHATSTATES
import nbxmpp
from common.connection_handlers_events import MessageOutgoingEvent

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
                                    (ged.GUI2, self.chatstate_received),
                                'message-received':
                                    (ged.GUI2, self.message_received),}
        self.gui_extension_points = {'chat_control_base_set_control_active':
                                    (self.set_control_active, None),}
        self.active = None

    def set_control_active(self, control, state):
        if control.type_id != 'gc':
            return
       # print state, dir(control), control.room_jid, control.nick, control.contact.jid
        # send chatstate inactive to the one we're leaving
        # and active to the one we visit
        if state:
            message_buffer = control.msg_textview.get_buffer()
            if message_buffer.get_char_count():
                self.send_chatstate('paused', control.contact, control)
            else:
                self.send_chatstate('active', control.contact, control)
            #self.reset_kbd_mouse_timeout_vars()
            #gobject.source_remove(self.possible_paused_timeout_id)
            #gobject.source_remove(self.possible_inactive_timeout_id)
            #self._schedule_activity_timers()
        else:
            self.send_chatstate('inactive', control.contact, control)
    def send_chatstate(self, state, contact=None, control=None):
        chatstate_setting = gajim.config.get('outgoing_chat_state_notifications')
        if chatstate_setting == 'disabled':
            return
        elif chatstate_setting == 'composing_only' and state != 'active' and\
                state != 'composing':
            return

        if contact is None:
            contact = self.parent_win.get_active_contact()
            if contact is None:
                # contact was from pm in MUC, and left the room so contact is None
                # so we cannot send chatstate anymore
                return

        # Don't send chatstates to offline contacts
        if contact.show == 'offline':
            return
        print state
        #if not contact.supports(NS_CHATSTATES):
            #printNS_CHATSTATES
            #returnNS_CHATSTATES

        # if the new state we wanna send (state) equals
        # the current state (contact.our_chatstate) then return
        if contact.our_chatstate == state:
            return

        # if wel're inactive prevent composing (XEP violation)
        if contact.our_chatstate == 'inactive' and state == 'composing':
            # go active before
            msg_iq = nbxmpp.Message(control.room_jid, None, typ='groupchat')
            msg_iq.setTag('active', namespace=NS_CHATSTATES)
            control.connection.connection.send(msg_iq)
            contact.our_chatstate = 'active'
            #self.reset_kbd_mouse_timeout_vars()
        msg_iq = nbxmpp.Message(control.room_jid, None, typ='groupchat')
        msg_iq.setTag(state, namespace=NS_CHATSTATES)
        control.connection.connection.send(msg_iq)
        contact.our_chatstate = state
        #if state == 'active':
            #self.reset_kbd_mouse_timeout_vars()

    def _on_notebook_switch_page(self, notebook, page, page_num):
        old_no = notebook.get_current_page()
        if old_no >= 0:
            old_ctrl = self._widget_to_control(notebook.get_nth_page(old_no))
            old_ctrl.set_control_active(False)

        new_ctrl = self._widget_to_control(notebook.get_nth_page(page_num))
        new_ctrl.set_control_active(True)
        self.show_title(control = new_ctrl)

        control = self.get_active_control()
        if isinstance(control, ChatControlBase):
            control.msg_textview.grab_focus()

    def message_received(self, obj):
        if not self.active or not obj.gc_control or obj.mtype != 'groupchat':
            return

        obj.get_chatstate()
        chatstate = obj.chatstate
        nick = obj.resource
        gc_control = obj.gc_control
        if chatstate not in self.chatstates.keys():
            return

        iter_ = gc_control.get_contact_iter(nick)
        if not iter_:
            return
        gc_contact = gajim.contacts.get_gc_contact(obj.conn.name, obj.jid,
                nick)

        name = gobject.markup_escape_text(gc_contact.name)
        if chatstate != 'gone':
            color = self.chatstates[chatstate]
            name = '<span foreground="%s">%s</span>' % (color, name)

        # Strike name if blocked
        fjid = obj.fjid
        if helpers.jid_is_blocked(obj.conn.name, fjid):
            name = '<span strikethrough="true">%s</span>' % name
        status = gc_contact.status
        # add status msg, if not empty, under contact name in the treeview
        if status and gajim.config.get('show_status_msgs_in_roster'):
            status = status.strip()
            if status != '':
                status = helpers.reduce_chars_newlines(status, max_lines=1)
                # escape markup entities and make them small italic and fg color
                name += ('\n<span size="small" style="italic" foreground="%s">'
                    '%s</span>') % (self.status_color, gobject.markup_escape_text(
                    status))

        gc_control.model[iter_][3] = name

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
