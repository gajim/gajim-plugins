# -*- coding: utf-8 -*-

import gtk
import re
import os
import urllib2
import base64
from urlparse import urlparse

from common import gajim
from common import helpers
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from plugins.gui import GajimPluginConfigDialog
from conversation_textview import TextViewImage

ACCEPTED_MIME_TYPES = ('image/png','image/jpeg','image/gif','image/raw',
                        'image/svg+xml')

class UrlImagePreviewPlugin(GajimPlugin):
    @log_calls('UrlImagePreviewPlugin')
    def init(self):
        self.config_dialog = UrlImagePreviewPluginConfigDialog(self)
        self.gui_extension_points = {
                'chat_control_base': (self.connect_with_chat_control,
                                       self.disconnect_from_chat_control),
                'print_special_text': (self.print_special_text,
                                       self.print_special_text1),}
        self.config_default_values = {
                    'PREVIEW_SIZE': (150, 'Preview size(10-512)'),
                    'MAX_FILE_SIZE': (524288, 'Max file size for image preview')}
        self.chat_control = None
        self.controls = []

    @log_calls('UrlImagePreviewPlugin')
    def connect_with_chat_control(self, chat_control):

        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)

    @log_calls('UrlImagePreviewPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    def print_special_text(self, tv, special_text, other_tags, graphics=True,
    iter_=None):
        for control in self.controls:
            if control.chat_control.conv_textview != tv:
                continue
            control.print_special_text(special_text, other_tags, graphics=True,
                iter_=iter_)

    def print_special_text1(self, chat_control, special_text, other_tags=None,
        graphics=True, iter_=None):
        for control in self.controls:
            if control.chat_control == chat_control:
                control.disconnect_from_chat_control()
                self.controls.remove(control)

class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview

    def print_special_text(self, special_text, other_tags, graphics=True,
    iter_=None):
        # remove qip bbcode
        special_text = special_text.rsplit('[/img]')[0]

        if special_text.startswith('www.'):
            special_text = 'http://' + special_text
        if special_text.startswith('ftp.'):
            special_text = 'ftp://' + special_text
        
        parts = urlparse(special_text)
        if not parts.scheme in ["https", "http", "ftp", "ftps"] or \
            not parts.netloc:
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
        buffer_.insert_with_tags(iter_, special_text, \
            *[(ttt.lookup(t) if isinstance(t, str) else t) for t in ["url"]])
        repl_end = buffer_.create_mark(None, iter_, True)

        # First get the http head request with does not fetch data, just headers
        gajim.thread_interface(self._get_http_head, [self.textview.account, 
            special_text], self._check_mime_size, [special_text, repl_start, repl_end])

        # Don't print the URL in the message window (in the calling function)
        self.textview.plugin_modified = True

    def _check_mime_size(self, (file_mime, file_size), url, repl_start, repl_end):
        # Check if mime type is acceptable
        if file_mime.lower() not in ACCEPTED_MIME_TYPES:
            # URL is already displayed
            log.info('Not accepted mime type for URL: %s' % url)
            return
        # Check if file size is acceptable
        if file_size > self.plugin.config['MAX_FILE_SIZE'] or file_size == 0:
            log.info('File size to big or unknown for URL: %s' % url)
            # URL is already displayed
            return

        # Start downloading image
        gajim.thread_interface(helpers.download_image, [ self.textview.account, {
                'src': url, 'max_size':self.plugin.config['MAX_FILE_SIZE'] } ], 
                self._update_img, [url, file_mime, repl_start, repl_end])

    def _update_img(self, (mem, alt), url, file_mime, repl_start, repl_end):
        if mem:
            try:
                loader = gtk.gdk.PixbufLoader()
                loader.write(mem)
                loader.close()
                pixbuf = loader.get_pixbuf()
                w, h = self.get_thumb_size(pixbuf, self.plugin.config['PREVIEW_SIZE'])
                imgb64 = base64.b64encode(mem)
                xhtml = '<body xmlns=\'http://www.w3.org/1999/xhtml\'><br/>'
                xhtml += '<a href="%s">' % url
                xhtml += '<img src="data:%s;base64,%s" width="%s" height="%s"/> ' % \
                (file_mime, imgb64, w, h)
                xhtml += '</a></body>'
                buffer_ = repl_start.get_buffer()
                iter_ = buffer_.get_iter_at_mark(repl_start)
                buffer_.delete(iter_, buffer_.get_iter_at_mark(repl_end))
                self.textview.tv.display_html(xhtml.encode('utf-8'), self.textview.tv, 
                    self.textview, iter_=iter_)
            except Exception:
                # URL is already displayed
                log.error('Could not display image for URL: %s' % url)
        else:
            # If image could not be downloaded, URL is already displayed
            log.error('Could not download image for URL: %s' % url)

    def _get_http_head (self, account, url):
        # Check if proxy is used
        proxy = helpers.get_proxy_info(account)
        if proxy and proxy['type'] in ('http', 'socks5'):
            return self._get_http_head_proxy(url, proxy)
        return self._get_http_head_direct(url)

    def _get_http_head_direct (self, url):
        log.debug('Get head request direct for URL: %s' % url)
        try:
            req = urllib2.Request(url)
            req.get_method = lambda : 'HEAD'
            req.add_header('User-Agent', 'Gajim %s' % gajim.version)
            f = urllib2.urlopen(req)
        except Exception, ex:
            log.debug('Could not get head response for URL: %s' % url)
            return ('', 0)
        url_headers = f.info()
        ctype = ''
        ctype_list = url_headers.getheaders('Content-Type')
        if ctype_list:
            ctype = ctype_list[0]
        clen_list = url_headers.getheaders('Content-Length')
        clen = 0
        if  clen_list:
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
            c.setopt(pycurl.CONNECTTIMEOUT, 5)
            # Make a HEAD request:
            c.setopt(pycurl.CUSTOMREQUEST, 'HEAD')
            c.setopt(pycurl.NOBODY, 1)
            c.setopt(pycurl.HEADER, 1)

            c.setopt(pycurl.TIMEOUT, 10)
            c.setopt(pycurl.MAXFILESIZE, 2000000)
            c.setopt(pycurl.WRITEFUNCTION, b.write)
            c.setopt(pycurl.USERAGENT, 'Gajim ' + gajim.version)

            # set proxy
            c.setopt(pycurl.PROXY, proxy['host'].encode('utf-8'))
            c.setopt(pycurl.PROXYPORT, proxy['port'])
            if proxy['useauth']:
                c.setopt(pycurl.PROXYUSERPWD, proxy['user'].encode('utf-8')\
                    + ':' + proxy['pass'].encode('utf-8'))
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
            return ('', 0)

        ctype = ''
        searchObj = re.search( r'^Content-Type: (.*)$', headers, re.M|re.I)
        if searchObj:
            ctype = searchObj.group(1).strip()
        clen = 0
        searchObj = re.search( r'^Content-Length: (.*)$', headers, re.M|re.I)
        if searchObj:
            try:
                clen = int(searchObj.group(1).strip())
            except ValueError:
                pass    
        return (ctype, clen)

    def get_thumb_size(self, pixbuf, size):
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

        return (image_width, image_height)

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
            self.max_size_combobox.set_active(self.max_file_size.index(value))
        else:
            self.max_size_combobox.set_active(-1)

    def preview_size_value_changed(self, spinbutton):
        self.plugin.config['PREVIEW_SIZE'] = spinbutton.get_value()

    def max_size_value_changed(self, widget):
        self.plugin.config['MAX_FILE_SIZE'] =  self.max_file_size[
            self.max_size_combobox.get_active()]
        
