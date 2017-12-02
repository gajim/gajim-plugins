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

from common import demandimport
demandimport.enable()
demandimport.ignore += ['builtins', '__builtin__', 'PIL', '_imp']

import gtk
import gobject
import os
import time
import base64
import tempfile
import urllib2
import mimetypes        # better use the magic packet, but that's not a standard lib
import gtkgui_helpers
import threading
from Queue import Queue
try:
    from PIL import Image
    pil_available = True
except:
    pil_available = False
from io import BytesIO

import binascii
from common import gajim
from common import ged
import chat_control
from plugins import GajimPlugin
from plugins.helpers import log_calls
import logging
from dialogs import FileChooserDialog, ImageChooserDialog, ErrorDialog
import nbxmpp

log = logging.getLogger('gajim.plugin_system.httpupload')

try:
    if os.name == 'nt':
        from cryptography.hazmat.backends.openssl import backend
    else:
        from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms
    from cryptography.hazmat.primitives.ciphers.modes import GCM
    encryption_available = True
except Exception as e:
    DEP_MSG = 'For encryption of files, ' \
              'please install python-cryptography!'
    log.debug('Cryptography Import Error: ' + str(e))
    log.info('Decryption/Encryption disabled due to errors')
    encryption_available = False

# XEP-0363 (http://xmpp.org/extensions/xep-0363.html)
NS_HTTPUPLOAD = 'urn:xmpp:http:upload'
TAGSIZE = 16

jid_to_servers = {}
iq_ids_to_callbacks = {}
last_info_query = {}
max_thumbnail_size = 2048
max_thumbnail_dimension = 160


