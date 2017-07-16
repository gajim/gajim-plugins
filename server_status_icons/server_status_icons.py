# -*- coding: utf-8 -*-
##
import os

from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim import gtkgui_helpers
from gajim.common import app
from gajim.common import helpers
from gajim.common import ged


class ServerStatusIconsPlugin(GajimPlugin):

    @log_calls('ServerStatusIconsPlugin')
    def init(self):
        self.description = _('Replace standard Gajim status icons with server'
            ' specific for known XMPP server accounts (vk.com, ...)')
        self.pos_list = [_('after statusicon'), _('before avatar')]
        self.gui_extension_points = {
            'roster_draw_contact': (self.connect_with_roster_draw_contact,
                                    self.disconnect_from_roster_draw_contact)}
        self.known_servers = {'chat.facebook.com': 'facebook',
                              'gmail.com': 'gtalk',
                              'livejournal.com': 'livejournal',
                              'odnoklassniki.ru': 'odnoklassniki',
                              'vk.com': 'vkontakte',
                              'ya.ru': 'yaonline'}
        self.config_dialog = None

    @log_calls('ServerStatusIconsPlugin')
    def connect_with_roster_draw_contact(self, roster, jid, account, contact):
        if not self.active:
            return
        if app.jid_is_transport(jid):
            return

        child_iters = roster._get_contact_iter(jid, account, contact,
            roster.model)
        if not child_iters:
            return

        icon_name = helpers.get_icon_name_to_show(contact, account)
        if app.events.get_events(account, jid) or icon_name == 'requested':
            return

        host = jid.split('@')[1]
        server = self.known_servers.get(host, False)
        if not server:
            return

        if server not in roster.transports_state_images['16']:
            # we don't have iconset for this transport loaded yet. Let's do it
            self.make_transport_state_images(roster, server)
        if server in roster.transports_state_images['16'] and \
            icon_name in roster.transports_state_images['16'][server]:
            state_images = roster.transports_state_images['16'][server]
            img = state_images[icon_name]
            for child_iter in child_iters:
                roster.model[child_iter][0] = img

    def make_transport_state_images(self, roster, transport):
        """
        Initialize opened and closed 'transport' iconset dict
        """

        folder = os.path.join(self.local_file_path(transport), '16x16')
        pixo, pixc = gtkgui_helpers.load_icons_meta()
        roster.transports_state_images['opened'][transport] = \
            gtkgui_helpers.load_iconset(folder, pixo, transport=True)
        roster.transports_state_images['closed'][transport] = \
            gtkgui_helpers.load_iconset(folder, pixc, transport=True)
        roster.transports_state_images['16'][transport] = \
            gtkgui_helpers.load_iconset(folder, transport=True)
        folder = os.path.join(self.local_file_path(transport), '32x32')
        roster.transports_state_images['32'][transport] = \
            gtkgui_helpers.load_iconset(folder, transport=True)

    def _nec_our_show(self, obj):
        account = obj.conn.name
        roster = app.interface.roster
        status = app.connections[account].connected

        if account not in app.contacts.get_accounts():
            return
        child_iterA = roster._get_account_iter(account, roster.model)
        if not child_iterA:
            return

        hostname = app.config.get_per('accounts', account, 'hostname')
        server = self.known_servers.get(hostname, False)
        if not server:
            return

        if not roster.regroup:
            show = app.SHOW_LIST[status]
        else: # accounts merged
            show = helpers.get_global_show()

        if server not in roster.transports_state_images['16']:
            # we don't have iconset for this transport loaded yet. Let's do it
            self.make_transport_state_images(roster, server)
        if server in roster.transports_state_images['16'] and \
            show in roster.transports_state_images['16'][server]:
            roster.model[child_iterA][0] = roster.transports_state_images[
                '16'][server][show]

    @log_calls('ServerStatusIconsPlugin')
    def disconnect_from_roster_draw_contact(self, roster, jid, account,
        contact):
        pass

    @log_calls('ServerStatusIconsPlugin')
    def activate(self):
        self.active = True
        app.interface.roster.setup_and_draw_roster()
        app.ged.register_event_handler('our-show', ged.GUI2,
            self._nec_our_show)

    @log_calls('ServerStatusIconsPlugin')
    def deactivate(self):
        self.active = None
        app.ged.remove_event_handler('our-show', ged.GUI2,
            self._nec_our_show)
        app.interface.roster.setup_and_draw_roster()
