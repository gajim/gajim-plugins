# -*- coding: utf-8 -*-
#
# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim.  If not, see <http://www.gnu.org/licenses/>.


from gi.repository import GObject, Gtk, GLib
import os
import sys
import time
from urllib.request import Request, urlopen
import mimetypes        # better use the magic packet, but that's not a standard lib
import gtkgui_helpers
import logging
from queue import Queue
import binascii

from common import gajim
from common import ged
from plugins import GajimPlugin
from plugins.helpers import log_calls
from dialogs import FileChooserDialog, ErrorDialog
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
    ENCRYPTION_AVAILABLE = True
except Exception as exc:
    DEP_MSG = 'For encryption of files, ' \
              'please install python-cryptography!'
    log.debug('Cryptography Import Error: %s', exc)
    log.info('Decryption/Encryption disabled due to errors')
    ENCRYPTION_AVAILABLE = False

# XEP-0363 (http://xmpp.org/extensions/xep-0363.html)
IQ_CALLBACK = {}
NS_HTTPUPLOAD = 'urn:xmpp:http:upload'
TAGSIZE = 16


class HttpuploadPlugin(GajimPlugin):
    def init(self):
        if not ENCRYPTION_AVAILABLE:
            self.available_text = DEP_MSG
        self.config_dialog = None  # HttpuploadPluginConfigDialog(self)
        self.events_handlers = {}
        self.events_handlers['agent-info-received'] = (
            ged.PRECORE, self.handle_agent_info_received)
        self.events_handlers['raw-iq-received'] = (
            ged.PRECORE, self.handle_iq_received)
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                  self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (self.update_chat_control,
                                                 None)}
        self.gui_interfaces = {}

    @staticmethod
    def handle_iq_received(event):
        id_ = event.stanza.getAttr("id")
        if id_ in IQ_CALLBACK:
            try:
                IQ_CALLBACK[id_](event.stanza)
            except:
                raise
            finally:
                del IQ_CALLBACK[id_]

    def handle_agent_info_received(self, event):
        if (NS_HTTPUPLOAD in event.features and
                gajim.jid_is_transport(event.jid)):
            account = event.conn.name
            interface = self.get_interface(account)
            interface.enabled = True
            interface.component = event.jid
            interface.update_button_states(True)

    def connect_with_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        self.get_interface(account).add_button(chat_control)

    def disconnect_from_chat_control(self, chat_control):
        jid = chat_control.contact.jid
        account = chat_control.account
        interface = self.get_interface(account)
        if jid not in interface.controls:
            return
        actions_hbox = chat_control.xml.get_object('actions_hbox')
        actions_hbox.remove(interface.controls[jid])

    def update_chat_control(self, chat_control):
        account = chat_control.account
        if gajim.connections[account].connection is None:
            self.get_interface(account).update_button_states(False)

    def get_interface(self, account):
        try:
            return self.gui_interfaces[account]
        except KeyError:
            self.gui_interfaces[account] = Base(self, account)
            return self.gui_interfaces[account]


