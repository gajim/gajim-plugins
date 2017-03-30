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
import urllib2
import socket
import threading
import platform
import subprocess
import binascii
from io import BufferedWriter, FileIO, BytesIO
from urlparse import urlparse, urldefrag

import gtk
import gobject
import gtkgui_helpers
from common import configpaths
from dialogs import ErrorDialog, YesNoDialog

from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers import algorithms
from cryptography.hazmat.primitives.ciphers.modes import GCM
from cryptography.hazmat.backends import default_backend

log = logging.getLogger('gajim.plugin_system.omemo.filedecryption')

DIRECTORY = os.path.join(configpaths.gajimpaths['MY_DATA'], 'downloads')
try:
    if not os.path.exists(DIRECTORY):
        os.makedirs(DIRECTORY)
    ERROR = False
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
        self.chat_control = None
        self.orig_handler = None
        self.tv = None
        self.progress_windows = {}

    def activate(self, chat_control):
        if ERROR:
            return
        self.tv = chat_control.conv_textview.tv
        self.chat_control = chat_control
        self.orig_handler = self.tv.hyperlink_handler
        self.tv.hyperlink_handler = self.hyperlink_handler

    def deactivate(self):
        self.tv.hyperlink_handler = self.orig_handler

    def hyperlink_handler(self, texttag, widget, event, iter_, kind):
        if event.type != gtk.gdk.BUTTON_PRESS:
            return
        if event.button == 3:
            self.orig_handler(texttag, widget, event, iter_, kind)
            return
        begin_iter = iter_.copy()
        # we get the begining of the tag
        while not begin_iter.begins_tag(texttag):
            begin_iter.backward_char()
        end_iter = iter_.copy()
        # we get the end of the tag
        while not end_iter.ends_tag(texttag):
            end_iter.forward_char()

        url = self.tv.get_buffer().get_text(begin_iter, end_iter, True)
        urlparts = urlparse(url)
        file = File(urlparts.geturl())

        if urlparts.scheme not in ["https"] or not urlparts.netloc:
            log.info("Not accepting URL for decryption: %s", url)
            self.orig_handler(texttag, widget, event, iter_, kind)
            return

        if not self.is_encrypted(file):
            log.info('Url not encrypted: %s', url)
            self.orig_handler(texttag, widget, event, iter_, kind)
            return

        self.create_paths(file)

        if os.path.exists(file.filepath):
            self.finished(file)
            return

        event = threading.Event()
        progressbar = ProgressWindow(self.plugin, self.chat_control, event)
        thread = threading.Thread(target=Download,
                                  args=(file, progressbar, self.chat_control,
                                        event, self))
        thread.daemon = True
        thread.start()

    def is_encrypted(self, file):
        if file.fragment:
            try:
                fragment = binascii.unhexlify(file.fragment)
                file.key = fragment[16:]
                file.iv = fragment[:16]
                if len(file.key) == 32 and len(file.iv) == 16:
                    return True
            except:
                return False
        return False

    def create_paths(self, file):
        file.filename = os.path.basename(file.url)
        ext = os.path.splitext(file.filename)[1]
        name = os.path.splitext(file.filename)[0]
        urlhash = hashlib.sha1(file.url).hexdigest()
        newfilename = name + '_' + urlhash[:10] + ext
        file.filepath = os.path.join(DIRECTORY, newfilename)

    def finished(self, file):
        question = 'Do you want to open %s' % file.filename
        YesNoDialog('Open File', question,
                    transient_for=self.chat_control.parent_win.window,
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
    def __init__(self, file, progressbar, chat_control, event, base):
        self.file = file
        self.progressbar = progressbar
        self.chat_control = chat_control
        self.event = event
        self.base = base
        self.download()

    def download(self):
        gobject.idle_add(self.progressbar.set_text, 'Downloading...')
        data = self.load_url()
        if isinstance(data, str):
            gobject.idle_add(self.progressbar.close_dialog)
            gobject.idle_add(self.error, data)
            return

        gobject.idle_add(self.progressbar.set_text, 'Decrypting...')
        decrypted_data = self.aes_decrypt(data)

        gobject.idle_add(
            self.progressbar.set_text, 'Writing file to harddisk...')
        self.write_file(decrypted_data)

        gobject.idle_add(self.progressbar.close_dialog)

        gobject.idle_add(self.base.finished, self.file)

    def load_url(self):
        try:
            get_request = urllib2.urlopen(self.file.url, timeout=30)
            size = get_request.info().getheader('Content-Length').strip()
            if not size:
                errormsg = 'Content-Length not found in header'
                log.error(errormsg)
                return errormsg
            stream = BytesIO()
            while True:
                try:
                    if self.event.isSet():
                        raise DownloadAbortedException
                    temp = get_request.read(10000)
                    gobject.idle_add(
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
        except urllib2.URLError as error:
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
        ErrorDialog(
            _('Error'), error,
            transient_for=self.chat_control.parent_win.window)
        return False


class ProgressWindow:
    def __init__(self, plugin, chat_control, event):
        self.plugin = plugin
        self.event = event
        self.xml = gtkgui_helpers.get_gtk_builder(
            self.plugin.local_file_path('download_progress_dialog.ui'))
        self.dialog = self.xml.get_object('progress_dialog')
        self.dialog.set_transient_for(chat_control.parent_win.window)
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
