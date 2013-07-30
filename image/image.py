# -*- coding: utf-8 -*-
##
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
import os
import base64
import urllib

import chat_control
from plugins import GajimPlugin
from plugins.helpers import log_calls
from dialogs import ImageChooserDialog, ErrorDialog

NS_XHTML_IM = 'http://jabber.org/protocol/xhtml-im'             # XEP-0071


class ImagePlugin(GajimPlugin):
    @log_calls('ImagePlugin')
    def init(self):
        self.description = _('This plugin is designed to send '
            'a small(0 - 40 kb) graphic image to your contact.\n'
            'Client on the other side must support XEP-0071: XHTML-IM'
            ' and maintain the scheme data: URI.\n'
            'Psi+ and Jabbim supported this.')
        self.config_dialog = None  # ImagePluginConfigDialog(self)
        self.controls = []
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (self.update_button_state,
                None)}
        self.first_run = True

    @log_calls('ImagePlugin')
    def connect_with_chat_control(self, control):
        if not isinstance(control, chat_control.ChatControl):
            return
        self.chat_control = control
        base = Base(self, self.chat_control)
        self.controls.append(base)

    @log_calls('ImagePlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    @log_calls('ImagePlugin')
    def update_button_state(self, chat_control):
        for base in self.controls:
            if base.chat_control == chat_control:
                is_support_xhtml = chat_control.contact.supports(NS_XHTML_IM)
                base.button.set_sensitive(is_support_xhtml and not \
                    chat_control.gpg_is_active)
                if not is_support_xhtml:
                    text = _('This contact does not support XHTML_IM')
                else:
                    text = _('Send image (Alt+L)')
                base.button.set_tooltip_text(text)


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        actions_hbox = chat_control.xml.get_object('actions_hbox')

        self.button = Gtk.Button(label=None, stock=None, use_underline=True)
        self.button.set_property('relief', Gtk.ReliefStyle.NONE)
        self.button.set_property('can-focus', False)
        img = Gtk.Image()
        img.set_from_stock('gtk-orientation-portrait', Gtk.IconSize.MENU)
        self.button.set_image(img)
        self.button.set_tooltip_text('Send image (Alt+L)')
        ag = Gtk.accel_groups_from_object(self.chat_control.parent_win.window)[0]
        self.button.add_accelerator('activate', ag, Gdk.KEY_L,
            Gdk.ModifierType.MOD1_MASK, Gtk.AccelFlags.VISIBLE)
        send_button = chat_control.xml.get_object('send_button')

        actions_hbox.pack_start(self.button, False, False , 0)
        actions_hbox.reorder_child(self.button,
            len(actions_hbox.get_children()) - 3)
        id_ = self.button.connect('clicked', self.on_image_button_clicked)
        self.button.show()

    def _on_message_textview_key_press_event(self, widget, event):
        if event.get_state() & Gdk.ModifierType.MOD1_MASK and \
            event.keyval == Gdk.KEY_l:
            if not self.chat_control.contact.supports(NS_XHTML_IM):
                from dialogs import WarningDialog
                WarningDialog('Warning',
                    _('This contact does not support XHTML_IM'),
                    self.chat_control.parent_win.window)
                return True
            self.on_image_button_clicked(widget)
            return True

    def on_image_button_clicked(self, widget):
        def on_ok(widget, path_to_file):
            filesize = os.path.getsize(path_to_file)  # in bytes
            invalid_file = False
            msg = ''
            if os.path.isfile(path_to_file):
                stat = os.stat(path_to_file)
                if stat[6] == 0:
                    invalid_file = True
                    msg = _('File is empty')
            else:
                invalid_file = True
                msg = _('File does not exist')
            if filesize < 60000:
                file_ = open(path_to_file, "rb")
                img = urllib.parse.quote(base64.standard_b64encode(
                    file_.read()), '')
                if len(img) > 60000:
                    invalid_file = True
                    msg = _('File too big')
                file_.close()
            else:
                invalid_file = True
                msg = _('File too big')
            if invalid_file:
                ErrorDialog(_('Could not load image'), msg)
                return

            dlg.destroy()
            msg = 'HTML image'
            extension = os.path.splitext(os.path.split(path_to_file)[1])[1] \
                .lower()[1:]
            xhtml = ' <img alt="img" src="data:image/%s;base64,%s"/>' % (
                extension, img)
            self.chat_control.send_message(message=msg, xhtml=xhtml)
            self.chat_control.msg_textview.grab_focus()

        dlg = ImageChooserDialog(on_response_ok=on_ok, on_response_cancel=None)

    def disconnect_from_chat_control(self):
        actions_hbox = self.chat_control.xml.get_object('actions_hbox')
        actions_hbox.remove(self.button)
