# -*- coding: utf-8 -*-

import gtk
import re
import os

import urllib
import gobject

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls
from plugins.gui import GajimPluginConfigDialog
from conversation_textview import TextViewImage

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
        self.conn.close()

    def print_special_text(self, tv, special_text, other_tags, graphics=True):
        for control in self.controls:
            if control.chat_control.conv_textview != tv:
                continue
            control.print_special_text(special_text, other_tags, graphics=True)

    def print_special_text1(self, chat_control, special_text, other_tags=None,
        graphics=True):
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
        if not gajim.interface.basic_pattern_re.match(special_text):
            return

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
        gobject.idle_add(self.insert_pic_preview, mark, special_text, special_text)

    def insert_pic_preview(self, mark, special_text, url):
        pixbuf = self.get_pixbuf_from_url( url, self.plugin.config[
            'PREVIEW_SIZE'])
        if pixbuf:
            # insert image
            buffer_ = mark.get_buffer()
            end_iter = buffer_.get_iter_at_mark(mark)
            anchor = buffer_.create_child_anchor(end_iter)
            img = TextViewImage(anchor, special_text)
            img.set_from_pixbuf(pixbuf)
            img.show()
            self.textview.tv.add_child_at_anchor(img, anchor)


    def get_pixbuf_from_url(self, url, size):
        # download image and resize
        # Returns pixbuf or False if broken image or not connected
        try:
            data = urllib.urlopen(url).read()
            pix = gtk.gdk.PixbufLoader()
            pix.write(data)
            pix.close()
            pixbuf = pix.get_pixbuf()
            pixbuf, w, h = self.get_pixbuf_of_size(pixbuf, size)
        except:
            return False
        return pixbuf

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
            gtk.gdk.INTERP_BILINEAR)
        return (crop_pixbuf, image_width, image_height)

    def disconnect_from_chat_control(self):
        pass


class UrlImagePreviewPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.preview_size_spinbutton = self.xml.get_object('preview_size')
        self.preview_size_spinbutton.get_adjustment().set_all(20, 10, 512, 1,
            10, 0)
        vbox = self.xml.get_object('vbox1')
        self.child.pack_start(vbox)

        self.xml.connect_signals(self)

    def on_run(self):
        self.preview_size_spinbutton.set_value(self.plugin.config[
            'PREVIEW_SIZE'])


    def preview_size_value_changed(self, spinbutton):
        self.plugin.config['PREVIEW_SIZE'] = spinbutton.get_value()
