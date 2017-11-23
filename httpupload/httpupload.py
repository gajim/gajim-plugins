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
from urllib.parse import urlparse
import io
import mimetypes
import logging
from functools import partial
if os.name == 'nt':
    import certifi

import nbxmpp
from gi.repository import Gtk, GLib

from gajim.common import app
from gajim.common import ged
from gajim.plugins import GajimPlugin
from gajim.dialogs import FileChooserDialog, ErrorDialog

from .config_dialog import HTTPUploadConfigDialog

log = logging.getLogger('gajim.plugin_system.httpupload')

IQ_CALLBACK = {}
NS_HTTPUPLOAD = 'urn:xmpp:http:upload'


class HTTPUploadPlugin(GajimPlugin):
    def init(self):
        self.config_default_values = {
            'verify': (True, '')
        }
        self.config_dialog = partial(HTTPUploadConfigDialog, self)
        self.events_handlers = {
            'agent-info-received': (
                ged.PRECORE, self.handle_agent_info_received),
            'stanza-message-outgoing': (
                ged.OUT_PREGUI, self.handle_outgoing_stanza),
            'gc-stanza-message-outgoing': (
                ged.OUT_PREGUI, self.handle_outgoing_stanza),
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
        if (NS_HTTPUPLOAD not in event.features or not
                app.jid_is_transport(event.jid)):
            return

        if not event.id_.startswith('Gajim_'):
            return

        account = event.conn.name
        interface = self.get_interface(account)
        interface.enabled = True
        interface.component = event.jid
        interface.update_button_states(True)

        for form in event.data:
            form_dict = form.asDict()
            if form_dict.get('FORM_TYPE', None) != NS_HTTPUPLOAD:
                continue
            size = form_dict.get('max-file-size', None)
            if size is not None:
                interface.max_file_size = int(size)
                break

        if interface.max_file_size is None:
            log.warning('%s does not provide maximum file size', account)
        else:
            log.info('%s has a maximum file size of: %s',
                     account, interface.max_file_size)

    def handle_outgoing_stanza(self, event):
        message = event.msg_iq.getTagData('body')
        if message and message in self.messages:
            self.messages.remove(message)
            oob = event.msg_iq.addChild('x', namespace=nbxmpp.NS_X_OOB)
            oob.addChild('url').setData(message)
            if 'gajim' in event.additional_data:
                event.additional_data['gajim']['oob_url'] = message
            else:
                event.additional_data['gajim'] = {'oob_url': message}

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
        if actions_hbox is None:
            actions_hbox = chat_control.xml.get_object('hbox')
        actions_hbox.remove(interface.controls[jid])

    def update_chat_control(self, chat_control):
        account = chat_control.account
        if app.connections[account].connection is None:
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
        self.max_file_size = None
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

        if actions_hbox is None:
            actions_hbox = chat_control.xml.get_object('hbox')
            style = button.get_style_context()
            style.add_class('chatcontrol-actionbar-button')

        actions_hbox.add(button)

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

    @staticmethod
    def encryption_activated(chat_control):
        log.info('Encryption is: %s', chat_control.encryption or 'disabled')
        return chat_control.encryption is not None

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

    def on_file_dialog_ok(self, widget, chat_control):
        path = widget.get_filename()
        widget.destroy()

        if not path or not os.path.exists(path):
            return

        invalid_file = False
        stat = os.stat(path)

        if os.path.isfile(path):
            if stat[6] == 0:
                invalid_file = True
                msg = _('File is empty')
        else:
            invalid_file = True
            msg = _('File does not exist')

        if self.max_file_size is not None and \
                stat.st_size > self.max_file_size:
            invalid_file = True
            msg = _('File is too large, maximum allowed file size is: %s') % \
                GLib.format_size_full(self.max_file_size,
                GLib.FormatSizeFlags.IEC_UNITS)

        if invalid_file:
            ErrorDialog(_('Could not open file'), msg,
                        transient_for=chat_control.parent_win.window)
            return

        mime = mimetypes.MimeTypes().guess_type(path)[0]
        if not mime:
            mime = 'application/octet-stream'  # fallback mime type
        log.info("Detected MIME type of file: %s", mime)

        event = threading.Event()
        progress = ProgressWindow(
            self.plugin, chat_control.parent_win.window, event)

        try:
            file = File(path, mime=mime, encrypted=False,
                        control=chat_control, progress=progress, event=event)
        except Exception as error:
            log.exception('Error while loading file')
            file.progress.close_dialog()
            ErrorDialog(_('Error'), str(error),
                        transient_for=file.control.parent_win.window)
            return

        if self.encryption_activated(chat_control):
            self.encrypt_file(file)
        else:
            self.request_slot(file)

    def encrypt_file(self, file):
        GLib.idle_add(file.progress.label.set_text, _('Encrypting file...'))
        encryption = file.control.encryption
        plugin = app.plugin_manager.encryption_plugins[encryption]
        if hasattr(plugin, 'encrypt_file'):
            plugin.encrypt_file(file, self.account, self.request_slot)
        else:
            file.progress.close_dialog()
            ErrorDialog(
                _('Error'),
                'For the choosen encryption is no encryption method available',
                transient_for=file.control.parent_win.window)

    def request_slot(self, file):
        GLib.idle_add(file.progress.label.set_text,
                      _('Requesting HTTP Upload Slot...'))
        iq = nbxmpp.Iq(typ='get', to=self.component)
        id_ = app.get_an_id()
        iq.setID(id_)
        request = iq.setTag(name="request", namespace=NS_HTTPUPLOAD)
        request.addChild('filename', payload=os.path.basename(file.path))
        request.addChild('size', payload=file.size)
        request.addChild('content-type', payload=file.mime)

        log.info("Sending request for slot")
        IQ_CALLBACK[id_] = lambda stanza: self.received_slot(stanza, file)
        app.connections[self.account].connection.send(iq)

    @staticmethod
    def get_slot_error_message(stanza):
        tmp = stanza.getTag('error').getTag('file-too-large')

        if tmp is not None:
            max_file_size = int(tmp.getTag('max-file-size').getData())
            return _('File is too large, maximum allowed file size is: %s') % \
                GLib.format_size_full(max_file_size,
                GLib.FormatSizeFlags.IEC_UNITS)

        return stanza.getErrorMsg()

    def received_slot(self, stanza, file):
        log.info("Received slot")
        if stanza.getType() == 'error':
            file.progress.close_dialog()
            ErrorDialog(_('Could not request upload slot'),
                        self.get_slot_error_message(stanza),
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
            if (urlparse(file.put).scheme != 'https' or
                    urlparse(file.get).scheme != 'https'):
                raise UnsecureTransportError
        except UnsecureTransportError as error:
            file.progress.close_dialog()
            ErrorDialog(_('Error'), str(error),
                        transient_for=file.control.parent_win.window)
            return

        try:
            file.stream = StreamFileWithProgress(file)
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
            headers = {'User-Agent': 'Gajim %s' % app.version,
                       'Content-Type': file.mime,
                       'Content-Length': file.size}

            request = Request(
                file.put, data=file.stream, headers=headers, method='PUT')
            log.info("Opening Urllib upload request...")

            if not self.plugin.config['verify']:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                log.warning('CERT Verification disabled')
                transfer = urlopen(request, timeout=30, context=context)
            else:
                if os.name == 'nt':
                    transfer = urlopen(
                        request, cafile=certifi.where(), timeout=30)
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
            if file.user_data:
                message += '#' + file.user_data
                message = self.convert_to_aegscm(message)
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

    @staticmethod
    def convert_to_aegscm(url):
        return 'aesgcm' + url[5:]


class File:
    def __init__(self, path, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.stream = None
        self.path = path
        self.put = None
        self.get = None
        self.data = None
        self.user_data = None
        self.size = None
        self.load_data()

    def load_data(self):
        with open(self.path, 'rb') as content:
            self.data = content.read()
        self.size = len(self.data)

    def get_data(self, full=False):
        if full:
            return io.BytesIO(self.data).getvalue()
        return io.BytesIO(self.data)

class StreamFileWithProgress:
    def __init__(self, file, *args):
        self.event = file.event
        self.backing = file.get_data()
        self.backing.seek(0, os.SEEK_END)
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


class UnsecureTransportError(Exception):
    def __str__(self):
        return 'Server returned unsecure transport'