class Base(object):
    def __init__(self, plugin, account):
        self.plugin = plugin
        self.account = account
        self.encrypted_upload = False
        self.enabled = False
        self.component = None
        self.controls = {}
        self.conn = gajim.connections[account].connection

    def add_button(self, chat_control):
        jid = chat_control.contact.jid

        img = Gtk.Image()
        img.set_from_file(self.plugin.local_file_path('httpupload.png'))
        actions_hbox = chat_control.xml.get_object('actions_hbox')
        button = Gtk.Button(label=None, stock=None, use_underline=True)
        button.set_property('can-focus', False)
        button.set_image(img)
        button.set_relief(Gtk.ReliefStyle.NONE)

        actions_hbox.add(button)
        send_button = chat_control.xml.get_object('send_button')
        button_pos = actions_hbox.child_get_property(send_button, 'position')
        actions_hbox.child_set_property(button, 'position', button_pos - 1)

        self.controls[jid] = button
        id_ = button.connect('clicked', self.on_file_button_clicked, jid, chat_control)
        chat_control.handlers[id_] = button
        self.set_button_state(self.enabled, button)
        button.show()

    @staticmethod
    def set_button_state(state, button):
        if state:
            button.set_sensitive(state)
            button.set_tooltip_text(_('Send file via http upload'))
        else:
            button.set_sensitive(state)
            button.set_tooltip_text(
                _('Your server does not support http uploads'))

    def update_button_states(self, state):
        for jid in self.controls:
            self.set_button_state(state, self.controls[jid])

    def encryption_activated(self, jid):
        if not ENCRYPTION_AVAILABLE:
            return False
        for plugin in gajim.plugin_manager.active_plugins:
            if type(plugin).__name__ == 'OmemoPlugin':
                state = plugin.get_omemo_state(self.account)
                encryption = state.encryption.is_active(jid)
                log.info('Encryption is: %s', encryption)
                return encryption
        log.info('OMEMO not found, encryption disabled')
        return False

    def on_file_dialog_ok(self, widget, jid, chat_control):
        path = widget.get_filename()
        widget.destroy()

        if not path or not os.path.exists(path):
            return

        invalid_file = False
        if os.path.isfile(path):
            stat = os.stat(path)
            if stat[6] == 0:
                invalid_file = True
                msg = _('File is empty')
        else:
            invalid_file = True
            msg = _('File does not exist')
        if invalid_file:
            ErrorDialog(_('Could not open file'), msg,
                        transient_for=chat_control.parent_win.window)
            return

        encrypted = self.encryption_activated(jid)
        size = os.path.getsize(path)
        key, iv = None, None
        if encrypted:
            key = os.urandom(32)
            iv = os.urandom(16)
            size += TAGSIZE

        mime = mimetypes.MimeTypes().guess_type(path)[0]
        if not mime:
            mime = 'application/octet-stream'  # fallback mime type
        log.info("Detected MIME type of file: ", mime)

        progress_messages = Queue(8)
        progress_window = ProgressWindow(_('HTTP Upload'), _('Requesting HTTP Upload Slot...'),
                progress_messages, self.plugin, parent=chat_control.parent_win.window)

        file = File(path=path, size=size, mime=mime, encrypted=encrypted,
                    key=key, iv=iv, control=chat_control,
                    progress=progress_window)
        self.request_slot(file)

        def upload_file(stanza):

            def upload_complete(response_code):
                if response_code == 0:
                    return      # Upload was aborted
                if 200 <= response_code < 300:
                    log.info("Upload completed successfully")
                    xhtml = None
                    is_image = mime_type.split('/', 1)[0] == 'image'
                    progress_window.close_dialog()
                    id_ = gajim.get_an_id()
                    def add_oob_tag():
                        pass
                    if self.encrypted_upload:
                        keyAndIv = '#' + binascii.hexlify(iv) + binascii.hexlify(key)
                        self.chat_control.send_message(message=get.getData() + keyAndIv, xhtml=None)
                    else:
                        self.chat_control.send_message(message=get.getData(), xhtml=xhtml)
                    self.chat_control.msg_textview.grab_focus()
                else:
                    progress_window.close_dialog()
                    log.error("got unexpected http upload response code: " + str(response_code))
                    ErrorDialog(_('Could not upload file'),
                                _('Got unexpected http response code from server: ') + str(response_code),
                                transient_for=self.chat_control.parent_win.window)

            def on_upload_error():
                progress_window.close_dialog()
                ErrorDialog(_('Could not upload file'),
                            _('Got unexpected exception while uploading file'
                              ' (see error log for more information)'),
                            transient_for=self.chat_control.parent_win.window)
                return 0

            def uploader():
                progress_messages.put(_('Uploading file via HTTP...'))
                try:
                    headers = {'User-Agent': 'Gajim %s' % gajim.version,
                               'Content-Type': mime_type}
                    request = Request(put.getData(), data=data, headers=headers, method='PUT')
                    log.debug("opening urllib upload request...")
                    transfer = urlopen(request, timeout=30)
                    data.close()
                    log.debug("urllib upload request done, response code: " + str(transfer.getcode()))
                    return transfer.getcode()
                except UploadAbortedException:
                    log.info("Upload aborted")
                except:
                    log.error("Exception during upload", exc_info=sys.exc_info())
                    GLib.idle_add(on_upload_error)
                return 0

            log.info("Uploading file to '%s'..." % str(put.getData()))
            log.info("Please download from '%s' later..." % str(get.getData()))

            gajim.thread_interface(uploader, [], upload_complete)

        self.chat_control.msg_textview.grab_focus()

    def on_file_button_clicked(self, widget, jid, chat_control):
        FileChooserDialog(
            on_response_ok=lambda widget: self.on_file_dialog_ok(widget, jid,
                                                                 chat_control),
            title_text=_('Choose file to send'),
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_OPEN, Gtk.ResponseType.OK),
            default_response=Gtk.ResponseType.OK,
            transient_for=chat_control.parent_win.window)

    def request_slot(self, file):
        iq = nbxmpp.Iq(typ='get', to=self.component)
        id_ = gajim.get_an_id()
        iq.setID(id_)
        request = iq.setTag(name="request", namespace=NS_HTTPUPLOAD)
        request.addChild('filename', payload=os.path.basename(file.path))
        request.addChild('size', payload=file.size)
        request.addChild('content-type', payload=file.mime)

        log.info("Sending request for slot")
        IQ_CALLBACK[id_] = lambda stanza: self.received_slot(stanza, file)
        self.conn.send(iq)

    def received_slot(self, stanza, file):
        if stanza.getType() == 'error':
            file.progress.close_dialog()
            ErrorDialog(_('Could not request upload slot'),
                        stanza.getErrorMsg(),
                        transient_for=file.control.parent_win.window)
            log.error(stanza)
            return

        try:
            file.put = stanza.getTag("slot").getTag("put")
            file.get = stanza.getTag("slot").getTag("get")
        except Exception as exc:
            file.progress.close_dialog()
            log.error("Got unexpected stanza: ", stanza)
            log.exception('Error')
            ErrorDialog(_('Could not request upload slot'),
                        _('Got unexpected response from server (see log)'),
                        transient_for=file.control.parent_win.window)
            return

        try:
            file.stream = StreamFileWithProgress(file, "rb")
        except Exception as exc:
            file.progress.close_dialog()
            log.exception("Could not open file")
            ErrorDialog(_('Could not open file'),
                        _('Exception raised while opening file (see log)'),
                        transient_for=file.control.parent_win.window)
            return


