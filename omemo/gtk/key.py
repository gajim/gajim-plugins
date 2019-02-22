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

import time
import logging

from gi.repository import Gtk
from gi.repository import GdkPixbuf

from gajim.common import app
from gajim.plugins.plugins_i18n import _

from omemo.gtk.util import DialogButton, ButtonAction
from omemo.gtk.util import NewConfirmationDialog
from omemo.gtk.util import Trust
from omemo.backend.util import IdentityKeyExtended
from omemo.backend.util import get_fingerprint

log = logging.getLogger('gajim.plugin_system.omemo')

TRUST_DATA = {
    Trust.NOT_TRUSTED: ('dialog-error-symbolic',
                        _('Not Trusted'),
                        'error-color'),
    Trust.UNKNOWN: ('security-low-symbolic',
                    _('Not Decided'),
                    'warning-color'),
    Trust.VERIFIED: ('security-high-symbolic',
                     _('Trusted'),
                     'success-color')
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

        # Header
        jid = self._contact.jid
        self._header = Gtk.Label(label=_('Fingerprints for %s') % jid)
        self._header.get_style_context().add_class('bold')
        self._header.get_style_context().add_class('dim-label')

        # Fingerprints list
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.NEVER,
                                  Gtk.PolicyType.AUTOMATIC)
        self._scrolled.add(self._listbox)

        # Own fingerprint
        self._label = Gtk.Label(label=_('Own Fingerprint'))
        self._label.get_style_context().add_class('bold')
        self._label.get_style_context().add_class('dim-label')

        self._omemo_logo = Gtk.Image()
        omemo_img_path = self._plugin.local_file_path('omemo.png')
        omemo_pixbuf = GdkPixbuf.Pixbuf.new_from_file(omemo_img_path)
        self._omemo_logo.set_from_pixbuf(omemo_pixbuf)

        identity_key = self._omemo.backend.storage.getIdentityKeyPair()
        ownfpr_format = get_fingerprint(identity_key, formatted=True)
        self._ownfpr = Gtk.Label(label=ownfpr_format)
        self._ownfpr.get_style_context().add_class('omemo-mono')
        self._ownfpr.set_selectable(True)

        self._ownfpr_box = Gtk.Box(spacing=12)
        self._ownfpr_box.set_halign(Gtk.Align.CENTER)
        self._ownfpr_box.pack_start(self._omemo_logo, True, True, 0)
        self._ownfpr_box.pack_start(self._ownfpr, True, True, 0)

        box = self.get_content_area()
        box.set_orientation(Gtk.Orientation.VERTICAL)
        box.set_spacing(12)
        box.pack_start(self._header, False, True, 0)
        box.pack_start(self._scrolled, True, True, 0)
        box.pack_start(self._label, False, True, 0)
        box.pack_start(self._ownfpr_box, False, True, 0)

        self.update()
        self.connect('destroy', self._on_destroy)
        self.show_all()

    def update(self):
        self._listbox.foreach(self._listbox.remove)
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
            self._listbox.add(row)

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

        buttons = {
            Gtk.ResponseType.CANCEL: DialogButton(_('Cancel')),
            Gtk.ResponseType.OK: DialogButton(_('Delete'),
                                              _remove,
                                              ButtonAction.DESTRUCTIVE),
        }

        NewConfirmationDialog(
            _('Delete Fingerprint'),
            _('Doing so will permanently delete this Fingerprint'),
            buttons,
            transient_for=self.get_toplevel())

    def set_trust(self):
        icon_name, tooltip, css_class = TRUST_DATA[self.trust]
        image = self._trust_button.get_child()
        image.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        image.get_style_context().add_class(css_class)
        image.set_tooltip_text(tooltip)

        backend = self.get_toplevel()._omemo.backend
        backend.storage.setTrust(self._identity_key, self.trust)

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
        if row.trust != Trust.VERIFIED:
            self._listbox.add(VerifiedOption())
        if row.trust != Trust.NOT_TRUSTED:
            self._listbox.add(NotTrustedOption())
        self._listbox.add(DeleteOption())
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
        if self._row.trust != Trust.NOT_TRUSTED:
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


class VerifiedOption(MenuOption):

    type_ = Trust.VERIFIED
    icon = 'security-high-symbolic'
    label = _('Trusted')
    color = 'success-color'

    def __init__(self):
        MenuOption.__init__(self)


class NotTrustedOption(MenuOption):

    type_ = Trust.NOT_TRUSTED
    icon = 'dialog-error-symbolic'
    label = _('Not Trusted')
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
