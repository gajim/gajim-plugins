# -*- coding: utf-8 -*-
##
import database
import gtk
import os
import base64
import urllib2
from plugins import GajimPlugin
from plugins.helpers import log_calls
import gui_menu_builder
import gtkgui_helpers
from common import gajim
from fileshare_window import FileShareWindow
import fshare_protocol
from common import ged
from common import caps_cache
from common import xmpp
from plugins.gui import GajimPluginConfigDialog


class FileSharePlugin(GajimPlugin):

    filesharewindow = {}
    prohandler = {}

    @log_calls('FileSharePlugin')
    def init(self):
        self.activated = False
        self.config_dialog = FileSharePluginConfigDialog(self)
        home_path = os.path.expanduser('~/')
        self.config_default_values = {'incoming_dir': (home_path, '')}
        self.database = database.FilesharingDatabase(self.config.FILE_PATH)
        # Create one protocol handler per account
        accounts = gajim.contacts.get_accounts()
        for account in gajim.contacts.get_accounts():
            FileSharePlugin.prohandler[account] = \
                fshare_protocol.Protocol(account, self)
        self.events_handlers = {
            'raw-iq-received': (ged.CORE, self._nec_raw_iq)
            }

    def activate(self):
        self.activated = True
        # Add fs feature
        if fshare_protocol.NS_FILE_SHARING not in gajim.gajim_common_features:
            gajim.gajim_common_features.append(fshare_protocol.NS_FILE_SHARING)
        self._compute_caps_hash()
        # Replace the contact menu
        self.__get_contact_menu = gui_menu_builder.get_contact_menu
        gui_menu_builder.get_contact_menu = self.contact_menu
        # Replace get_file_info
        for account in gajim.contacts.get_accounts():
            conn = gajim.connections[account]
            self._get_file_info = conn.get_file_info
            conn.get_file_info = self.get_file_info

    def deactivate(self):
        self.activated = False
        # Remove fs feature
        if fshare_protocol.NS_FILE_SHARING not in gajim.gajim_common_features:
            gajim.gajim_common_features.remove(fshare_protocol.NS_FILE_SHARING)
        self._compute_caps_hash()
        # Restore the contact menu
        gui_menu_builder.get_contact_menu = self.__get_contact_menu
        # Restore get_file_info
        for account in gajim.contacts.get_accounts():
            conn = gajim.connections[account]
            conn.get_file_info = self._get_file_info

    def _compute_caps_hash(self):
        for a in gajim.connections:
            gajim.caps_hash[a] = caps_cache.compute_caps_hash([
                gajim.gajim_identity], gajim.gajim_common_features + \
                gajim.gajim_optional_features[a])
            # re-send presence with new hash
            connected = gajim.connections[a].connected
            if connected > 1 and gajim.SHOW_LIST[connected] != 'invisible':
                gajim.connections[a].change_status(gajim.SHOW_LIST[connected],
                    gajim.connections[a].status)

    def _nec_raw_iq(self, obj):
        if obj.stanza.getTag('match',
                namespace=fshare_protocol.NS_FILE_SHARING) and self.activated:
            account = obj.conn.name
            pro = FileSharePlugin.prohandler[account]
            pro.handler(obj.stanza)
            raise xmpp.NodeProcessed

    def __get_contact_menu(self, contact, account):
        raise NotImplementedError

    def contact_menu(self, contact, account):
        menu = self.__get_contact_menu(contact, account)
        fs = gtk.MenuItem('File sharing')
        submenu = gtk.Menu()
        fs.set_submenu(submenu)
        bf = gtk.MenuItem('Browse files')
        bf.connect('activate', self.browse_menu_clicked, account, contact)
        msf = gtk.MenuItem('Manage shared files')
        msf.connect('activate', self.manage_menu_clicked, account, contact)
        enable_fs = gtk.CheckMenuItem('Enable file sharing')
        enable_fs.set_active(True)
        submenu.attach(bf, 0, 1, 0, 1)
        submenu.attach(msf, 0, 1, 1, 2)
        submenu.attach(enable_fs, 0, 1, 2, 3)
        if gajim.account_is_disconnected(account) or \
        contact.show in ('offline', 'error') or not \
        contact.supports(fshare_protocol.NS_FILE_SHARING):
            bf.set_sensitive(False)
        submenu.show()
        bf.show()
        msf.show()
        enable_fs.show()
        fs.show()
        menu.attach(fs, 0, 1, 3, 4)
        return menu

    def _get_file_info(self, peerjid, hash_=None, name=None, account=None):
        raise NotImplementedError

    def get_file_info(self, peerjid, hash_=None, name=None, account=None):
        file_info = self._get_file_info(hash_, name)
        if file_info:
            return file_info
        raw_info = self.database.get_file(account, peerjid, hash_, name)
        file_info = {'name': raw_info[0],
                     'file-name' : raw_info[5],
                     'hash' : raw_info[1],
                     'size' : raw_info[2],
                     'date' : raw_info[4],
                     'peerjid' : peerjid
                    }

        return file_info

    def __get_fsw_instance(self, account):
        # Makes sure we only have one instance of the window per account
        if account not in FileSharePlugin.filesharewindow:
            FileSharePlugin.filesharewindow[account] = fsw = FileShareWindow(
                self)
            FileSharePlugin.prohandler[account].set_window(fsw)
        return FileSharePlugin.filesharewindow[account]

    def __init_window(self, account, contact):
        fsw = self.__get_fsw_instance(account)
        fsw.set_account(account)
        fsw.contacts_rows = []
        fsw.ts_contacts.clear()
        fsw.ts_search.clear()
        # Add information to widgets
        fsw.add_contact_manage(contact)
        fsw.add_contact_browse(contact)
        return fsw

    def manage_menu_clicked(self, widget, account, contact):
        fsw = self.__init_window(account, contact)
        fsw.notebook.set_current_page(1)

    def browse_menu_clicked(self, widget, account, contact):
        fsw = self.__init_window(account, contact)
        fsw.notebook.set_current_page(0)

class FileSharePluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['hbox111'])
        hbox = self.xml.get_object('hbox111')
        self.child.pack_start(hbox)
        self.connect('hide', self.on_hide)

    def on_run(self):
        widget = self.xml.get_object('dl_folder')
        widget.set_text(str(self.plugin.config['incoming_dir']))

    def on_hide(self, widget):
        widget = self.xml.get_object('dl_folder')
        self.plugin.config['incoming_dir'] = widget.get_text()
