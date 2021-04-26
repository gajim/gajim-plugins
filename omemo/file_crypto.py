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

import hashlib
import logging
import binascii
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import unquote

from gi.repository import GLib
from gi.repository import Soup

from gajim.common import configpaths
from gajim.common.helpers import write_file_async
from gajim.common.helpers import open_file
from gajim.common.const import URIType
from gajim.common.const import FTState
from gajim.common.filetransfer import FileTransfer
from gajim.plugins.plugins_i18n import _
from gajim.gui.dialogs import DialogButton
from gajim.gui.dialogs import ConfirmationDialog
from gajim.gui.filetransfer_progress import FileTransferProgress

from omemo.backend.aes import aes_decrypt_file


log = logging.getLogger('gajim.p.omemo.filedecryption')

DIRECTORY = Path(configpaths.get('MY_DATA')) / 'downloads'


class FileDecryption:
    def __init__(self, plugin):
        self.plugin = plugin
        self.window = None
        self._session = Soup.Session()

    def hyperlink_handler(self, uri, instance, window):
        if uri.type != URIType.WEB:
            return
        self.window = window

        urlparts = urlparse(uri.data)
        if urlparts.scheme != 'aesgcm':
            log.info('URL not encrypted: %s', uri.data)
            return

        try:
            key, iv = self._parse_fragment(urlparts.fragment)
        except ValueError:
            log.info('URL not encrypted: %s', uri.data)
            return

        file_path = self._get_file_path(uri.data, urlparts)
        if file_path.exists():
            instance.plugin_modified = True
            self._show_file_open_dialog(file_path)
            return

        file_path.parent.mkdir(mode=0o700, exist_ok=True)

        transfer = OMEMODownload(instance.account,
                                 urlparts,
                                 file_path,
                                 key,
                                 iv)

        transfer.connect('cancel', self._cancel_download)
        FileTransferProgress(transfer)

        self._download_content(transfer)
        instance.plugin_modified = True

    def _download_content(self, transfer):
        log.info('Start downloading: %s', transfer.request_uri)
        transfer.set_started()
        message = transfer.get_soup_message()
        message.connect('got-headers', self._on_got_headers, transfer)
        message.connect('got-chunk', self._on_got_chunk, transfer)

        self._session.queue_message(message, self._on_finished, transfer)

    def _cancel_download(self, transfer, _signalname):
        message = transfer.get_soup_message()
        self._session.cancel_message(message, Soup.Status.CANCELLED)
        transfer.set_cancelled()

    @staticmethod
    def _on_got_headers(message, transfer):
        transfer.set_in_progress()
        size = message.props.response_headers.get_content_length()
        transfer.size = size

    def _on_got_chunk(self, message, chunk, transfer):
        transfer.set_chunk(chunk.get_data())
        if transfer.size:
            # This gets called even when the requested file is not found
            # So only update the progress if the file was actually found and
            # we know the size 
            transfer.update_progress()

        self._session.pause_message(message)
        GLib.idle_add(self._session.unpause_message, message)

    def _on_finished(self, _session, message, transfer):
        if message.props.status_code == Soup.Status.CANCELLED:
            log.info('Download cancelled')
            return

        if message.status_code != Soup.Status.OK:
            log.warning('Download failed: %s', transfer.request_uri)
            log.warning(Soup.Status.get_phrase(message.status_code))
            transfer.set_error('http-error', 'Download failed: %s', transfer.request_uri)
            return

        data = message.props.response_body_data.get_data()
        if data is None:
            return

        decrypted_data = aes_decrypt_file(transfer.key,
                                          transfer.iv,
                                          data)

        write_file_async(transfer.path,
                         decrypted_data,
                         self._on_decrypted,
                         transfer)

        transfer.set_decrypting()

    def _on_decrypted(self, _result, error, transfer):
        if error is not None:
            log.error('%s: %s', transfer.path, error)
            return
        transfer.set_finished()
        self._show_file_open_dialog(transfer.path)

    def _show_file_open_dialog(self, file_path):
        def _open_file():
            open_file(file_path)

        def _open_folder():
            open_file(file_path.parent)

        ConfirmationDialog(
            _('Open File'),
            _('Open File?'),
            _('Do you want to open %s?') % file_path.name,
            [DialogButton.make('Cancel',
                               text=_('_No')),
             DialogButton.make('OK',
                               text=_('Open _Folder'),
                               callback=_open_folder),
             DialogButton.make('Accept',
                               text=_('_Open'),
                               callback=_open_file)],
            transient_for=self.window).show()

    @staticmethod
    def _parse_fragment(fragment):
        if not fragment:
            raise ValueError('Invalid fragment')

        fragment = binascii.unhexlify(fragment)
        size = len(fragment)
        # Clients started out with using a 16 byte IV but long term
        # want to swtich to the more performant 12 byte IV
        # We have to support both
        if size == 48:
            key = fragment[16:]
            iv = fragment[:16]
        elif size == 44:
            key = fragment[12:]
            iv = fragment[:12]
        else:
            raise ValueError('Invalid fragment size: %s' % size)

        return key, iv

    @staticmethod
    def _get_file_path(uri, urlparts):
        path = Path(unquote(urlparts.path))
        stem = path.stem
        extension = path.suffix

        if len(stem) > 90:
            # Many Filesystems have a limit on filename length
            # Most have 255, some encrypted ones only 143
            # We add around 50 chars for the hash,
            # so the filename should not exceed 90
            stem = stem[:90]

        name_hash = hashlib.sha1(str(uri).encode()).hexdigest()

        hash_filename = '%s_%s%s' % (stem, name_hash, extension)

        file_path = DIRECTORY / hash_filename
        return file_path


class OMEMODownload(FileTransfer):

    _state_descriptions = {
        FTState.DECRYPTING: _('Decrypting file…'),
        FTState.STARTED: _('Downloading…'),
    }

    def __init__(self, account, urlparts, path, key, iv):
        FileTransfer.__init__(self, account)

        self._urlparts = urlparts
        self.path = path
        self.iv = iv
        self.key = key

        self._message = None

    @property
    def request_uri(self):
        urlparts = self._urlparts._replace(scheme='https', fragment='')
        return urlparts.geturl()

    @property
    def filename(self):
        return Path(self._urlparts.path).name

    def set_chunk(self, bytes_):
        self._seen += len(bytes_)

    def get_soup_message(self):
        if self._message is None:
            self._message = Soup.Message.new('GET', self.request_uri)
        return self._message
