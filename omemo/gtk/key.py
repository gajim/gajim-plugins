# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of OMEMO Gajim Plugin.
#
# OMEMO Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import os
import time
import locale
import logging
import tempfile
from packaging.version import Version as V

from pkg_resources import get_distribution
from gi.repository import Gtk
from gi.repository import GdkPixbuf

from gajim.common import app
from gajim.plugins.plugins_i18n import _
from gajim.plugins.helpers import get_builder
from gajim.gui.dialogs import ConfirmationDialog
from gajim.gui.dialogs import DialogButton

from omemo.backend.util import Trust
from omemo.backend.util import IdentityKeyExtended
from omemo.backend.util import get_fingerprint

log = logging.getLogger('gajim.p.omemo')


TRUST_DATA = {
    Trust.UNTRUSTED: ('dialog-error-symbolic',
                      _('Untrusted'),
                      'error-color'),
    Trust.UNDECIDED: ('security-low-symbolic',
                      _('Not Decided'),
                      'warning-color'),
    Trust.VERIFIED: ('security-high-symbolic',
                     _('Verified'),
                     'encrypted-color'),
    Trust.BLIND: ('security-medium-symbolic',
                  _('Blind Trust'),
                  'encrypted-color')
}


class KeyDialog(Gtk.Dialog):
    def __init__(self, plugin, contact, transient, windows,
                 groupchat=False):
        super().__init__(title=_('OMEMO Fingerprints'),
                         destroy_with_parent=True)

        self.set_transient_for(transient)
        self.set_resizable(True)
        self.set_default_size(500, 450)

        self.get_style_context().add_class('omemo-key-dialog')

        self._groupchat = groupchat
        self._contact = contact
        self._windows = windows
        self._account = self._contact.account.name
        self._plugin = plugin
        self._omemo = self._plugin.get_omemo(self._account)
        self._own_jid = app.get_jid_from_account(self._account)
        self._show_inactive = False

        path = self._plugin.local_file_path('gtk/key.ui')
        self._ui = get_builder(path)

        markup = '<a href="%s">%s</a>' % (
            'https://dev.gajim.org/gajim/gajim-plugins/-/'
            'wikis/omemogajimplugin', _('Read more about blind trust.'))
        self._ui.btbv_link.set_markup(markup)
        self._ui.infobar.set_revealed(
            self._plugin.config['SHOW_HELP_FINGERPRINTS'])

        self._ui.header.set_text(_('Fingerprints for %s') % self._contact.jid)

        omemo_img_path = self._plugin.local_file_path('omemo.png')
        self._ui.omemo_image.set_from_file(omemo_img_path)

        self._ui.list.set_filter_func(self._filter_func, None)
        self._ui.list.set_sort_func(self._sort_func, None)

        self._identity_key = self._omemo.backend.storage.getIdentityKeyPair()
        ownfpr_format = get_fingerprint(self._identity_key, formatted=True)
        self._ui.own_fingerprint.set_text(ownfpr_format)

        self.get_content_area().add(self._ui.box)

        self.update()
        self._load_qrcode()
        self._ui.connect_signals(self)
        self.connect('destroy', self._on_destroy)
        self.show_all()

    def _on_infobar_response(self, _widget, response):
        if response == Gtk.ResponseType.CLOSE:
            self._ui.infobar.set_revealed(False)
            self._plugin.config['SHOW_HELP_FINGERPRINTS'] = False

    def _filter_func(self, row, _user_data):
        search_text = self._ui.search.get_text()
        if search_text and search_text.lower() not in str(row.jid):
            return False
        if self._show_inactive:
            return True
        return row.active

    @staticmethod
    def _sort_func(row1, row2, _user_data):
        result = locale.strcoll(str(row1.jid), str(row2.jid))
        if result != 0:
            return result

        if row1.active != row2.active:
            return -1 if row1.active else 1

        if row1.trust != row2.trust:
            return -1 if row1.trust > row2.trust else 1
        return 0

    def _on_search_changed(self, _entry):
        self._ui.list.invalidate_filter()

    def update(self):
        self._ui.list.foreach(self._ui.list.remove)
        self._load_fingerprints(self._own_jid)
        self._load_fingerprints(self._contact.jid, self._groupchat is True)

    def _load_fingerprints(self, contact_jid, groupchat=False):
        if groupchat:
            members = list(self._omemo.backend.get_muc_members(contact_jid))
            sessions = self._omemo.backend.storage.getSessionsFromJids(members)
        else:
            sessions = self._omemo.backend.storage.getSessionsFromJid(contact_jid)

        rows = {}
        if groupchat:
            results = self._omemo.backend.storage.getMucFingerprints(members)
        else:
            results = self._omemo.backend.storage.getFingerprints(contact_jid)
        for result in results:
            rows[result.public_key] = KeyRow(result.recipient_id,
                                             result.public_key,
                                             result.trust,
                                             result.timestamp)

        for item in sessions:
            if item.record.isFresh():
                return
            identity_key = item.record.getSessionState().getRemoteIdentityKey()
            identity_key = IdentityKeyExtended(identity_key.getPublicKey())
            try:
                key_row = rows[identity_key]
            except KeyError:
                log.warning('Could not find session identitykey %s',
                            item.device_id)
                self._omemo.backend.storage.deleteSession(item.recipient_id,
                                                          item.device_id)
                continue

            key_row.active = item.active
            key_row.device_id = item.device_id

        for row in rows.values():
            self._ui.list.add(row)

    @staticmethod
    def _get_qrcode(jid, sid, identity_key):
        fingerprint = get_fingerprint(identity_key)
        path = os.path.join(tempfile.gettempdir(),
                            'omemo_{}.png'.format(jid))

        ver_string = 'xmpp:{}?omemo-sid-{}={}'.format(jid, sid, fingerprint)
        log.debug('Verification String: %s', ver_string)

        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=2,
                           box_size=4, border=1)
        qr.add_data(ver_string)
        qr.make(fit=True)
        qr.make()

        fill_color = 'black'
        back_color = 'transparent'
        if app.css_config.prefer_dark:
            back_color = 'white'
        if V(get_distribution('qrcode').version) < V('6.0'):
            # meaning of fill_color and back_color were switched
            # before this commit in qrcode between versions 5.3
            # and 6.0: https://github.com/lincolnloop/python-qrcode/
            # commit/01f440d64b7d1f61bb75161ce118b86eca85b15c
            back_color, fill_color = fill_color, back_color

        img = qr.make_image(fill_color=fill_color, back_color=back_color)
        img.save(path)
        return path

    def _load_qrcode(self):
        try:
            path = self._get_qrcode(self._own_jid,
                                    self._omemo.backend.own_device,
                                    self._identity_key)
        except ImportError:
            log.exception('Failed to generate QR code')
            self._ui.qrcode.hide()
            self._ui.qrinfo.show()
        else:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
            self._ui.qrcode.set_from_pixbuf(pixbuf)
            self._ui.qrcode.show()
            self._ui.qrinfo.hide()

    def _on_show_inactive(self, switch, param):
        self._show_inactive = switch.get_active()
        self._ui.list.invalidate_filter()

    def _on_destroy(self, *args):
        del self._windows['dialog']


