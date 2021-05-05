# This file is part of Image Preview Gajim Plugin.
#
# Image Preview Gajim Plugin is free software;
# you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Image Preview Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Image Preview Gajim Plugin.
# If not, see <http://www.gnu.org/licenses/>.

import os
import logging
import shutil
import mimetypes
from pathlib import Path
from functools import partial
from urllib.parse import urlparse

import gi
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import Soup
try:
    gi.require_version('Gst', '1.0')
    gi.require_version('GstPbutils', '1.0')
    from gi.repository import Gst
    from gi.repository import GstPbutils
except Exception:
    pass


from gajim.common import app
from gajim.common import configpaths
from gajim.common.helpers import open_file
from gajim.common.helpers import open_uri
from gajim.common.helpers import write_file_async
from gajim.common.helpers import load_file_async
from gajim.common.helpers import get_tls_error_phrase
from gajim.common.helpers import get_user_proxy
from gajim.gui.dialogs import ErrorDialog
from gajim.gui.filechoosers import FileSaveDialog
from gajim.gui.util import get_cursor
from gajim.gui.util import get_monitor_scale_factor
from gajim.gui.util import load_icon

from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _

from url_image_preview.config_dialog import UrlImagePreviewConfigDialog
from url_image_preview.mime_types import MIME_TYPES

log = logging.getLogger('gajim.p.preview')

ERROR_MSG = None
try:
    from PIL import Image  # pylint: disable=unused-import
except ImportError:
    Image = None
    log.error('Pillow not available')
    ERROR_MSG = _('Please install python-pillow')

try:
    import cryptography  # pylint: disable=unused-import
except Exception:
    ERROR_MSG = _('Please install python-cryptography')
    log.error('python-cryptography not available')

# pylint: disable=ungrouped-imports
if ERROR_MSG is None:
    from url_image_preview.utils import aes_decrypt
    from url_image_preview.utils import get_image_paths
    from url_image_preview.utils import split_geo_uri
    from url_image_preview.utils import parse_fragment
    from url_image_preview.utils import create_thumbnail
    from url_image_preview.utils import pixbuf_from_data
    from url_image_preview.utils import filename_from_uri
# pylint: enable=ungrouped-imports


def get_previewable_mime_types():
    previewable_mime_types = set()
    for fmt in GdkPixbuf.Pixbuf.get_formats():
        for mime_type in fmt.get_mime_types():
            previewable_mime_types.add(mime_type.lower())
    if Image is not None:
        Image.init()
        for mime_type in Image.MIME.values():
            previewable_mime_types.add(mime_type.lower())
    return tuple(filter(
        lambda mime_type: mime_type.startswith('image'),
        previewable_mime_types
    ))


PREVIEWABLE_MIME_TYPES = get_previewable_mime_types()
mime_types = set(MIME_TYPES)
# Merge both: if it’s a previewable image, it should be allowed
ALLOWED_MIME_TYPES = mime_types.union(PREVIEWABLE_MIME_TYPES)


