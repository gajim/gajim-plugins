# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

import logging
import binascii
import textwrap

from gi.repository import Gtk
from gi.repository import GdkPixbuf

from gajim.common import app
from gajim.plugins.plugins_i18n import _

from omemo.gtk.util import DialogButton, ButtonAction
from omemo.gtk.util import NewConfirmationDialog
from omemo.gtk.util import Trust

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
    def __init__(self, plugin, contact, transient, windowinstances,
                 groupchat=False):
        flags = Gtk.DialogFlags.DESTROY_WITH_PARENT
        super().__init__(_('OMEMO Fingerprints'), None, flags)

        self.set_transient_for(transient)
        self.set_resizable(True)
        self.set_default_size(-1, 400)

        self.get_style_context().add_class('omemo-key-dialog')

        self._groupchat = groupchat
        self._contact = contact
        self._windowinstances = windowinstances
        self._account = self._contact.account.name
        self._plugin = plugin
        self._con = plugin.connections[self._account]
        self.omemostate = self._plugin.get_omemo(self._account)
        self._own_jid = app.get_jid_from_account(self._account)

        # Header
        jid = self._contact.jid
        self._header = Gtk.Label(_('Fingerprints for %s') % jid)
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
        self._label = Gtk.Label(_('Own Fingerprint'))
        self._label.get_style_context().add_class('bold')
        self._label.get_style_context().add_class('dim-label')

        self._omemo_logo = Gtk.Image()
        omemo_img_path = self._plugin.local_file_path('omemo.png')
        omemo_pixbuf = GdkPixbuf.Pixbuf.new_from_file(omemo_img_path)
        self._omemo_logo.set_from_pixbuf(omemo_pixbuf)

        ownfpr = binascii.hexlify(self.omemostate.store.getIdentityKeyPair()
                                  .getPublicKey().serialize()).decode('utf-8')
        ownfpr_format = KeyRow._format_fingerprint(ownfpr[2:])
        self._ownfpr = Gtk.Label(ownfpr_format)
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
        self._listbox.foreach(lambda row: self._listbox.remove(row))
        self._load_fingerprints(self._own_jid)
        self._load_fingerprints(self._contact.jid, self._groupchat is True)

    def _load_fingerprints(self, contact_jid, groupchat=False):
        from axolotl.state.sessionrecord import SessionRecord
        state = self.omemostate

        if groupchat:
            contact_jids = []
            for nick in self._con.groupchat[contact_jid]:
                real_jid = self._con.groupchat[contact_jid][nick]
                if real_jid == self._own_jid:
                    continue
                contact_jids.append(real_jid)
            session_db = state.store.getSessionsFromJids(contact_jids)
        else:
            session_db = state.store.getSessionsFromJid(contact_jid)

        for item in session_db:
            _id, jid, deviceid, record, active = item

            active = bool(active)

            identity_key = SessionRecord(serialized=record). \
                getSessionState().getRemoteIdentityKey()
            fpr = binascii.hexlify(identity_key.getPublicKey().serialize()).decode('utf-8')
            fpr = fpr[2:]
            trust = state.store.isTrustedIdentity(jid, identity_key)

            log.info('Load: %s %s', fpr, trust)
            self._listbox.add(KeyRow(jid, deviceid, fpr, trust, active))

    def _on_destroy(self, *args):
        del self._windowinstances['dialog']


class KeyRow(Gtk.ListBoxRow):
    def __init__(self, jid, deviceid, fpr, trust, active):
        Gtk.ListBoxRow.__init__(self)
        self.set_activatable(False)

        self.active = active
        self.trust = trust
        self.jid = jid
        self.deviceid = deviceid

        box = Gtk.Box()
        box.set_spacing(12)

        self._trust_button = TrustButton(self)
        box.add(self._trust_button)

        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        jid_label = Gtk.Label(jid)
        jid_label.get_style_context().add_class('dim-label')
        jid_label.set_selectable(False)
        jid_label.set_halign(Gtk.Align.START)
        jid_label.set_valign(Gtk.Align.START)
        jid_label.set_hexpand(True)
        label_box.add(jid_label)

        fingerprint = Gtk.Label(
            label=self._format_fingerprint(fpr))
        fingerprint.get_style_context().add_class('omemo-mono')
        if not active:
            fingerprint.get_style_context().add_class('omemo-inactive-color')
        fingerprint.set_selectable(True)
        fingerprint.set_halign(Gtk.Align.START)
        fingerprint.set_valign(Gtk.Align.START)
        fingerprint.set_hexpand(True)
        label_box.add(fingerprint)

        box.add(label_box)

        self.add(box)
        self.show_all()

    def delete_fingerprint(self, *args):
        def _remove():
            state = self.get_toplevel().omemostate
            record = state.store.loadSession(self.jid, self.deviceid)
            identity_key = record.getSessionState().getRemoteIdentityKey()

            state.store.deleteSession(self.jid, self.deviceid)
            state.store.deleteIdentity(self.jid, identity_key)
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

        state = self.get_toplevel().omemostate
        record = state.store.loadSession(self.jid, self.deviceid)
        identity_key = record.getSessionState().getRemoteIdentityKey()
        state.store.setTrust(identity_key, self.trust)

    @staticmethod
    def _format_fingerprint(fingerprint):
        fplen = len(fingerprint)
        wordsize = fplen // 8
        buf = ''
        for w in range(0, fplen, wordsize):
            buf += '{0} '.format(fingerprint[w:w + wordsize])
        buf = textwrap.fill(buf, width=36)
        return buf.rstrip().upper()


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

    def _activated(self, listbox, row):
        self.popdown()
        if row.type_ is None:
            self._row.delete_fingerprint()
        else:
            self._row.trust = row.type_
            self._row.set_trust()
            self.get_relative_to().update()
            self.update()

    def update(self):
        self._listbox.foreach(lambda row: self._listbox.remove(row))
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