class KeyRow(Gtk.ListBoxRow):
    def __init__(self, jid, identity_key, trust, last_seen):
        Gtk.ListBoxRow.__init__(self)
        self.set_activatable(False)

        self._active = False
        self._device_id = None
        self._identity_key = identity_key
        self.trust = trust
        self.jid = jid

        grid = Gtk.Grid()
        grid.set_column_spacing(12)

        self._trust_button = TrustButton(self)
        grid.attach(self._trust_button, 1, 1, 1, 3)

        jid_label = Gtk.Label(label=jid)
        jid_label.get_style_context().add_class('dim-label')
        jid_label.set_selectable(False)
        jid_label.set_halign(Gtk.Align.START)
        jid_label.set_valign(Gtk.Align.START)
        jid_label.set_hexpand(True)
        grid.attach(jid_label, 2, 1, 1, 1)

        self.fingerprint = Gtk.Label(
            label=self._identity_key.get_fingerprint(formatted=True))
        self.fingerprint.get_style_context().add_class('omemo-mono')
        self.fingerprint.get_style_context().add_class('omemo-inactive-color')
        self.fingerprint.set_selectable(True)
        self.fingerprint.set_halign(Gtk.Align.START)
        self.fingerprint.set_valign(Gtk.Align.START)
        self.fingerprint.set_hexpand(True)
        grid.attach(self.fingerprint, 2, 2, 1, 1)

        if last_seen is not None:
            last_seen = time.strftime('%d-%m-%Y %H:%M:%S',
                                      time.localtime(last_seen))
        else:
            last_seen = _('Never')
        last_seen_label = Gtk.Label(label=_('Last seen: %s') % last_seen)
        last_seen_label.set_halign(Gtk.Align.START)
        last_seen_label.set_valign(Gtk.Align.START)
        last_seen_label.set_hexpand(True)
        last_seen_label.get_style_context().add_class('omemo-last-seen')
        last_seen_label.get_style_context().add_class('dim-label')
        grid.attach(last_seen_label, 2, 3, 1, 1)

        self.add(grid)
        self.show_all()

    def delete_fingerprint(self, *args):
        def _remove():
            backend = self.get_toplevel()._omemo.backend

            backend.remove_device(self.jid, self.device_id)
            backend.storage.deleteSession(self.jid, self.device_id)
            backend.storage.deleteIdentity(self.jid, self._identity_key)

            self.get_parent().remove(self)
            self.destroy()

        ConfirmationDialog(
            _('Delete'),
            _('Delete Fingerprint'),
            _('Doing so will permanently delete this Fingerprint'),
            [DialogButton.make('Cancel'),
             DialogButton.make('Remove',
                               text=_('Delete'),
                               callback=_remove)],
            transient_for=self.get_toplevel()).show()

    def set_trust(self):
        icon_name, tooltip, css_class = TRUST_DATA[self.trust]
        image = self._trust_button.get_child()
        image.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        image.get_style_context().add_class(css_class)
        image.set_tooltip_text(tooltip)

        backend = self.get_toplevel()._omemo.backend
        backend.storage.setTrust(self.jid, self._identity_key, self.trust)

    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, active):
        context = self.fingerprint.get_style_context()
        self._active = bool(active)
        if self._active:
            context.remove_class('omemo-inactive-color')
        else:
            context.add_class('omemo-inactive-color')
        self._trust_button.update()

    @property
    def device_id(self):
        return self._device_id

    @device_id.setter
    def device_id(self, device_id):
        self._device_id = device_id


