# -*- coding: utf-8 -*-
##

import gtk
import gobject
import pango

from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from common import ged
from common import gajim
from common import helpers
import gtkgui_helpers


class ChatstatePlugin(GajimPlugin):

    @log_calls('ChatstatePlugin')
    def init(self):
        self.config_dialog = ChatstatePluginConfigDialog(self)
        self.events_handlers = {'raw-message-received' :
                                    (ged.POSTCORE, self.raw_pres_received),}
        self.config_default_values = {
            'active': ('darkblue',''),
            'composing': ('darkgreen', ''),
            'inactive': ('#675B5B',''),
            'paused': ('darkred', ''),}
        self.compose = ('active', 'composing', 'gone', 'inactive', 'paused')
        self.active = None


    def raw_pres_received(self, event_object):
        if not self.active:
            return
        jid = str(event_object.xmpp_msg.getFrom())
        account = event_object.account
        contact = gajim.contacts.get_contact_from_full_jid(account, jid)
        if not contact:
            return

        for compose in self.compose:
            state = event_object.xmpp_msg.getTag(compose)
            if state:
                break
        if not state:
            return

        self.model = gajim.interface.roster.model
        child_iters = gajim.interface.roster._get_contact_iter(
                jid.split('/')[0], account, contact, self.model)

        for child_iter in child_iters:
            name = gobject.markup_escape_text(contact.get_shown_name())
            if compose != 'gone':
                name = '<span foreground="%s">%s</span>' % (
                        self.config[compose], name)
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


class ChatstatePluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['vbox1'])
        vbox1 = self.xml.get_object('vbox1')
        self.child.pack_start(vbox1)
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)

    def on_run(self):
        for name in self.plugin.config_default_values:
            widget = self.xml.get_object(name)
            widget.set_color(gtk.gdk.color_parse(self.plugin.config[name]))

    def changed(self, entry):
        name = gtk.Buildable.get_name(entry)
        self.plugin.config[name] = entry.get_text()

    def on_hide(self, widget):
        for name in self.plugin.config_default_values:
            widget = self.xml.get_object(name)
            self.plugin.config[name] = widget.get_color().to_string()
