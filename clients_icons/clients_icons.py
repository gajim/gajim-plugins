# -*- coding: utf-8 -*-
##

import gtk
import os

from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from common import ged
from common import gajim
import cell_renderer_image

clients = {
    'http://gajim.org': 'gajim.png',
    'http://gajim.org/caps': 'gajim.png',
    'http://bombus-im.org/java': 'bombus.png',
    'http://bombusmod.net.ru/caps': 'bombusmod.png',
    'http://psi-dev.googlecode.com/caps': 'psiplus.png',
    'http://bombusng-md.googlecode.com': 'bombusng.png',
    'http://bombus-im.org/ng': 'bombusng.png',
    'http://voffk.org.ru/bombus': 'bombusplus.png',
    'http://bombusng-qd.googlecode.com': 'bombusqd.png',
    'http://bombusmod-qd.wen.ru/caps': 'bombusqd.png',
    'http://bombusmod.net.ru': 'bombusmod.png',
    'http://ex-im.name/caps': 'bombusmod.png',
    'http://bombusmod.eu,http://bombus.pl': 'bombuspl.png',
    'http://mcabber.com/caps': 'mcabber.png',
    'http://miranda-im.org/caps': 'miranda.png',
    'http://www.asterisk.org/xmpp/client/caps': 'asterisk.png',
    'http://www.google.com/xmpp/client/caps': 'talkonaut.png',
    'http://oneteam.im/caps': 'oneteamiphone.png',
    'http://tkabber.jabber.ru/': 'tkabber.png',
    'http://pidgin.im/': 'pidgin.png',
    'http://qutim.org': 'qutim.png',
    'http://exodus.jabberstudio.org/caps': 'exodus.png',
    'http://bitlbee.org/xmpp/caps': 'bitlbee.png',
    'http://coccinella.sourceforge.net/protocol/caps': 'coccinella.png',
    'http://mcabber.lilotux.net/caps': 'mcabber.png',
    'http://dev.jabbim.cz/jabbim/caps': 'jabbim.png',
    'http://palringo.com/caps': 'palringo.png',
    'http://vacuum-im.googlecode.com': 'vacuum.png',
    'http://code.google.com/p/vacuum-im/': 'vacuum.png',
    'http://jajc.jrudevels.org/caps': 'jajc.png',
    'http://gaim.sf.net/caps': 'gaim.png',
    'http://mchat.mgslab.com/': 'mchat.png',
    'http://online.yandex.ru/caps': 'yaonline.png',
    'http://psi-im.org/caps': 'psi.png',
    'http://jimm.net.ru/caps': 'jimm-aspro.png',
    'http://bluendo.com/protocol/caps': 'lampiro.png',
    'nimbuzz:caps': 'nimbuzz.png',
    'http://isida.googlecode.com': 'isida-bot.png',
    'http://isida-bot.com': 'isida-bot.png',
    'http://apps.radio-t.com/caps': 'radio-t.png',
    'http://pda.qip.ru/caps': 'qippda.png',
    'http://kopete.kde.org/jabber/caps': 'kopete.png',
    'http://www.apple.com/ichat/caps': 'ichat.png',
    'http://pjc.googlecode.com/caps': 'jubo.png',
    'talk.google.com': 'talk.google.com.png',
    'http://swift.im': 'swift.png',
    'http://fatal-bot.spb.ru/caps': 'bot.png',
    'http://svn.posix.ru/fatal-bot/trunk': 'bot.png',
    'http://storm-bot.googlecode.com/svn/trunk': 'bot.png',
    'http://talk.google.com/xmpp/bot/caps': 'google.png',
    'http://jabbrik.ru/caps': 'bot.png',
    'http://jabrvista.net.ru': 'bot.png',
    'http://xu-6.jabbrik.ru/caps': 'bot.png',
    'http://jabber.pdg.pl/caps': 'bombus-klub.png',
    'http://klub54.wen.ru': 'bombus-klub.png',
    'http://aqq.eu/': 'aqq.png',
    'http://2010.qip.ru/caps': 'qipinfium.png',
    'http://qip.ru/caps': 'qipinfium.png',
    'http://glu.net/': 'glu.png',
    '-Z-r': 'siejc.png',
    'telepathy.': 'telepathy.freedesktop.org.png',
    'http://live.genome.org/empathy/caps': 'telepathy.freedesktop.org.png',
    'http://telepathy.freedesktop.org/caps': 'telepathy.freedesktop.org.png',
    'http://www.adiumx.com/caps': 'adium.png',
    'http://www.adiumx.com': 'adium.png',
}

