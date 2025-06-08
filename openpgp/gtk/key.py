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

from __future__ import annotations

from typing import cast

import logging
import time

from gi.repository import Gtk
from nbxmpp import JID

from gajim.common import app
from gajim.gtk.alert import ConfirmationAlertDialog
from gajim.gtk.util.misc import container_remove_all
from gajim.gtk.widgets import GajimAppWindow
from gajim.plugins.plugins_i18n import _

from openpgp.modules.key_store import KeyData
from openpgp.modules.openpgp import OpenPGP
from openpgp.modules.util import Trust

log = logging.getLogger("gajim.p.openpgp.keydialog")

TRUST_DATA = {
    Trust.NOT_TRUSTED: ("dialog-error-symbolic", _("Not Trusted"), "error-color"),
    Trust.UNKNOWN: ("security-low-symbolic", _("Not Decided"), "warning-color"),
    Trust.BLIND: ("security-medium-symbolic", _("Blind Trust"), "encrypted-color"),
    Trust.VERIFIED: ("security-high-symbolic", _("Verified"), "encrypted-color"),
}


class KeyDialog(GajimAppWindow):
    def __init__(self, account: str, jid: JID, transient: Gtk.Window) -> None:

        GajimAppWindow.__init__(
            self,
            name="PGPKeyDialog",
            title=_("Public Keys for %s") % jid,
            default_width=450,
            default_height=400,
            transient_for=transient,
            modal=True,
        )

        self.window.add_css_class("openpgp-key-dialog")

        self._client = app.get_client(account)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        self._scrolled = Gtk.ScrolledWindow(hexpand=True)
        self._scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scrolled.set_child(self._listbox)

        self.set_child(self._scrolled)

        open_pgp_module = cast(OpenPGP, self._client.get_module("OpenPGP"))  # type: ignore
        keys = open_pgp_module.get_keys(jid, only_trusted=False)
        for key in keys:
            log.info("Load: %s", key.fingerprint)
            self._listbox.append(KeyRow(key, self))

        self.show()

    def _cleanup(self) -> None:
        del self._client
        del self._listbox
        del self._scrolled


class KeyRow(Gtk.ListBoxRow):
    def __init__(self, key: KeyData, dialog: GajimAppWindow):
        Gtk.ListBoxRow.__init__(self)
        self.set_activatable(False)

        self._dialog = dialog
        self.key = key

        box = Gtk.Box()
        box.set_spacing(12)

        self._trust_button = Gtk.MenuButton()
        self._trust_button.set_popover(TrustPopver(self))
        self._update_button_state()
        box.append(self._trust_button)

        label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        fingerprint = Gtk.Label(label=self._format_fingerprint(key.fingerprint))
        fingerprint.get_style_context().add_class("openpgp-mono")
        if not key.active:
            fingerprint.get_style_context().add_class("openpgp-inactive-color")
        fingerprint.set_selectable(True)
        fingerprint.set_halign(Gtk.Align.START)
        fingerprint.set_valign(Gtk.Align.START)
        fingerprint.set_hexpand(True)
        label_box.append(fingerprint)

        date = Gtk.Label(label=self._format_timestamp(key.timestamp))
        date.set_halign(Gtk.Align.START)
        date.get_style_context().add_class("openpgp-mono")
        if not key.active:
            date.get_style_context().add_class("openpgp-inactive-color")
        label_box.append(date)

        box.append(label_box)
        self.set_child(box)

    def _update_button_state(self) -> None:
        icon_name, tooltip, css_class = TRUST_DATA[self.key.trust]
        self._trust_button.set_icon_name(icon_name)

        for css_cls in self._trust_button.get_css_classes():
            if css_cls.startswith("openpgp"):
                self._trust_button.remove_css_class(css_cls)

        if not self.key.active:
            css_class = "inactive-color"
            tooltip = "%s - %s" % (_("Inactive"), tooltip)

        self._trust_button.add_css_class(f"openpgp-{css_class}")
        self._trust_button.set_tooltip_text(tooltip)

    def delete_fingerprint(self):
        def _remove():
            listbox = cast(Gtk.ListBox, self.get_parent())
            listbox.remove(self)
            self.key.delete()

        ConfirmationAlertDialog(
            _("Delete Public Key?"),
            _("This will permanently delete this public key"),
            confirm_label=_("_Delete"),
            appearance="destructive",
            callback=_remove,
        )

    def set_trust(self, trust: Trust) -> None:
        self.key.trust = trust
        self._update_button_state()

    @staticmethod
    def _format_fingerprint(fingerprint: str) -> str:
        fplen = len(fingerprint)
        wordsize = fplen // 8
        buf = ""
        for w in range(0, fplen, wordsize):
            buf += f"{fingerprint[w : w + wordsize]} "
        return buf.rstrip()

    @staticmethod
    def _format_timestamp(timestamp: float) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


class TrustPopver(Gtk.Popover):
    def __init__(self, row: KeyRow):
        Gtk.Popover.__init__(self)
        self._row = row
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        if row.key.trust != Trust.VERIFIED:
            self._listbox.append(VerifiedOption())
        if row.key.trust != Trust.NOT_TRUSTED:
            self._listbox.append(NotTrustedOption())
        self._listbox.append(DeleteOption())
        self.set_child(self._listbox)
        self._listbox.connect("row-activated", self._activated)
        self.add_css_class("openpgp-trust-popover")

    def _activated(self, listbox: Gtk.ListBox, row: MenuOption) -> None:
        self.popdown()
        if row.type_ is None:
            self._row.delete_fingerprint()
        else:
            self._row.set_trust(row.type_)
            self.update()

    def update(self):
        container_remove_all(self._listbox)
        if self._row.key.trust != Trust.VERIFIED:
            self._listbox.append(VerifiedOption())
        if self._row.key.trust != Trust.NOT_TRUSTED:
            self._listbox.append(NotTrustedOption())
        self._listbox.append(DeleteOption())


class MenuOption(Gtk.ListBoxRow):

    type_: Trust | None
    icon: str
    label: str
    color: str

    def __init__(self):
        Gtk.ListBoxRow.__init__(self)
        box = Gtk.Box()
        box.set_spacing(6)

        image = Gtk.Image.new_from_icon_name(self.icon)
        if self.color:
            image.add_css_class(self.color)

        label = Gtk.Label(label=self.label)
        box.append(image)
        box.append(label)
        self.set_child(box)


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