class UrlImagePreviewPlugin(GajimPlugin):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        if ERROR_MSG:
            self.activatable = False
            self.available_text = ERROR_MSG
            self.config_dialog = None
            return

        self.description = _('Displays a preview of image links.')
        self.config_dialog = partial(UrlImagePreviewConfigDialog, self)

        self.gui_extension_points = {
            'chat_control_base': (self._on_connect_chat_control_base,
                                  self._on_disconnect_chat_control_base),
            'history_window': (self._on_connect_history_window,
                               self._on_disconnect_history_window),
            'print_real_text': (self._print_real_text, None),
        }

        self.config_default_values = {
            'PREVIEW_SIZE': (150, 'Preview size (100-1000)'),
            'MAX_FILE_SIZE': ('10485760', 'Max file size for image preview'),
            'ALLOW_ALL_IMAGES': (False, ''),
            'LEFTCLICK_ACTION': ('open_menuitem', 'Open'),
            'ANONYMOUS_MUC': (False, ''),
            'VERIFY': (True, ''),
        }

        self._textviews = {}
        self._sessions = {}

        self._orig_dir = Path(configpaths.get('MY_DATA')) / 'downloads'
        self._thumb_dir = Path(configpaths.get('MY_CACHE')) / 'downloads.thumb'

        if GLib.mkdir_with_parents(str(self._orig_dir), 0o700) != 0:
            log.error('Failed to create: %s', self._orig_dir)

        if GLib.mkdir_with_parents(str(self._thumb_dir), 0o700) != 0:
            log.error('Failed to create: %s', self._thumb_dir)

        if app.settings.get('use_kib_mib'):
            self._units = GLib.FormatSizeFlags.IEC_UNITS
        else:
            self._units = GLib.FormatSizeFlags.DEFAULT

        self._migrate_config()
        self._load_css()

    def _migrate_config(self):
        action = self.config['LEFTCLICK_ACTION']
        if action.endswith('_menuitem'):
            self.config['LEFTCLICK_ACTION'] = action[:-9]

    @staticmethod
    def _load_css():
        path = Path(__file__).parent / 'preview.css'
        try:
            with path.open('r') as file:
                css = file.read()
        except Exception as exc:
            log.error('Error loading css: %s', exc)
            return

        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(bytes(css.encode('utf-8')))
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),
                                                     provider, 610)
        except Exception:
            log.exception('Error loading application css')

    def _on_connect_chat_control_base(self, chat_control):
        account = chat_control.account
        if account not in self._sessions:
            self._sessions[account] = self._create_session(account)
        self._textviews[chat_control.control_id] = chat_control.conv_textview

    def _on_disconnect_chat_control_base(self, chat_control):
        self._textviews.pop(chat_control.control_id, None)

    def _on_connect_history_window(self, history_window):
        account = history_window.account
        if (account is not None and account not in self._sessions):
            self._sessions[account] = self._create_session(account)
        self._textviews[id(history_window)] = history_window.history_textview

    def _on_disconnect_history_window(self, history_window):
        self._textviews.pop(id(history_window), None)

    def _get_control_id(self, textview):
        for control_id, textview_ in self._textviews.items():
            if textview == textview_:
                return control_id

    @staticmethod
    def _create_session(account):
        session = Soup.Session()
        session.add_feature_by_type(Soup.ContentSniffer)
        session.props.https_aliases = ['aesgcm']
        session.props.ssl_strict = False

        proxy = get_user_proxy(account)
        if proxy is None:
            resolver = None
        else:
            resolver = proxy.get_resolver()

        session.props.proxy_resolver = resolver
        return session, resolver

    def _get_session(self, account):
        return self._sessions[account][0]

    def _print_real_text(self, textview, text, _text_tags, _graphics,
                         iter_, additional_data):

        if len(text.split(' ')) > 1:
            # urlparse doesn't recognise spaces as URL delimiter
            log.debug('Text is not an uri: %s...', text[:15])
            return

        uri = text
        urlparts = urlparse(uri)
        if not self._accept_uri(urlparts, uri, additional_data):
            return

        textview.plugin_modified = True
        control_id = self._get_control_id(textview)

        start_mark, end_mark = self._print_text(textview.tv.get_buffer(),
                                                iter_,
                                                uri)

        if uri.startswith('geo:'):
            preview = self._process_geo_uri(uri,
                                            start_mark,
                                            end_mark,
                                            control_id,
                                            textview.account)
            if preview is None:
                return
            pixbuf = load_icon('map',
                               size=preview.size,
                               scale=get_monitor_scale_factor(),
                               pixbuf=True)
            self._update_textview(preview, pixbuf)
            return

        preview = self._process_web_uri(uri,
                                        urlparts,
                                        start_mark,
                                        end_mark,
                                        control_id,
                                        textview.account)

        if not preview.orig_exists():
            self._download_content(preview)

        elif not preview.thumb_exists():
            load_file_async(preview.orig_path,
                            self._on_orig_load_finished,
                            preview)

        else:
            load_file_async(preview.thumb_path,
                            self._on_thumb_load_finished,
                            preview)

    @staticmethod
    def _print_text(buffer_, iter_, text):
        if not iter_:
            iter_ = buffer_.get_end_iter()

        start_mark = buffer_.create_mark(None, iter_, True)
        buffer_.insert_with_tags_by_name(iter_, text, 'url')
        end_mark = buffer_.create_mark(None, iter_, True)
        return start_mark, end_mark

    def _accept_uri(self, urlparts, uri, additional_data):
        try:
            oob_url = additional_data['gajim']['oob_url']
        except (KeyError, AttributeError):
            oob_url = None

        # geo
        if urlparts.scheme == 'geo':
            return True

        if not urlparts.netloc:
            log.info('No netloc found in URL: %s', uri)
            return False

        # aesgcm
        if urlparts.scheme == 'aesgcm':
            return True

        # http/https
        if urlparts.scheme in ('https', 'http'):
            if self.config['ALLOW_ALL_IMAGES']:
                return True

            if oob_url is None:
                log.info('No oob url for: %s', uri)
                return False

            if uri != oob_url:
                log.info('uri != oob url: %s != %s', uri, oob_url)
                return False
            return True

        log.info('Unsupported URI scheme: %s', uri)
        return False

    @staticmethod
    def _process_geo_uri(uri,
                         start_mark,
                         end_mark,
                         control_id,
                         account):
        try:
            split_geo_uri(uri)
        except Exception as err:
            log.error(uri)
            log.error(err)
            return

        return Preview(uri,
                       None,
                       None,
                       None,
                       start_mark,
                       end_mark,
                       96,
                       control_id,
                       account)

    def _process_web_uri(self,
                         uri,
                         urlparts,
                         start_mark,
                         end_mark,
                         control_id,
                         account):

        size = self.config['PREVIEW_SIZE']
        orig_path, thumb_path = get_image_paths(uri,
                                                urlparts,
                                                size,
                                                self._orig_dir,
                                                self._thumb_dir)
        return Preview(uri,
                       urlparts,
                       orig_path,
                       thumb_path,
                       start_mark,
                       end_mark,
                       size,
                       control_id,
                       account)

    def _on_orig_load_finished(self, data, error, preview):
        if data is None:
            log.error('%s: %s', preview.orig_path.name, error)
            return

        preview.mime_type = self._guess_mime_type(preview.orig_path)
        preview.file_size = os.path.getsize(preview.orig_path)
        if preview.is_previewable:
            if preview.create_thumbnail(data):
                write_file_async(preview.thumb_path,
                                 preview.thumbnail,
                                 self._on_thumb_write_finished,
                                 preview)
        else:
            self._update_textview(preview, None)

    def _on_thumb_load_finished(self, data, error, preview):
        if data is None:
            log.error('%s: %s', preview.thumb_path.name, error)
            return

        preview.thumbnail = data
        preview.mime_type = self._guess_mime_type(preview.orig_path)
        preview.file_size = os.path.getsize(preview.orig_path)

        try:
            pixbuf = pixbuf_from_data(preview.thumbnail)
        except Exception as err:
            log.error('Unable to load: %s, %s',
                      preview.thumb_path.name,
                      err)
            return
        self._update_textview(preview, pixbuf)

    def _download_content(self, preview, force=False):
        if preview.account is None:
            # History Window can be opened without account context
            # This means we can not apply proxy settings
            return
        log.info('Start downloading: %s', preview.request_uri)
        message = Soup.Message.new('GET', preview.request_uri)
        message.connect('starting', self._check_certificate, preview)
        message.connect(
            'content-sniffed', self._on_content_sniffed, preview, force)

        session = self._get_session(preview.account)
        session.queue_message(message, self._on_finished, preview)

    def _check_certificate(self, message, preview):
        _https_used, _tls_certificate, tls_errors = message.get_https_status()

        if not self.config['VERIFY']:
            return

        if tls_errors:
            phrase = get_tls_error_phrase(tls_errors)
            log.warning('TLS verification failed: %s', phrase)
            session = self._get_session(preview.account)
            session.cancel_message(message, Soup.Status.CANCELLED)
            return

    def _on_content_sniffed(self, message, type_, _params, preview, force):
        file_size = message.props.response_headers.get_content_length()
        uri = message.props.uri.to_string(False)
        session = self._get_session(preview.account)
        preview.mime_type = type_
        preview.file_size = file_size

        if type_ not in ALLOWED_MIME_TYPES:
            log.info('Not an allowed content type: %s, %s', type_, uri)
            session.cancel_message(message, Soup.Status.CANCELLED)
            return

        if file_size == 0 or file_size > int(self.config['MAX_FILE_SIZE']):
            log.info(
                'File size (%s) too big or unknown (zero) for URL: \'%s\'',
                file_size, uri)
            if not force:
                session.cancel_message(message, Soup.Status.CANCELLED)

        self._update_textview(preview, None)

    def _on_finished(self, _session, message, preview):
        if message.status_code != Soup.Status.OK:
            log.warning('Download failed: %s', preview.request_uri)
            log.warning(Soup.Status.get_phrase(message.status_code))
            return

        data = message.props.response_body_data.get_data()
        if data is None:
            return

        if preview.is_aes_encrypted:
            data = aes_decrypt(preview, data)

        if preview.mime_type == 'application/octet-stream':
            preview.mime_type = self._guess_mime_type(preview.orig_path, data)

        write_file_async(preview.orig_path,
                         data,
                         self._on_orig_write_finished,
                         preview)

        if preview.is_previewable:
            if preview.create_thumbnail(data):
                write_file_async(preview.thumb_path,
                                 preview.thumbnail,
                                 self._on_thumb_write_finished,
                                 preview)

    def _on_orig_write_finished(self, _result, error, preview):
        if error is not None:
            log.error('%s: %s', preview.orig_path.name, error)
            return

        log.info('File stored: %s', preview.orig_path.name)
        preview.file_size = os.path.getsize(preview.orig_path)
        if not preview.is_previewable:
            # Don’t update preview if thumb is already displayed,
            # but update preview for audio files
            self._update_textview(preview, None)

    def _on_thumb_write_finished(self, _result, error, preview):
        if error is not None:
            log.error('%s: %s', preview.thumb_path.name, error)
            return

        log.info('Thumbnail stored: %s ', preview.thumb_path.name)

        try:
            pixbuf = pixbuf_from_data(preview.thumbnail)
        except Exception as err:
            log.error('Unable to load: %s, %s',
                      preview.thumb_path.name,
                      err)
            return
        self._update_textview(preview, pixbuf)

    @staticmethod
    def _guess_mime_type(file_path, data=None):
        mime_type, _ = mimetypes.MimeTypes().guess_type(str(file_path))
        if mime_type is None:
            # Try to guess MIME type by file name
            mime_type, _ = Gio.content_type_guess(str(file_path), data)
        log.debug('Guessed MIME type: %s', str(mime_type))
        return mime_type

    @staticmethod
    def _get_icon_for_mime_type(mime_type):
        if mime_type is None:
            return Gio.Icon.new_for_string('mail-attachment')
        return Gio.content_type_get_icon(mime_type)

    def _update_textview(self, preview, data):
        textview = self._textviews.get(preview.control_id)
        if textview is None:
            # Control closed
            return

        buffer_ = preview.start_mark.get_buffer()
        iter_ = buffer_.get_iter_at_mark(preview.start_mark)
        buffer_.insert(iter_, '\n')
        anchor = buffer_.create_child_anchor(iter_)
        anchor.plaintext = preview.uri

        preview_widget = self._create_preview_widget(preview, data)

        textview.tv.add_child_at_anchor(preview_widget, anchor)
        buffer_.delete(iter_,
                       buffer_.get_iter_at_mark(preview.end_mark))

        if textview.autoscroll:
            textview.scroll_to_end()

    def _create_preview_widget(self, preview, data):
        if isinstance(data, GdkPixbuf.PixbufAnimation):
            image = Gtk.Image.new_from_animation(data)
        elif isinstance(data, GdkPixbuf.Pixbuf):
            image = Gtk.Image.new_from_pixbuf(data)
        else:
            icon = self._get_icon_for_mime_type(preview.mime_type)
            image = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.DIALOG)

        path = self.local_file_path('preview.ui')
        ui = get_builder(path)
        ui.connect_signals(self)

        ui.download_button.set_no_show_all(True)
        ui.download_button.connect('clicked', self._on_download, preview)
        ui.save_as_button.set_no_show_all(True)
        ui.save_as_button.connect('clicked', self._on_save_as, preview)
        ui.open_folder_button.set_no_show_all(True)
        ui.open_folder_button.connect('clicked', self._on_open_folder, preview)

        ui.image_button.add(image)
        ui.image_button.set_tooltip_text(preview.filename)
        ui.image_button.connect('clicked',
                                self._on_image_button_clicked,
                                preview)
        ui.image_button.connect('button_press_event',
                                self._on_button_press_event,
                                preview)

        ui.preview_box.show_all()

        if preview.is_geo_uri:
            ui.file_name.set_text(_('Click to view location'))
            ui.save_as_button.hide()
            ui.open_folder_button.hide()
            ui.download_button.hide()
            location = split_geo_uri(preview.uri)
            ui.file_size.set_text(_('Lat: %s Lon: %s') % (
                location.lat, location.lon))
            ui.image_button.set_tooltip_text(
                _('Location at Lat: %s Lon: %s') % (
                    location.lat, location.lon))
            ui.image_event_box.set_halign(Gtk.Align.CENTER)
            ui.preview_box.set_size_request(160, -1)
            return ui.preview_box

        if preview.is_previewable and preview.orig_exists():
            ui.image_event_box.set_halign(Gtk.Align.CENTER)
        else:
            image.set_property('pixel-size', 64)

        if preview.orig_exists():
            ui.download_button.hide()
            if (preview.is_audio and app.is_installed('GST') and
                    self._contains_audio_streams(preview.orig_path)):
                audio_widget = AudioWidget(preview.orig_path)
                ui.preview_box.pack_start(audio_widget, True, True, 0)
        else:
            ui.save_as_button.hide()
            ui.open_folder_button.hide()

        file_size_string = _('File size unknown')
        if preview.file_size != 0:
            file_size_string = GLib.format_size_full(
                preview.file_size, self._units)
        ui.file_size.set_text(file_size_string)

        ui.preview_box.set_size_request(300, -1)
        ui.file_name.set_text(preview.filename)
        ui.file_name.set_tooltip_text(preview.filename)

        return ui.preview_box

    def _get_context_menu(self, preview):
        def destroy(menu, _pspec):
            visible = menu.get_property('visible')
            if not visible:
                GLib.idle_add(menu.destroy)

        path = self.local_file_path('context_menu.ui')
        ui = get_builder(path)

        ui.download.connect(
            'activate', self._on_download, preview)
        ui.open.connect(
            'activate', self._on_open, preview)
        ui.save_as.connect(
            'activate', self._on_save_as, preview)
        ui.open_folder.connect(
            'activate', self._on_open_folder, preview)
        ui.open_link_in_browser.connect(
            'activate', self._on_open_link_in_browser, preview)
        ui.copy_link_location.connect(
            'activate', self._on_copy_link_location, preview)
        ui.context_menu.connect('notify::visible', destroy)

        if preview.is_aes_encrypted:
            ui.open_link_in_browser.hide()

        if preview.is_geo_uri:
            ui.download.hide()
            ui.open_link_in_browser.hide()
            ui.save_as.hide()
            ui.open_folder.hide()
            return ui.context_menu

        if preview.orig_exists():
            ui.download.hide()
        else:
            ui.open.hide()
            ui.save_as.hide()
            ui.open_folder.hide()

        return ui.context_menu

    def _on_download(self, _menu, preview):
        if not preview.orig_exists():
            self._download_content(preview, force=True)

    def _on_open(self, _menu, preview):
        if preview.is_geo_uri:
            open_uri(preview.uri)
            return

        if not preview.orig_exists():
            self._download_content(preview, force=True)
            return

        open_file(preview.orig_path)

    def _on_save_as(self, _menu, preview):
        def on_ok(target_path):
            dirname = Path(target_path).parent
            if not os.access(dirname, os.W_OK):
                ErrorDialog(
                    _('Directory \'%s\' is not writable') % dirname,
                    _('You do not have the proper permissions to '
                      'create files in this directory.'),
                    transient_for=app.app.get_active_window())
                return
            shutil.copyfile(str(preview.orig_path), target_path)

        if not preview.orig_exists():
            self._download_content(preview, force=True)
            return

        FileSaveDialog(on_ok,
                       path=app.settings.get('last_save_dir'),
                       file_name=preview.filename,
                       transient_for=app.app.get_active_window())

    def _on_open_folder(self, _menu, preview):
        if not preview.orig_exists():
            self._download_content(preview, force=True)
            return
        open_file(preview.orig_path.parent)

    @staticmethod
    def _on_copy_link_location(_menu, preview):
        clipboard = Gtk.Clipboard.get_default(Gdk.Display.get_default())
        clipboard.set_text(preview.uri, -1)

    @staticmethod
    def _on_open_link_in_browser(_menu, preview):
        if preview.is_aes_encrypted:
            if preview.is_geo_uri:
                open_uri(preview.uri)
                return
            open_file(preview.orig_path)
        else:
            open_uri(preview.uri)

    def _on_image_button_clicked(self, _button, preview):
        action = self.config['LEFTCLICK_ACTION']
        method = getattr(self, '_on_%s' % action)
        method(None, preview)

    def _on_button_press_event(self, _button, event, preview):
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            # Right klick
            menu = self._get_context_menu(preview)
            menu.popup_at_pointer(event)

    @staticmethod
    def _contains_audio_streams(file_path):
        # Check if it is really an audio file
        has_audio = False
        discoverer = GstPbutils.Discoverer()
        try:
            info = discoverer.discover_uri(f'file://{file_path}')
            has_audio = bool(info.get_audio_streams())
        except GLib.Error as err:
            log.error('Error while reading %s: %s', str(file_path), err)
            return False
        if not has_audio:
            log.warning('File does not contain audio stream: %s',
                        str(file_path))
        return has_audio

    @staticmethod
    def _on_realize(event_box):
        event_box.get_window().set_cursor(get_cursor('pointer'))