class ClientsIconsPlugin(GajimPlugin):

    @log_calls('ClientsIconsPlugin')
    def init(self):
        self.pos_list = ['after statusicon', 'befor avatar']
        self.events_handlers = {'presence-received':
                                    (ged.POSTGUI, self.presence_received),
                                'gc-presence-received':
                                    (ged.POSTGUI, self.gc_presence_received),}
        self.gui_extension_points = {
            'groupchat_control' : (self.connect_with_groupchat_control,
                                    self.disconnect_from_groupchat_control)}
        self.config_default_values = {
                'show_in_roster': (True,''),
                'show_in_groupchats': (True,''),
                'show_unknown_icon': (True,''),
                'pos_in_list': (0,''),}

        self.config_dialog = ClientsIconsPluginConfigDialog(self)
        icon_path = os.path.join(self.local_file_path('icons'), 'unknown.png')
        self.default_pixbuf = gtk.gdk.pixbuf_new_from_file_at_size( icon_path,
            16, 16)

    @log_calls('ClientsIconsPlugin')
    def connect_with_groupchat_control(self, chat_control):
        chat_control.nb_ext_renderers += 1
        chat_control.columns += [gtk.gdk.Pixbuf]
        self.groupchats_tree_is_transformed = True
        self.chat_control = chat_control
        col = gtk.TreeViewColumn()
        self.muc_renderer_num = 4 + chat_control.nb_ext_renderers
        client_icon_rend = ('client_icon', gtk.CellRendererPixbuf(), False,
                'pixbuf', self.muc_renderer_num,
                self.tree_cell_data_func, chat_control)
        # remove old column
        chat_control.list_treeview.remove_column(
            chat_control.list_treeview.get_column(0))
        # add new renderer in renderers list
        position_list = ['name', 'avatar']
        position = position_list[self.config['pos_in_list']]
        for renderer in chat_control.renderers_list:
            if renderer[0] == position:
                break
        num = chat_control.renderers_list.index(renderer)
        chat_control.renderers_list.insert(num, client_icon_rend)
        # fill and append column
        chat_control.fill_column(col)
        chat_control.list_treeview.insert_column(col, 0)
        # redraw roster
        store = gtk.TreeStore(*chat_control.columns)
        store.set_sort_func(1, chat_control.tree_compare_iters)
        store.set_sort_column_id(1, gtk.SORT_ASCENDING)
        chat_control.list_treeview.set_model(store)

    @log_calls('ClientsIconsPlugin')
    def disconnect_from_groupchat_control(self, chat_control):
        pass

    @log_calls('ClientsIconsPlugin')
    def activate(self):
        roster = gajim.interface.roster
        col = gtk.TreeViewColumn()
        roster.nb_ext_renderers += 1
        self.renderer_num = 10 + roster.nb_ext_renderers
        self.renderer = gtk.CellRendererPixbuf()
        client_icon_rend = ('client_icon', self.renderer, False,
                'pixbuf', self.renderer_num,
                roster._fill_pep_pixbuf_renderer, self.renderer_num)
        # remove old column
        roster.tree.remove_column(roster.tree.get_column(0))
        # add new renderer in renderers list
        position_list = ['name', 'avatar']
        position = position_list[self.config['pos_in_list']]
        for renderer in roster.renderers_list:
            if renderer[0] == position:
                break
        num = roster.renderers_list.index(renderer)
        roster.renderers_list.insert(num, client_icon_rend)
        # fill and append column
        roster.fill_column(col)
        roster.tree.insert_column(col, 0)
        # redraw roster
        roster.columns += [gtk.gdk.Pixbuf]
        roster.setup_and_draw_roster()

    @log_calls('ClientsIconsPlugin')
    def deactivate(self):
        roster = gajim.interface.roster
        roster.nb_ext_renderers -= 1
        col = roster.tree.get_column(0)
        roster.tree.remove_column(col)
        col = gtk.TreeViewColumn()
        for renderer in roster.renderers_list:
            if renderer[0] == 'client_icon':
                roster.renderers_list.remove(renderer)
                break
        roster.fill_column(col)
        roster.tree.insert_column(col, 0)
        roster.columns = roster.columns[:self.renderer_num] + roster.columns[
            self.renderer_num+1:]
        roster.setup_and_draw_roster()

    def presence_received(self, iq_obj):
        if not self.config['show_in_roster']:
            return
        roster = gajim.interface.roster
        contact = gajim.contacts.get_contact_with_highest_priority(
            iq_obj.conn.name, iq_obj.jid)
        if not contact:
            return
        iter_ = roster._get_contact_iter(iq_obj.jid, iq_obj.conn.name, contact,
            roster.model)[0]
        caps = contact.client_caps._node
        if not caps:
            tag = iq_obj.iq_obj.getTags('c')
            if tag:
                caps = tag[0].getAttr('node')
            self.set_icon(roster.model, iter_, self.renderer_num, caps)
            return
        self.set_icon(roster.model, iter_, self.renderer_num, caps)

    def gc_presence_received(self, iq_obj):
        if not self.config['show_in_groupchats']:
            return
        contact = gajim.contacts.get_gc_contact(iq_obj.conn.name,
            iq_obj.presence_obj.jid, iq_obj.nick.decode('utf-8'))
        if not contact:
            return
        caps = None
        tag = iq_obj.iq_obj.getTags('c')
        if tag:
            caps = tag[0].getAttr('node')
        iter_ = iq_obj.gc_control.get_contact_iter(iq_obj.nick.decode('utf-8'))
        model = iq_obj.gc_control.list_treeview.get_model()
        if model[iter_][self.muc_renderer_num] is not None:
            return
        self.set_icon(model, iter_, self.muc_renderer_num, caps)

    def set_icon(self, model, iter_, pos, caps):
        if not caps:
            if self.config['show_unknown_icon']:
                model[iter_][pos] = self.default_pixbuf
            return
        client_icon = clients.get(caps.split('#')[0], None)
        if not client_icon:
            if self.config['show_unknown_icon']:
                model[iter_][pos] = self.default_pixbuf
        else:
            icon_path = os.path.join(self.local_file_path('icons'),
                client_icon)
            pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(icon_path, 16, 16)
            model[iter_][pos] = pixbuf

    def tree_cell_data_func(self, column, renderer, model, iter_, control):
        if not model.iter_parent(iter_):
            renderer.set_property('visible', False)
            return
        renderer.set_property('visible', True)

        contact = gajim.contacts.get_gc_contact(control.account,
            control.room_jid, model[iter_][1].decode('utf-8'))
        if not contact:
            return

        bgcolor = gajim.config.get_per('themes', gajim.config.get(
            'roster_theme'), 'contactbgcolor')
        if bgcolor:
            renderer.set_property('cell-background', bgcolor)
        else:
            renderer.set_property('cell-background', None)
        renderer.set_property('width', 16)

class ClientsIconsPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['vbox1'])
        vbox = self.xml.get_object('vbox1')
        self.child.pack_start(vbox)
        self.xml.connect_signals(self)
        self.connect('hide', self.on_hide)
        self.combo = self.xml.get_object('combobox1')
        self.liststore = gtk.ListStore(str)
        self.combo.set_model(self.liststore)
        cellrenderer = gtk.CellRendererText()
        self.combo.pack_start(cellrenderer, True)
        self.combo.add_attribute(cellrenderer, 'text', 0)

        for item in self.plugin.pos_list:
            self.liststore.append((item,))
        self.combo.set_active(self.plugin.config['pos_in_list'])

    def on_hide(self, widget):
        pass

    def on_run(self):
        self.xml.get_object('show_in_roster').set_active(
            self.plugin.config['show_in_roster'])
        self.xml.get_object('show_in_groupchats').set_active(
            self.plugin.config['show_in_groupchats'])
        self.xml.get_object('show_unknown_icon').set_active(
            self.plugin.config['show_unknown_icon'])

    def on_show_in_roster_toggled(self, widget):
        self.plugin.config['show_in_roster'] = widget.get_active()

    def on_show_in_groupchats_toggled(self, widget):
        self.plugin.config['show_in_groupchats'] = widget.get_active()

    def on_show_unknown_icon_toggled(self, widget):
        self.plugin.config['show_unknown_icon'] = widget.get_active()

    def on_combobox1_changed(self, widget):
        self.plugin.config['pos_in_list'] = widget.get_active()