class TrustButton(Gtk.MenuButton):
    def __init__(self, row):
        Gtk.MenuButton.__init__(self)
        self._row = row
        self._css_class = ''
        self.set_popover(TrustPopver(row))
        self.set_valign(Gtk.Align.CENTER)
        self.update()

    def update(self):
        icon_name, tooltip, css_class = TRUST_DATA[self._row.trust]
        image = self.get_child()
        image.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        # Remove old color from icon
        image.get_style_context().remove_class(self._css_class)

        if not self._row.active:
            css_class = 'omemo-inactive-color'
            tooltip = '%s - %s' % (_('Inactive'), tooltip)

        image.get_style_context().add_class(css_class)
        self._css_class = css_class
        self.set_tooltip_text(tooltip)


class TrustPopver(Gtk.Popover):
    def __init__(self, row):
        Gtk.Popover.__init__(self)
        self._row = row
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.update()
        self.add(self._listbox)
        self._listbox.show_all()
        self._listbox.connect('row-activated', self._activated)
        self.get_style_context().add_class('omemo-trust-popover')

    def _activated(self, _listbox, row):
        self.popdown()
        if row.type_ is None:
            self._row.delete_fingerprint()
        else:
            self._row.trust = row.type_
            self._row.set_trust()
            self.get_relative_to().update()
            self.update()

    def update(self):
        self._listbox.foreach(self._listbox.remove)
        if self._row.trust != Trust.VERIFIED:
            self._listbox.add(VerifiedOption())
        if self._row.trust != Trust.BLIND:
            self._listbox.add(BlindOption())
        if self._row.trust != Trust.UNTRUSTED:
            self._listbox.add(NotTrustedOption())
        self._listbox.add(DeleteOption())


class MenuOption(Gtk.ListBoxRow):
    def __init__(self):
        Gtk.ListBoxRow.__init__(self)
        box = Gtk.Box()
        box.set_spacing(6)

        image = Gtk.Image.new_from_icon_name(self.icon,
                                             Gtk.IconSize.MENU)
        label = Gtk.Label(label=self.label)
        image.get_style_context().add_class(self.color)

        box.add(image)
        box.add(label)
        self.add(box)
        self.show_all()


class BlindOption(MenuOption):

    type_ = Trust.BLIND
    icon = 'security-medium-symbolic'
    label = _('Blind Trust')
    color = 'encrypted-color'

    def __init__(self):
        MenuOption.__init__(self)


class VerifiedOption(MenuOption):

    type_ = Trust.VERIFIED
    icon = 'security-high-symbolic'
    label = _('Verified')
    color = 'encrypted-color'

    def __init__(self):
        MenuOption.__init__(self)


class NotTrustedOption(MenuOption):

    type_ = Trust.UNTRUSTED
    icon = 'dialog-error-symbolic'
    label = _('Untrusted')
    color = 'error-color'

    def __init__(self):
        MenuOption.__init__(self)


class DeleteOption(MenuOption):

    type_ = None
    icon = 'user-trash-symbolic'
    label = _('Delete')
    color = ''

    def __init__(self):
        MenuOption.__init__(self)
