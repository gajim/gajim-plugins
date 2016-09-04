# -*- coding: utf-8 -*-

import gtk
import gobject
import re
import os
import urllib2
import hashlib
from urlparse import urlparse

import logging
import nbxmpp
from common import gajim
from common import ged
from common import helpers
from common import configpaths
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from plugins.gui import GajimPluginConfigDialog
from conversation_textview import TextViewImage
from .aes_gcm import aes_decrypt

from common import demandimport
demandimport.enable()
demandimport.ignore += ['_imp']

log = logging.getLogger('gajim.plugin_system.url_image_preview')


try:
    if os.name == 'nt':
        from cryptography.hazmat.backends.openssl import backend
    else:
        from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms
    from cryptography.hazmat.primitives.ciphers.modes import GCM
    decryption_available = True
except Exception as e:
    log.debug('Cryptography Import Error: ' + str(e))
    log.debug('Decryption/Encryption disabled')
    decryption_available = False

ACCEPTED_MIME_TYPES = ('image/png', 'image/jpeg', 'image/gif', 'image/raw',
                       'image/svg+xml')


class UrlImagePreviewPlugin(GajimPlugin):
    @log_calls('UrlImagePreviewPlugin')
    def init(self):
        self.config_dialog = UrlImagePreviewPluginConfigDialog(self)
        self.events_handlers = {}
        self.events_handlers['message-received'] = (
            ged.PRECORE, self.handle_message_received)
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                  self.disconnect_from_chat_control),
            'print_special_text': (self.print_special_text, None), }
        self.config_default_values = {
            'PREVIEW_SIZE': (150, 'Preview size(10-512)'),
            'MAX_FILE_SIZE': (524288, 'Max file size for image preview')}
        self.controls = {}

    # remove oob tag if oob url == message text
    def handle_message_received(self, event):
        oob_node = event.stanza.getTag('x', namespace=nbxmpp.NS_X_OOB)
        oob_url = None
        oob_desc = None
        if oob_node:
            oob_url = oob_node.getTagData('url')
            oob_desc = oob_node.getTagData('desc')
            if oob_url and oob_url == event.msgtxt and \
                    (not oob_desc or oob_desc == ""):
                log.debug("Detected oob tag containing same"
                          "url as the message text, deleting oob tag...")
                event.stanza.delChild(oob_node)

    @log_calls('UrlImagePreviewPlugin')
    def connect_with_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid = chat_control.contact.jid
        if account not in self.controls:
            self.controls[account] = {}
        self.controls[account][jid] = Base(self, chat_control)

    @log_calls('UrlImagePreviewPlugin')
    def disconnect_from_chat_control(self, chat_control):
        account = chat_control.contact.account.name
        jid = chat_control.contact.jid
        del self.controls[account][jid]

    def print_special_text(self, tv, special_text, other_tags, graphics=True,
                           iter_=None):
        account = tv.account
        for jid in self.controls[account]:
            if self.controls[account][jid].chat_control.conv_textview != tv:
                continue
            self.controls[account][jid].print_special_text(
                special_text, other_tags, graphics=True, iter_=iter_)
            return


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview
        if os.name == 'nt':
            self.backend = backend
        else:
            self.backend = default_backend()

    def print_special_text(self, special_text, other_tags, graphics=True,
                           iter_=None):
        # remove qip bbcode
        special_text = special_text.rsplit('[/img]')[0]

        if special_text.startswith('www.'):
            special_text = 'http://' + special_text
        if special_text.startswith('ftp.'):
            special_text = 'ftp://' + special_text

        urlparts = urlparse(special_text)
        if urlparts.scheme not in ["https", "http", "ftp", "ftps"] or \
                not urlparts.netloc:
            log.info("Not accepting URL for image preview: %s" % special_text)
            return

        buffer_ = self.textview.tv.get_buffer()
        if not iter_:
            iter_ = buffer_.get_end_iter()

        # Detect XHTML-IM link
        ttt = buffer_.get_tag_table()
        tags_ = [(ttt.lookup(t) if isinstance(t, str) else t) for t in other_tags]
        for t in tags_:
            is_xhtml_link = getattr(t, 'href', None)
            if is_xhtml_link:
                break

        # Show URL, until image is loaded (if ever)
        repl_start = buffer_.create_mark(None, iter_, True)
        buffer_.insert_with_tags(iter_, special_text,
            *[(ttt.lookup(t) if isinstance(t, str) else t) for t in ["url"]])
        repl_end = buffer_.create_mark(None, iter_, True)

        directory = os.path.join(configpaths.gajimpaths['MY_CACHE'],
                                 'Downloads')

        filename = os.path.basename(urlparts.path)
        ext = os.path.splitext(filename)[1]
        name = os.path.splitext(filename)[0]
        namehash = hashlib.sha1(special_text).hexdigest()
        newfilename = name + '_' + namehash + ext

        fullpath = os.path.join(directory, newfilename)

        if os.path.exists(fullpath):
            def open_file():
                with open(fullpath, 'rb') as f:
                    mem = f.read()
                    f.closed
                log.debug('File from disk')
                return (mem, '')

            gajim.thread_interface(
                open_file, [],
                self._update_img, [special_text, repl_start,
                                   repl_end, fullpath])

        else:
            key = ''
            iv = ''
            encrypted = False
            if len(urlparts.fragment):
                fragment = []
                for i in range(0, len(urlparts.fragment), 2):
                    fragment.append(chr(int(urlparts.fragment[i:i + 2], 16)))
                fragment = ''.join(fragment)
                key = fragment[16:]
                iv = fragment[:16]
                if len(key) == 32 and len(iv) == 16:
                    encrypted = True

            if encrypted:
                if decryption_available:
                    # First get the http head request
                    # which does not fetch data, just headers
                    gajim.thread_interface(
                        self._get_http_head,
                        [self.textview.account, special_text],
                        self._check_mime_size,
                        [special_text, repl_start, repl_end,
                         fullpath, directory, key, iv, encrypted])
                else:
                    log.debug('Please install Crytography to decrypt pictures')
            else:
                # First get the http head request
                # which does not fetch data, just headers
                gajim.thread_interface(
                    self._get_http_head, [self.textview.account, special_text],
                    self._check_mime_size, [special_text, repl_start, repl_end,
                                            fullpath, directory, key, iv,
                                            encrypted])

        # Don't print the URL in the message window (in the calling function)
        self.textview.plugin_modified = True

    def _check_mime_size(self, (file_mime, file_size),
                         url, repl_start, repl_end, fullpath,
                         directory, key, iv, encrypted):
        # Check if mime type is acceptable
        if file_mime == '' and file_size == 0:
            log.info("Failed to load HEAD Request for URL: '%s'"
                     "(see debug log for more info)" % url)
            # URL is already displayed
            return
        if file_mime.lower() not in ACCEPTED_MIME_TYPES:
            log.info("Not accepted mime type '%s' for URL: '%s'"
                     % (file_mime.lower(), url))
            # URL is already displayed
            return
        # Check if file size is acceptable
        if file_size > self.plugin.config['MAX_FILE_SIZE'] or file_size == 0:
            log.info("File size (%s) too big or unknown (zero) for URL: '%s'"
                     % (str(file_size), url))
            # URL is already displayed
            return

        attributes = {'src': url,
                      'max_size': self.plugin.config['MAX_FILE_SIZE'],
                      'fullpath': fullpath,
                      'directory': directory,
                      'key': key,
                      'iv': iv}

        gajim.thread_interface(
            self._download_image, [self.textview.account,
                                   attributes, encrypted],
            self._update_img, [url, repl_start, repl_end, fullpath])

    def aes_decrypt_fast(self, key, iv, payload):
        # Use AES128 GCM with the given key and iv to decrypt the payload.
        data = payload[:-16]
        tag = payload[-16:]
        decryptor = Cipher(
            algorithms.AES(key),
            GCM(iv, tag=tag),
            backend=self.backend).decryptor()
        return decryptor.update(data) + decryptor.finalize()

    def _update_img(self, (mem, alt), url, repl_start, repl_end, fullpath):
        if mem:
            try:
                loader = gtk.gdk.PixbufLoader()
                loader.write(mem)
                loader.close()
                pixbuf = loader.get_pixbuf()
                pixbuf, w, h = self.get_pixbuf_of_size(
                    pixbuf, self.plugin.config['PREVIEW_SIZE'])
                eb = gtk.EventBox()
                eb.connect('button-press-event', self.on_button_press_event,
                           fullpath)
                eb.connect('enter-notify-event', self.on_enter_event)
                eb.connect('leave-notify-event', self.on_leave_event)

                # this is threadsafe
                # (gtk textview is NOT threadsafe by itself!!)

                def add_to_textview():
                    try:        # textview closed in the meantime etc.
                        buffer_ = repl_start.get_buffer()
                        iter_ = buffer_.get_iter_at_mark(repl_start)
                        buffer_.insert(iter_, "\n")
                        anchor = buffer_.create_child_anchor(iter_)
                        # Use url as tooltip for image
                        img = TextViewImage(anchor, fullpath)
                        img.set_from_pixbuf(pixbuf)
                        eb.add(img)
                        eb.show_all()
                        self.textview.tv.add_child_at_anchor(eb, anchor)
                        buffer_.delete(iter_,
                                       buffer_.get_iter_at_mark(repl_end))
                    except:
                        pass
                    return False
                gobject.idle_add(add_to_textview)
            except Exception:
                # URL is already displayed
                log.error('Could not display image for URL: %s'
                          % url)
                raise
        else:
            # If image could not be downloaded, URL is already displayed
            log.error('Could not download image for URL: %s -- %s'
                      % (url, alt))

    def _get_http_head(self, account, url):
        # Check if proxy is used
        proxy = helpers.get_proxy_info(account)
        if proxy and proxy['type'] in ('http', 'socks5'):
            return self._get_http_head_proxy(url, proxy)
        return self._get_http_head_direct(url)

    def _download_image(self, account, attrs, encrypted):
        proxy = helpers.get_proxy_info(account)
        fullpath = attrs['fullpath']
        directory = attrs['directory']
        key = attrs['key']
        iv = attrs['iv']

        if proxy and proxy['type'] in ('http', 'socks5'):
            mem, alt = self._get_img_proxy(attrs, proxy)
        else:
            mem, alt = self._get_img_direct(attrs)

        # Decrypt file if necessary
        if encrypted:
            mem = self.aes_decrypt_fast(key, iv, mem)

        # Write file to harddisk
        self.write_file(fullpath, directory, mem)
        log.error('downloading file')
        return (mem, alt)

    def write_file(self, fullpath, directory, data):

        def create_path(directory):
            head, tail = os.path.split(directory)
            if not os.path.exists(head):
                create_path(head)
            if os.path.exists(directory):
                return
            log.debug('creating directory')
            os.mkdir(directory, 0700)

        create_path(directory)

        try:
            with open(fullpath, "wb") as output_file:
                output_file.write(data)
                output_file.closed
        except Exception as e:
            log.debug(e)

    def _get_http_head_direct(self, url):
        log.debug('Get head request direct for URL: %s' % url)
        try:
            req = urllib2.Request(url)
            req.get_method = lambda: 'HEAD'
            req.add_header('User-Agent', 'Gajim %s' % gajim.version)
            f = urllib2.urlopen(req)
        except Exception, ex:
            log.debug('Could not get head response for URL: %s' % url)
            log.debug("%s" % str(ex))
            return ('', 0)
        url_headers = f.info()
        ctype = ''
        ctype_list = url_headers.getheaders('Content-Type')
        if ctype_list:
            ctype = ctype_list[0]
        clen = 0
        clen_list = url_headers.getheaders('Content-Length')
        if clen_list:
            try:
                clen = int(clen_list[0])
            except ValueError:
                pass
        return (ctype, clen)

    def _get_http_head_proxy(self, url, proxy):
        log.debug('Get head request with proxy for URL: %s' % url)
        if not gajim.HAVE_PYCURL:
            log.error('PYCURL not installed')
            return ('', 0)
        import pycurl
        from cStringIO import StringIO

        headers = ''
        try:
            b = StringIO()
            c = pycurl.Curl()
            c.setopt(pycurl.URL, url.encode('utf-8'))
            c.setopt(pycurl.FOLLOWLOCATION, 1)
            # Make a HEAD request:
            c.setopt(pycurl.CUSTOMREQUEST, 'HEAD')
            c.setopt(pycurl.NOBODY, 1)
            c.setopt(pycurl.HEADER, 1)

            c.setopt(pycurl.MAXFILESIZE, 2000000)
            c.setopt(pycurl.WRITEFUNCTION, b.write)
            c.setopt(pycurl.USERAGENT, 'Gajim ' + gajim.version)

            # set proxy
            c.setopt(pycurl.PROXY, proxy['host'].encode('utf-8'))
            c.setopt(pycurl.PROXYPORT, proxy['port'])
            if proxy['useauth']:
                c.setopt(pycurl.PROXYUSERPWD, proxy['user'].encode('utf-8') +
                         ':' + proxy['pass'].encode('utf-8'))
                c.setopt(pycurl.PROXYAUTH, pycurl.HTTPAUTH_ANY)
            if proxy['type'] == 'http':
                c.setopt(pycurl.PROXYTYPE, pycurl.PROXYTYPE_HTTP)
            elif proxy['type'] == 'socks5':
                c.setopt(pycurl.PROXYTYPE, pycurl.PROXYTYPE_SOCKS5)
            x = c.perform()
            c.close()
            headers = b.getvalue()
        except pycurl.error, ex:
            log.debug('Could not get head response for URL: %s' % url)
            log.debug("%s" % str(ex))
            return ('', 0)

        ctype = ''
        searchObj = re.search(r'^Content-Type: (.*)$', headers, re.M | re.I)
        if searchObj:
            ctype = searchObj.group(1).strip()
        clen = 0
        searchObj = re.search(r'^Content-Length: (.*)$', headers, re.M | re.I)
        if searchObj:
            try:
                clen = int(searchObj.group(1).strip())
            except ValueError:
                pass
        return (ctype, clen)

    def _get_img_direct(self, attrs):
        """
        Download an image. This function should
        be launched in a separated thread.
        """
        mem, alt, max_size = '', '', 2 * 1024 * 1024
        if 'max_size' in attrs:
            max_size = attrs['max_size']
        try:
            req = urllib2.Request(attrs['src'])
            req.add_header('User-Agent', 'Gajim ' + gajim.version)
            f = urllib2.urlopen(req)
        except Exception, ex:
            log.debug('Error loading image %s '
                      % attrs['src'] + str(ex))
            pixbuf = None
            alt = attrs.get('alt', 'Broken image')
        else:
            while True:
                try:
                    temp = f.read(100)
                except socket.timeout, ex:
                    log.debug('Timeout loading image %s '
                              % attrs['src'] + str(ex))
                    alt = attrs.get('alt', '')
                    if alt:
                        alt += '\n'
                    alt += _('Timeout loading image')
                    break
                if temp:
                    mem += temp
                else:
                    break
                if len(mem) > max_size:
                    alt = attrs.get('alt', '')
                    if alt:
                        alt += '\n'
                    alt += _('Image is too big')
                    break
        return (mem, alt)

    def _get_img_proxy(self, attrs, proxy):
        """
        Download an image through a proxy.
        This function should be launched in a
        separated thread.
        """
        if not gajim.HAVE_PYCURL:
            return '', _('PyCURL is not installed')
        mem, alt, max_size = '', '', 2 * 1024 * 1024
        if 'max_size' in attrs:
            max_size = attrs['max_size']
        try:
            b = StringIO()
            c = pycurl.Curl()
            c.setopt(pycurl.URL, attrs['src'].encode('utf-8'))
            c.setopt(pycurl.FOLLOWLOCATION, 1)
            c.setopt(pycurl.MAXFILESIZE, max_size)
            c.setopt(pycurl.WRITEFUNCTION, b.write)
            c.setopt(pycurl.USERAGENT, 'Gajim ' + gajim.version)
            # set proxy
            c.setopt(pycurl.PROXY, proxy['host'].encode('utf-8'))
            c.setopt(pycurl.PROXYPORT, proxy['port'])
            if proxy['useauth']:
                c.setopt(pycurl.PROXYUSERPWD, proxy['user'].encode('utf-8') +
                         ':' + proxy['pass'].encode('utf-8'))
                c.setopt(pycurl.PROXYAUTH, pycurl.HTTPAUTH_ANY)
            if proxy['type'] == 'http':
                c.setopt(pycurl.PROXYTYPE, pycurl.PROXYTYPE_HTTP)
            elif proxy['type'] == 'socks5':
                c.setopt(pycurl.PROXYTYPE, pycurl.PROXYTYPE_SOCKS5)
            x = c.perform()
            c.close()
            t = b.getvalue()
            return (t, attrs.get('alt', ''))
        except pycurl.error, ex:
            alt = attrs.get('alt', '')
            if alt:
                alt += '\n'
            if ex[0] == pycurl.E_FILESIZE_EXCEEDED:
                alt += _('Image is too big')
            elif ex[0] == pycurl.E_OPERATION_TIMEOUTED:
                alt += _('Timeout loading image')
            else:
                alt += _('Error loading image')
        except Exception, ex:
            log.debug('Error loading image %s ' % attrs['src'] + str(ex))
            pixbuf = None
            alt = attrs.get('alt', 'Broken image')
        return ('', alt)

    # Change mouse pointer to HAND2 when
    # mouse enter the eventbox with the image
    def on_enter_event(self, eb, event):
        self.textview.tv.get_window(
            gtk.TEXT_WINDOW_TEXT).set_cursor(gtk.gdk.Cursor(gtk.gdk.HAND2))

    # Change mouse pointer to default when mouse leaves the eventbox
    def on_leave_event(self, eb, event):
        self.textview.tv.get_window(
            gtk.TEXT_WINDOW_TEXT).set_cursor(gtk.gdk.Cursor(gtk.gdk.XTERM))

    def on_button_press_event(self, eb, event, fullpath):
        if event.button == 1:  # left click
            helpers.launch_file_manager(fullpath)

    def get_pixbuf_of_size(self, pixbuf, size):
        # Creates a pixbuf that fits in the specified square of sizexsize
        # while preserving the aspect ratio
        # Returns tuple: (scaled_pixbuf, actual_width, actual_height)
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
        return (crop_pixbuf, image_width, image_height)

    def disconnect_from_chat_control(self):
        pass


