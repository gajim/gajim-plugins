# -*- coding: utf-8 -*-
##

import gtk
import os

from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log_calls
from common import ged
from common import gajim
import cell_renderer_image

clients = {
    'http://gajim.org': ['gajim.png', 'Gajim'],
    'http://gajim.org/caps': ['gajim.png', 'Gajim'],
    'http://bombus-im.org/java': ['bombus.png', 'Bombus'],
    'http://bombusmod.net.ru/caps': ['bombusmod.png', 'Bombusmod'],
    'http://psi-dev.googlecode.com/caps': ['psiplus.png', 'Psi+'],
    'http://bombusng-md.googlecode.com': ['bombusng.png', 'Bombus-NG'],
    'http://bombus-im.org/ng': ['bombusng.png', 'Bombus-NG'],
    'http://voffk.org.ru/bombus': ['bombusplus.png', 'Bombus+'],
    'http://bombusng-qd.googlecode.com': ['bombusqd.png', 'Bombus-NG'],
    'http://bombusmod-qd.wen.ru/caps': ['bombusqd.png', 'BombusQD'],
    'http://bombusmod.net.ru': ['bombusmod.png', 'Bombusmod'],
    'http://ex-im.name/caps': ['bombusmod.png', 'Bombusmod'],
    'http://bombusmod.eu,http://bombus.pl': ['bombuspl.png', 'Bombusmod'],
    'http://miranda-im.org/caps': ['miranda.png', 'Miranda'],
    'http://www.asterisk.org/xmpp/client/caps': ['asterisk.png', 'Asterisk'],
    'http://www.google.com/xmpp/client/caps': ['talkonaut.png', 'Talkonaut'],
    'http://talkgadget.google.com/client/caps': ['google.png', 'GTalk'],
    'http://oneteam.im/caps': ['oneteamiphone.png', 'OneTeam'],
    'http://tkabber.jabber.ru/': ['tkabber.png', 'Tkabber'],
    'http://pidgin.im/': ['pidgin.png', 'Pidgin'],
    'http://pidgin.im/caps': ['pidgin.png', 'Pidgin'],
    'http://qutim.org': ['qutim.png', 'QutIM'],
    'http://qutim.org/': ['qutim.png', 'QutIM'],
    'http://exodus.jabberstudio.org/caps': ['exodus.png', 'Exodus'],
    'http://bitlbee.org/xmpp/caps': ['bitlbee.png', 'Bitlbee'],
    'http://coccinella.sourceforge.net/protocol/caps': ['coccinella.png', 'Coccinella'],
    'http://dev.jabbim.cz/jabbim/caps': ['jabbim.png', 'Jabbim'],
    'http://palringo.com/caps': ['palringo.png', 'Palringo'],
    'http://vacuum-im.googlecode.com': ['vacuum.png', 'Vacuum-im'],
    'http://code.google.com/p/vacuum-im/': ['vacuum.png', 'Vacuum-im'],
    'http://jajc.jrudevels.org/caps': ['jajc.png', 'JAJC'],
    'http://gaim.sf.net/caps': ['gaim.png', 'Gaim'],
    'http://mchat.mgslab.com/': ['mchat.png', 'Mchat'],
    'http://online.yandex.ru/caps': ['yaonline.png', 'Yaonline'],
    'http://psi-im.org/caps': ['psi.png', 'Psi'],
    'http://jimm.net.ru/caps': ['jimm-aspro.png', 'Jimm'],
    'http://jabga.ru': ['fin.png', 'Fin jabber'],
    'http://bluendo.com/protocol/caps': ['lampiro.png', 'Lampiro'],
    'nimbuzz:caps': ['nimbuzz.png', 'Nimbuzz'],
    'http://nimbuzz.com/caps': ['nimbuzz.png', 'Nimbuzz'],
    'http://isida.googlecode.com': ['isida-bot.png', 'iSida Jabber Bot'],
    'http://isida-bot.com': ['isida-bot.png', 'iSida Jabber Bot'],
    'http://apps.radio-t.com/caps': ['radio-t.png', 'Radio-t'],
    'http://pda.qip.ru/caps': ['qippda.png', 'Qip-PDA'],
    'http://kopete.kde.org/jabber/caps': ['kopete.png', 'Kopete'],
    'http://www.apple.com/ichat/caps': ['ichat.png', 'IChat'],
    'http://pjc.googlecode.com/caps': ['jubo.png', 'Jubo'],
    'talk.google.com': ['talk.google.com.png', 'GTalk'],
    'http://www.android.com/gtalk/client/caps': ['talk.google.com.png', 'GTalk'],
    'http://swift.im': ['swift.png', 'Swift'],
    'http://fatal-bot.spb.ru/caps': ['bot.png', 'Fatal-bot'],
    'http://svn.posix.ru/fatal-bot/trunk': ['bot.png', 'Fatal-bot'],
    'http://storm-bot.googlecode.com/svn/trunk': ['bot.png', 'Storm-bot'],
    'http://talk.google.com/xmpp/bot/caps': ['google.png', 'GTalk'],
    'http://jabbrik.ru/caps': ['bot.png', 'Jabbrik'],
    'http://jabrvista.net.ru': ['bot.png', 'Jabvista'],
    'http://xu-6.jabbrik.ru/caps': ['bot.png', 'XU-6'],
    'http://jabber.pdg.pl/caps': ['bombus-klub.png', 'Bombus-klub'],
    'http://klub54.wen.ru': ['bombus-klub.png', 'Bombus-klub'],
    'http://aqq.eu/': ['aqq.png', 'Aqq'],
    'http://2010.qip.ru/caps': ['qip.png', 'Qip'],
    'http://qip.ru/caps': ['qip.png', 'Qip'],
    'http://qip.ru/caps?QIP': ['qip.png', 'Qip'],
    'http://glu.net/': ['glu.png', 'Glu'],
    'Siemens': ['siejc.png', 'Siemens'],  # Siemens Native Jabber Client
    'telepathy.': ['telepathy.freedesktop.org.png', 'Telepathy'],
    'http://live.gnome.org/empathy/caps': ['telepathy.freedesktop.org.png', 'Empathy'],
    'http://telepathy.freedesktop.org/caps': ['telepathy.freedesktop.org.png', 'Telepathy'],
    'http://www.adiumx.com/caps': ['adium.png', 'Adium'],
    'http://www.adiumx.com': ['adium.png', 'Adium'],
    'http://juick.com/caps': ['juick.png', 'Juick'],
    'vk.com': ['vkontakte.png', 'Vkontakte'],
    'facebook.com': ['facebook.png', 'Facebook'],
    'http://mail.google.com/xmpp/client/caps': ['google.com.png', 'GMail'],
    'http://snapi-bot.googlecode.com/caps': ['bot.png', 'Snapi-bot'],
    'http://www.barobin.com/caps': ['bayanicq.png', 'Bayanicq'],
    'http://chat.ovi.com/caps': ['ovi-chat.png', 'Ovi-chat'],
    'http://trillian.im/caps': ['trillian.png', 'Trillian'],
    'http://pandion.im/': ['pandion.png', 'Pandion'],
    'http://agent.mail.ru/caps': ['mailruagent.png', 'Mailruagent'],
    'http://agent.mail.ru/': ['mailruagent.png', 'Mailruagent'],
    'http://digsby.com/caps': ['digsby.png', 'Digsby'],
    'http://jabber-net.ru/caps/talisman-bot': ['bot.png', 'Talisman-bot'],
    'http://jabber-net.ru/talisman-bot/caps': ['bot.png', 'Talisman-bot'],
    'http://j-tmb.ru/caps': ['bot.png', 'J-tmb'],
    'http://simpleapps.ru/caps#blacksmith': ['bot.png', 'Blacksmith'],
    'http://blacksmith-2.googlecode.com/svn/': ['bot.png', 'Blacksmith-2'],
    'http://qabber.ru/jame-bot': ['bot.png', 'Jame-bot'],
    'http://chat.freize.org/caps': ['freize.png', 'Freize'],
    'http://pyvk-t.googlecode.com/caps': ['vkontakte.png', 'Vkontakte'],
    'http://pyvk': ['vkontakte.png', 'Vkontakte'],
    'http://pyicq': ['pyicq-t.png', 'PyICQ-t'],
    'http://spectrum.im/transport': ['pyicq-t.png', 'PyICQ-t'],
    'http://pyaim': ['pyaim-t.png', 'PyAIM-t'],
    'http://jabbroid.akuz.de': ['android.png', 'Jabbroid'],
    'http://jabbroid.akuz.de/caps': ['android.png', 'Jabbroid'],
    'http://witcher-team.ucoz.ru/': ['bot.png', 'Witcher'],
    'http://home.gna.org/': ['omnipresence.png', 'Omnipresence'],
    'http://ayttm.souceforge.net/caps': ['ayttm.png', 'Ayttm'],
    'http://www.process-one.net/en/solutions/oneteam_iphone/': \
        ['oneteamiphone.png', 'OneTeam-iphone'],
    'http://qq-im.com/caps': ['qq.png', 'QQ'],
    'http://qq.com/caps': ['qq.png', 'QQ'],
    'http://www.lonelycatgames.com/slick/caps': ['slick.png', 'Slick'],
    'http://sim-im.org/caps': ['sim.png', 'Sim'],
    'http://www.igniterealtime.org/project/spark/caps': ['spark.png', 'Spark'],
    'http://emess.eqx.su/caps': ['emess.png', 'Emess'],
    'http://jappix.org/': ['jappix.png', 'Jappix'],
    'http://japyt.googlecode.com': ['japyt.png', 'Japyt'],
    'http://www.xfire.com/': ['xfire.png', 'Xfire'],
    'http://www.xfire.com/caps': ['xfire.png', 'Xfire'],
    'http://lytgeygen.ru/caps': ['bot.png', 'Lytgeygen'],
    'http://aspro.users.ru/historian-bot/': ['bot.png', 'Historian-bot'],
    'http://pigeon.vpro.ru/caps': ['pigeon.png', 'Pigeon'],
    'http://jtalk.ustyugov.net/caps': ['jtalk.png', 'Jtalk'],
    'psto@psto.net': ['psto.png', 'Psto'],
    'http://jasmineicq.ru/caps': ['jasmine.png', 'Jasmine'],
    'http://tomclaw.com/mandarin_im/caps': ['mandarin.png', 'Mandarin'],
    'http://gabber.sourceforge.net': ['gabber.png', 'Gabber'],
    'http://megafonvolga.ru/': ['megafon.png', 'Megafon'],
    'rss@isida-bot.com': ['osiris.png', 'Osiris'],
    'libpurple': ['libpurple.png', 'Libpurple'],
    'http://www.adium.im/': ['adium.png', 'Adium'],
    'http://eqo.com/': ['libpurple.png', 'Eqo'],
    'http://instantbird.com/': ['instantbird.png', 'Instantbird'],
    'https://www.meebo.com/': ['meebo.png', 'Meebo'],
    'http://opensource.palm.com/packages.html': ['palm.png', 'Palm'],
    'http://spectrum.im/': ['spectrum.png', 'Spectrum'],
    'http://tigase.org/messenger': ['tigase.png', 'Tigase'],
    'http://jitsi.org' :['jitsi.png', 'Jitsi'],
    'http://miranda-ng.org/caps' :['miranda_ng.png', 'Miranda NG'],
    'http://monal.im/caps': ['monal.png', 'Monal'],
    #
    'Poezio' :['poezio.png', 'Poezio'],
    'Emacs' :['emacs.png', ''],
    'mcabber' :['mcabber.png', ''],
    'yaxim' :['yaxim.png', ''],
    'Xabber' :['xabber.png', ''],
}
libpurple_clients ={
    'adium': 'http://www.adium.im/',
    'eqo': 'http://eqo.com/',
    'finch': 'http://pidgin.im/',
    'instantbird': 'http://instantbird.com/',
    'meebo': 'https://www.meebo.com/',
    'palm': 'http://opensource.palm.com/packages.html',
    'pidgin': 'http://pidgin.im/',
    'spectrum': 'http://spectrum.im/',
    'telepathy-haze': 'http://pidgin.im/'
}

