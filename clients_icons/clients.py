# This file is part of Gajim.
#
# Gajim is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

from collections import UserDict
from collections import namedtuple

from gajim.plugins.plugins_i18n import _

ClientData = namedtuple('ClientData', ['default', 'variations'])
ClientData.__new__.__defaults__ = (None,)


def get_variations(client_name):
    # get_variations('Conversation Legacy 1.2.3')
    #
    # Returns List:
    # [Conversation Legacy 1.2.3,
    #  Conversation Legacy
    #  Conversation]
    if client_name is None:
        return []
    alts = client_name.split()
    alts = [" ".join(alts[:(i + 1)]) for i in range(len(alts))]
    alts.reverse()
    return alts


class ClientsDict(UserDict):
    def get_client_data(self, name, node):
        client_data = self.get(node)
        if client_data is None:
            return _('Unknown'), 'xmpp-client-unknown'

        if client_data.variations is None:
            client_name, icon_name = client_data.default
            return client_name, 'xmpp-client-%s' % icon_name

        variations = get_variations(name)
        for var in variations:
            try:
                return var, 'xmpp-client-%s' % client_data.variations[var]
            except KeyError:
                pass
        client_name, icon_name = client_data.default
        return client_name, 'xmpp-client-%s' % icon_name


# ClientData(
#   default=(Shown name, icon name)
#   variations={Shown name, icon name}
# )