class UrlImagePreviewPluginConfigDialog(GajimPluginConfigDialog):
    max_file_size = [262144, 524288, 1048576, 5242880, 10485760]

    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, [
            'vbox1', 'liststore1'])
        self.preview_size_spinbutton = self.xml.get_object('preview_size')
        self.preview_size_spinbutton.get_adjustment().set_all(20, 10, 512, 1,
                                                              10, 0)
        self.max_size_combobox = self.xml.get_object('max_size_combobox')
        vbox = self.xml.get_object('vbox1')
        self.child.pack_start(vbox)

        self.xml.connect_signals(self)

    def on_run(self):
        self.preview_size_spinbutton.set_value(self.plugin.config[
            'PREVIEW_SIZE'])
        value = self.plugin.config['MAX_FILE_SIZE']
        if value:
            # this fails if we upgrade from an old version
            # which has other file size values than we have now
            try:
                self.max_size_combobox.set_active(
                    self.max_file_size.index(value))
            except:
                pass
        else:
            self.max_size_combobox.set_active(-1)

    def preview_size_value_changed(self, spinbutton):
        self.plugin.config['PREVIEW_SIZE'] = spinbutton.get_value()

    def max_size_value_changed(self, widget):
        self.plugin.config['MAX_FILE_SIZE'] = self.max_file_size[
            self.max_size_combobox.get_active()]
