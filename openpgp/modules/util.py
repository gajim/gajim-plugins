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
import random
import time
import string
from enum import IntEnum
from collections import namedtuple
from base64 import b64decode, b64encode

import nbxmpp
from nbxmpp import Node

NS_OPENPGP = 'urn:xmpp:openpgp:0'
NS_OPENPGP_PUBLIC_KEYS = 'urn:xmpp:openpgp:0:public-keys'
NS_NOTIFY = NS_OPENPGP_PUBLIC_KEYS + '+notify'

NOT_ENCRYPTED_TAGS = [('no-store', nbxmpp.NS_MSG_HINTS),
                      ('store', nbxmpp.NS_MSG_HINTS),
                      ('no-copy', nbxmpp.NS_MSG_HINTS),
                      ('no-permanent-store', nbxmpp.NS_MSG_HINTS),
                      ('thread', None)]

Key = namedtuple('Key', 'fingerprint date')

log = logging.getLogger('gajim.plugin_system.openpgp.util')


class Trust(IntEnum):
    NOT_TRUSTED = 0
    UNKNOWN = 1
    BLIND = 2
    VERIFIED = 3


def unpack_public_key_list(stanza, from_jid):
    fingerprints = []

    parent = stanza.getTag('pubsub', namespace=nbxmpp.NS_PUBSUB)
    if parent is None:
        parent = stanza.getTag('event', namespace=nbxmpp.NS_PUBSUB_EVENT)
        if parent is None:
            log.warning('PGP keys list has no pubsub/event node')
            return

    items = parent.getTag('items', attrs={'node': NS_OPENPGP_PUBLIC_KEYS})
    if items is None:
        log.warning('PGP keys list has no items node')
        return

    item = items.getTags('item')
    if not item:
        log.warning('PGP keys list has no item node')
        return

    if len(item) > 1:
        log.warning('PGP keys list has more than one item')
        return

    key_list = item[0].getTag('public-keys-list', namespace=NS_OPENPGP)
    if key_list is None:
        log.warning('PGP keys list has no public-keys-list node')
        return

    metadata = key_list.getTags('pubkey-metadata')
    if not metadata:
        return []

    for node in metadata:
        attrs = node.getAttrs()
        if 'v4-fingerprint' not in attrs:
            log.warning('No fingerprint in metadata node')
            return

        date = attrs.get('date', None)

        fingerprints.append(
            Key(attrs['v4-fingerprint'], date))

    return fingerprints


def unpack_public_key(stanza, fingerprint):
    pubsub = stanza.getTag('pubsub', namespace=nbxmpp.NS_PUBSUB)
    if pubsub is None:
        log.warning('PGP public key has no pubsub node')
        return
    node = '%s:%s' % (NS_OPENPGP_PUBLIC_KEYS, fingerprint)
    items = pubsub.getTag('items', attrs={'node': node})
    if items is None:
        log.warning('PGP public key has no items node')
        return

    item = items.getTags('item')
    if not item:
        log.warning('PGP public key has no item node')
        return

    if len(item) > 1:
        log.warning('PGP public key has more than one item')
        return

    pub_key = item[0].getTag('pubkey', namespace=NS_OPENPGP)
    if pub_key is None:
        log.warning('PGP public key has no pubkey node')
        return

    data = pub_key.getTag('data')
    if data is None:
        log.warning('PGP public key has no data node')
        return

    return b64decode(data.getData().encode('utf8'))


def create_signcrypt_node(obj):
    '''
    <signcrypt xmlns='urn:xmpp:openpgp:0'>
      <to jid='juliet@example.org'/>
      <time stamp='2014-07-10T17:06:00+02:00'/>
      <rpad>
        f0rm1l4n4-mT8y33j!Y%fRSrcd^ZE4Q7VDt1L%WEgR!kv
      </rpad>
      <payload>
        <body xmlns='jabber:client'>
          This is a secret message.
        </body>
      </payload>
    </signcrypt>
    '''

    encrypted_nodes = []
    child_nodes = obj.msg_iq.getChildren()
    for node in child_nodes:
        if (node.name, node.namespace) not in NOT_ENCRYPTED_TAGS:
            if not node.namespace:
                node.setNamespace(nbxmpp.NS_CLIENT)
            encrypted_nodes.append(node)
            obj.msg_iq.delChild(node)

    signcrypt = Node('signcrypt', attrs={'xmlns': NS_OPENPGP})
    signcrypt.addChild('to', attrs={'jid': obj.jid})

    timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    signcrypt.addChild('time', attrs={'stamp': timestamp})

    signcrypt.addChild('rpad').addData(get_rpad())

    payload = signcrypt.addChild('payload')

    for node in encrypted_nodes:
        payload.addChild(node=node)

    return signcrypt


def get_rpad():
    rpad_range = random.randint(30, 50)
    return ''.join(
        random.choice(string.ascii_letters) for _ in range(rpad_range))


def create_openpgp_message(obj, encrypted_payload):
    b64encoded_payload = b64encode(
        encrypted_payload.encode('utf-8')).decode('utf8')

    openpgp_node = nbxmpp.Node('openpgp', attrs={'xmlns': NS_OPENPGP})
    openpgp_node.addData(b64encoded_payload)
    obj.msg_iq.addChild(node=openpgp_node)

    eme_node = nbxmpp.Node('encryption',
                           attrs={'xmlns': nbxmpp.NS_EME,
                                  'namespace': NS_OPENPGP})
    obj.msg_iq.addChild(node=eme_node)

    if obj.message:
        obj.msg_iq.setBody(get_info_message())


def get_info_message():
    return '[This message is *encrypted* with OpenPGP (See :XEP:`0373`]'


class VerifyFailed(Exception):
    pass


class DecryptionFailed(Exception):
    pass
