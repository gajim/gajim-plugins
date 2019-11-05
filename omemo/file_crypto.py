# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of OMEMO Gajim Plugin.
#
# OMEMO Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import hashlib
import logging
import socket
import threading
import binascii
import ssl
from urllib.request import urlopen
from urllib.error import URLError
from urllib.parse import urlparse, urldefrag
from io import BufferedWriter, FileIO, BytesIO

from gi.repository import GLib

from gajim.common import app
from gajim.common import configpaths
from gajim.common import helpers
from gajim.common.const import URIType
from gajim.plugins.plugins_i18n import _
from gajim.gtk.dialogs import ErrorDialog
from gajim.gtk.dialogs import DialogButton
from gajim.gtk.dialogs import NewConfirmationDialog

from omemo.gtk.progress import ProgressWindow
from omemo.backend.aes import aes_decrypt_file

if sys.platform in ('win32', 'darwin'):
    import certifi

log = logging.getLogger('gajim.p.omemo.filedecryption')

DIRECTORY = os.path.join(configpaths.get('MY_DATA'), 'downloads')

ERROR = False
try:
    if not os.path.exists(DIRECTORY):
        os.makedirs(DIRECTORY)
except Exception:
    ERROR = True
    log.exception('Error')


class File:
    def __init__(self, url, account):
        self.account = account
        self.url, self.fragment = urldefrag(url)
        self.key = None
        self.iv = None
        self.filepath = None
        self.filename = None


class FileDecryption:
    def __init__(self, plugin):
        self.plugin = plugin
        self.window = None

    def hyperlink_handler(self, uri, instance, window):
        if ERROR or uri.type != URIType.WEB:
            return
        self.window = window
        urlparts = urlparse(uri.data)
        file = File(urlparts.geturl(), instance.account)

        if urlparts.scheme not in ['https', 'aesgcm'] or not urlparts.netloc:
            log.info("Not accepting URL for decryption: %s", uri.data)
            return

        if urlparts.scheme == 'aesgcm':
            log.debug('aesgcm scheme detected')
            file.url = 'https://' + file.url[9:]

        if not self.is_encrypted(file):
            log.info('URL not encrypted: %s', uri.data)
            return

        self.create_paths(file)

        if os.path.exists(file.filepath):
            instance.plugin_modified = True
            self.finished(file)
            return

        event = threading.Event()
        progressbar = ProgressWindow(self.plugin, self.window, event)
        thread = threading.Thread(target=Download,
                                  args=(file, progressbar, self.window,
                                        event, self))
        thread.daemon = True
        thread.start()
        instance.plugin_modified = True

    def is_encrypted(self, file):
        if file.fragment:
            try:
                fragment = binascii.unhexlify(file.fragment)
                file.key = fragment[16:]
                file.iv = fragment[:16]
                if len(file.key) == 32 and len(file.iv) == 16:
                    return True

                file.key = fragment[12:]
                file.iv = fragment[:12]
                if len(file.key) == 32 and len(file.iv) == 12:
                    return True
            except:
                return False
        return False

    def create_paths(self, file):
        file.filename = os.path.basename(file.url)
        ext = os.path.splitext(file.filename)[1]
        name = os.path.splitext(file.filename)[0]
        urlhash = hashlib.sha1(file.url.encode('utf-8')).hexdigest()
        newfilename = name + '_' + urlhash[:10] + ext
        file.filepath = os.path.join(DIRECTORY, newfilename)

    def finished(self, file):
        def _open_file():
            helpers.open_file(file.filepath)

        NewConfirmationDialog(
            _('Open File'),
            _('Open File?'),
            _('Do you want to open %s?') % file.filename,
            [DialogButton.make('Cancel',
                               text=_('_No')),
             DialogButton.make('Accept',
                               text=_('_Open'),
                               callback=_open_file)],
            transient_for=self.window).show()

        return False


class Download:
    def __init__(self, file, progressbar, window, event, base):
        self.file = file
        self.progressbar = progressbar
        self.window = window
        self.event = event
        self.base = base
        self.download()

    def download(self):
        GLib.idle_add(self.progressbar.set_text, _('Downloading...'))
        data = self.load_url()
        if isinstance(data, str):
            GLib.idle_add(self.progressbar.close_dialog)
            GLib.idle_add(self.error, data)
            return

        GLib.idle_add(self.progressbar.set_text, _('Decrypting...'))

        decrypted_data = aes_decrypt_file(self.file.key,
                                          self.file.iv,
                                          data.getvalue())

        GLib.idle_add(
            self.progressbar.set_text, _('Writing file to harddisk...'))
        self.write_file(decrypted_data)

        GLib.idle_add(self.progressbar.close_dialog)

        GLib.idle_add(self.base.finished, self.file)

    def load_url(self):
        try:
            stream = BytesIO()
            if not app.config.get_per('accounts',
                                      self.file.account,
                                      'httpupload_verify'):
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                log.warning('CERT Verification disabled')
                get_request = urlopen(self.file.url, timeout=30, context=context)
            else:
                cafile = None
                if sys.platform in ('win32', 'darwin'):
                    cafile = certifi.where()
                context = ssl.create_default_context(cafile=cafile)
                get_request = urlopen(self.file.url, timeout=30, context=context)

            size = get_request.info()['Content-Length']
            if not size:
                errormsg = 'Content-Length not found in header'
                log.error(errormsg)
                return errormsg
            while True:
                try:
                    if self.event.isSet():
                        raise DownloadAbortedException
                    temp = get_request.read(10000)
                    GLib.idle_add(
                        self.progressbar.update_progress, len(temp), size)
                except socket.timeout:
                    errormsg = 'Request timeout'
                    log.error(errormsg)
                    return errormsg
                if temp:
                    stream.write(temp)
                else:
                    return stream
        except DownloadAbortedException as error:
            log.info('Download Aborted')
            errormsg = error
        except URLError as error:
            log.exception('URLError')
            errormsg = error.reason
        except Exception as error:
            log.exception('Error')
            errormsg = error
        stream.close()
        return str(errormsg)

    def write_file(self, data):
        log.info('Writing data to %s', self.file.filepath)
        try:
            with BufferedWriter(FileIO(self.file.filepath, "wb")) as output:
                output.write(data)
                output.close()
        except Exception:
            log.exception('Failed to write file')

    def error(self, error):
        ErrorDialog(_('Error'), error, transient_for=self.window)
        return False


class DownloadAbortedException(Exception):
    def __str__(self):
        return _('Download Aborted')