class Preview:
    def __init__(self, uri, urlparts, orig_path, thumb_path,
                 start_mark, end_mark, size, control_id, account):
        self._uri = uri
        self._urlparts = urlparts
        self._filename = filename_from_uri(self._uri)

        self.size = size
        self.control_id = control_id
        self.orig_path = orig_path
        self.thumb_path = thumb_path
        self.start_mark = start_mark
        self.end_mark = end_mark
        self.account = account

        self.thumbnail = None
        self.mime_type = None
        self.file_size = 0

        self.key, self.iv = None, None
        if self.is_aes_encrypted:
            self.key, self.iv = parse_fragment(urlparts.fragment)

    @property
    def is_geo_uri(self):
        return self._uri.startswith('geo:')

    @property
    def is_web_uri(self):
        return not self.is_geo_uri

    @property
    def is_previewable(self):
        return self.mime_type in PREVIEWABLE_MIME_TYPES

    @property
    def is_audio(self):
        is_allowed = bool(self.mime_type in ALLOWED_MIME_TYPES)
        return is_allowed and self.mime_type.startswith('audio/')

    @property
    def uri(self):
        return self._uri

    @property
    def filename(self):
        return self._filename

    @property
    def request_uri(self):
        if self.is_aes_encrypted:
            # Remove fragments so we dont transmit it to the server
            urlparts = self._urlparts._replace(scheme='https', fragment='')
            return urlparts.geturl()
        return self._urlparts.geturl()

    @property
    def is_aes_encrypted(self):
        if self._urlparts is None:
            return False
        return self._urlparts.scheme == 'aesgcm'

    def thumb_exists(self):
        return self.thumb_path.exists()

    def orig_exists(self):
        return self.orig_path.exists()

    def create_thumbnail(self, data):
        self.thumbnail = create_thumbnail(data, self.size)
        if self.thumbnail is None:
            log.warning('Creating thumbnail failed for: %s', self.orig_path)
            return False
        return True


