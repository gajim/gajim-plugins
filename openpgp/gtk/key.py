# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the OpenPGP Gajim Plugin.
#
# OpenPGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OpenPGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OpenPGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import logging
import time

from gi.repository import Gtk

from gajim.common import app
from gajim.gtk.dialogs import ConfirmationDialog
from gajim.gtk.dialogs import DialogButton
from gajim.plugins.plugins_i18n import _

from openpgp.modules.util import Trust

log = logging.getLogger("gajim.p.openpgp.keydialog")

TRUST_DATA = {
    Trust.NOT_TRUSTED: ("dialog-error-symbolic", _("Not Trusted"), "error-color"),
    Trust.UNKNOWN: ("security-low-symbolic", _("Not Decided"), "warning-color"),
    Trust.BLIND: ("security-medium-symbolic", _("Blind Trust"), "encrypted-color"),
    Trust.VERIFIED: ("security-high-symbolic", _("Verified"), "encrypted-color"),
}


class KeyDialog(Gtk.Dialog):
    def __init__(self, account, jid, transient):
        super().__init__(title=_("Public Keys for %s") % jid, destroy_with_parent=True)

        self.set_transient_for(transient)
        self.set_resizable(True)
        self.set_default_size(500, 300)

        self.get_style_context().add_class("openpgp-key-dialog")

        self._client = app.get_client(account)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        self._scrolled = Gtk.ScrolledWindow()
        self._scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.add(self._listbox)

        box = self.get_content_area()
        box.pack_start(self._scrolled, True, True, 0)

        keys = self._client.get_module("OpenPGP").get_keys(jid, only_trusted=False)
        for key in keys:
            log.info("Load: %s", key.fingerprint)
            self._listbox.add(KeyRow(key))
        self.show_all()


class KeyRow(Gtk.ListBoxRow):
    def __init__(self, key):
        Gtk.ListBoxRow.__init__(self)
        self.set_activatable(False)

        self._dialog = self.get_toplevel()
        self.key = key

        box = Gtk.Box()
        box.set_spacing(12)

        self._trust_button = TrustButton(self)
        box.add(self._trust_button)

        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        fingerprint = Gtk.Label(label=self._format_fingerprint(key.fingerprint))
        fingerprint.get_style_context().add_class("openpgp-mono")
        if not key.active:
            fingerprint.get_style_context().add_class("openpgp-inactive-color")
        fingerprint.set_selectable(True)
        fingerprint.set_halign(Gtk.Align.START)
        fingerprint.set_valign(Gtk.Align.START)
        fingerprint.set_hexpand(True)
        label_box.add(fingerprint)

        date = Gtk.Label(label=self._format_timestamp(key.timestamp))
        date.set_halign(Gtk.Align.START)
        date.get_style_context().add_class("openpgp-mono")
        if not key.active:
            date.get_style_context().add_class("openpgp-inactive-color")
        label_box.add(date)

        box.add(label_box)

        self.add(box)
        self.show_all()

    def delete_fingerprint(self, *args):
        def _remove():
            self.get_parent().remove(self)
            self.key.delete()
            self.destroy()

        ConfirmationDialog(
            _("Delete Public Key?"),
            _("This will permanently delete this public key"),
            [
                DialogButton.make("Cancel"),
                DialogButton.make("Remove", text=_("Delete"), callback=_remove),
            ],
        ).show()

    def set_trust(self, trust):
        icon_name, tooltip, css_class = TRUST_DATA[trust]
        image = self._trust_button.get_child()
        image.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        image.get_style_context().add_class(css_class)

    @staticmethod
    def _format_fingerprint(fingerprint):
        fplen = len(fingerprint)
        wordsize = fplen // 8
        buf = ""
        for w in range(0, fplen, wordsize):
            buf += "{0} ".format(fingerprint[w : w + wordsize])
        return buf.rstrip()

    @staticmethod
    def _format_timestamp(timestamp):
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


class TrustButton(Gtk.MenuButton):
    def __init__(self, row):
        Gtk.MenuButton.__init__(self)
        self._row = row
        self._css_class = ""
        self.set_popover(TrustPopver(row))
        self.update()

    def update(self):
        icon_name, tooltip, css_class = TRUST_DATA[self._row.key.trust]
        image = self.get_child()
        image.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        # remove old color from icon
        image.get_style_context().remove_class(self._css_class)

        if not self._row.key.active:
            css_class = "openpgp-inactive-color"
            tooltip = "%s - %s" % (_("Inactive"), tooltip)

        image.get_style_context().add_class(css_class)
        self._css_class = css_class
        self.set_tooltip_text(tooltip)


class TrustPopver(Gtk.Popover):
    def __init__(self, row):
        Gtk.Popover.__init__(self)
        self._row = row
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        if row.key.trust != Trust.VERIFIED:
            self._listbox.add(VerifiedOption())
        if row.key.trust != Trust.NOT_TRUSTED:
            self._listbox.add(NotTrustedOption())
        self._listbox.add(DeleteOption())
        self.add(self._listbox)
        self._listbox.show_all()
        self._listbox.connect("row-activated", self._activated)
        self.get_style_context().add_class("openpgp-trust-popover")

    def _activated(self, listbox, row):
        self.popdown()
        if row.type_ is None:
            self._row.delete_fingerprint()
        else:
            self._row.key.trust = row.type_
            self.get_relative_to().update()
            self.update()

    def update(self):
        self._listbox.foreach(lambda row: self._listbox.remove(row))
        if self._row.key.trust != Trust.VERIFIED:
            self._listbox.add(VerifiedOption())
        if self._row.key.trust != Trust.NOT_TRUSTED:
            self._listbox.add(NotTrustedOption())
        self._listbox.add(DeleteOption())


class MenuOption(Gtk.ListBoxRow):
    def __init__(self):
        Gtk.ListBoxRow.__init__(self)
        box = Gtk.Box()
        box.set_spacing(6)

        image = Gtk.Image.new_from_icon_name(self.icon, Gtk.IconSize.MENU)
        label = Gtk.Label(label=self.label)
        image.get_style_context().add_class(self.color)

        box.add(image)
        box.add(label)
        self.add(box)
        self.show_all()


class VerifiedOption(MenuOption):

    type_ = Trust.VERIFIED
    icon = "security-high-symbolic"
    label = _("Verified")
    color = "encrypted-color"

    def __init__(self):
        MenuOption.__init__(self)


class NotTrustedOption(MenuOption):

    type_ = Trust.NOT_TRUSTED
    icon = "dialog-error-symbolic"
    label = _("Not Trusted")
    color = "error-color"

    def __init__(self):
        MenuOption.__init__(self)


class DeleteOption(MenuOption):

    type_ = None
    icon = "user-trash-symbolic"
    label = _("Delete")
    color = ""

    def __init__(self):
        MenuOption.__init__(self)
