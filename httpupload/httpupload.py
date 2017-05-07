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

import os
import threading
import ssl
import urllib
from urllib.request import Request, urlopen
import mimetypes
import logging
from binascii import hexlify
if os.name == 'nt':
    import certifi

import nbxmpp
from gi.repository import Gtk, GLib

from common import gajim
from common import ged
from plugins import GajimPlugin
from dialogs import FileChooserDialog, ErrorDialog

log = logging.getLogger('gajim.plugin_system.httpupload')

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms
    from cryptography.hazmat.primitives.ciphers.modes import GCM
    ENCRYPTION_AVAILABLE = True
except Exception as exc:
    DEP_MSG = 'For encryption of files, ' \
              'please install python-cryptography!'
    log.error('Cryptography Import Error: %s', exc)
    log.info('Decryption/Encryption disabled due to errors')
    ENCRYPTION_AVAILABLE = False

IQ_CALLBACK = {}
NS_HTTPUPLOAD = 'urn:xmpp:http:upload'
TAGSIZE = 16


class HttpuploadPlugin(GajimPlugin):
    def init(self):
        if not ENCRYPTION_AVAILABLE:
            self.available_text = DEP_MSG
        self.config_dialog = None
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
            'chat_control_base_update_toolbar': (self.update_chat_control,
                                                 None)}
        self.gui_interfaces = {}
        self.messages = []

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

    def handle_outgoing_stanza(self, event):
        message = event.msg_iq.getTagData('body')
        if message and message in self.messages:
            self.messages.remove(message)
            oob = event.msg_iq.addChild('x', namespace=nbxmpp.NS_X_OOB)
            oob.addChild('url').setData(message)

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
        id_ = button.connect(
            'clicked', self.on_file_button_clicked, chat_control)
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

    def encryption_activated(self, chat_control):
        encrypted = chat_control.encryption == 'OMEMO'
        log.info('Encryption is: %s', encrypted)
        return encrypted

    def on_file_dialog_ok(self, widget, chat_control):
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

        encrypted = self.encryption_activated(chat_control)
        if encrypted and not ENCRYPTION_AVAILABLE:
            ErrorDialog(
                _('Error'),
                'Please install python-cryptography for encrypted uploads',
                transient_for=chat_control.parent_win.window)
            return
        size = os.path.getsize(path)
        key, iv = None, None
        if encrypted:
            key = os.urandom(32)
            iv = os.urandom(16)
            size += TAGSIZE

        mime = mimetypes.MimeTypes().guess_type(path)[0]
        if not mime:
            mime = 'application/octet-stream'  # fallback mime type
        log.info("Detected MIME type of file: %s", mime)

        event = threading.Event()
        progress = ProgressWindow(
            self.plugin, chat_control.parent_win.window, event)

        file = File(path=path, size=size, mime=mime, encrypted=encrypted,
                    key=key, iv=iv, control=chat_control,
                    progress=progress, event=event)
        self.request_slot(file)

    def on_file_button_clicked(self, widget, chat_control):
        FileChooserDialog(
            on_response_ok=lambda widget: self.on_file_dialog_ok(widget,
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
        gajim.connections[self.account].connection.send(iq)

    def received_slot(self, stanza, file):
        log.info("Received slot")
        if stanza.getType() == 'error':
            file.progress.close_dialog()
            ErrorDialog(_('Could not request upload slot'),
                        stanza.getErrorMsg(),
                        transient_for=file.control.parent_win.window)
            log.error(stanza)
            return

        try:
            file.put = stanza.getTag("slot").getTag("put").getData()
            file.get = stanza.getTag("slot").getTag("get").getData()
        except Exception:
            file.progress.close_dialog()
            log.error("Got unexpected stanza: %s", stanza)
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

        log.info('Uploading file to %s', file.put)
        log.info('Please download from %s', file.get)

        thread = threading.Thread(target=self.upload_file, args=(file,))
        thread.daemon = True
        thread.start()

    def upload_file(self, file):
        GLib.idle_add(file.progress.label.set_text,
                      _('Uploading file via HTTP...'))
        try:
            headers = {'User-Agent': 'Gajim %s' % gajim.version,
                       'Content-Type': file.mime}
            request = Request(
                file.put, data=file.stream, headers=headers, method='PUT')
            log.info("Opening Urllib upload request...")
            if os.name == 'nt':
                transfer = urlopen(request, cafile=certifi.where(), timeout=30)
            else:
                transfer = urlopen(request, timeout=30)
            file.stream.close()
            log.info('Urllib upload request done, response code: %s',
                     transfer.getcode())
            GLib.idle_add(self.upload_complete, transfer.getcode(), file)
            return
        except UploadAbortedException as exc:
            log.info(exc)
            error_msg = exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, ssl.SSLError):
                error_msg = exc.reason.reason
                if error_msg == 'CERTIFICATE_VERIFY_FAILED':
                    log.exception('Certificate verify failed')
            else:
                log.exception('URLError')
                error_msg = exc.reason
        except Exception as exc:
            log.exception("Exception during upload")
            error_msg = exc
        GLib.idle_add(file.progress.close_dialog)
        GLib.idle_add(self.on_upload_error, file, error_msg)

    def upload_complete(self, response_code, file):
        file.progress.close_dialog()
        if 200 <= response_code < 300:
            log.info("Upload completed successfully")
            message = file.get
            if file.encrypted:
                message += '#' + hexlify(file.iv + file.key).decode('utf-8')
            else:
                self.plugin.messages.append(message)
            file.control.send_message(message=message)
            file.control.msg_textview.grab_focus()
        else:
            log.error('Got unexpected http upload response code: %s',
                      response_code)
            ErrorDialog(
                _('Could not upload file'),
                _('HTTP response code from server: %s') % response_code,
                transient_for=file.control.parent_win.window)

    @staticmethod
    def on_upload_error(file, reason):
        file.progress.close_dialog()
        ErrorDialog(_('Error'), str(reason),
                    transient_for=file.control.parent_win.window)


class File:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.stream = None
        self.put = None
        self.get = None


class StreamFileWithProgress:
    def __init__(self, file, mode, *args):
        self.event = file.event
        self.backing = open(file.path, mode)
        self.encrypted = file.encrypted
        self.backing.seek(0, os.SEEK_END)
        if self.encrypted:
            self.encryptor = Cipher(
                algorithms.AES(file.key),
                GCM(file.iv),
                backend=default_backend()).encryptor()
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
        if self.event.isSet():
            raise UploadAbortedException
        if self.encrypted:
            data = self.backing.read(size)
            if len(data) > 0:
                data = self.encryptor.update(data)
                self._seen += len(data)
                if (self._seen + TAGSIZE) == self._total:
                    self.encryptor.finalize()
                    data += self.encryptor.tag
                    self._seen += TAGSIZE
                if self._callback:
                    GLib.idle_add(
                        self._callback, self._seen, self._total, *self._args)
            return data
        else:
            data = self.backing.read(size)
            self._seen += len(data)
            if self._callback:
                GLib.idle_add(
                    self._callback, self._seen, self._total, *self._args)
            return data

    def close(self):
        return self.backing.close()


class ProgressWindow:
    def __init__(self, plugin, parent, event):
        self.plugin = plugin
        self.event = event
        glade_file = self.plugin.local_file_path('upload_progress_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.add_from_file(glade_file)
        self.dialog = self.xml.get_object('progress_dialog')
        self.dialog.set_transient_for(parent)
        self.dialog.set_title('HTTP Upload')
        self.label = self.xml.get_object('label')
        self.label.set_text(_('Requesting HTTP Upload Slot...'))
        self.progressbar = self.xml.get_object('progressbar')
        self.dialog.show_all()
        self.xml.connect_signals(self)

        self.pulse = GLib.timeout_add(100, self.pulse_progressbar)

    def pulse_progressbar(self):
        if self.dialog:
            self.progressbar.pulse()
            return True
        return False

    def on_destroy(self, *args):
        self.event.set()
        if self.pulse:
            GLib.source_remove(self.pulse)

    def update_progress(self, seen, total):
        if self.event.isSet():
            return
        if self.pulse:
            GLib.source_remove(self.pulse)
            self.pulse = None
        pct = (float(seen) / total) * 100.0
        self.progressbar.set_fraction(float(seen) / total)
        self.progressbar.set_text(str(int(pct)) + "%")

    def close_dialog(self, *args):
        self.dialog.destroy()


class UploadAbortedException(Exception):
    def __str__(self):
        return "Upload Aborted"
