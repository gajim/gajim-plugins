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

import os
import hashlib
import binascii
import logging
import math
from urllib.parse import urlparse
from urllib.parse import unquote
from io import BytesIO
import shutil
from functools import partial

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

from gajim.common import app
from gajim.common import helpers
from gajim.common import configpaths

from gajim import dialogs
from gajim import gtkgui_helpers

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.plugins_i18n import _

from url_image_preview.http_functions import get_http_head, get_http_file
from url_image_preview.config_dialog import UrlImagePreviewConfigDialog
from url_image_preview.resize_gif import resize_gif

from gajim.gtk.filechoosers import FileSaveDialog


log = logging.getLogger('gajim.plugin_system.preview')

PILLOW_AVAILABLE = True
try:
    from PIL import Image
except:
    log.debug('Pillow not available')
    PILLOW_AVAILABLE = False

try:
    if os.name == 'nt':
        from cryptography.hazmat.backends.openssl import backend
    else:
        from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms
    from cryptography.hazmat.primitives.ciphers.modes import GCM
    decryption_available = True
except Exception:
    DEP_MSG = 'For preview of encrypted images, ' \
              'please install python-cryptography!'
    log.exception('Error')
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
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                  self.disconnect_from_chat_control),
            'history_window':
                (self.connect_with_history, self.disconnect_from_history),
            'print_real_text': (self.print_real_text, None), }
        self.config_default_values = {
            'PREVIEW_SIZE': (150, 'Preview size(10-512)'),
            'MAX_FILE_SIZE': (5242880, 'Max file size for image preview'),
            'ALLOW_ALL_IMAGES': (False, ''),
            'LEFTCLICK_ACTION': ('open_menuitem', 'Open'),
            'ANONYMOUS_MUC': (False, ''),
            'GEO_PREVIEW_PROVIDER': ('Google', 'Google Maps'),
            'VERIFY': (True, ''),}
        self.controls = {}
        self.history_window_control = None

    @log_calls('UrlImagePreviewPlugin')
    def connect_with_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid = chat_control.contact.jid
        if account not in self.controls:
            self.controls[account] = {}
        self.controls[account][jid] = Base(self, chat_control.conv_textview)

    @log_calls('UrlImagePreviewPlugin')
    def disconnect_from_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid = chat_control.contact.jid
        self.controls[account][jid].deinit_handlers()
        del self.controls[account][jid]

    @log_calls('UrlImagePreviewPlugin')
    def connect_with_history(self, history_window):
        if self.history_window_control:
            self.history_window_control.deinit_handlers()
        self.history_window_control = Base(
            self, history_window.history_textview)

    @log_calls('UrlImagePreviewPlugin')
    def disconnect_from_history(self, history_window):
        if self.history_window_control:
            self.history_window_control.deinit_handlers()
        self.history_window_control = None

    def print_real_text(self, tv, real_text, text_tags, graphics,
                        iter_, additional_data):
        if tv.used_in_history_window and self.history_window_control:
            self.history_window_control.print_real_text(
                real_text, text_tags, graphics, iter_, additional_data)

        account = tv.account
        for jid in self.controls[account]:
            if self.controls[account][jid].textview != tv:
                continue
            self.controls[account][jid].print_real_text(
                real_text, text_tags, graphics, iter_, additional_data)
            return


