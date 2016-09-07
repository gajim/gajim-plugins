import urllib2

from common import helpers
from common import gajim
import logging

log = logging.getLogger('gajim.plugin_system.url_image_preview.http_functions')

def get_http_head(account, url):
    # Check if proxy is used
    proxy = helpers.get_proxy_info(account)
    if proxy and proxy['type'] in ('http', 'socks5'):
        return _get_http_head_proxy(url, proxy)
    return _get_http_head_direct(url)

def get_http_file(account, attrs):
    # Check if proxy is used
    proxy = helpers.get_proxy_info(account)
    if proxy and proxy['type'] in ('http', 'socks5'):
        return _get_http_proxy(attrs, proxy)
    else:
        return _get_http_direct(attrs)

def _get_http_head_direct(url):
    log.debug('Head request direct for URL: %s' % url)
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

def _get_http_head_proxy(url, proxy):
    log.debug('Head request with proxy for URL: %s' % url)
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

def _get_http_direct(attrs):
    """
    Download a file. This function should
    be launched in a separated thread.
    """
    log.debug('Get request direct for URL: %s' % url)
    mem, alt, max_size = '', '', 2 * 1024 * 1024
    if 'max_size' in attrs:
        max_size = attrs['max_size']
    try:
        req = urllib2.Request(attrs['src'])
        req.add_header('User-Agent', 'Gajim ' + gajim.version)
        f = urllib2.urlopen(req)
    except Exception, ex:
        log.debug('Error loading file %s '
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

def _get_http_proxy(attrs, proxy):
    """
    Download an image through a proxy.
    This function should be launched in a
    separated thread.
    """
    log.debug('Get request with proxy for URL: %s' % url)
    if not gajim.HAVE_PYCURL:
        log.error('PYCURL not installed')
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
        log.debug('Error loading file %s ' % attrs['src'] + str(ex))
        pixbuf = None
        alt = attrs.get('alt', 'Broken image')
    return ('', alt)