class File:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.stream = None
        self.put = None
        self.get = None


class StreamFileWithProgress:
    def __init__(self, file, mode, *args):
        self.backing = open(file.path, mode)
        self.encrypted_upload = file.encrypted
        self.backing.seek(0, os.SEEK_END)
        if self.encrypted_upload:
            if os.name == 'nt':
                self.backend = backend
            else:
                self.backend = default_backend()
            self.encryptor = Cipher(
                algorithms.AES(file.key),
                GCM(file.iv),
                backend=self.backend).encryptor()
            self._total = self.backing.tell() + TAGSIZE
        else:
            self._total = self.backing.tell()
        self.backing.seek(0)
        self._callback = file.progress.update_progress
        self._args = args
        self._seen = 0

    def __len__(self):
        return self._total

    def read(self, size):
        if self.encrypted_upload:
            data = self.backing.read(size)
            if len(data) > 0:
                data = self.encryptor.update(data)
                self._seen += len(data)
                if (self._seen + TAGSIZE) == self._total:
                    self.encryptor.finalize()
                    data += self.encryptor.tag
                    self._seen += TAGSIZE
                if self._callback:
                    self._callback(self._seen, self._total, *self._args)
            return data
        else:
            data = self.backing.read(size)
            self._seen += len(data)
            if self._callback:
                self._callback(self._seen, self._total, *self._args)
            return data

    def close(self):
        return self.backing.close()


class ProgressWindow:
    def __init__(self, title_text, during_text, messages_queue, plugin, parent):
        self.plugin = plugin
        self.xml = gtkgui_helpers.get_gtk_builder(self.plugin.local_file_path('upload_progress_dialog.ui'))
        self.messages_queue = messages_queue
        self.dialog = self.xml.get_object('progress_dialog')
        self.dialog.set_transient_for(parent)
        self.label = self.xml.get_object('label')
        self.cancel_button = self.xml.get_object('close_button')
        self.label.set_markup('<big>' + during_text + '</big>')
        self.progressbar = self.xml.get_object('progressbar')
        self.progressbar.set_text("")
        self.dialog.set_title(title_text)
        #self.dialog.set_geometry_hints(min_width=400, min_height=96)
        #self.dialog.set_position(Gtk.WIN_POS_CENTER_ON_PARENT)
        self.dialog.show_all()
        self.xml.connect_signals(self)

        self.stopped = False
        self.pulse_progressbar_timeout_id = GLib.timeout_add(100, self.pulse_progressbar)
        self.process_messages_queue_timeout_id = GLib.timeout_add(100, self.process_messages_queue)


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

    def on_progress_dialog_delete_event(self, widget, event):
        self.stopped = True
        if self.pulse_progressbar_timeout_id:
            GLib.source_remove(self.pulse_progressbar_timeout_id)
        GLib.source_remove(self.process_messages_queue_timeout_id)

    def on_cancel(self, widget):
        self.stopped = True
        if self.pulse_progressbar_timeout_id:
            GLib.source_remove(self.pulse_progressbar_timeout_id)
        GLib.source_remove(self.process_messages_queue_timeout_id)
        self.dialog.destroy()

    def update_progress(self, seen, total):
        if self.stopped == True:
            raise UploadAbortedException
        if self.pulse_progressbar_timeout_id:
            GLib.source_remove(self.pulse_progressbar_timeout_id)
            self.pulse_progressbar_timeout_id = None
        pct = (float(seen) / total) * 100.0
        self.progressbar.set_fraction(float(seen) / total)
        self.progressbar.set_text(str(int(pct)) + "%")
        log.debug('upload progress: %.2f%% (%d of %d bytes)' % (pct, seen, total))

    def close_dialog(self):
        self.on_cancel(None)

class UploadAbortedException(Exception):
    def __str__(self):
        return "Upload Aborted"
