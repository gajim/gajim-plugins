# -*- coding: utf-8 -*-
#
# Copyright 2017 Philipp Hörist <philipp@hoerist.com>
#
# This file is part of Gajim-OMEMO plugin.
#
# The Gajim-OMEMO plugin is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Gajim-OMEMO is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# the Gajim-OMEMO plugin.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import hashlib
import logging
import socket
import threading
import platform
import subprocess
import binascii
from urllib.request import urlopen
from urllib.error import URLError
from urllib.parse import urlparse, urldefrag
from io import BufferedWriter, FileIO, BytesIO

from gi.repository import GLib
import gtkgui_helpers
from common import configpaths
from dialogs import ErrorDialog, YesNoDialog
if os.name == 'nt':
    import certifi

log = logging.getLogger('gajim.plugin_system.omemo.filedecryption')

ERROR = False
try:
    from cryptography.hazmat.primitives.ciphers import Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms
    from cryptography.hazmat.primitives.ciphers.modes import GCM
    from cryptography.hazmat.backends import default_backend
except ImportError:
    log.exception('ImportError')
    ERROR = True

DIRECTORY = os.path.join(configpaths.gajimpaths['MY_DATA'], 'downloads')

try:
    if not os.path.exists(DIRECTORY):
        os.makedirs(DIRECTORY)
except Exception:
    ERROR = True
    log.exception('Error')


class File:
    def __init__(self, url):
        self.url, self.fragment = urldefrag(url)
        self.key = None
        self.iv = None
        self.filepath = None
        self.filename = None


class FileDecryption:
    def __init__(self, plugin):
        self.plugin = plugin
        self.window = None

    def hyperlink_handler(self, url, kind, instance, window):
        if ERROR or kind != 'url':
            return
        self.window = window
        urlparts = urlparse(url)
        file = File(urlparts.geturl())

        if urlparts.scheme not in ['https', 'aesgcm'] or not urlparts.netloc:
            log.info("Not accepting URL for decryption: %s", url)
            return

        if urlparts.scheme == 'aesgcm':
            log.debug('aesgcm scheme detected')
            file.url = 'https://' + file.url[9:]

        if not self.is_encrypted(file):
            log.info('Url not encrypted: %s', url)
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
        question = 'Do you want to open %s' % file.filename
        YesNoDialog('Open File', question,
                    transient_for=self.window,
                    on_response_yes=(self.open_file, file.filepath))
        return False

    def open_file(self, checked, path):
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


class Download:
    def __init__(self, file, progressbar, window, event, base):
        self.file = file
        self.progressbar = progressbar
        self.window = window
        self.event = event
        self.base = base
        self.download()

    def download(self):
        GLib.idle_add(self.progressbar.set_text, 'Downloading...')
        data = self.load_url()
        if isinstance(data, str):
            GLib.idle_add(self.progressbar.close_dialog)
            GLib.idle_add(self.error, data)
            return

        GLib.idle_add(self.progressbar.set_text, 'Decrypting...')
        decrypted_data = self.aes_decrypt(data)

        GLib.idle_add(
            self.progressbar.set_text, 'Writing file to harddisk...')
        self.write_file(decrypted_data)

        GLib.idle_add(self.progressbar.close_dialog)

        GLib.idle_add(self.base.finished, self.file)

    def load_url(self):
        try:
            stream = BytesIO()
            if os.name == 'nt':
                get_request = urlopen(
                    self.file.url, cafile=certifi.where(), timeout=30)
            else:
                get_request = urlopen(self.file.url, timeout=30)
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

    def aes_decrypt(self, payload):
        # Use AES128 GCM with the given key and iv to decrypt the payload.
        payload = payload.getvalue()
        data = payload[:-16]
        tag = payload[-16:]
        decryptor = Cipher(
            algorithms.AES(self.file.key),
            GCM(self.file.iv, tag=tag),
            backend=default_backend()).decryptor()
        return decryptor.update(data) + decryptor.finalize()

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


class ProgressWindow:
    def __init__(self, plugin, window, event):
        self.plugin = plugin
        self.event = event
        self.xml = gtkgui_helpers.get_gtk_builder(
            self.plugin.local_file_path('download_progress_dialog.ui'))
        self.dialog = self.xml.get_object('progress_dialog')
        self.dialog.set_transient_for(window)
        self.label = self.xml.get_object('label')
        self.progressbar = self.xml.get_object('progressbar')
        self.progressbar.set_text("")
        self.dialog.show_all()
        self.xml.connect_signals(self)
        self.seen = 0

    def set_text(self, text):
        self.label.set_markup('<big>%s</big>' % text)
        return False

    def update_progress(self, seen, total):
        self.seen += seen
        pct = (self.seen / float(total)) * 100.0
        self.progressbar.set_fraction(self.seen / float(total))
        self.progressbar.set_text(str(int(pct)) + "%")
        return False

    def close_dialog(self, *args):
        self.dialog.destroy()
        return False

    def on_destroy(self, *args):
        self.event.set()


class DownloadAbortedException(Exception):
    def __str__(self):
        return _('Download Aborted')
