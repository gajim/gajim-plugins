# -*- coding: utf-8 -*-
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim.  If not, see <http://www.gnu.org/licenses/>.
##

import urllib.request as urllib2
import socket
import ssl
import logging
import os

from gajim.common import app
from gajim.plugins.plugins_i18n import _


if os.name == 'nt':
    import certifi

log = logging.getLogger('gajim.p.preview.http_functions')

def get_http_head(account, url, verify):
    return _get_http_head_direct(url, verify)

def get_http_file(account, attrs):
    return _get_http_direct(attrs)

def _get_http_head_direct(url, verify):
    log.info('Head request direct for URL: %s', url)
    try:
        req = urllib2.Request(url)
        req.get_method = lambda: 'HEAD'
        req.add_header('User-Agent', 'Gajim %s' % app.version)
        if not verify:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            log.warning('CERT Verification disabled')
            file_ = urllib2.urlopen(req, timeout=30, context=context)
        else:
            if os.name == 'nt':
                file_ = urllib2.urlopen(req, cafile=certifi.where())
            else:
                file_ = urllib2.urlopen(req)
    except Exception as ex:
        log.debug('Error', exc_info=True)
        return ('', 0)
    ctype = file_.headers['Content-Type']
    clen = file_.headers['Content-Length']
    try:
        clen = int(clen)
    except (TypeError, ValueError):
        pass
    return (ctype, clen)

def _get_http_direct(attrs):
    '''
    Download a file. This function should
    be launched in a separated thread.
    '''
    log.info('Get request direct for URL: %s', attrs['src'])
    mem, alt, max_size = b'', '', 2 * 1024 * 1024
    if 'max_size' in attrs:
        max_size = attrs['max_size']
    try:
        req = urllib2.Request(attrs['src'])
        req.add_header('User-Agent', 'Gajim ' + app.version)
        if not attrs['verify']:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            log.warning('CERT Verification disabled')
            file_ = urllib2.urlopen(req, timeout=30, context=context)
        else:
            if os.name == 'nt':
                file_ = urllib2.urlopen(req, cafile=certifi.where())
            else:
                file_ = urllib2.urlopen(req)
    except Exception as ex:
        log.debug('Error', exc_info=True)
        pixbuf = None
        alt = attrs.get('alt', 'Broken image')
    else:
        while True:
            try:
                temp = file_.read(100)
            except socket.timeout as ex:
                log.debug('Timeout loading image %s', attrs['src'] + str(ex))
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
