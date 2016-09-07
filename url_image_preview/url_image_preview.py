# -*- coding: utf-8 -*-

import gtk
import gobject
import re
import os
import sys
import hashlib
from urlparse import urlparse
from io import BytesIO
import shutil

import logging
import nbxmpp
import gtkgui_helpers
from common import gajim
from common import ged
from common import helpers
from common import configpaths
import dialogs
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from plugins.gui import GajimPluginConfigDialog
from conversation_textview import TextViewImage
from .http_functions import get_http_head, get_http_file

from common import demandimport
demandimport.enable()
demandimport.ignore += ['_imp']

log = logging.getLogger('gajim.plugin_system.url_image_preview')

try:
    from PIL import Image
except:
    log.debug('Pillow not available')

try:
    if os.name == 'nt':
        from cryptography.hazmat.backends.openssl import backend
    else:
        from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms
    from cryptography.hazmat.primitives.ciphers.modes import GCM
    decryption_available = True
except Exception as e:
    log.debug('Cryptography Import Error: ' + str(e))
    log.info('Decryption/Encryption disabled due to errors')
    decryption_available = False

ACCEPTED_MIME_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/raw',
                       'image/svg+xml', 'image/x-ms-bmp')


class UrlImagePreviewPlugin(GajimPlugin):
    @log_calls('UrlImagePreviewPlugin')
    def init(self):
        self.config_dialog = UrlImagePreviewPluginConfigDialog(self)
        self.events_handlers = {}
        self.events_handlers['message-received'] = (
            ged.PRECORE, self.handle_message_received)
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                  self.disconnect_from_chat_control),
            'print_special_text': (self.print_special_text, None), }
        self.config_default_values = {
            'PREVIEW_SIZE': (150, 'Preview size(10-512)'),
            'MAX_FILE_SIZE': (524288, 'Max file size for image preview')}
        self.controls = {}

    # remove oob tag if oob url == message text
    def handle_message_received(self, event):
        oob_node = event.stanza.getTag('x', namespace=nbxmpp.NS_X_OOB)
        oob_url = None
        oob_desc = None
        if oob_node:
            oob_url = oob_node.getTagData('url')
            oob_desc = oob_node.getTagData('desc')
            if oob_url and oob_url == event.msgtxt and \
                    (not oob_desc or oob_desc == ""):
                log.debug("Detected oob tag containing same"
                          "url as the message text, deleting oob tag...")
                event.stanza.delChild(oob_node)

    @log_calls('UrlImagePreviewPlugin')
    def connect_with_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid = chat_control.contact.jid
        if account not in self.controls:
            self.controls[account] = {}
        self.controls[account][jid] = Base(self, chat_control)

    @log_calls('UrlImagePreviewPlugin')
    def disconnect_from_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid = chat_control.contact.jid
        self.controls[account][jid].deinit()
        del self.controls[account][jid]

    def print_special_text(self, tv, special_text, other_tags, graphics=True,
                           iter_=None):
        account = tv.account
        for jid in self.controls[account]:
            if self.controls[account][jid].chat_control.conv_textview != tv:
                continue
            self.controls[account][jid].print_special_text(
                special_text, other_tags, graphics=True, iter_=iter_)
            return


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview
        self.handlers = {}
        if os.name == 'nt':
            self.backend = backend
        else:
            self.backend = default_backend()

        self.directory = os.path.join(configpaths.gajimpaths['MY_DATA'],
                                      'downloads')
        self.thumbpath = os.path.join(configpaths.gajimpaths['MY_CACHE'],
                                      'downloads.thumb')

        try:
            self._create_path(self.directory)
            self._create_path(self.thumbpath)
        except Exception as e:
            log.error("Error creating download and/or thumbnail folder!")
            raise

    def deinit(self):
        # remove all register handlers on wigets, created by self.xml
        # to prevent circular references among objects
        for i in list(self.handlers.keys()):
            if self.handlers[i].handler_is_connected(i):
                self.handlers[i].disconnect(i)
            del self.handlers[i]

    def print_special_text(self, special_text, other_tags, graphics=True,
                           iter_=None):
        # remove qip bbcode
        special_text = special_text.rsplit('[/img]')[0]

        if special_text.startswith('www.'):
            special_text = 'http://' + special_text
        if special_text.startswith('ftp.'):
            special_text = 'ftp://' + special_text

        urlparts = urlparse(special_text)
        if urlparts.scheme not in ["https", "http", "ftp", "ftps"] or \
                not urlparts.netloc:
            log.info("Not accepting URL for image preview: %s" % special_text)
            return

        buffer_ = self.textview.tv.get_buffer()
        if not iter_:
            iter_ = buffer_.get_end_iter()

        # Show URL, until image is loaded (if ever)
        ttt = buffer_.get_tag_table()
        repl_start = buffer_.create_mark(None, iter_, True)
        buffer_.insert_with_tags(iter_, special_text,
            *[(ttt.lookup(t) if isinstance(t, str) else t) for t in ["url"]])
        repl_end = buffer_.create_mark(None, iter_, True)

        filename = os.path.basename(urlparts.path)
        ext = os.path.splitext(filename)[1]
        name = os.path.splitext(filename)[0]
        namehash = hashlib.sha1(special_text).hexdigest()
        newfilename = name + '_' + namehash + ext
        thumbfilename = name + '_' + namehash + '_thumb' + ext

        filepath = os.path.join(self.directory, newfilename)
        thumbpath = os.path.join(self.thumbpath, thumbfilename)
        filepaths = [filepath, thumbpath]

        key = ''
        iv = ''
        encrypted = False
        if len(urlparts.fragment):
            fragment = []
            for i in range(0, len(urlparts.fragment), 2):
                fragment.append(chr(int(urlparts.fragment[i:i + 2], 16)))
            fragment = ''.join(fragment)
            key = fragment[16:]
            iv = fragment[:16]
            if len(key) == 32 and len(iv) == 16:
                encrypted = True

        # file exists but thumbnail got deleted
        if os.path.exists(filepath) and not os.path.exists(thumbpath):
            with open(filepath, 'rb') as f:
                mem = f.read()
                f.closed
            gajim.thread_interface(
                self._save_thumbnail, [thumbpath, (mem, '')],
                self._update_img, [special_text, repl_start,
                                    repl_end, filepath, encrypted])

        # display thumbnail if already downloaded (but only if file also exists)
        elif os.path.exists(filepath) and os.path.exists(thumbpath):
            gajim.thread_interface(
                self._load_thumbnail, [thumbpath],
                self._update_img, [special_text, repl_start,
                                    repl_end, filepath, encrypted])

        # or download file, calculate thumbnail and finally display it
        else:
            if encrypted and not decryption_available:
                log.debug('Please install Crytography to decrypt pictures')
            else:
                # First get the http head request
                # which does not fetch data, just headers
                # then check the mime type and filesize
                gajim.thread_interface(
                    get_http_head, [self.textview.account, special_text],
                    self._check_mime_size, [special_text, repl_start, repl_end,
                                            filepaths, key, iv, encrypted])

        # Don't print the URL in the message window (in the calling function)
        self.textview.plugin_modified = True

    def _save_thumbnail(self, thumbpath, (mem, alt)):
        size = self.plugin.config['PREVIEW_SIZE']
        use_gtk = False
        output = None

        try:
            output = BytesIO()
            im = Image.open(BytesIO(mem))
            im.thumbnail((size, size), Image.ANTIALIAS)
            im.save(output, "jpeg", quality=100, optimize=True)
        except Exception as e:
            if output:
                output.close()
            log.info("Failed to load image using pillow, falling back to gdk pixbuf.")
            log.debug(e)
            use_gtk = True

        if use_gtk:
            log.info("Pillow not available or file corrupt, trying to load using gdk pixbuf.")
            try:
                output = BytesIO()
                loader = gtk.gdk.PixbufLoader()
                loader.write(mem)
                loader.close()
                pixbuf = loader.get_pixbuf()
                pixbuf, w, h = self._get_pixbuf_of_size(pixbuf, size)
                def cb(buf, data=None):
                    output.write(buf)
                    return True
                pixbuf.save_to_callback(cb, "jpeg", {"quality": "100"})
            except Exception as e:
                if output:
                    output.close()
                log.info("Failed to load image using gdk pixbuf, ignoring image.")
                log.debug(e)
                return ('', '')

        mem = output.getvalue()
        output.close()
        try:
            self._create_path(os.path.dirname(thumbpath))
            self._write_file(thumbpath, mem)
        except Exception as e:
            dialogs.ErrorDialog(_('Could not save file'),
                                _('Exception raised while saving thumbnail for image file'
                                  ' (see error log for more information)'),
                                transient_for=self.chat_control.parent_win.window)
            log.error(str(e))
        return (mem, alt)

    def _load_thumbnail(self, thumbpath):
        with open(thumbpath, 'rb') as f:
            mem = f.read()
            f.closed
        return (mem, '')

    def _write_file(self, path, data):
        log.info("Writing '%s' of size %d..." % (path, len(data)))
        try:
            with open(path, "wb") as output_file:
                output_file.write(data)
                output_file.closed
        except Exception as e:
            log.error("Failed to write file '%s'!" % path)
            raise

    def _update_img(self, (mem, alt), url, repl_start, repl_end, filepath, encrypted):
        if mem:
            try:
                urlparts = urlparse(url)
                filename = os.path.basename(urlparts.path)
                eb = gtk.EventBox()
                eb.connect('button-press-event', self.on_button_press_event,
                           filepath, filename, url, encrypted)
                eb.connect('enter-notify-event', self.on_enter_event)
                eb.connect('leave-notify-event', self.on_leave_event)

                # this is threadsafe
                # (gtk textview is NOT threadsafe by itself!!)
                def add_to_textview():
                    try:        # textview closed in the meantime etc.
                        buffer_ = repl_start.get_buffer()
                        iter_ = buffer_.get_iter_at_mark(repl_start)
                        buffer_.insert(iter_, "\n")
                        anchor = buffer_.create_child_anchor(iter_)
                        # Use url as tooltip for image
                        img = TextViewImage(anchor, url)

                        loader = gtk.gdk.PixbufLoader()
                        loader.write(mem)
                        loader.close()
                        pixbuf = loader.get_pixbuf()
                        img.set_from_pixbuf(pixbuf)

                        eb.add(img)
                        eb.show_all()
                        self.textview.tv.add_child_at_anchor(eb, anchor)
                        buffer_.delete(iter_, buffer_.get_iter_at_mark(repl_end))
                    except:
                        pass
                    return False
                # add to mainloop --> make call threadsafe
                gobject.idle_add(add_to_textview)
            except Exception:
                # URL is already displayed
                log.error('Could not display image for URL: %s'
                          % url)
                raise
        else:
            # If image could not be downloaded, URL is already displayed
            log.error('Could not download image for URL: %s -- %s'
                      % (url, alt))

    def _check_mime_size(self, (file_mime, file_size),
                         url, repl_start, repl_end, filepaths,
                         key, iv, encrypted):
        # Check if mime type is acceptable
        if file_mime == '' and file_size == 0:
            log.info("Failed to load HEAD Request for URL: '%s'"
                     "(see debug log for more info)" % url)
            # URL is already displayed
            return
        if file_mime.lower() not in ACCEPTED_MIME_TYPES:
            log.info("Not accepted mime type '%s' for URL: '%s'"
                     % (file_mime.lower(), url))
            # URL is already displayed
            return
        # Check if file size is acceptable
        if file_size > self.plugin.config['MAX_FILE_SIZE'] or file_size == 0:
            log.info("File size (%s) too big or unknown (zero) for URL: '%s'"
                     % (str(file_size), url))
            # URL is already displayed
            return

        attributes = {'src': url,
                      'max_size': self.plugin.config['MAX_FILE_SIZE'],
                      'filepaths': filepaths,
                      'key': key,
                      'iv': iv}

        gajim.thread_interface(
            self._download_image, [self.textview.account,
                                   attributes, encrypted],
            self._update_img, [url, repl_start, repl_end, filepaths[0], encrypted])

    def _download_image(self, account, attributes, encrypted):
        filepath = attributes['filepaths'][0]
        thumbpath = attributes['filepaths'][1]
        key = attributes['key']
        iv = attributes['iv']
        mem, alt = get_http_file(account, attributes)

        # Decrypt file if necessary
        if encrypted:
            mem = self._aes_decrypt_fast(key, iv, mem)

        try:
            # Write file to harddisk
            self._write_file(filepath, mem)
        except Exception as e:
            dialogs.ErrorDialog(_('Could not save file'),
                            _('Exception raised while saving image file'
                              ' (see error log for more information)'),
                            transient_for=self.chat_control.parent_win.window)
            log.error(str(e))

        # Create thumbnail, write it to harddisk and return it
        return self._save_thumbnail(thumbpath, (mem, alt))

    def _create_path(self, folder):
        if os.path.exists(folder):
            return
        log.debug("creating folder '%s'" % folder)
        os.mkdir(folder, 0700)

    def _aes_decrypt_fast(self, key, iv, payload):
        # Use AES128 GCM with the given key and iv to decrypt the payload.
        data = payload[:-16]
        tag = payload[-16:]
        decryptor = Cipher(
            algorithms.AES(key),
            GCM(iv, tag=tag),
            backend=self.backend).decryptor()
        return decryptor.update(data) + decryptor.finalize()

    def _get_pixbuf_of_size(self, pixbuf, size):
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

    def make_rightclick_menu(self, event, filepath, original_filename, url, encrypted):
        xml = gtk.Builder()
        xml.set_translation_domain('gajim_plugins')
        xml.add_from_file(self.plugin.local_file_path('context_menu.ui'))
        menu = xml.get_object('context_menu')

        open_menuitem = xml.get_object('open_menuitem')
        save_as_menuitem = xml.get_object('save_as_menuitem')
        copy_link_location_menuitem = xml.get_object('copy_link_location_menuitem')
        open_link_in_browser_menuitem = xml.get_object('open_link_in_browser_menuitem')

        if encrypted:
            open_link_in_browser_menuitem.hide()

        id_ = open_menuitem.connect('activate', self.on_open_menuitem_activate, filepath)
        self.handlers[id_] = open_menuitem
        id_ = save_as_menuitem.connect('activate', self.on_save_as_menuitem_activate,
                    filepath, original_filename)
        self.handlers[id_] = save_as_menuitem
        id_ = copy_link_location_menuitem.connect('activate',
                    self.on_copy_link_location_menuitem_activate, url)
        self.handlers[id_] = copy_link_location_menuitem
        id_ = open_link_in_browser_menuitem.connect('activate',
                    self.on_open_link_in_browser_menuitem_activate, url)
        self.handlers[id_] = open_link_in_browser_menuitem

        return menu

    def on_open_menuitem_activate(self, menu, filepath):
        helpers.launch_file_manager(filepath)

    def on_save_as_menuitem_activate(self, menu, filepath, original_filename):
        def on_continue(response, target_path):
            if response < 0:
                return
            shutil.copy(filepath, target_path)
            dialog.destroy()

        def on_ok(widget):
            target_path = dialog.get_filename()
            if os.path.exists(target_path):
                # check if we have write permissions
                if not os.access(target_path, os.W_OK):
                    file_name = os.path.basename(target_path)
                    dialogs.ErrorDialog(_('Cannot overwrite existing file "%s"') % \
                        file_name, _('A file with this name already exists and you '
                        'do not have permission to overwrite it.'))
                    return
                dialog2 = dialogs.FTOverwriteConfirmationDialog(
                    _('This file already exists'), _('What do you want to do?'),
                    propose_resume=False, on_response=(on_continue, target_path),
                    transient_for=dialog)
                dialog2.set_destroy_with_parent(True)
            else:
                dirname = os.path.dirname(target_path)
                if not os.access(dirname, os.W_OK):
                    dialogs.ErrorDialog(_('Directory "%s" is not writable') % \
                        dirname, _('You do not have permission to create files in '
                        'this directory.'))
                    return
                on_continue(0, target_path)

        def on_cancel(widget):
            dialog.destroy()

        dialog = dialogs.FileChooserDialog(title_text=_('Save Image as...'),
            action=gtk.FILE_CHOOSER_ACTION_SAVE, buttons=(gtk.STOCK_CANCEL,
            gtk.RESPONSE_CANCEL, gtk.STOCK_SAVE, gtk.RESPONSE_OK),
            default_response=gtk.RESPONSE_OK,
            current_folder=gajim.config.get('last_save_dir'), on_response_ok=on_ok,
            on_response_cancel=on_cancel)

        dialog.set_current_name(original_filename)
        dialog.connect('delete-event', lambda widget, event:
            on_cancel(widget))

    def on_copy_link_location_menuitem_activate(self, menu, url):
        clipboard = gtk.Clipboard()
        clipboard.set_text(url)

    def on_open_link_in_browser_menuitem_activate(self, menu, url):
        helpers.launch_file_manager(url)

    # Change mouse pointer to HAND2 when
    # mouse enter the eventbox with the image
    def on_enter_event(self, eb, event):
        self.textview.tv.get_window(
            gtk.TEXT_WINDOW_TEXT).set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))

    # Change mouse pointer to default when mouse leaves the eventbox
    def on_leave_event(self, eb, event):
        self.textview.tv.get_window(
            gtk.TEXT_WINDOW_TEXT).set_cursor(gtk.gdk.Cursor(gtk.gdk.XTERM))

    def on_button_press_event(self, eb, event, filepath,
                            original_filename, url, encrypted):
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 1:     # left click
            helpers.launch_file_manager(filepath)
        elif event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:   #right klick
            menu = self.make_rightclick_menu(event, filepath,
                            original_filename, url, encrypted)
            #menu.attach_to_widget(self.tv, None)
            menu.popup(None, None, None, event.button, event.time)

    def disconnect_from_chat_control(self):
        pass