CLIENTS = ClientsDict({
    'http://gajim.org': ClientData(('Gajim', 'gajim')),
    'https://gajim.org': ClientData(('Gajim', 'gajim')),
    'http://conversations.im': ClientData(
        default=('Conversations', 'conversations'),
        variations={'Conversations Legacy': 'conversations-legacy'}
    ),
    'http://jabber.pix-art.de': ClientData(('Pix-Art Messenger', 'pixart')),
    'http://blabber.im': ClientData(('blabber.im', 'blabber')),
    'http://monocles.de': ClientData(('monocles chat', 'monocles-chat')),
    'http://pidgin.im/': ClientData(('Pidgin', 'pidgin')),
    'https://poez.io': ClientData(('Poezio', 'poezio')),
    'https://yaxim.org/': ClientData(('yaxim', 'yaxim')),
    'https://yaxim.org/bruno/': ClientData(('Bruno', 'bruno')),
    'http://mcabber.com/caps': ClientData(('MCabber', 'mcabber')),
    'http://psi-plus.com': ClientData(('Psi+', 'psiplus')),
    'https://psi-plus.com': ClientData(('Psi+', 'psiplus')),
    'https://dino.im': ClientData(('Dino', 'dino')),
    'http://monal.im/': ClientData(('Monal', 'monal')),
    'http://slixmpp.com/ver/1.2.4': ClientData(('Bot', 'bot')),
    'http://slixmpp.com/ver/1.3.0': ClientData(('Bot', 'bot')),
    'https://www.xabber.com/': ClientData(('Xabber', 'xabber')),
    'http://www.profanity.im': ClientData(('Profanity', 'profanity')),
    'http://swift.im': ClientData(('Swift', 'swift')),
    'https://salut-a-toi.org': ClientData(('Salut à Toi', 'sat')),
    'https://conversejs.org': ClientData(('Converse', 'conversejs')),
    'http://bitlbee.org/xmpp/caps': ClientData(('BitlBee', 'bitlbee')),
    'http://tkabber.jabber.ru/': ClientData(('Tkabber', 'tkabber')),
    'http://miranda-ng.org/caps': ClientData(('Miranda NG', 'miranda_ng')),
    'http://www.adium.im/': ClientData(('Adium', 'adium')),
    'http://www.adiumx.com/caps': ClientData(('Adium', 'adium')),
    'http://www.adiumx.com': ClientData(('Adium', 'adium')),
    'http://aqq.eu/': ClientData(('Aqq', 'aqq')),
    'http://www.asterisk.org/xmpp/client/caps': ClientData(('Asterisk', 'asterisk')),
    'http://ayttm.souceforge.net/caps': ClientData(('Ayttm', 'ayttm')),
    'http://www.barobin.com/caps': ClientData(('Bayanicq', 'bayanicq')),
    'http://simpleapps.ru/caps#blacksmith': ClientData(('Blacksmith', 'bot')),
    'http://blacksmith-2.googlecode.com/svn/': ClientData(('Blacksmith-2', 'bot')),
    'http://coccinella.sourceforge.net/protocol/caps': ClientData(('Coccinella', 'coccinella')),
    'http://digsby.com/caps': ClientData(('Digsby', 'digsby')),
    'http://emacs-jabber.sourceforge.net': ClientData(('Emacs Jabber Client', 'emacs')),
    'http://emess.eqx.su/caps': ClientData(('Emess', 'emess')),
    'http://live.gnome.org/empathy/caps': ClientData(('Empathy', 'telepathy.freedesktop.org')),
    'http://eqo.com/': ClientData(('Eqo', 'libpurple')),
    'http://exodus.jabberstudio.org/caps': ClientData(('Exodus', 'exodus')),
    'http://fatal-bot.spb.ru/caps': ClientData(('Fatal-bot', 'bot')),
    'http://svn.posix.ru/fatal-bot/trunk': ClientData(('Fatal-bot', 'bot')),
    'http://isida.googlecode.com': ClientData(('Isida', 'isida-bot')),
    'http://isida-bot.com': ClientData(('Isida', 'isida-bot')),
    'http://jabga.ru': ClientData(('Fin jabber', 'fin')),
    'http://chat.freize.org/caps': ClientData(('Freize', 'freize')),
    'http://gabber.sourceforge.net': ClientData(('Gabber', 'gabber')),
    'http://glu.net/': ClientData(('Glu', 'glu')),
    'http://mail.google.com/xmpp/client/caps': ClientData(('GMail', 'google.com')),
    'http://www.android.com/gtalk/client/caps': ClientData(('GTalk', 'talk.google.com')),
    'talk.google.com': ClientData(('GTalk', 'talk.google.com')),
    'http://talkgadget.google.com/client/caps': ClientData(('GTalk', 'google')),
    'http://talk.google.com/xmpp/bot/caps': ClientData(('GTalk', 'google')),
    'http://aspro.users.ru/historian-bot/': ClientData(('Historian-bot', 'bot')),
    'http://www.apple.com/ichat/caps': ClientData(('IChat', 'ichat')),
    'http://instantbird.com/': ClientData(('Instantbird', 'instantbird')),
    'http://j-tmb.ru/caps': ClientData(('J-tmb', 'bot')),
    'http://jabbroid.akuz.de': ClientData(('Jabbroid', 'android')),
    'http://jabbroid.akuz.de/caps': ClientData(('Jabbroid', 'android')),
    'http://dev.jabbim.cz/jabbim/caps': ClientData(('Jabbim', 'jabbim')),
    'http://jabbrik.ru/caps': ClientData(('Jabbrik', 'bot')),
    'http://jabrvista.net.ru': ClientData(('Jabvista', 'bot')),
    'http://jajc.jrudevels.org/caps': ClientData(('JAJC', 'jajc')),
    'http://qabber.ru/jame-bot': ClientData(('Jame-bot', 'bot')),
    'https://www.jappix.com/': ClientData(('Jappix', 'jappix')),
    'http://japyt.googlecode.com': ClientData(('Japyt', 'japyt')),
    'http://jasmineicq.ru/caps': ClientData(('Jasmine', 'jasmine')),
    'http://jimm.net.ru/caps': ClientData(('Jimm', 'jimm-aspro')),
    'http://jitsi.org': ClientData(('Jitsi', 'jitsi')),
    'http://jtalk.ustyugov.net/caps': ClientData(('Jtalk', 'jtalk')),
    'http://pjc.googlecode.com/caps': ClientData(('Jubo', 'jubo')),
    'http://juick.com/caps': ClientData(('Juick', 'juick')),
    'http://kopete.kde.org/jabber/caps': ClientData(('Kopete', 'kopete')),
    'http://bluendo.com/protocol/caps': ClientData(('Lampiro', 'lampiro')),
    'http://lytgeygen.ru/caps': ClientData(('Lytgeygen', 'bot')),
    'http://agent.mail.ru/caps': ClientData(('Mailruagent', 'mailruagent')),
    'http://agent.mail.ru/': ClientData(('Mailruagent', 'mailruagent')),
    'http://tomclaw.com/mandarin_im/caps': ClientData(('Mandarin', 'mandarin')),
    'http://mchat.mgslab.com/': ClientData(('Mchat', 'mchat')),
    'https://www.meebo.com/': ClientData(('Meebo', 'meebo')),
    'http://megafonvolga.ru/': ClientData(('Megafon', 'megafon')),
    'http://miranda-im.org/caps': ClientData(('Miranda', 'miranda')),
    'https://movim.eu/': ClientData(('Movim', 'movim')),
    'http://moxl.movim.eu/': ClientData(('Movim', 'movim')),
    'nimbuzz:caps': ClientData(('Nimbuzz', 'nimbuzz')),
    'http://nimbuzz.com/caps': ClientData(('Nimbuzz', 'nimbuzz')),
    'http://home.gna.org/': ClientData(('Omnipresence', 'omnipresence')),
    'http://oneteam.im/caps': ClientData(('OneTeam', 'oneteamiphone')),
    'http://www.process-one.net/en/solutions/oneteam_iphone/': ClientData(('OneTeam-IPhone', 'oneteamiphone')),
    'rss@isida-bot.com': ClientData(('Osiris', 'osiris')),
    'http://chat.ovi.com/caps': ClientData(('Ovi-chat', 'ovi-chat')),
    'http://opensource.palm.com/packages.html': ClientData(('Palm', 'palm')),
    'http://palringo.com/caps': ClientData(('Palringo', 'palringo')),
    'http://pandion.im/': ClientData(('Pandion', 'pandion')),
    'http://pigeon.vpro.ru/caps': ClientData(('Pigeon', 'pigeon')),
    'psto@psto.net': ClientData(('Psto', 'psto')),
    'http://qq-im.com/caps': ClientData(('QQ', 'qq')),
    'http://qq.com/caps': ClientData(('QQ', 'qq')),
    'http://2010.qip.ru/caps': ClientData(('Qip', 'qip')),
    'http://qip.ru/caps': ClientData(('Qip', 'qip')),
    'http://qip.ru/caps?QIP': ClientData(('Qip', 'qip')),
    'http://pda.qip.ru/caps': ClientData(('Qip-PDA', 'qippda')),
    'http://qutim.org': ClientData(('QutIM', 'qutim')),
    'http://qutim.org/': ClientData(('QutIM', 'qutim')),
    'http://apps.radio-t.com/caps': ClientData(('Radio-t', 'radio-t')),
    'http://sim-im.org/caps': ClientData(('Sim', 'sim')),
    'http://www.lonelycatgames.com/slick/caps': ClientData(('Slick', 'slick')),
    'http://snapi-bot.googlecode.com/caps': ClientData(('Snapi-bot', 'bot')),
    'http://www.igniterealtime.org/project/spark/caps': ClientData(('Spark', 'spark')),
    'http://spectrum.im/': ClientData(('Spectrum', 'spectrum')),
    'http://storm-bot.googlecode.com/svn/trunk': ClientData(('Storm-bot', 'bot')),
    'http://jabber-net.ru/caps/talisman-bot': ClientData(('Talisman-bot', 'bot')),
    'http://jabber-net.ru/talisman-bot/caps': ClientData(('Talisman-bot', 'bot')),
    'http://www.google.com/xmpp/client/caps': ClientData(('Talkonaut', 'talkonaut')),
    'http://telepathy.freedesktop.org/caps': ClientData(('SlicTelepathyk', 'telepathy.freedesktop.org')),
    'http://tigase.org/messenger': ClientData(('Tigase', 'tigase')),
    'http://trillian.im/caps': ClientData(('Trillian', 'trillian')),
    'http://vacuum-im.googlecode.com': ClientData(('Vacuum', 'vacuum')),
    'http://code.google.com/p/vacuum-im/': ClientData(('Vacuum', 'vacuum')),
    'http://witcher-team.ucoz.ru/': ClientData(('Witcher', 'bot')),
    'http://online.yandex.ru/caps': ClientData(('Yaonline', 'yaonline')),
    'http://www.igniterealtime.org/projects/smack/': ClientData(('Xabber', 'xabber')),
    'http://www.xfire.com/': ClientData(('Xfire', 'xfire')),
    'http://www.xfire.com/caps': ClientData(('Xfire', 'xfire')),
    'http://xu-6.jabbrik.ru/caps': ClientData(('XU-6', 'bot')),
})


def get_data(*args):
    return CLIENTS.get_client_data(*args)
