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

from typing import cast

import logging
import threading
from enum import IntEnum

from gi.repository import GLib
from gi.repository import Gtk

from gajim.common import app
from gajim.common.client import Client
from gajim.gtk.control import ChatControl
from gajim.plugins.plugins_i18n import _

from ..pgpplugin import OpenPGPPlugin

log = logging.getLogger("gajim.p.openpgp.wizard")


class Page(IntEnum):
    WELCOME = 0
    NEWKEY = 1
    SUCCESS = 2
    ERROR = 3


class KeyWizard(Gtk.Assistant):
    def __init__(
        self, plugin: OpenPGPPlugin, account: str, chat_control: ChatControl
    ) -> None:
        Gtk.Assistant.__init__(self)

        self._client = app.get_client(account)
        self._plugin = plugin
        self._account = account
        self._data_form_widget = None
        self._is_form = None
        self._chat_control = chat_control

        self.set_application(app.app)
        self.set_transient_for(app.window)
        self.set_resizable(True)

        self.set_default_size(600, 400)
        self.get_style_context().add_class("dialog-margin")

        self._add_page(WelcomePage())
        # self._add_page(BackupKeyPage())
        self._add_page(NewKeyPage(self, self._client))
        # self._add_page(SaveBackupCodePage())
        self._add_page(SuccessfulPage())
        self._add_page(ErrorPage())

        self.connect("prepare", self._on_page_change)
        self.connect("cancel", self._on_cancel)
        self.connect("close", self._on_cancel)

        self._remove_sidebar()
        self.show()

    def _add_page(self, page: Gtk.Box) -> None:
        self.append_page(page)
        self.set_page_type(page, page.type_)
        self.set_page_title(page, page.title)
        self.set_page_complete(page, page.complete)

    def _remove_sidebar(self):
        main_box = self.get_child()
        sidebar = main_box.get_first_child()
        main_box.remove(sidebar)

    def _activate_encryption(self):
        action = app.window.lookup_action("set-encryption")
        action.activate(GLib.Variant("s", self._plugin.encryption_name))

    def _on_page_change(self, assistant: Gtk.Assistant, page: Page) -> None:
        if self.get_current_page() == Page.NEWKEY:
            if self._client.get_module("OpenPGP").secret_key_available:
                self.set_current_page(Page.SUCCESS)
            else:
                page.generate()
        elif self.get_current_page() == Page.SUCCESS:
            self._activate_encryption()

    def _on_cancel(self, widget: Gtk.Assistant):
        self.destroy()


class WelcomePage(Gtk.Box):
    type_ = Gtk.AssistantPageType.INTRO
    title = _("Welcome")
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(18)
        title_label = Gtk.Label(label=_("Setup OpenPGP"))
        text_label = Gtk.Label(label=_("Gajim will now try to setup OpenPGP for you"))
        self.append(title_label)
        self.append(text_label)


class RequestPage(Gtk.Box):
    type_ = Gtk.AssistantPageType.INTRO
    title = _("Request OpenPGP Key")
    complete = False

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(18)
        spinner = Gtk.Spinner()
        self.append(spinner)
        spinner.start()


# class BackupKeyPage(Gtk.Box):

#     type_ = Gtk.AssistantPageType.INTRO
#     title = _('Supply Backup Code')
#     complete = True

#     def __init__(self):
#         super().__init__(orientation=Gtk.Orientation.VERTICAL)
#         self.set_spacing(18)
#         title_label = Gtk.Label(label=_('Backup Code'))
#         text_label = Gtk.Label(
#             label=_('We found a backup Code, please supply your password'))
#         self.add(title_label)
#         self.add(text_label)
#         entry = Gtk.Entry()
#         self.add(entry)


class NewKeyPage(RequestPage):
    type_ = Gtk.AssistantPageType.PROGRESS
    title = _("Generating new Key")
    complete = False

    def __init__(self, assistant: Gtk.Assistant, client: Client) -> None:
        super().__init__()
        self._assistant = assistant
        self._client = client

    def generate(self):
        log.info("Creating Key")
        thread = threading.Thread(target=self.worker)
        thread.start()

    def worker(self):
        text = None
        try:
            self._client.get_module("OpenPGP").generate_key()
        except Exception as error:
            text = str(error)

        GLib.idle_add(self.finished, text)

    def finished(self, error: str | None) -> None:
        if error is None:
            self._client.get_module("OpenPGP").get_own_key_details()
            self._client.get_module("OpenPGP").set_public_key()
            self._client.get_module("OpenPGP").request_keylist()
            self._assistant.set_current_page(Page.SUCCESS)
        else:
            error_page = cast(ErrorPage, self._assistant.get_nth_page(Page.ERROR))
            error_page.set_text(error)
            self._assistant.set_current_page(Page.ERROR)


# class SaveBackupCodePage(RequestPage):

#     type_ = Gtk.AssistantPageType.PROGRESS
#     title = _('Save this code')
#     complete = False

#     def __init__(self):
#         super().__init__(orientation=Gtk.Orientation.VERTICAL)
#         self.set_spacing(18)
#         title_label = Gtk.Label(label=_('Backup Code'))
#         text_label = Gtk.Label(
#             label=_('This is your backup code, you need it if you reinstall Gajim'))
#         self.add(title_label)
#         self.add(text_label)


class SuccessfulPage(Gtk.Box):
    type_ = Gtk.AssistantPageType.SUMMARY
    title = _("Setup successful")
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(12)
        self.set_homogeneous(True)

        icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
        icon.add_css_class("success-color")
        icon.set_valign(Gtk.Align.END)
        label = Gtk.Label(label=_("Setup successful"))
        label.add_css_class("bold16")
        label.set_valign(Gtk.Align.START)

        self.append(icon)
        self.append(label)


class ErrorPage(Gtk.Box):
    type_ = Gtk.AssistantPageType.SUMMARY
    title = _("Setup failed")
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(12)
        self.set_homogeneous(True)

        icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        icon.get_style_context().add_class("error-color")
        icon.set_valign(Gtk.Align.END)
        self._label = Gtk.Label()
        self._label.get_style_context().add_class("bold16")
        self._label.set_valign(Gtk.Align.START)

        self.append(icon)
        self.append(self._label)

    def set_text(self, text: str) -> None:
        self._label.set_text(text)
