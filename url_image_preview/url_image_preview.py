# -*- coding: utf-8 -*-

from gi.repository import Gtk
from gi.repository import GdkPixbuf
import re
import os

from gajim.common import app
from gajim.common import helpers
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.conversation_textview import TextViewImage

EXTENSIONS = ('.png','.jpg','.jpeg','.gif','.raw','.svg')


class UrlImagePreviewPlugin(GajimPlugin):
    @log_calls('UrlImagePreviewPlugin')
    def init(self):
        self.description = _('Url image preview in chatbox.\n'
            'Based on patch in ticket #5300:\n'
            'http://trac.gajim.org/attachment/ticket/5300.')
        self.config_dialog = UrlImagePreviewPluginConfigDialog(self)
        self.gui_extension_points = {
                'chat_control_base': (self.connect_with_chat_control,
                                       self.disconnect_from_chat_control),
                'print_special_text': (self.print_special_text,
                                       self.print_special_text1),}
        self.config_default_values = {
                    'PREVIEW_SIZE': (150, 'Preview size(10-512)'),}
        self.chat_control = None
        self.controls = []

    @log_calls('UrlImagePreviewPlugin')
    def connect_with_chat_control(self, chat_control):

        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)

    @log_calls('UrlImagePreviewPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    def print_special_text(self, tv, special_text, other_tags, graphics=True,
            additional_data={}):
        for control in self.controls:
            if control.chat_control.conv_textview != tv:
                continue
            control.print_special_text(special_text, other_tags, graphics=True)

    def print_special_text1(self, chat_control, special_text, other_tags=None,
        graphics=True, additional_data={}):
        for control in self.controls:
            if control.chat_control == chat_control:
                control.disconnect_from_chat_control()
                self.controls.remove(control)

class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview

    def print_special_text(self, special_text, other_tags, graphics=True):
        if not app.interface.basic_pattern_re.match(special_text):
            return
        # remove qip bbcode
        special_text = special_text.rsplit('[/img]')[0]

        name, extension = os.path.splitext(special_text)
        if extension.lower() not in EXTENSIONS:
            return
        if not special_text.startswith('http://') and \
        special_text.startswith('www.'):
            special_text = 'http://' + special_text
        if not special_text.startswith('ftp://') and \
        special_text.startswith('ftp.'):
            special_text = 'ftp://' + special_text

        # show pics preview
        buffer_ = self.textview.tv.get_buffer()
        iter_ = buffer_.get_end_iter()
        mark = buffer_.create_mark(None, iter_, True)
        # start downloading image
        app.thread_interface(helpers.download_image, [
            self.textview.account, {'src': special_text}], self._update_img,
            [mark])

    def _update_img(self, mem_alt, mark):
        mem, alt = mem_alt
        if mem:
            try:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(mem)
                loader.close()
                pixbuf = loader.get_pixbuf()
                pixbuf, w, h = self.get_pixbuf_of_size(pixbuf,
                    self.plugin.config['PREVIEW_SIZE'])
                buffer_ = mark.get_buffer()
                end_iter = buffer_.get_iter_at_mark(mark)
                anchor = buffer_.create_child_anchor(end_iter)
                img = TextViewImage(anchor, alt)
                img.set_from_pixbuf(pixbuf)
                img.show()
                self.textview.tv.add_child_at_anchor(img, anchor)
            except Exception:
                pass

    def get_pixbuf_of_size(self, pixbuf, size):
        # Creates a pixbuf that fits in the specified square of sizexsize
        # while preserving the aspect ratio
        # Returns tuple: (scaled_pixbuf, actual_width, actual_height)
        image_width = pixbuf.get_width()
        image_height = pixbuf.get_height()

        if image_width > image_height:
            if image_width > size:
                image_height = int(size / float(image_width) * image_height)
                image_width = int(size)
        else:
            if image_height > size:
                image_width = int(size / float(image_height) * image_width)
                image_height = int(size)

        crop_pixbuf = pixbuf.scale_simple(image_width, image_height,
            GdkPixbuf.InterpType.BILINEAR)
        return (crop_pixbuf, image_width, image_height)

    def disconnect_from_chat_control(self):
        pass


class UrlImagePreviewPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.preview_size_spinbutton = self.xml.get_object('preview_size')
        adjustment = Gtk.Adjustment(value=20,
                                    lower=10,
                                    upper=512,
                                    step_increment=1,
                                    page_increment=10,
                                    page_size=0)
        self.preview_size_spinbutton.set_adjustment(adjustment)
        vbox = self.xml.get_object('vbox1')
        self.get_child().pack_start(vbox, True, True, 0)

        self.xml.connect_signals(self)

    def on_run(self):
        self.preview_size_spinbutton.set_value(self.plugin.config[
            'PREVIEW_SIZE'])


    def preview_size_value_changed(self, spinbutton):
        self.plugin.config['PREVIEW_SIZE'] = spinbutton.get_value()
