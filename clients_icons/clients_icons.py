# -*- coding: utf-8 -*-
##

import gtk
import os

#from plugins.gui import GajimPluginConfigDialog
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from common import ged
from common import gajim
import cell_renderer_image

clients = {
    'http://gajim.org': 'gajim.png',
    'http://bombus-im.org/java': 'bombus.png',
    'http://bombusmod.net.ru/caps': 'bombusmod.png',
    'http://psi-dev.googlecode.com/caps': 'psiplus.png',
    'http://bombusng-md.googlecode.com': 'bombusng.png',
    'http://mcabber.com/caps': 'mcabber.png',
    'http://miranda-im.org/caps': 'miranda.png',
    'http://www.asterisk.org/xmpp/client/caps': 'asterisk.png',
    'http://www.google.com/xmpp/client/caps': 'talkonaut.png',
    'http://oneteam.im/caps': 'oneteamiphone.png',
    'http://bombus-im.org/ng': 'bombusng.png',
    'http://voffk.org.ru/bombus': 'bombusplus.png',
    'http://bombusng-qd.googlecode.com': 'bombusqd.png',
    'http://tkabber.jabber.ru/': 'tkabber.png',
    'http://qip.ru/caps': 'qipinfium.png',
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
    'http://bombusmod-qd.wen.ru/caps': 'bombusqd.png',
    'http://bombusmod.net.ru': 'bombusmod.png',
    'http://ex-im.name/caps': 'bombusmod.png',
    'http://psi-im.org/caps': 'psi.png',
    'http://jimm.net.ru/caps': 'jimm-aspro.png',
    'http://bluendo.com/protocol/caps': 'lampiro.png',
    'nimbuzz:caps': 'nimbuzz.png',
    'http://bombusmod.eu,http://bombus.pl': 'bombuspl.png',
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
    'http://jabbrik.ru/caps': 'bot.png',#Utah Jabber Bot
    'http://jabrvista.net.ru': 'bot.png',#Utah Jabber Bot
    'http://xu-6.jabbrik.ru/caps': 'bot.png',#XU-6 Bot
    'http://jabber.pdg.pl/caps': 'bombus-klub.png',
    'http://klub54.wen.ru': 'bombus-klub.png',#BombusKlub
    'http://aqq.eu/': 'aqq.png',
    'http://2010.qip.ru/caps': 'qipinfium.png',#QIP 2010
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
        self.config_dialog = None#ClientsIconsPluginConfigDialog(self)
        self.events_handlers = {'CAPS_RECEIVED':
                                        (ged.POSTCORE, self.caps_received),
                                'presence-received':
                                        (ged.POSTCORE, self.presence_received),}

    @log_calls('ClientsIconsPlugin')
    def activate(self):
        roster = gajim.interface.roster
        col = gtk.TreeViewColumn()
        roster.nb_ext_renderers += 1
        self.renderer_num = 10 + roster.nb_ext_renderers
        client_icon_rend = ('client_icon', gtk.CellRendererPixbuf(), False,
                'pixbuf', self.renderer_num,
                roster._fill_pep_pixbuf_renderer, self.renderer_num)
        # remove old column
        roster.tree.remove_column(roster.tree.get_column(0))
        # add new renderer in renderers list after location pixbuf renderer
        for renderer in roster.renderers_list:
            if renderer[0] == 'location':
                break
        num = roster.renderers_list.index(renderer)
        roster.renderers_list.insert(num+1, client_icon_rend)
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
        roster.columns.remove(roster.columns[self.renderer_num])
        roster.setup_and_draw_roster()

    def caps_received(self, account, data):
        roster = gajim.interface.roster
        jid = data[0].split('/')[0]
        for account in gajim.contacts.get_accounts():
            contact = gajim.contacts.get_contact_with_highest_priority(
                    account, jid)
            if not contact:
                continue
            caps = contact.client_caps._node
            if not caps:
                continue
            client_icon = clients.get(caps.split('#')[0], None)
            if not client_icon:
                continue
            icon_path = os.path.join(self.local_file_path('icons'), client_icon)
            pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(icon_path, 16, 16)
            iter_ = roster._get_contact_iter(jid, account, contact,
                    roster.model)[0]
            roster.model[iter_][self.renderer_num] = pixbuf

    def presence_received(self, iq_obj):
        if iq_obj.new_show == 0:
            self.caps_received(iq_obj.conn.name, [iq_obj.fjid])
