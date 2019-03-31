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
import threading
import string
import random
from textwrap import wrap
from enum import IntEnum

from gi.repository import Gtk
from gi.repository import GLib

from gajim.common import app
from gajim.plugins.plugins_i18n import _

log = logging.getLogger('gajim.p.openpgp.wizard')


class Page(IntEnum):
    WELCOME = 0
    FOUND_KEY = 1
    NEWKEY = 2
    SAVE_KEY = 3
    SUCCESS = 4
    ERROR = 5


class KeyWizard(Gtk.Assistant):
    def __init__(self, plugin, account, chat_control):
        Gtk.Assistant.__init__(self)

        self._con = app.connections[account]
        self._plugin = plugin
        self._account = account
        self._data_form_widget = None
        self._is_form = None
        self._chat_control = chat_control
        self.backup_code = None

        self.set_application(app.app)
        self.set_transient_for(chat_control.parent_win.window)
        self.set_resizable(True)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.set_default_size(600, 400)
        self.get_style_context().add_class('dialog-margin')

        self._add_page(WelcomePage())
        self._add_page(FoundKeyPage())
        self._add_page(NewKeyPage(self, self._con))
        self._add_page(SaveBackupCodePage())
        self._add_page(SuccessfulPage())
        self._add_page(ErrorPage())

        self.connect('prepare', self._on_page_change)
        self.connect('cancel', self._on_cancel)
        self.connect('close', self._on_cancel)

        self._remove_sidebar()
        self.show_all()

    def _add_page(self, page):
        self.append_page(page)
        self.set_page_type(page, page.type_)
        self.set_page_title(page, page.title)
        self.set_page_complete(page, page.complete)

    def set_backup_code(self, backup_code):
        save_key_page = self.get_nth_page(Page.SAVE_KEY)
        save_key_page.set_backup_code(backup_code)

    def _remove_sidebar(self):
        main_box = self.get_children()[0]
        sidebar = main_box.get_children()[0]
        main_box.remove(sidebar)

    def _activate_encryption(self):
        win = self._chat_control.parent_win.window
        action = win.lookup_action(
            'set-encryption-%s' % self._chat_control.control_id)
        action.activate(GLib.Variant("s", self._plugin.encryption_name))

    def _on_page_change(self, assistant, page):
        if self.get_current_page() == Page.NEWKEY:
            if self._con.get_module('OpenPGP').secret_key_available:
                self.set_current_page(Page.SUCCESS)
            else:
                page.generate()
        elif self.get_current_page() == Page.SUCCESS:
            self._activate_encryption()

    def _on_error(self, error_text):
        log.info('Show Error page')
        page = self.get_nth_page(Page.ERROR)
        page.set_text(error_text)
        self.set_current_page(Page.ERROR)

    def _on_cancel(self, widget):
        self.destroy()


class WelcomePage(Gtk.Box):

    type_ = Gtk.AssistantPageType.INTRO
    title = _('Welcome')
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(18)
        title_label = Gtk.Label(label=_('Setup OpenPGP'))
        text_label = Gtk.Label(
            label=_('Gajim will now try to setup OpenPGP for you'))
        self.add(title_label)
        self.add(text_label)


class RequestPage(Gtk.Box):

    type_ = Gtk.AssistantPageType.INTRO
    title = _('Request OpenPGP Key')
    complete = False

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(18)
        spinner = Gtk.Spinner()
        self.pack_start(spinner, True, True, 0)
        spinner.start()


class FoundKeyPage(Gtk.Box):

    type_ = Gtk.AssistantPageType.INTRO
    title = _('Supply Backup Code')
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(18)
        title_label = Gtk.Label(label=_('Backup Code'))
        text_label = Gtk.Label(
            label=_('We found a backup Code, please supply your password'))
        self.add(title_label)
        self.add(text_label)
        entry = Gtk.Entry()
        self.add(entry)


class NewKeyPage(RequestPage):

    type_ = Gtk.AssistantPageType.PROGRESS
    title = _('Generating new Key')
    complete = False

    def __init__(self, assistant, con):
        super().__init__()
        self._assistant = assistant
        self._con = con

    def generate(self):
        log.info('Creating Key')
        thread = threading.Thread(target=self.worker)
        thread.start()

    def worker(self):
        error = None
        try:
            self._con.get_module('OpenPGP').generate_key()
        except Exception as e:
            error = e

        GLib.idle_add(self.finished, error)

    @staticmethod
    def generate_backup_code():
        range_ = '123456789ABCDEFGHIJKLMNPQRSTUVWXYZ'
        code = ''.join(random.choice(range_) for x in range(24))
        return '-'.join(wrap(code.upper(), 4))

    def finished(self, error):
        if error is not None:
            log.error(error)
            self._assistant.set_current_page(Page.ERROR)
            return

        self._con.get_module('OpenPGP').get_own_key_details()
        if not self._con.get_module('OpenPGP').secret_key_available:
            log.error('PGP Error')
            self._assistant.set_current_page(Page.ERROR)
            return

        backup_code = self.generate_backup_code()
        self._assistant.set_backup_code(backup_code)
        self._con.get_module('OpenPGP').set_public_key()
        self._con.get_module('OpenPGP').request_keylist()
        self._con.get_module('OpenPGP').set_secret_key(backup_code)
        self._assistant.set_current_page(Page.SAVE_KEY)


class SaveBackupCodePage(Gtk.Box):

    type_ = Gtk.AssistantPageType.SUMMARY
    title = _('Save this code')
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(18)
        title_label = Gtk.Label(label=_('Backup Code'))
        text_label = Gtk.Label(
            label=_('This is your backup code, you need it if you reinstall Gajim'))
        self._code_label = Gtk.Label()
        self._code_label.set_selectable(True)

        icon = Gtk.Image.new_from_icon_name('object-select-symbolic',
                                            Gtk.IconSize.DIALOG)
        icon.get_style_context().add_class('success-color')
        icon.set_valign(Gtk.Align.END)

        self.add(icon)
        self.add(title_label)
        self.add(text_label)
        self.add(self._code_label)

    def set_backup_code(self, backup_code):
        self._code_label.set_label(backup_code)


class SuccessfulPage(Gtk.Box):

    type_ = Gtk.AssistantPageType.SUMMARY
    title = _('Setup successful')
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(12)
        self.set_homogeneous(True)

        icon = Gtk.Image.new_from_icon_name('object-select-symbolic',
                                            Gtk.IconSize.DIALOG)
        icon.get_style_context().add_class('success-color')
        icon.set_valign(Gtk.Align.END)
        label = Gtk.Label(label=_('Setup successful'))
        label.get_style_context().add_class('bold16')
        label.set_valign(Gtk.Align.START)

        self.add(icon)
        self.add(label)


class ErrorPage(Gtk.Box):

    type_ = Gtk.AssistantPageType.SUMMARY
    title = _('Registration failed')
    complete = True

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_spacing(12)
        self.set_homogeneous(True)

        icon = Gtk.Image.new_from_icon_name('dialog-error-symbolic',
                                            Gtk.IconSize.DIALOG)
        icon.get_style_context().add_class('error-color')
        icon.set_valign(Gtk.Align.END)
        self._label = Gtk.Label()
        self._label.get_style_context().add_class('bold16')
        self._label.set_valign(Gtk.Align.START)

        self.add(icon)
        self.add(self._label)

    def set_text(self, text):
        self._label.set_text(text)