class HttpuploadPlugin(GajimPlugin):

    @log_calls('HttpuploadPlugin')
    def init(self):
        if not encryption_available:
            self.available_text = DEP_MSG
        self.config_dialog = None  # HttpuploadPluginConfigDialog(self)
        self.controls = []
        self.events_handlers = {
            'agent-info-received': (
                ged.PRECORE, self.handle_agent_info_received),
            'stanza-message-outgoing': (
                99, self.handle_outgoing_stanza),
            'gc-stanza-message-outgoing': (
                99, self.handle_outgoing_stanza),
            'raw-iq-received': (
                ged.PRECORE, self.handle_iq_received)}
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (self.update_button_state,
                None)}
        self.messages = []
        self.first_run = True

    def handle_iq_received(self, event):
        global iq_ids_to_callbacks
        id_ = event.stanza.getAttr("id")
        if str(id_) in iq_ids_to_callbacks:
            try:
                iq_ids_to_callbacks[str(id_)](event.stanza)
            except:
                raise
            finally:
                del iq_ids_to_callbacks[str(id_)]

    def handle_agent_info_received(self, event):
        global jid_to_servers
        if NS_HTTPUPLOAD in event.features and gajim.jid_is_transport(event.jid):
            own_jid = gajim.get_jid_without_resource(str(event.stanza.getTo()))
            jid_to_servers[own_jid] = event.jid        # map own jid to upload component's jid
            log.info(own_jid + " can do http uploads via component " + event.jid)
            # update all buttons
            for base in self.controls:
                self.update_button_state(base.chat_control)

    def handle_outgoing_stanza(self, event):
        message = event.msg_iq.getTagData('body')
        if message and message in self.messages:
            self.messages.remove(message)
            oob = event.msg_iq.addChild('x', namespace=nbxmpp.NS_X_OOB)
            oob.addChild('url').setData(message)

    @log_calls('HttpuploadPlugin')
    def connect_with_chat_control(self, control):
        self.chat_control = control
        base = Base(self, self.chat_control)
        self.controls.append(base)
        if self.first_run:
            # ALT + U
            gtk.binding_entry_add_signal(control.msg_textview,
                gtk.keysyms.u, gtk.gdk.MOD1_MASK, 'mykeypress',
                int, gtk.keysyms.u, gtk.gdk.ModifierType, gtk.gdk.MOD1_MASK)
            self.first_run = False
        self.update_button_state(self.chat_control)

    @log_calls('HttpuploadPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    @log_calls('HttpuploadPlugin')
    def update_button_state(self, chat_control):
        global jid_to_servers
        global iq_ids_to_callbacks
        global last_info_query

        if gajim.connections[chat_control.account].connection == None and \
            gajim.get_jid_from_account(chat_control.account) in jid_to_servers:
            # maybe don't delete this and detect vanished upload components when actually trying to upload something
            log.info("Deleting %s from jid_to_servers (disconnected)" % gajim.get_jid_from_account(chat_control.account))
            del jid_to_servers[gajim.get_jid_from_account(chat_control.account)]
            #pass

        # query info at most every 60 seconds in case something goes wrong
        if (not chat_control.account in last_info_query or \
            last_info_query[chat_control.account] + 60 < time.time()) and \
            not gajim.get_jid_from_account(chat_control.account) in jid_to_servers and \
            gajim.account_is_connected(chat_control.account):
            log.info("Account %s: Using dicovery to find jid of httpupload component" % chat_control.account)
            id_ = gajim.get_an_id()
            iq = nbxmpp.Iq(
                typ='get',
                to=gajim.get_server_from_jid(gajim.get_jid_from_account(chat_control.account)),
                queryNS="http://jabber.org/protocol/disco#items"
            )
            iq.setID(id_)
            def query_info(stanza):
                global last_info_query
                for item in stanza.getTag("query").getTags("item"):
                    id_ = gajim.get_an_id()
                    iq = nbxmpp.Iq(
                        typ='get',
                        to=item.getAttr("jid"),
                        queryNS="http://jabber.org/protocol/disco#info"
                    )
                    iq.setID(id_)
                    last_info_query[chat_control.account] = time.time()
                    gajim.connections[chat_control.account].connection.send(iq)
            iq_ids_to_callbacks[str(id_)] = query_info
            gajim.connections[chat_control.account].connection.send(iq)
            #send disco query to main server jid
            id_ = gajim.get_an_id()
            iq = nbxmpp.Iq(
                typ='get',
                to=gajim.get_server_from_jid(gajim.get_jid_from_account(chat_control.account)),
                queryNS="http://jabber.org/protocol/disco#info"
            )
            iq.setID(id_)
            last_info_query[chat_control.account] = time.time()
            gajim.connections[chat_control.account].connection.send(iq)

        for base in self.controls:
            if base.chat_control == chat_control:
                is_supported = gajim.get_jid_from_account(chat_control.account) in jid_to_servers and \
                    gajim.connections[chat_control.account].connection != None
                log.info("Account %s: httpupload is_supported: %s" % (str(chat_control.account), str(is_supported)))
                if not is_supported:
                    text = _('Your server does not support http uploads')
                    image_text = text
                else:
                    text = _('Send file via http upload')
                    image_text = _('Send image via http upload')
                base.button.set_sensitive(is_supported)
                base.button.set_tooltip_text(text)
                base.image_button.set_sensitive(is_supported)
                base.image_button.set_tooltip_text(image_text)


class Base(object):
    def __init__(self, plugin, chat_control):
        self.dlg = None
        self.dialog_type = 'file'
        self.keypress_id = chat_control.msg_textview.connect('mykeypress',
            self.on_key_press)
        self.plugin = plugin
        self.encrypted_upload = False
        self.chat_control = chat_control
        actions_hbox = chat_control.xml.get_object('actions_hbox')
        self.button = gtk.Button(label=None, stock=None, use_underline=True)
        self.button.set_property('relief', gtk.RELIEF_NONE)
        self.button.set_property('can-focus', False)
        self.button.set_sensitive(False)
        img = gtk.Image()
        img.set_from_file(self.plugin.local_file_path('httpupload.png'))
        self.button.set_image(img)
        self.button.set_tooltip_text(_('Your server does not support http uploads'))
        self.image_button = gtk.Button(label=None, stock=None, use_underline=True)
        self.image_button.set_property('relief', gtk.RELIEF_NONE)
        self.image_button.set_property('can-focus', False)
        self.image_button.set_sensitive(False)
        img = gtk.Image()
        img.set_from_file(self.plugin.local_file_path('image.png'))
        self.image_button.set_image(img)
        self.image_button.set_tooltip_text(_('Your server does not support http uploads'))
        send_button = chat_control.xml.get_object('send_button')
        send_button_pos = actions_hbox.child_get_property(send_button,
            'position')
        actions_hbox.add_with_properties(self.button, 'position',
            send_button_pos - 2, 'expand', False)

        actions_hbox.add_with_properties(self.image_button, 'position',
            send_button_pos - 1, 'expand', False)

        file_id = self.button.connect('clicked', self.on_file_button_clicked)
        image_id = self.image_button.connect('clicked', self.on_image_button_clicked)
        chat_control.handlers[file_id] = self.button
        chat_control.handlers[image_id] = self.image_button
        chat_control.handlers[self.keypress_id] = chat_control.msg_textview
        self.button.show()
        self.image_button.show()

    def on_key_press(self, widget, event_keyval, event_keymod):
        # construct event instance from binding
        event = gtk.gdk.Event(gtk.gdk.KEY_PRESS)  # it's always a key-press here
        event.keyval = event_keyval
        event.state = event_keymod
        event.time = 0  # assign current time

        if event.keyval != gtk.keysyms.u:
            return
        if event.state != gtk.gdk.MOD1_MASK:  # ALT+u
            return
        is_supported = gajim.get_jid_from_account(self.chat_control.account) in jid_to_servers and \
                    gajim.connections[self.chat_control.account].connection != None
        if not is_supported:
            from dialogs import WarningDialog
            WarningDialog('Warning', _('Your server does not support http uploads'),
                transient_for=self.chat_control.parent_win.window)
            return
        self.on_file_button_clicked(widget)

    def disconnect_from_chat_control(self):
        actions_hbox = self.chat_control.xml.get_object('actions_hbox')
        actions_hbox.remove(self.button)
        actions_hbox.remove(self.image_button)
        if self.keypress_id in self.chat_control.handlers and \
            self.chat_control.handlers[self.keypress_id].handler_is_connected(self.keypress_id):
            self.chat_control.handlers[self.keypress_id].disconnect(self.keypress_id)
            del self.chat_control.handlers[self.keypress_id]

    def encryption_activated(self):
        jid = self.chat_control.contact.jid
        account = self.chat_control.account
        for plugin in gajim.plugin_manager.active_plugins:
            if type(plugin).__name__ == 'OmemoPlugin':
                state = plugin.get_omemo_state(account)
                log.info('Encryption is: ' +
                          str(state.encryption.is_active(jid)))
                return state.encryption.is_active(jid)
        log.info('Encryption is: False / OMEMO not found')
        return False

    def on_file_dialog_ok(self, widget, path_to_file=None):
        global jid_to_servers

        try:
            self.encrypted_upload = self.encryption_activated()
        except Exception as e:
            log.debug(e)
            self.encrypted_upload = False

        if self.encrypted_upload and not encryption_available:
            ErrorDialog(
                _('Error'),
                'Please install python-cryptography for encrypted uploads',
                transient_for=self.chat_control.parent_win.window)
            return

        if not path_to_file:
            path_to_file = self.dlg.get_filename()
            if not path_to_file:
                self.dlg.destroy()
                return
            path_to_file = gtkgui_helpers.decode_filechooser_file_paths(
                    (path_to_file,))[0]
        self.dlg.destroy()
        if not os.path.exists(path_to_file):
            return
        if self.encrypted_upload:
            filesize = os.path.getsize(path_to_file) + TAGSIZE  # in bytes
        else:
            filesize = os.path.getsize(path_to_file)
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
        if invalid_file:
            ErrorDialog(_('Could not open file'), msg, transient_for=self.chat_control.parent_win.window)
            return

        mime_type = mimetypes.MimeTypes().guess_type(path_to_file)[0]
        if not mime_type:
            mime_type = 'application/octet-stream'  # fallback mime type
        log.info("Detected MIME Type of file: " + str(mime_type))
        progress_messages = Queue(8)
        event = threading.Event()
        progress_window = ProgressWindow(_('Requesting HTTP Upload Slot...'), progress_messages, self, event)

        def upload_file(stanza):
            if stanza.getType() == 'error':
                ErrorDialog(_('Could not request upload slot'),
                            stanza.getErrorMsg(),
                            transient_for=self.chat_control.parent_win.window)
                log.error(stanza)
                progress_window.close_dialog()
                return

            slot = stanza.getTag("slot")
            if slot:
                put = slot.getTag("put")
                get = slot.getTag("get")
            else:
                progress_window.close_dialog()
                log.error("got unexpected stanza: " + str(stanza))
                ErrorDialog(_('Could not request upload slot'),
                            _('Got unexpected response from server (see log)'),
                            transient_for=self.chat_control.parent_win.window)
                return

            try:
                if self.encrypted_upload:
                    key = os.urandom(32)
                    iv = os.urandom(16)
                    data = StreamFileWithProgress(path_to_file,
                                                  "rb",
                                                  progress_window.update_progress, event,
                                                  self.encrypted_upload, key, iv)
                else:
                    data = StreamFileWithProgress(path_to_file,
                                                  "rb",
                                                  progress_window.update_progress, event)
            except:
                progress_window.close_dialog()
                ErrorDialog(_('Could not open file'), 
                            _('Exception raised while opening file (see error log for more information)'),
                            transient_for=self.chat_control.parent_win.window)
                raise       # fill error log with useful information

            def upload_complete(response_code):
                if isinstance(response_code, str):
                    # We got a error Message
                    ErrorDialog(
                        _('Error'), response_code,
                        transient_for=self.chat_control.parent_win.window)
                    return
                if response_code >= 200 and response_code < 300:
                    log.info("Upload completed successfully")
                    xhtml = None
                    is_image = mime_type.split('/', 1)[0] == 'image'
                    if (not isinstance(self.chat_control, chat_control.ChatControl) or not self.chat_control.gpg_is_active) and \
                        self.dialog_type == 'image' and is_image and not self.encrypted_upload:

                        progress_messages.put(_('Calculating (possible) image thumbnail...'))
                        thumb = None
                        quality_steps = (100, 80, 60, 50, 40, 35, 30, 25, 23, 20, 18, 15, 13, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)
                        with open(path_to_file, 'rb') as content_file:
                            thumb = urllib2.quote(base64.standard_b64encode(content_file.read()), '')
                        if thumb and len(thumb) < max_thumbnail_size:
                            quality = 100
                            log.info("Image small enough (%d bytes), not resampling" % len(thumb))
                        elif pil_available:
                            log.info("PIL available, using it for image downsampling")
                            try:
                                for quality in quality_steps:
                                    thumb = Image.open(path_to_file)
                                    thumb.thumbnail((max_thumbnail_dimension, max_thumbnail_dimension), Image.ANTIALIAS)
                                    output = BytesIO()
                                    thumb.save(output, format='JPEG', quality=quality, optimize=True)
                                    thumb = output.getvalue()
                                    output.close()
                                    thumb = urllib2.quote(base64.standard_b64encode(thumb), '')
                                    log.debug("pil thumbnail jpeg quality %d produces an image of size %d..." % (quality, len(thumb)))
                                    if len(thumb) < max_thumbnail_size:
                                        break
                            except:
                                thumb = None
                        else:
                            thumb = None
                        if not thumb:
                            log.info("PIL not available, using GTK for image downsampling")
                            temp_file = None
                            try:
                                with open(path_to_file, 'rb') as content_file:
                                    thumb = content_file.read()
                                loader = gtk.gdk.PixbufLoader()
                                loader.write(thumb)
                                loader.close()
                                pixbuf = loader.get_pixbuf()
                                scaled_pb = self.get_pixbuf_of_size(pixbuf, max_thumbnail_dimension)
                                handle, temp_file = tempfile.mkstemp(suffix='.jpeg', prefix='gajim_httpupload_scaled_tmp', dir=gajim.TMP)
                                log.debug("Saving temporary jpeg image to '%s'..." % temp_file)
                                os.close(handle)
                                for quality in quality_steps:
                                    scaled_pb.save(temp_file, "jpeg", {"quality": str(quality)})
                                    with open(temp_file, 'rb') as content_file:
                                        thumb = content_file.read()
                                    thumb = urllib2.quote(base64.standard_b64encode(thumb), '')
                                    log.debug("gtk thumbnail jpeg quality %d produces an image of size %d..." % (quality, len(thumb)))
                                    if len(thumb) < max_thumbnail_size:
                                        break
                            except:
                                thumb = None
                            finally:
                                if temp_file:
                                    os.unlink(temp_file)
                        if thumb:
                            if len(thumb) > max_thumbnail_size:
                                log.info("Couldn't compress image enough, not sending any thumbnail")
                            else:
                                log.info("Using thumbnail jpeg quality %d (image size: %d bytes)" % (quality, len(thumb)))
                                xhtml = '<body><br/><a href="%s"> <img alt="%s" src="data:image/png;base64,%s"/> </a></body>' % \
                                    (get.getData(), get.getData(), thumb)
                    progress_window.close_dialog()
                    id_ = gajim.get_an_id()

                    if self.encrypted_upload:
                        keyAndIv = '#' + binascii.hexlify(iv) + binascii.hexlify(key)
                        self.chat_control.send_message(message=get.getData() + keyAndIv, xhtml=None)
                    else:
                        self.plugin.messages.append(get.getData())
                        self.chat_control.send_message(message=get.getData(), xhtml=xhtml)
                    self.chat_control.msg_textview.grab_focus()
                else:
                    progress_window.close_dialog()
                    log.error("got unexpected http upload response code: " + str(response_code))
                    ErrorDialog(_('Could not upload file'),
                                _('Got unexpected http response code from server: ') + str(response_code),
                                transient_for=self.chat_control.parent_win.window)
            
            def uploader():
                progress_messages.put(_('Uploading file via HTTP...'))
                try:
                    headers = {'User-Agent': 'Gajim %s' % gajim.version,
                               'Content-Type': mime_type}
                    request = urllib2.Request(put.getData().encode("utf-8"), data=data, headers=headers)
                    request.get_method = lambda: 'PUT'
                    log.debug("opening urllib2 upload request...")
                    transfer = urllib2.urlopen(request, timeout=30)
                    log.debug("urllib2 upload request done, response code: " + str(transfer.getcode()))
                    return transfer.getcode()
                except UploadAbortedException as error:
                    log.info('Upload Aborted')
                    return str(error)
                except urllib2.URLError as error:
                    log.exception('URLError')
                    errormsg = error.reason
                except Exception as error:
                    log.exception('Error')
                    errormsg = error
                gobject.idle_add(progress_window.close_dialog)
                return str(errormsg)

            log.info("Uploading file to '%s'..." % str(put.getData()))
            log.info("Please download from '%s' later..." % str(get.getData()))

            gajim.thread_interface(uploader, [], upload_complete)

        is_supported = gajim.get_jid_from_account(self.chat_control.account) in jid_to_servers and \
                    gajim.connections[self.chat_control.account].connection != None
        log.info("jid_to_servers of %s: %s ; connection: %s" % (gajim.get_jid_from_account(self.chat_control.account), str(jid_to_servers[gajim.get_jid_from_account(self.chat_control.account)]), str(gajim.connections[self.chat_control.account].connection)))
        if not is_supported:
            progress_window.close_dialog()
            log.error("upload component vanished, account got disconnected??")
            ErrorDialog(_('Your server does not support http uploads or you just got disconnected.\nPlease try to reconnect or reopen the chat window to fix this.'),
                transient_for=self.chat_control.parent_win.window)
            return

        # create iq for slot request
        id_ = gajim.get_an_id()
        iq = nbxmpp.Iq(
            typ='get',
            to=jid_to_servers[gajim.get_jid_from_account(self.chat_control.account)],
            queryNS=None
        )
        iq.setID(id_)
        request = iq.addChild(
            name="request",
            namespace=NS_HTTPUPLOAD
        )
        filename = request.addChild(
            name="filename",
        )
        filename.addData(os.path.basename(path_to_file))
        size = request.addChild(
            name="size",
        )
        size.addData(filesize)
        content_type = request.addChild(
            name="content-type",
        )
        content_type.addData(mime_type)

        # send slot request and register callback
        log.debug("sending httpupload slot request iq...")
        iq_ids_to_callbacks[str(id_)] = upload_file
        gajim.connections[self.chat_control.account].connection.send(iq)

        self.chat_control.msg_textview.grab_focus()

    def on_file_button_clicked(self, widget):
        self.dialog_type = 'file'
        self.dlg = FileChooserDialog(on_response_ok=self.on_file_dialog_ok, on_response_cancel=None,
            title_text = _('Choose file to send'), action = gtk.FILE_CHOOSER_ACTION_OPEN,
            buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK),
            default_response = gtk.RESPONSE_OK,)

    def on_image_button_clicked(self, widget):
        self.dialog_type = 'image'
        self.dlg = ImageChooserDialog(on_response_ok=self.on_file_dialog_ok, on_response_cancel=None)

    def get_pixbuf_of_size(self, pixbuf, size):
        # Creates a pixbuf that fits in the specified square of sizexsize
        # while preserving the aspect ratio
        # Returns scaled_pixbuf
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
        return crop_pixbuf