class ClientsIconsPlugin(GajimPlugin):

    @log_calls('ClientsIconsPlugin')
    def init(self):
        self.pos_list = [_('after statusicon'), _('before avatar')]
        self.events_handlers = {'caps-presence-received':
                                    (ged.POSTGUI, self.presence_received),
                                'caps-disco-received':
                                    (ged.POSTGUI, self.caps_disco_received), }
        self.gui_extension_points = {
            'groupchat_control': (self.connect_with_groupchat_control,
                                    self.disconnect_from_groupchat_control),
            'roster_draw_contact': (self.connect_with_roster_draw_contact,
                                    self.disconnect_from_roster_draw_contact),
            'roster_tooltip_populate': (self.connect_with_roster_tooltip_populate,
                                    self.disconnect_from_roster_tooltip_populate),
            'gc_tooltip_populate': (self.connect_with_gc_tooltip_populate,
                                    self.disconnect_from_gc_tooltip_populate),}
        self.config_default_values = {
                'show_in_roster': (True, ''),
                'show_in_groupchats': (True, ''),
                'show_in_tooltip': (True, ''),
                'show_unknown_icon': (True, ''),
                'pos_in_list': (0, ''),
                'show_facebook': (True, ''),}

        self.config_dialog = ClientsIconsPluginConfigDialog(self)
        icon_path = os.path.join(self.local_file_path('icons'), 'unknown.png')
        self.default_pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(icon_path,
            16, 16)
        self.icon_cache = {}

    @log_calls('ClientsIconsPlugin')
    def connect_with_gc_tooltip_populate(self, tooltip, contact,
    vcard_table):
        if not self.config['show_in_tooltip']:
            return

        #fill clients table
        self.table = gtk.Table(4, 1)
        self.table.set_property('column-spacing', 2)
        vcard_current_row = vcard_table.get_property('n-rows')

        caps = contact.client_caps._node
        caps_image , client_name = self.get_icon(caps, contact)
        identities = contact.client_caps._lookup_in_cache(
            gajim.caps_cache.capscache).identities
        if identities and client_name == _('Unknown'):
            client_name = identities[0].get('name', _('Unknown'))
        caps_image.set_alignment(0, 0)
        self.table.attach(caps_image, 1, 2, vcard_current_row,
            vcard_current_row + 1, 0, 0, 0, 0)
        label = gtk.Label()
        label.set_alignment(0, 0)
        label.set_markup(client_name)
        self.table.attach(label, 2, 3, vcard_current_row,
            vcard_current_row + 1, 0, 0, 0, 0)
        # set label
        label = gtk.Label()
        label.set_alignment(0, 0)
        label.set_markup(_('Client:'))
        vcard_table.attach(label, 1, 2, vcard_current_row,
            vcard_current_row + 1, gtk.FILL, gtk.FILL, 0, 0)
        # set client table to tooltip
        vcard_table.attach(self.table, 2, 3, vcard_current_row,
            vcard_current_row + 1, gtk.FILL, gtk.FILL, 0, 0)

        # rewrite avatar
        if vcard_table.get_property('n-columns') == 4:
            if tooltip.avatar_image not in vcard_table.get_children():
                return
            avatar_widget_idx = vcard_table.get_children().index(
                tooltip.avatar_image)
            vcard_table.remove(vcard_table.get_children()[avatar_widget_idx])
            vcard_table.attach(tooltip.avatar_image, 3, 4, 2,
                vcard_table.get_property('n-rows'), gtk.FILL,
                    gtk.FILL | gtk.EXPAND, 3, 3)

    @log_calls('ClientsIconsPlugin')
    def connect_with_roster_tooltip_populate(self, tooltip, contacts,
    vcard_table):
        if not self.config['show_in_tooltip']:
            return
        if len(contacts) == 1 and contacts[0].jid in gajim.get_our_jids():
            return
        if contacts[0].is_groupchat():
            return

        # put contacts in dict, where key is priority
        num_resources = 0
        contacts_dict = {}
        for contact in contacts:
            if contact.resource:
                num_resources += 1
                if contact.priority in contacts_dict:
                    contacts_dict[contact.priority].append(contact)
                else:
                    contacts_dict[contact.priority] = [contact]
        contact_keys = sorted(contacts_dict.keys())
        if not contact_keys:
            # contact have not resource
            contacts_dict[0] = [contact]
            contact_keys = sorted(contacts_dict.keys())
        contact_keys.reverse()

        #fill clients table
        self.table = gtk.Table(4, 1)
        self.table.set_property('column-spacing', 2)
        first_place = vcard_current_row = vcard_table.get_property('n-rows')
        vcard_current_row = 0
        for priority in contact_keys:
            for acontact in contacts_dict[priority]:
                caps = acontact.client_caps._node
                caps_image , client_name = self.get_icon(caps, acontact)
                identities = acontact.client_caps._lookup_in_cache(
                    gajim.caps_cache.capscache).identities
                if identities and client_name == _('Unknown'):
                    client_name = identities[0].get('name', _('Unknown'))
                caps_image.set_alignment(0, 0)
                self.table.attach(caps_image, 1, 2, vcard_current_row,
                    vcard_current_row + 1, gtk.FILL, gtk.FILL, 0, 0)
                label = gtk.Label()
                label.set_alignment(0, 0)
                label.set_markup(client_name)
                self.table.attach(label, 2, 3, vcard_current_row,
                    vcard_current_row + 1, gtk.FILL | gtk.EXPAND, 0, 0, 0)
                vcard_current_row += 1
        # set label
        label = gtk.Label()
        label.set_alignment(0, 0)
        if num_resources > 1:
            label.set_markup(_('Clients:'))
        else:
            if contact.show == 'offline':
                return
            label.set_markup(_('Client:'))
        vcard_table.attach(label, 1, 2, first_place,
            first_place + 1, gtk.FILL, gtk.FILL, 0, 0)
        # set clients table to tooltip
        vcard_table.attach(self.table, 2, 3, first_place, first_place + 1,
            gtk.FILL, gtk.FILL, 0, 0)

        # rewrite avatar
        if vcard_table.get_property('n-columns') == 4:
            if tooltip.avatar_image not in vcard_table.get_children():
                return
            avatar_widget_idx = vcard_table.get_children().index(
                tooltip.avatar_image)
            vcard_table.remove(vcard_table.get_children()[avatar_widget_idx])
            vcard_table.attach(tooltip.avatar_image, 4, 5, 2,
                vcard_table.get_property('n-rows'), gtk.FILL,
                    gtk.FILL | gtk.EXPAND, 3, 3)

    def get_icon(self, caps, contact=None):
        if not caps:
            return gtk.image_new_from_pixbuf(self.default_pixbuf), _('Unknown')

        if 'pidgin.im/' in caps:
            caps = 'libpurple'
            for client in libpurple_clients:
                if client in contact.resource.lower():
                    caps = libpurple_clients[client]

        caps_from_jid = self.check_jid(contact.jid)
        if caps_from_jid:
            caps = caps_from_jid

        caps_ = caps.split('#')[0].split()
        if caps_:
            client_icon = clients.get(caps_[0].split()[0], (None,))[0]
            client_name = clients.get(caps_[0].split()[0], ('', _('Unknown')))[1]
        else:
            client_icon = None
        if client_name == _('Unknown'):
            identities = contact.client_caps._lookup_in_cache(
                gajim.caps_cache.capscache).identities
            if identities:
                client_name = identities[0].get('name', _('Unknown'))
                client_icon = clients.get(client_name.split()[0], (None,))[0]

        if not client_icon:
            return gtk.image_new_from_pixbuf(self.default_pixbuf), _('Unknown')
        else:
            icon_path = os.path.join(self.local_file_path('icons'),
                client_icon)
            if icon_path in self.icon_cache:
                return gtk.image_new_from_pixbuf(self.icon_cache[icon_path]), \
                    client_name
            else:
                pb = gtk.gdk.pixbuf_new_from_file_at_size(icon_path, 16, 16)
                self.icon_cache[icon_path] = pb
                return gtk.image_new_from_pixbuf(pb), client_name

    @log_calls('ClientsIconsPlugin')
    def disconnect_from_roster_tooltip_populate(self, tooltip, contacts,
    vcard_table):
        pass

    def check_jid(self, jid):
        caps = None
        if 'facebook.com' in jid and self.config['show_facebook']:
            caps = 'facebook.com'
        elif '@vk.com' in jid and self.config['show_facebook']:
            caps = 'vk.com'
        elif 'juick.com' in jid:
            caps = 'http://juick.com/caps'
        elif jid == 'psto@psto.net':
            caps = 'psto@psto.net'
        elif jid == 'rss@isida-bot.com':
            caps = 'rss@isida-bot.com'
        return caps

    @log_calls('ClientsIconsPlugin')
    def connect_with_roster_draw_contact(self, roster, jid, account, contact):
        if not self.active:
            return
        if not self.config['show_in_roster']:
            return
        child_iters = roster._get_contact_iter(jid, account, contact,
            roster.model)
        if not child_iters:
            return
        for iter_ in child_iters:
            if roster.model[iter_][self.renderer_num] is None:
                caps = contact.client_caps._node
                if not caps:
                    caps = self.check_jid(jid)
                self.set_icon(roster.model, iter_, self.renderer_num,
                    caps, contact)

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
        chat_control.model = gtk.TreeStore(*chat_control.columns)
        chat_control.model.set_sort_func(1, chat_control.tree_compare_iters)
        chat_control.model.set_sort_column_id(1, gtk.SORT_ASCENDING)
        chat_control.list_treeview.set_model(chat_control.model)
        # draw roster
        for nick in gajim.contacts.get_nick_list(chat_control.account,
            chat_control.room_jid):
            gc_contact = gajim.contacts.get_gc_contact(chat_control.account,
                chat_control.room_jid, nick)
            iter_ = chat_control.add_contact_to_roster(nick, gc_contact.show,
                gc_contact.role, gc_contact.affiliation, gc_contact.status,
                gc_contact.jid)
            if not self.config['show_in_groupchats']:
                continue
            caps = gc_contact.client_caps._node
            self.set_icon(chat_control.model, iter_, self.muc_renderer_num,
                caps, gc_contact)
        chat_control.draw_all_roles()
        # Recalculate column width for ellipsizin
        chat_control.list_treeview.columns_autosize()

    @log_calls('ClientsIconsPlugin')
    def disconnect_from_groupchat_control(self, gc_control):
        gc_control.nb_ext_renderers -= 1
        col = gc_control.list_treeview.get_column(0)
        gc_control.list_treeview.remove_column(col)
        col = gtk.TreeViewColumn()
        for renderer in gc_control.renderers_list:
            if renderer[0] == 'client_icon':
                gc_control.renderers_list.remove(renderer)
                break
        gc_control.fill_column(col)
        gc_control.list_treeview.insert_column(col, 0)
        gc_control.columns = gc_control.columns[:self.muc_renderer_num] + \
            gc_control.columns[self.muc_renderer_num + 1:]
        gc_control.model = gtk.TreeStore(*gc_control.columns)
        gc_control.model.set_sort_func(1, gc_control.tree_compare_iters)
        gc_control.model.set_sort_column_id(1, gtk.SORT_ASCENDING)
        gc_control.list_treeview.set_model(gc_control.model)
        gc_control.draw_roster()

    @log_calls('ClientsIconsPlugin')
    def disconnect_from_roster_draw_contact(self, roster, jid, account,
        contact):
        pass

    @log_calls('ClientsIconsPlugin')
    def activate(self):
        self.active = None
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
        self.active = True
        roster.setup_and_draw_roster()

    @log_calls('ClientsIconsPlugin')
    def deactivate(self):
        self.active = None
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
            self.renderer_num + 1:]
        roster.setup_and_draw_roster()

    def caps_disco_received(self, iq_obj):
        roster = gajim.interface.roster
        contact = gajim.contacts.get_contact_from_full_jid(iq_obj.conn.name,
            iq_obj.jid)
        if contact is None:
            room_jid, nick = gajim.get_room_and_nick_from_fjid(iq_obj.fjid)
            contact = gajim.contacts.get_gc_contact(iq_obj.conn.name, room_jid,
                nick)
            if contact:
                gc_control = gajim.interface.msg_win_mgr.get_gc_control(
                    iq_obj.jid, iq_obj.conn.name)
                iter_ = gc_control.get_contact_iter(nick)
                self.set_icon(gc_control.model, iter_, self.muc_renderer_num,
                    None, contact)
                return
        if not contact:
            return
        child_iters = roster._get_contact_iter(iq_obj.jid, iq_obj.conn.name,
            contact, roster.model)
        if not child_iters:
            return
        for iter_ in child_iters:
            caps = contact.client_caps._node
            caps_ = self.check_jid(iq_obj.jid)
            if caps_:
                caps = caps_
            self.set_icon(roster.model, iter_, self.renderer_num,
                caps, contact)

    def presence_received(self, iq_obj):
        roster = gajim.interface.roster
        contact = gajim.contacts.get_contact_from_full_jid(iq_obj.conn.name,
            iq_obj.jid)
        if contact is None:
            room_jid, nick = gajim.get_room_and_nick_from_fjid(iq_obj.fjid)
            contact = gajim.contacts.get_gc_contact(iq_obj.conn.name, room_jid,
                nick)
            if contact:
                self.gc_presence_received(iq_obj, contact)
                return
        if not contact:
            return

        if not self.config['show_in_roster']:
            return
        contact = gajim.contacts.get_contact_with_highest_priority(
            iq_obj.conn.name, iq_obj.jid)

        if iq_obj.resource == 'local':
            # zeroconf
            return

        iters = roster._get_contact_iter(iq_obj.jid, iq_obj.conn.name, contact,
            roster.model)
        iter_ = iters[0]

        if contact.show == 'error':
            self.set_icon(roster.model, iter_, self.renderer_num, None, contact)
            return

        if contact.get_full_jid() != iq_obj.fjid:
            # higest contact changed
            if roster.model[iter_][self.renderer_num] is not None:
                caps = contact.client_caps._node
                if caps:
                    self.set_icon(roster.model, iter_, self.renderer_num,
                        caps, contact)
                    return
        caps = None
        tag = iq_obj.stanza.getTags('c')
        if tag:
            caps = tag[0].getAttr('node')
            if caps:
                if 'pidgin.im/' in caps:
                    caps = 'libpurple'
                    for client in libpurple_clients:
                        if client in contact.resource.lower():
                            caps = libpurple_clients[client]

        caps_from_jid = self.check_jid(iq_obj.jid)
        if caps_from_jid:
            caps = caps_from_jid

        for iter_ in iters:
            self.set_icon(roster.model, iter_, self.renderer_num, caps, contact)

    def gc_presence_received(self, iq_obj, contact):
        if not self.config['show_in_groupchats']:
            return

        caps = None
        tag = iq_obj.stanza.getTags('c')
        if tag:
            caps = tag[0].getAttr('node')
            if 'pidgin.im/' in caps:
                caps = 'libpurple'

        gc_control = gajim.interface.msg_win_mgr.get_gc_control(iq_obj.jid,
            iq_obj.conn.name)
        iter_ = gc_control.get_contact_iter(iq_obj.resource.decode('utf-8'))
        model = gc_control.model
        if model[iter_][self.muc_renderer_num] is not None:
            return
        self.set_icon(model, iter_, self.muc_renderer_num, caps, contact)

    def set_icon(self, model, iter_, pos, caps, contact):
        if caps:
            caps_ = caps.split('#')[0].split()
            if caps_:
                client_icon = clients.get(caps_[0].split()[0], (None,))[0]
        else:
            client_icon = None

        if not client_icon:
            identities = contact.client_caps._lookup_in_cache(
                gajim.caps_cache.capscache).identities
            if identities:
                client_name = identities[0].get('name', _('Unknown'))
                client_icon = clients.get(client_name.split()[0], (None,))[0]

        if not client_icon:
            if self.config['show_unknown_icon']:
                model[iter_][pos] = self.default_pixbuf
        else:
            icon_path = os.path.join(self.local_file_path('icons'),
                client_icon)
            if icon_path in self.icon_cache:
                model[iter_][pos] = self.icon_cache[icon_path]
            else:
                pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(icon_path, 16, 16)
                model[iter_][pos] = pixbuf
                self.icon_cache[icon_path] = pixbuf

    def tree_cell_data_func(self, column, renderer, model, iter_, control):
        if not model.iter_parent(iter_):
            renderer.set_property('visible', False)
            return
        elif model[iter_][self.muc_renderer_num]:
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

    @log_calls('ClientsIconsPlugin')
    def disconnect_from_gc_tooltip_populate(self, tooltip, contact,
    vcard_table):
        pass


class ClientsIconsPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
                ['vbox1'])
        vbox = self.xml.get_object('vbox1')
        self.child.pack_start(vbox)
        self.combo = self.xml.get_object('combobox1')
        self.liststore = gtk.ListStore(str)
        self.combo.set_model(self.liststore)
        cellrenderer = gtk.CellRendererText()
        self.combo.pack_start(cellrenderer, True)
        self.combo.add_attribute(cellrenderer, 'text', 0)

        for item in self.plugin.pos_list:
            self.liststore.append((item,))
        self.combo.set_active(self.plugin.config['pos_in_list'])

        self.xml.get_object('show_in_roster').set_active(
            self.plugin.config['show_in_roster'])
        self.xml.get_object('show_in_groupchats').set_active(
            self.plugin.config['show_in_groupchats'])
        self.xml.get_object('show_unknown_icon').set_active(
            self.plugin.config['show_unknown_icon'])
        self.xml.get_object('show_facebook').set_active(
            self.plugin.config['show_facebook'])
        self.xml.get_object('show_in_tooltip').set_active(
            self.plugin.config['show_in_tooltip'])

        self.xml.connect_signals(self)

    def redraw_all(self):
        self.plugin.deactivate()
        self.plugin.activate()
        for gc_control in gajim.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.disconnect_from_groupchat_control(gc_control)
        for gc_control in gajim.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.connect_with_groupchat_control(gc_control)

    def on_show_in_roster_toggled(self, widget):
        self.plugin.config['show_in_roster'] = widget.get_active()
        self.plugin.deactivate()
        self.plugin.activate()

    def on_show_in_tooltip_toggled(self, widget):
        self.plugin.config['show_in_tooltip'] = widget.get_active()

    def on_show_in_groupchats_toggled(self, widget):
        self.plugin.config['show_in_groupchats'] = widget.get_active()
        for gc_control in gajim.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.disconnect_from_groupchat_control(gc_control)
        for gc_control in gajim.interface.msg_win_mgr.get_controls('gc'):
            self.plugin.connect_with_groupchat_control(gc_control)

    def on_show_unknown_icon_toggled(self, widget):
        self.plugin.config['show_unknown_icon'] = widget.get_active()
        self.redraw_all()

    def on_show_facebook_toggled(self, widget):
        self.plugin.config['show_facebook'] = widget.get_active()
        self.redraw_all()

    def on_combobox1_changed(self, widget):
        self.plugin.config['pos_in_list'] = widget.get_active()
        self.redraw_all()
