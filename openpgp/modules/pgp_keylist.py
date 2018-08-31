# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

# XEP-0373: OpenPGP for XMPP

import logging
import time

import nbxmpp

from gajim.common import app
from gajim.common.exceptions import StanzaMalformed
from gajim.common.modules.pep import AbstractPEPModule, AbstractPEPData
from gajim.common.modules.date_and_time import parse_datetime

from openpgp.modules import util
from openpgp.modules.util import Key

log = logging.getLogger('gajim.plugin_system.openpgp.pep')

# Module name
name = 'PGPKeylist'
zeroconf = False


class PGPKeylistData(AbstractPEPData):

    type_ = 'openpgp-keylist'

    def __init__(self, keylist):
        self._pep_specific_data = keylist
        self.data = keylist


class PGPKeylist(AbstractPEPModule):
    '''
    <item>
        <public-keys-list xmlns='urn:xmpp:openpgp:0'>
          <pubkey-metadata
            v4-fingerprint='1357B01865B2503C18453D208CAC2A9678548E35'
            date='2018-03-01T15:26:12Z'
            />
          <pubkey-metadata
            v4-fingerprint='67819B343B2AB70DED9320872C6464AF2A8E4C02'
            date='1953-05-16T12:00:00Z'
            />
        </public-keys-list>
      </item>
    '''

    name = 'openpgp-keylist'
    namespace = util.NS_OPENPGP_PUBLIC_KEYS
    pep_class = PGPKeylistData
    store_publish = True
    _log = log

    def __init__(self, con):
        AbstractPEPModule.__init__(self, con, con.name)

        self.handlers = []

    def _extract_info(self, item):
        keylist_tag = item.getTag('public-keys-list',
                                  namespace=util.NS_OPENPGP)
        if keylist_tag is None:
            raise StanzaMalformed('No public-keys-list node')

        metadata = keylist_tag.getTags('pubkey-metadata')
        if not metadata:
            raise StanzaMalformed('No metadata found')

        keylist = []
        for data in metadata:
            attrs = data.getAttrs()

            if not attrs or 'v4-fingerprint' not in attrs:
                raise StanzaMalformed('No fingerprint in metadata')

            date = attrs.get('date', None)
            if date is None:
                raise StanzaMalformed('No date in metadata')
            else:
                timestamp = parse_datetime(date, epoch=True)
                if timestamp is None:
                    raise StanzaMalformed('Invalid date timestamp: %s', date)

            keylist.append(Key(attrs['v4-fingerprint'], int(timestamp)))
        return keylist

    def _notification_received(self, jid, keylist):
        con = app.connections[self._account]
        con.get_module('OpenPGP').key_list_received(keylist.data,
                                                    jid.getStripped())

    def _build_node(self, keylist):
        keylist_node = nbxmpp.Node('public-keys-list',
                                   {'xmlns': util.NS_OPENPGP})
        if keylist is None:
            return keylist_node
        for key in keylist:
            attrs = {'v4-fingerprint': key.fingerprint}
            if key.date is not None:
                date = time.strftime(
                    '%Y-%m-%dT%H:%M:%SZ', time.gmtime(key.date))
                attrs['date'] = date
            keylist_node.addChild('pubkey-metadata', attrs=attrs)
        return keylist_node


def get_instance(*args, **kwargs):
    return PGPKeylist(*args, **kwargs), 'PGPKeylist'