class Base(object):
    def __init__(self, plugin, textview):
        self.plugin = plugin
        self.textview = textview
        self.handlers = {}

        self.directory = os.path.join(configpaths.get('MY_DATA'),
                                      'downloads')
        self.thumbpath = os.path.join(configpaths.get('MY_CACHE'),
                                      'downloads.thumb')

        try:
            self._create_path(self.directory)
            self._create_path(self.thumbpath)
        except Exception:
            log.error("Error creating download and/or thumbnail folder!")
            raise

    def deinit_handlers(self):
        # remove all register handlers on wigets, created by self.xml
        # to prevent circular references among objects
        for i in list(self.handlers.keys()):
            if self.handlers[i].handler_is_connected(i):
                self.handlers[i].disconnect(i)
            del self.handlers[i]

    def print_real_text(self, real_text, text_tags, graphics, iter_,
                        additional_data):

        if len(real_text.split(' ')) > 1:
            # urlparse dont recognises spaces as URL delimiter
            log.debug('Url with text will not be displayed: %s', real_text)
            return

        urlparts = urlparse(unquote(real_text))
        if not self._accept_uri(urlparts, real_text, additional_data):
            return

        # Don't print the URL in the message window (in the calling function)
        self.textview.plugin_modified = True

        buffer_ = self.textview.tv.get_buffer()
        if not iter_:
            iter_ = buffer_.get_end_iter()

        # Show URL, until image is loaded (if ever)
        ttt = buffer_.get_tag_table()
        repl_start = buffer_.create_mark(None, iter_, True)
        buffer_.insert_with_tags(iter_, real_text,
            *[(ttt.lookup(t) if isinstance(t, str) else t) for t in ["url"]])
        repl_end = buffer_.create_mark(None, iter_, True)

        # Handle geo:-URIs
        if real_text.startswith('geo:'):
            if self.plugin.config['GEO_PREVIEW_PROVIDER'] == 'no_preview':
                return
            size = self.plugin.config['PREVIEW_SIZE']
            geo_provider = self.plugin.config['GEO_PREVIEW_PROVIDER']
            key = ''
            iv = ''
            encrypted = False
            ext = '.png'
            color = 'blue'
            zoom = 16
            location = real_text[4:]
            lat, _, lon = location.partition(',')
            if lon == '':
                return

            filename = 'location_' + geo_provider + '_' \
                + location.replace(',', '_').replace('.', '-')
            newfilename = filename + ext
            thumbfilename = filename + '_thumb_' \
                + str(self.plugin.config['PREVIEW_SIZE']) + ext
            filepath = os.path.join(self.directory, newfilename)
            thumbpath = os.path.join(self.thumbpath, thumbfilename)
            filepaths = [filepath, thumbpath]

            # Google
            if geo_provider == 'Google':
                url = 'https://maps.googleapis.com/maps/api/staticmap?' \
                      'center={}&zoom={}&size={}x{}&markers=color:{}' \
                      '|label:.|{}'.format(location, zoom, size, size,
                                           color, location)
                weburl = 'https://www.google.com/maps/place/{}' \
                         .format(location)
                real_text = url
            else:
                # OpenStreetMap / MapQuest
                apikey = 'F7x36jLVv2hiANVAXmhwvUB044XvGASh'

                url = 'https://open.mapquestapi.com/staticmap/v4/' \
                      'getmap?key={}&center={}&zoom={}&size={},{}&type=map' \
                      '&imagetype=png&pois={},{}&scalebar=false' \
                      .format(apikey, location, zoom, size, size, color,
                              location)
                weburl = 'http://www.openstreetmap.org/' \
                         '?mlat={}&mlon={}#map={}/{}/{}&layers=N' \
                         .format(lat, lon, zoom, lat, lon)
                real_text = url
        else:
            weburl = real_text
            filename = os.path.basename(urlparts.path)
            ext = os.path.splitext(filename)[1]
            name = os.path.splitext(filename)[0]
            if len(name) > 90:
                # Many Filesystems have a limit on filename length
                # Most have 255, some encrypted ones only 143
                # We add around 50 chars for the hash,
                # so the filename should not exceed 90
                name = name[:90]
            namehash = hashlib.sha1(real_text.encode('utf-8')).hexdigest()
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
            if urlparts.scheme == 'geo':
                    real_text = weburl
            with open(filepath, 'rb') as f:
                mem = f.read()
            app.thread_interface(
                self._save_thumbnail, [thumbpath, mem],
                self._update_img, [real_text, repl_start,
                                   repl_end, filepath, encrypted])

        # display thumbnail if already downloadeded
        # (but only if file also exists)
        elif os.path.exists(filepath) and os.path.exists(thumbpath):
            if urlparts.scheme == 'geo':
                    real_text = weburl
            app.thread_interface(
                self._load_thumbnail, [thumbpath],
                self._update_img, [real_text, repl_start,
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
                    real_text = 'https://' + real_text[9:]
                verify = self.plugin.config['VERIFY']
                app.thread_interface(
                    get_http_head, [self.textview.account, real_text, verify],
                    self._check_mime_size, [real_text, weburl, repl_start,
                                            repl_end, filepaths, key, iv,
                                            encrypted])

    def _accept_uri(self, urlparts, real_text, additional_data):
        try:
            oob_url = additional_data["gajim"]["oob_url"]
        except (KeyError, AttributeError):
            oob_url = None

        if not urlparts.netloc:
            log.info('No netloc found in URL %s', real_text)
            return False

        # geo
        if urlparts.scheme == "geo":
            if self.plugin.config['GEO_PREVIEW_PROVIDER'] == 'no_preview':
                log.info('geo: link preview is disabled')
                return False
            return True

        # aesgcm
        if urlparts.scheme == 'aesgcm':
            return True

        # https
        if urlparts.scheme == 'https':
            if real_text == oob_url or self.plugin.config['ALLOW_ALL_IMAGES']:
                return True
            log.info('Incorrect oob data found')
            return False

        log.info('Not supported URI scheme found: %s', real_text)
        return False

    def _save_thumbnail(self, thumbpath, mem):
        size = self.plugin.config['PREVIEW_SIZE']

        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(mem)
            loader.close()
            if loader.get_format().get_name() == 'gif':
                pixbuf = loader.get_animation()
            else:
                pixbuf = loader.get_pixbuf()
        except GLib.GError as error:
            log.info('Failed to load image using Gdk.Pixbuf')
            log.debug(error)

            if not PILLOW_AVAILABLE:
                log.info('Pillow not available')
                return
            # Try Pillow
            image = Image.open(BytesIO(mem)).convert("RGBA")
            array = GLib.Bytes.new(image.tobytes())
            width, height = image.size
            pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                array, GdkPixbuf.Colorspace.RGB, True,
                8, width, height, width * 4)

        try:
            self._create_path(os.path.dirname(thumbpath))
            thumbnail = pixbuf
            if isinstance(pixbuf, GdkPixbuf.PixbufAnimation):
                if size < pixbuf.get_width() or size < pixbuf.get_height():
                    resize_gif(mem, thumbpath, (size, size))
                    thumbnail = self._load_thumbnail(thumbpath)
                else:
                    self._write_file(thumbpath, mem)
            else:
                width, height = self._get_thumbnail_size(pixbuf, size)
                thumbnail = pixbuf.scale_simple(
                    width, height, GdkPixbuf.InterpType.BILINEAR)
                thumbnail.savev(thumbpath, 'png', [], [])
        except Exception as error:
            GLib.idle_add(
                self._raise_error_dialog,
                _('Could not save file'),
                _('Exception raised while saving thumbnail '
                  'for image file (see error log for more '
                  'information)'))
            log.exception(error)
            return
        return thumbnail

    @staticmethod
    def _get_thumbnail_size(pixbuf, size):
        # Calculates the new thumbnail size while preserving the aspect ratio
        image_width = pixbuf.get_width()
        image_height = pixbuf.get_height()

        if image_width > image_height:
            if image_width > size:
                image_height = math.ceil((size / float(image_width) * image_height))
                image_width = int(size)
        else:
            if image_height > size:
                image_width = math.ceil((size / float(image_height) * image_width))
                image_height = int(size)

        return image_width, image_height

    @staticmethod
    def _load_thumbnail(thumbpath):
        ext = os.path.splitext(thumbpath)[1]
        if ext == '.gif':
            return GdkPixbuf.PixbufAnimation.new_from_file(thumbpath)
        return GdkPixbuf.Pixbuf.new_from_file(thumbpath)

    @staticmethod
    def _write_file(path, data):
        log.info("Writing '%s' of size %d...", path, len(data))
        try:
            with open(path, "wb") as output_file:
                output_file.write(data)
                output_file.closed
        except Exception as e:
            log.error("Failed to write file '%s'!", path)
            raise

    def _get_at_end(self):
        try:
            # Gajim 1.0.0
            return self.textview.at_the_end()
        except AttributeError:
            # Gajim 1.0.1
            return self.textview.autoscroll

    def _scroll_to_end(self):
        try:
            # Gajim 1.0.0
            self.textview.scroll_to_end_iter()
        except AttributeError:
            # Gajim 1.0.1
            self.textview.scroll_to_end()

    def _update_img(self, pixbuf, url, repl_start, repl_end,
                    filepath, encrypted):
        if pixbuf is None:
            # If image could not be downloaded, URL is already displayed
            log.error('Could not download image for URL: %s', url)
            return

        urlparts = urlparse(unquote(url))
        filename = os.path.basename(urlparts.path)
        if os.path.basename(filepath).startswith('location_'):
            filename = os.path.basename(filepath)

        event_box = Gtk.EventBox()
        event_box.connect('button-press-event', self.on_button_press_event,
                          filepath, filename, url, encrypted)
        event_box.connect('enter-notify-event', self.on_enter_event)
        event_box.connect('leave-notify-event', self.on_leave_event)

        def add_to_textview():
            try:
                at_end = self._get_at_end()

                buffer_ = repl_start.get_buffer()
                iter_ = buffer_.get_iter_at_mark(repl_start)
                buffer_.insert(iter_, "\n")
                anchor = buffer_.create_child_anchor(iter_)
                anchor.plaintext = url

                if isinstance(pixbuf, GdkPixbuf.PixbufAnimation):
                    image = Gtk.Image.new_from_animation(pixbuf)
                else:
                    image = Gtk.Image.new_from_pixbuf(pixbuf)

                css = '''#Preview {
                box-shadow: 0px 0px 3px 0px alpha(@theme_text_color, 0.2);
                margin: 5px 10px 5px 10px; }'''
                gtkgui_helpers.add_css_to_widget(image, css)
                image.set_name('Preview')

                event_box.set_tooltip_text(url)
                event_box.add(image)
                event_box.show_all()
                self.textview.tv.add_child_at_anchor(event_box, anchor)
                buffer_.delete(iter_,
                               buffer_.get_iter_at_mark(repl_end))

                if at_end:
                    self._scroll_to_end()
            except Exception as ex:
                log.exception("Exception while loading %s: %s", url, ex)
            return False
        # add to mainloop --> make call threadsafe
        GLib.idle_add(add_to_textview)

    def _check_mime_size(self, tuple_arg,
                         url, weburl, repl_start, repl_end, filepaths,
                         key, iv, encrypted):
        file_mime, file_size = tuple_arg
        # Check if mime type is acceptable
        if not file_mime or not file_size:
            log.info("Failed to load HEAD Request for URL: '%s' "
                     "mime: %s, size: %s", url, file_mime, file_size)
            # URL is already displayed
            return
        if file_mime.lower() not in ACCEPTED_MIME_TYPES:
            log.info("Not accepted mime type '%s' for URL: '%s'",
                     file_mime.lower(), url)
            # URL is already displayed
            return
        # Check if file size is acceptable
        max_size = int(self.plugin.config['MAX_FILE_SIZE'])
        if file_size > max_size or file_size == 0:
            log.info("File size (%s) too big or unknown (zero) for URL: '%s'",
                     file_size, url)
            # URL is already displayed
            return

        attributes = {'src': url,
                      'verify': self.plugin.config['VERIFY'],
                      'max_size': max_size,
                      'filepaths': filepaths,
                      'key': key,
                      'iv': iv}

        app.thread_interface(
            self._download_image, [self.textview.account,
                                   attributes, encrypted],
            self._update_img, [weburl, repl_start, repl_end,
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
            GLib.idle_add(
                self._raise_error_dialog,
                _('Could not save file'),
                _('Exception raised while saving image file'
                  ' (see error log for more information)'))
            log.error(str(e))

        # Create thumbnail, write it to harddisk and return it
        return self._save_thumbnail(thumbpath, mem)

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
            'activate', self.on_save_as_menuitem_activate_new, data)
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
        original_filename = data["original_filename"]
        url = data["url"]
        if original_filename.startswith('location_'):
            helpers.launch_browser_mailer('url', url)
            return
        helpers.launch_file_manager(filepath)

    def on_save_as_menuitem_activate_new(self, menu, data):
        filepath = data["filepath"]
        original_filename = data["original_filename"]

        def on_ok(target_path):
            dirname = os.path.dirname(target_path)
            if not os.access(dirname, os.W_OK):
                dialogs.ErrorDialog(
                    _('Directory "%s" is not writable') % dirname,
                    _('You do not have permission to '
                      'create files in this directory.'))
                return
            shutil.copy(filepath, target_path)

        FileSaveDialog(on_ok,
                       path=app.config.get('last_save_dir'),
                       file_name=original_filename,
                       transient_for=app.app.get_active_window())

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
                transient_for=app.app.get_active_window())
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
                transient_for=app.app.get_active_window())
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
            # menu.attach_to_widget(self.tv, None)
            # menu.popup(None, None, None, event.button, event.time)
            menu.popup_at_pointer(event)

    @staticmethod
    def _raise_error_dialog(pritext, sectext):
        # Used by methods that run in a different thread
        dialogs.ErrorDialog(pritext,
                            sectext,
                            transient_for=app.app.get_active_window())

    def disconnect_from_chat_control(self):
        pass
