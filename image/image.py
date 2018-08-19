import os
import base64
import urllib

from gi.repository import Gtk
from gi.repository import Gdk

from gajim import chat_control
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.dialogs import ErrorDialog

try:
    from gajim.gtk.filechoosers import FileChooserDialog
    NEW_FILECHOOSER = True
except ImportError:
    from gajim.dialogs import ImageChooserDialog
    NEW_FILECHOOSER = False


NS_XHTML_IM = 'http://jabber.org/protocol/xhtml-im'


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
                    chat_control.encryption)
                if not is_support_xhtml:
                    text = _('This contact does not support XHTML_IM')
                else:
                    text = _('Send image (Alt+L)')
                base.button.set_tooltip_text(text)


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        actions_hbox = chat_control.xml.get_object('hbox')

        self.button = Gtk.Button(label=None, stock=None, use_underline=True)
        self.button.get_style_context().add_class(
            'chatcontrol-actionbar-button')
        self.button.set_property('relief', Gtk.ReliefStyle.NONE)
        self.button.set_property('can-focus', False)
        img = Gtk.Image()
        img.set_from_icon_name('image-x-generic-symbolic.symbolic',
            Gtk.IconSize.MENU)
        self.button.set_image(img)
        self.button.set_tooltip_text('Send image (Alt+L)')
        ag = Gtk.accel_groups_from_object(self.chat_control.parent_win.window)[0]
        self.button.add_accelerator('activate', ag, Gdk.KEY_L,
            Gdk.ModifierType.MOD1_MASK, Gtk.AccelFlags.VISIBLE)

        actions_hbox.pack_start(self.button, False, False , 0)
        actions_hbox.reorder_child(self.button,
            len(actions_hbox.get_children()) - 2)
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
        if NEW_FILECHOOSER:
            self._new_filechooser()
        else:
            self._old_filechooser(widget)

    def _new_filechooser(self):
        def on_ok(filename):
            image = self._check_file(filename)
            if image is None:
                return

            self._send(image, filename)

        FileChooserDialog(on_ok,
                          select_multiple=False,
                          transient_for=self.chat_control.parent_win.window)

    def _old_filechooser(self, widget):
        def on_ok(widget, path_to_file):
            image = self._check_file(path_to_file)
            if image is None:
                return

            dlg.destroy()

            self._send(image, path_to_file)

        dlg = ImageChooserDialog(on_response_ok=on_ok, on_response_cancel=None)

    def _check_file(self, filename):
        filesize = os.path.getsize(filename)  # in bytes
        invalid_file = False
        msg = ''
        if os.path.isfile(filename):
            stat = os.stat(filename)
            if stat[6] == 0:
                invalid_file = True
                msg = _('File is empty')
        else:
            invalid_file = True
            msg = _('File does not exist')
        if filesize < 60000:
            file_ = open(filename, "rb")
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
        return img

    def _send(self, image, filename):
        msg = 'HTML image'
        extension = os.path.splitext(os.path.split(filename)[1])[1] \
            .lower()[1:]
        xhtml = '<body><br/> <img alt="img" src="data:image/%s;base64,%s"/> \
                </body>' % (extension, image)
        self.chat_control.send_message(message=msg, xhtml=xhtml)
        self.chat_control.msg_textview.grab_focus()

    def disconnect_from_chat_control(self):
        actions_hbox = self.chat_control.xml.get_object('hbox')
        actions_hbox.remove(self.button)
