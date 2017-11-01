# -*- coding: utf-8 -*-
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##

from gi.repository import Gtk, Gdk, GLib, GObject, GdkPixbuf, Gio
import os
import hashlib
import binascii
from urllib.parse import urlparse
from io import BytesIO
import shutil
from functools import partial

import logging
import nbxmpp
from gajim.common import app
from gajim.common import ged
from gajim.common import helpers
from gajim.common import configpaths
from gajim import dialogs
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.conversation_textview import TextViewImage
from .http_functions import get_http_head, get_http_file
from .config_dialog import UrlImagePreviewConfigDialog

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
    DEP_MSG = 'For preview of encrypted images, ' \
              'please install python-cryptography!'
    log.debug('Cryptography Import Error: ' + str(e))
    log.info('Decryption/Encryption disabled due to errors')
    decryption_available = False

ACCEPTED_MIME_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/raw',
                       'image/svg+xml', 'image/x-ms-bmp')


class UrlImagePreviewPlugin(GajimPlugin):
    @log_calls('UrlImagePreviewPlugin')
    def init(self):
        if not decryption_available:
            self.available_text = DEP_MSG
        self.config_dialog = partial(UrlImagePreviewConfigDialog, self)
        self.events_handlers = {}
        self.events_handlers['message-received'] = (
            ged.PRECORE, self.handle_message_received)
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                  self.disconnect_from_chat_control),
            'print_special_text': (self.print_special_text, None), }
        self.config_default_values = {
            'PREVIEW_SIZE': (150, 'Preview size(10-512)'),
            'MAX_FILE_SIZE': (524288, 'Max file size for image preview'),
            'LEFTCLICK_ACTION': ('open_menuitem', 'Open')}
        self.controls = {}

    # remove oob tag if oob url == message text
    def handle_message_received(self, event):
        oob_node = event.stanza.getTag('x', namespace=nbxmpp.NS_X_OOB)
        oob_url = None
        oob_desc = None
        if oob_node:
            oob_url = oob_node.getTagData('url')
            oob_desc = oob_node.getTagData('desc')
            if (oob_url and oob_url == event.msgtxt and
                    (not oob_desc or oob_desc == "")):
                log.debug("Detected oob tag containing same"
                          "url as the message text, deleting oob tag...")
                event.stanza.delChild(oob_node)
                event.additional_data["url_image_preview"] = {"oob": True}

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

    def print_special_text(self, tv, special_text, other_tags, graphics,
                           additional_data, iter_):
        account = tv.account
        for jid in self.controls[account]:
            if self.controls[account][jid].chat_control.conv_textview != tv:
                continue
            self.controls[account][jid].print_special_text(
                special_text, other_tags, graphics=graphics,
                additional_data=additional_data, iter_=iter_)
            return


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview
        self.handlers = {}

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

    def print_special_text(self, special_text, other_tags, graphics,
                           additional_data, iter_):
        
        urlparts = urlparse(special_text)
        if (urlparts.scheme not in ["https", "aesgcm"] or
                not urlparts.netloc):
            log.info("Not accepting URL scheme '%s' for image preview: %s" %
                     (str(urlparts.scheme), special_text))
            return

        # allow aesgcm uris without oob marker (aesgcm uris are always
        # httpupload filetransfers)
        if (urlparts.scheme != "aesgcm" and (
                not "url_image_preview" in additional_data or
                not "oob" in additional_data["url_image_preview"] or
                not additional_data["url_image_preview"]["oob"])):
            log.info("Not accepting URL for image preview"
                " (no oob marker given in additional_data): %s" % special_text)
            log.debug("additional_data: %s" % str(additional_data))
            return

        # Don't print the URL in the message window (in the calling function)
        self.textview.plugin_modified = True

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
        namehash = hashlib.sha1(special_text.encode('utf-8')).hexdigest()
        newfilename = name + '_' + namehash + ext
        thumbfilename = name + '_' + namehash + '_thumb_' \
            + str(self.plugin.config['PREVIEW_SIZE']) + ext

        filepath = os.path.join(self.directory, newfilename)
        thumbpath = os.path.join(self.thumbpath, thumbfilename)
        filepaths = [filepath, thumbpath]

        key = ''
        iv = ''
        encrypted = False
        if urlparts.fragment:
            fragment = binascii.unhexlify(urlparts.fragment)
            key = fragment[16:]
            iv = fragment[:16]
            if len(key) == 32 and len(iv) == 16:
                encrypted = True
            if not encrypted:
                key = fragment[12:]
                iv = fragment[:12]
                if len(key) == 32 and len(iv) == 12:
                    encrypted = True
        
        # file exists but thumbnail got deleted
        if os.path.exists(filepath) and not os.path.exists(thumbpath):
            with open(filepath, 'rb') as f:
                mem = f.read()
                f.closed
            app.thread_interface(
                self._save_thumbnail, [thumbpath, (mem, '')],
                self._update_img, [special_text, repl_start,
                                   repl_end, filepath, encrypted])

        # display thumbnail if already downloadeded
        # (but only if file also exists)
        elif os.path.exists(filepath) and os.path.exists(thumbpath):
            app.thread_interface(
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
                if urlparts.scheme == 'aesgcm':
                    special_text = 'https://' + special_text[9:]
                app.thread_interface(
                    get_http_head, [self.textview.account, special_text],
                    self._check_mime_size, [special_text, repl_start, repl_end,
                                            filepaths, key, iv, encrypted])

    def _save_thumbnail(self, thumbpath, tuple_arg):
        mem, alt = tuple_arg
        size = self.plugin.config['PREVIEW_SIZE']
        use_Gtk = False
        output = None

        try:
            output = BytesIO()
            im = Image.open(BytesIO(mem))
            im.thumbnail((size, size), Image.ANTIALIAS)
            im.save(output, "jpeg", quality=100, optimize=True)
            mem = output.getvalue()
            output.close()
        except Exception as e:
            if output:
                output.close()
            log.info("Failed to load image using pillow, "
                     "falling back to gdk pixbuf.")
            log.debug(e)
            use_Gtk = True

        if use_Gtk:
            log.info("Pillow not available or file corrupt, "
                     "trying to load using gdk pixbuf.")
            try:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(mem)
                loader.close()
                pixbuf = loader.get_pixbuf()
                pixbuf, w, h = self._get_pixbuf_of_size(pixbuf, size)
            
                ok, mem = pixbuf.save_to_bufferv("jpeg", ["quality"], ["100"])
            except Exception as e:
                log.info("Failed to load image using gdk pixbuf, "
                         "ignoring image.")
                log.debug(e)
                return ('', '')

        try:
            self._create_path(os.path.dirname(thumbpath))
            self._write_file(thumbpath, mem)
        except Exception as e:
            dialogs.ErrorDialog(
                _('Could not save file'),
                _('Exception raised while saving thumbnail '
                  'for image file (see error log for more '
                  'information)'),
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

    def _update_img(self, tuple_arg, url, repl_start, repl_end,
                    filepath, encrypted):
        mem, alt = tuple_arg
        if mem:
            try:
                urlparts = urlparse(url)
                filename = os.path.basename(urlparts.path)
                eb = Gtk.EventBox()
                eb.connect('button-press-event', self.on_button_press_event,
                           filepath, filename, url, encrypted)
                eb.connect('enter-notify-event', self.on_enter_event)
                eb.connect('leave-notify-event', self.on_leave_event)

                # this is threadsafe
                # (Gtk textview is NOT threadsafe by itself!!)
                def add_to_textview():
                    try:        # textview closed in the meantime etc.
                        buffer_ = repl_start.get_buffer()
                        iter_ = buffer_.get_iter_at_mark(repl_start)
                        buffer_.insert(iter_, "\n")
                        anchor = buffer_.create_child_anchor(iter_)
                        
                        # Use url as tooltip for image
                        img = TextViewImage(anchor, url)
                        loader = GdkPixbuf.PixbufLoader()
                        loader.write(mem)
                        loader.close()
                        pixbuf = loader.get_pixbuf()
                        img.set_from_pixbuf(pixbuf)

                        eb.add(img)
                        eb.show_all()
                        self.textview.tv.add_child_at_anchor(eb, anchor)
                        buffer_.delete(iter_,
                                    buffer_.get_iter_at_mark(repl_end))
                    except Exception as ex:
                        log.warn("Exception while loading %s: %s" % (str(url), str(ex)))
                    return False
                # add to mainloop --> make call threadsafe
                GObject.idle_add(add_to_textview)
            except Exception:
                # URL is already displayed
                log.error('Could not display image for URL: %s'
                          % url)
                raise
        else:
            # If image could not be downloaded, URL is already displayed
            log.error('Could not download image for URL: %s -- %s'
                      % (url, alt))

    def _check_mime_size(self, tuple_arg,
                         url, repl_start, repl_end, filepaths,
                         key, iv, encrypted):
        file_mime, file_size = tuple_arg
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

        app.thread_interface(
            self._download_image, [self.textview.account,
                                   attributes, encrypted],
            self._update_img, [url, repl_start, repl_end,
                               filepaths[0], encrypted])

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
            dialogs.ErrorDialog(
                _('Could not save file'),
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
        os.mkdir(folder, 0o700)

    def _aes_decrypt_fast(self, key, iv, payload):
        # Use AES128 GCM with the given key and iv to decrypt the payload.
        if os.name == 'nt':
            be = backend
        else:
            be = default_backend()
        data = payload[:-16]
        tag = payload[-16:]
        decryptor = Cipher(
            algorithms.AES(key),
            GCM(iv, tag=tag),
            backend=be).decryptor()
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
                                          GdkPixbuf.InterpType.BILINEAR)
        return (crop_pixbuf, image_width, image_height)

    def make_rightclick_menu(self, event, data):
        xml = Gtk.Builder()
        xml.set_translation_domain('gajim_plugins')
        xml.add_from_file(self.plugin.local_file_path('context_menu.ui'))
        menu = xml.get_object('context_menu')

        open_menuitem = xml.get_object('open_menuitem')
        save_as_menuitem = xml.get_object('save_as_menuitem')
        copy_link_location_menuitem = \
            xml.get_object('copy_link_location_menuitem')
        open_link_in_browser_menuitem = \
            xml.get_object('open_link_in_browser_menuitem')
        open_file_in_browser_menuitem = \
            xml.get_object('open_file_in_browser_menuitem')
        extras_separator = \
            xml.get_object('extras_separator')
        
        if data["encrypted"]:
            open_link_in_browser_menuitem.hide()
        if app.config.get('autodetect_browser_mailer') \
                or app.config.get('custombrowser') == '':
            extras_separator.hide()
            open_file_in_browser_menuitem.hide()

        id_ = open_menuitem.connect(
            'activate', self.on_open_menuitem_activate, data)
        self.handlers[id_] = open_menuitem
        id_ = save_as_menuitem.connect(
            'activate', self.on_save_as_menuitem_activate, data)
        self.handlers[id_] = save_as_menuitem
        id_ = copy_link_location_menuitem.connect(
            'activate', self.on_copy_link_location_menuitem_activate, data)
        self.handlers[id_] = copy_link_location_menuitem
        id_ = open_link_in_browser_menuitem.connect(
            'activate', self.on_open_link_in_browser_menuitem_activate, data)
        self.handlers[id_] = open_link_in_browser_menuitem
        id_ = open_file_in_browser_menuitem.connect(
            'activate', self.on_open_file_in_browser_menuitem_activate, data)
        self.handlers[id_] = open_file_in_browser_menuitem

        return menu

    def on_open_menuitem_activate(self, menu, data):
        filepath = data["filepath"]
        helpers.launch_file_manager(filepath)

    def on_save_as_menuitem_activate(self, menu, data):
        filepath = data["filepath"]
        original_filename = data["original_filename"]
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
                    dialogs.ErrorDialog(
                        _('Cannot overwrite existing file "%s"') % file_name,
                        _('A file with this name already exists and you do '
                          'not have permission to overwrite it.'))
                    return
                dialog2 = dialogs.FTOverwriteConfirmationDialog(
                    _('This file already exists'),
                    _('What do you want to do?'),
                    propose_resume=False,
                    on_response=(on_continue, target_path),
                    transient_for=dialog)
                dialog2.set_destroy_with_parent(True)
            else:
                dirname = os.path.dirname(target_path)
                if not os.access(dirname, os.W_OK):
                    dialogs.ErrorDialog(
                        _('Directory "%s" is not writable') % dirname,
                        _('You do not have permission to '
                          'create files in this directory.'))
                    return
                on_continue(0, target_path)

        def on_cancel(widget):
            dialog.destroy()

        dialog = dialogs.FileChooserDialog(
            title_text=_('Save Image as...'),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_SAVE, Gtk.ResponseType.OK),
            default_response=Gtk.ResponseType.OK,
            current_folder=app.config.get('last_save_dir'),
            on_response_ok=on_ok,
            on_response_cancel=on_cancel)

        dialog.set_current_name(original_filename)
        dialog.connect('delete-event', lambda widget, event:
                       on_cancel(widget))

    def on_copy_link_location_menuitem_activate(self, menu, data):
        url = data["url"]
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(url, -1)
        clipboard.store()

    def on_open_link_in_browser_menuitem_activate(self, menu, data):
        url = data["url"]
        if data["encrypted"]:
            dialogs.ErrorDialog(
                _('Encrypted file'),
                _('You cannot open encrypted files in your '
                  'browser directly. Try "Open Downloaded File '
                  'in Browser" instead.'),
                transient_for=self.chat_control.parent_win.window)
        else:
            helpers.launch_browser_mailer('url', url)
        
    def on_open_file_in_browser_menuitem_activate(self, menu, data):
        if os.name == "nt":
            filepath = "file://" + os.path.abspath(data["filepath"])
        else:
            filepath = "file://" + data["filepath"]
        if app.config.get('autodetect_browser_mailer') \
                or app.config.get('custombrowser') == '':
            dialogs.ErrorDialog(
                _('Cannot open downloaded file in browser'),
                _('You have to set a custom browser executable '
                  'in your gajim settings for this to work.'),
                transient_for=self.chat_control.parent_win.window)
            return
        command = app.config.get('custombrowser')
        command = helpers.build_command(command, filepath)
        try:
            helpers.exec_command(command)
        except Exception:
            pass

    # Change mouse pointer to HAND2 when
    # mouse enter the eventbox with the image
    def on_enter_event(self, eb, event):
        self.textview.tv.get_window(
            Gtk.TextWindowType.TEXT).set_cursor(Gdk.Cursor(Gdk.CursorType.HAND2))

    # Change mouse pointer to default when mouse leaves the eventbox
    def on_leave_event(self, eb, event):
        self.textview.tv.get_window(
            Gtk.TextWindowType.TEXT).set_cursor(Gdk.Cursor(Gdk.CursorType.XTERM))

    def on_button_press_event(self, eb, event, filepath,
                              original_filename, url, encrypted):
        data = {"filepath": filepath,
                "original_filename": original_filename,
                "url": url,
                "encrypted": encrypted}
        # left click
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            method = getattr(self, "on_"
                             + self.plugin.config['LEFTCLICK_ACTION']
                             + "_activate")
            method(event, data)
        # right klick
        elif event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            menu = self.make_rightclick_menu(event, data)
            #menu.attach_to_widget(self.tv, None)
            #menu.popup(None, None, None, event.button, event.time)
            menu.popup_at_pointer(event)

    def disconnect_from_chat_control(self):
        pass