class StreamFileWithProgress(file):
    def __init__(self, path, mode, callback, event,
                 encrypted_upload=False, key=None, iv=None, *args):
        file.__init__(self, path, mode)
        self.event = event
        self.encrypted_upload = encrypted_upload
        self.seek(0, os.SEEK_END)
        if self.encrypted_upload:
            if os.name == 'nt':
                self.backend = backend
            else:
                self.backend = default_backend()
            self.encryptor = Cipher(
                algorithms.AES(key),
                GCM(iv),
                backend=self.backend).encryptor()
            self._total = self.tell() + TAGSIZE
        else:
            self._total = self.tell()
        self.seek(0)
        self._callback = callback
        self._args = args
        self._seen = 0

    def __len__(self):
        return self._total

    def read(self, size):
        if self.event.isSet():
            raise UploadAbortedException
        if self.encrypted_upload:
            data = file.read(self, size)
            if len(data) > 0:
                data = self.encryptor.update(data)
                self._seen += len(data)
                if (self._seen + TAGSIZE) == self._total:
                    self.encryptor.finalize()
                    data += self.encryptor.tag
                    self._seen += TAGSIZE
                if self._callback:
                    gobject.idle_add(self._callback, self._seen, self._total, *self._args)
        else:
            data = file.read(self, size)
            self._seen += len(data)
            if self._callback:
                gobject.idle_add(self._callback, self._seen, self._total, *self._args)
        return data


