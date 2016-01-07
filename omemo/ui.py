# -*- coding: utf-8 -*-
#
# Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright 2015 Daniel Gultsch <daniel@cgultsch.de>
#
# This file is part of Gajim-OMEMO plugin.
#
# The Gajim-OMEMO plugin is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Gajim-OMEMO is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# the Gajim-OMEMO plugin.  If not, see <http://www.gnu.org/licenses/>.
#

import logging

import gtk

log = logging.getLogger('gajim.plugin_system.omemo')

# from plugins.helpers import log


class PreKeyButton(gtk.Button):
    def __init__(self, plugin, contact):
        super(PreKeyButton, self).__init__(label='Get Device Keys' + str(
            plugin.are_keys_missing(contact)))
        self.plugin = plugin
        self.contact = contact
        self.connect('clicked', self.on_click)
        self.refresh()

    def refresh(self):
        amount = self.plugin.are_keys_missing(self.contact)
        if amount == 0:
            self.set_no_show_all(True)
            self.hide()
        else:
            self.set_no_show_all(False)
            self.show()
        self.set_label('Get Device Keys ' + str(amount))

    def on_click(self, widget):
        self.plugin.query_prekey(self.contact)


class ClearDevicesButton(gtk.Button):
    def __init__(self, plugin, contact):
        super(ClearDevicesButton, self).__init__(label='Clear Devices')
        self.plugin = plugin
        self.contact = contact
        self.connect('clicked', self.on_click)

    def on_click(self, widget):
        self.plugin.clear_device_list(self.contact)


class Checkbox(gtk.CheckButton):
    def __init__(self, plugin, chat_control):
        super(Checkbox, self).__init__(label='OMEMO')
        self.chat_control = chat_control
        self.contact = chat_control.contact
        self.plugin = plugin
        self.connect('clicked', self.on_click)

    def on_click(self, widget):
        enabled = self.get_active()
        log.info('Clicked ' + str(enabled))
        if enabled:
            self.plugin.omemo_enable_for(self.contact)
            self.chat_control._show_lock_image(True, 'OMEMO', True, True, False)
            self.chat_control.print_conversation_line(
                u'\U0001F512 OMEMO encryption enabled ', 'status', '', None)
        else:
            self.plugin.omemo_disable_for(self.contact)
            self.chat_control._show_lock_image(False, 'OMEMO', False, True,
                                               False)
            self.chat_control.print_conversation_line(
                u'\U0001F513 OMEMO encryption disabled', 'status', '', None)


def _add_widget(widget, chat_control):
    actions_hbox = chat_control.xml.get_object('actions_hbox')
    send_button = chat_control.xml.get_object('send_button')
    send_button_pos = actions_hbox.child_get_property(send_button, 'position')
    actions_hbox.add_with_properties(widget, 'position', send_button_pos - 2,
                                     'expand', False)
    widget.show_all()


class Ui(object):

    def __init__(self, plugin, chat_control, enabled):
        contact = chat_control.contact
        self.prekey_button = PreKeyButton(plugin, contact)
        self.checkbox = Checkbox(plugin, chat_control)
        self.clear_button = ClearDevicesButton(plugin, contact)

        self.checkbox.set_active(enabled)
        self.chat_control = chat_control

        _add_widget(self.prekey_button, chat_control)
        _add_widget(self.checkbox, chat_control)
        _add_widget(self.clear_button, chat_control)

    def encryption_active(self):
        return self.checkbox.get_active()

    def encryption_disable(self):
        return self.checkbox.set_active(False)

    def activate_omemo(self):
        if not self.checkbox.get_active():
            self.checkbox.set_active(True)

    def plain_warning(self):
        self.chat_control.print_conversation_line(
            'Received plaintext message! ' +
            'Your next message will still be encrypted!', 'status', '', None)

    def update_prekeys(self):
        self.prekey_button.refresh()