class AudioWidget(Gtk.Box):
    def __init__(self, file_path):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.HORIZONTAL,
                         spacing=6)
        self._playbin = None
        self._query = None
        self._has_timeout = False

        self._build_audio_widget()
        self._setup_audio_player(file_path)

    def _build_audio_widget(self):
        play_button = Gtk.Button()
        play_button.get_style_context().add_class('flat')
        play_button.get_style_context().add_class('preview-button')
        play_button.set_tooltip_text(_('Start/stop playback'))
        self._play_icon = Gtk.Image.new_from_icon_name(
            'media-playback-start-symbolic',
            Gtk.IconSize.BUTTON)
        play_button.add(self._play_icon)
        play_button.connect('clicked', self._on_play_clicked)
        event_box = Gtk.EventBox()
        event_box.connect('realize', self._on_realize)
        event_box.add(play_button)
        self.add(event_box)

        self._seek_bar = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL)
        self._seek_bar.set_range(0.0, 1.0)
        self._seek_bar.set_hexpand(True)
        self._seek_bar.set_value_pos(Gtk.PositionType.RIGHT)
        self._seek_bar.connect('change-value', self._on_seek)
        self._seek_bar.connect(
            'format-value', self._format_audio_timestamp)
        event_box = Gtk.EventBox()
        event_box.connect('realize', self._on_realize)
        event_box.add(self._seek_bar)
        self.add(event_box)

        self.connect('destroy', self._on_destroy)
        self.show_all()

    def _setup_audio_player(self, file_path):
        self._playbin = Gst.ElementFactory.make('playbin', 'bin')
        if self._playbin is None:
            return
        self._playbin.set_property(
            'uri', f'file://{file_path}')
        state_return = self._playbin.set_state(Gst.State.PAUSED)
        if state_return == Gst.StateChangeReturn.FAILURE:
            return

        self._query = Gst.Query.new_position(Gst.Format.TIME)
        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self._on_bus_message)

    def _on_bus_message(self, _bus, message):
        if message.type == Gst.MessageType.EOS:
            self._set_pause(True)
            self._playbin.seek_simple(
                Gst.Format.TIME, Gst.SeekFlags.FLUSH, 0)
        elif message.type == Gst.MessageType.STATE_CHANGED:
            _success, duration = self._playbin.query_duration(
                Gst.Format.TIME)
            if duration > 0:
                self._seek_bar.set_range(0.0, duration)

            is_paused = self._get_paused()
            if (duration > 0 and not is_paused and
                    not self._has_timeout):
                GLib.timeout_add(500, self._update_seek_bar)
                self._has_timeout = True

    def _on_seek(self, _range, _scroll, value):
        self._playbin.seek_simple(
            Gst.Format.TIME, Gst.SeekFlags.FLUSH, value)
        return False

    def _on_play_clicked(self, _button):
        self._set_pause(not self._get_paused())

    def _on_destroy(self, _widget):
        self._playbin.set_state(Gst.State.NULL)

    def _get_paused(self):
        _, state, _ = self._playbin.get_state(20)
        return state == Gst.State.PAUSED

    def _set_pause(self, paused):
        if paused:
            self._playbin.set_state(Gst.State.PAUSED)
            self._play_icon.set_from_icon_name(
                'media-playback-start-symbolic',
                Gtk.IconSize.BUTTON)
        else:
            self._playbin.set_state(Gst.State.PLAYING)
            self._play_icon.set_from_icon_name(
                'media-playback-pause-symbolic',
                Gtk.IconSize.BUTTON)

    def _update_seek_bar(self):
        if self._get_paused():
            self._has_timeout = False
            return False

        if self._playbin.query(self._query):
            _fmt, cur_pos = self._query.parse_position()
            self._seek_bar.set_value(cur_pos)
        return True

    @staticmethod
    def _format_audio_timestamp(_widget, ns):
        seconds = ns / 1000000000
        minutes = seconds / 60
        hours = minutes / 60

        i_seconds = int(seconds)
        i_minutes = int(minutes)
        i_hours = int(hours)

        if i_hours > 0:
            return f'{i_hours:d}:{i_minutes:02d}:{i_seconds:02d}'
        return f'{i_minutes:d}:{i_seconds:02d}'

    @staticmethod
    def _on_realize(event_box):
        event_box.get_window().set_cursor(get_cursor('pointer'))