class ProgressWindow:
    def __init__(self, during_text, messages_queue, base, event):
        self.plugin = base.plugin
        self.event = event
        self.xml = gtkgui_helpers.get_gtk_builder(self.plugin.local_file_path('upload_progress_dialog.ui'))
        self.messages_queue = messages_queue
        self.dialog = self.xml.get_object('progress_dialog')
        self.dialog.set_transient_for(base.chat_control.parent_win.window)
        self.label = self.xml.get_object('label')
        self.label.set_markup('<big>' + during_text + '</big>')
        self.progressbar = self.xml.get_object('progressbar')
        self.progressbar.set_text("")
        self.dialog.show_all()
        self.xml.connect_signals(self)

        self.pulse_progressbar_timeout_id = gobject.timeout_add(100, self.pulse_progressbar)
        self.process_messages_queue_timeout_id = gobject.timeout_add(100, self.process_messages_queue)

    def pulse_progressbar(self):
        if self.dialog:
            self.progressbar.pulse()
            return True # loop forever
        return False

    def process_messages_queue(self):
        if not self.messages_queue.empty():
            self.label.set_markup('<big>' + self.messages_queue.get() + '</big>')
        if self.dialog:
            return True # loop forever
        return False

    def update_progress(self, seen, total):
        if self.event.isSet():
            return
        if self.pulse_progressbar_timeout_id:
            gobject.source_remove(self.pulse_progressbar_timeout_id)
            self.pulse_progressbar_timeout_id = None
        pct = (float(seen) / total) * 100.0
        self.progressbar.set_fraction(float(seen) / total)
        self.progressbar.set_text(str(int(pct)) + "%")
        log.debug('upload progress: %.2f%% (%d of %d bytes)' % (pct, seen, total))

    def close_dialog(self, *args):
        self.dialog.destroy()

    def on_destroy(self, event, *args):
        self.event.set()
        if self.pulse_progressbar_timeout_id:
            gobject.source_remove(self.pulse_progressbar_timeout_id)
        gobject.source_remove(self.process_messages_queue_timeout_id)


class UploadAbortedException(Exception):
    def __str__(self):
        return "Upload Aborted"