class UrlImagePreviewPluginConfigDialog(GajimPluginConfigDialog):
    max_file_size = [262144, 524288, 1048576, 5242880, 10485760]

    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, [
            'vbox1', 'liststore1'])
        self.preview_size_spinbutton = self.xml.get_object('preview_size')
        self.preview_size_spinbutton.get_adjustment().set_all(20, 10, 512, 1,
                                                              10, 0)
        self.max_size_combobox = self.xml.get_object('max_size_combobox')
        vbox = self.xml.get_object('vbox1')
        self.child.pack_start(vbox)

        self.xml.connect_signals(self)

    def on_run(self):
        self.preview_size_spinbutton.set_value(self.plugin.config[
            'PREVIEW_SIZE'])
        value = self.plugin.config['MAX_FILE_SIZE']
        if value:
            # this fails if we upgrade from an old version
            # which has other file size values than we have now
            try:
                self.max_size_combobox.set_active(
                    self.max_file_size.index(value))
            except:
                pass
        else:
            self.max_size_combobox.set_active(-1)

    def preview_size_value_changed(self, spinbutton):
        self.plugin.config['PREVIEW_SIZE'] = spinbutton.get_value()

    def max_size_value_changed(self, widget):
        self.plugin.config['MAX_FILE_SIZE'] = self.max_file_size[
            self.max_size_combobox.get_active()]
