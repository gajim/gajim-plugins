# -*- coding: utf-8 -*-
#
# Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
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

""" This module handles all the XMPP logic like creating different kind of
stanza nodes and geting data from stanzas.
"""

import logging
import random
from base64 import b64decode, b64encode

from nbxmpp.protocol import NS_PUBSUB, Iq
from nbxmpp.simplexml import Node

from common import gajim  # pylint: disable=import-error
from common.pep import AbstractPEP  # pylint: disable=import-error
from plugins.helpers import log_calls  # pylint: disable=import-error

NS_PUBSUB_EVENT = NS_PUBSUB + '#event'

NS_EME = 'urn:xmpp:eme:0'
NS_OMEMO = 'eu.siacs.conversations.axolotl'
NS_DEVICE_LIST = NS_OMEMO + '.devicelist'
NS_NOTIFY = NS_DEVICE_LIST + '+notify'
NS_BUNDLES = NS_OMEMO + '.bundles:'
log = logging.getLogger('gajim.plugin_system.omemo')


class PublishNode(Node):
    def __init__(self, node_str, data):
        assert node_str is not None and isinstance(data, Node)
        Node.__init__(self, tag='publish', attrs={'node': node_str})
        self.addChild('item').addChild(node=data)


class PubsubNode(Node):
    def __init__(self, data):
        assert isinstance(data, Node)
        Node.__init__(self, tag='pubsub', attrs={'xmlns': NS_PUBSUB})
        self.addChild(node=data)


class DeviceListAnnouncement(Iq):
    def __init__(self, device_list):
        assert isinstance(device_list, list)
        assert len(device_list) > 0
        id_ = gajim.get_an_id()
        attrs = {'id': id_}
        Iq.__init__(self, typ='set', attrs=attrs)

        list_node = Node('list', attrs={'xmlns': NS_OMEMO})
        for device in device_list:
            list_node.addChild('device').setAttr('id', device)

        publish = PublishNode(NS_DEVICE_LIST, list_node)
        pubsub = PubsubNode(publish)

        self.addChild(node=pubsub)


class OmemoMessage(Node):
    def __init__(self, msg_dict):
        # , contact_jid, key, iv, payload, dev_id, my_dev_id):
        Node.__init__(self, 'encrypted', attrs={'xmlns': NS_OMEMO})
        header = Node('header', attrs={'sid': msg_dict['sid']})
        for rid, (key, prekey) in msg_dict['keys'].items():
            if prekey:
                child = header.addChild('key',
                                        attrs={'prekey': 'true', 'rid': rid})
            else:
                child = header.addChild('key',
                                        attrs={'rid': rid})
            child.addData(b64encode(key))
        header.addChild('iv').addData(b64encode(msg_dict['iv']))
        self.addChild(node=header)
        payload = msg_dict['payload']
        if payload:
            self.addChild('payload').addData(b64encode(payload))


class BundleInformationQuery(Iq):
    def __init__(self, contact_jid, device_id):
        assert isinstance(device_id, int)
        id_ = gajim.get_an_id()
        attrs = {'id': id_}
        Iq.__init__(self, typ='get', attrs=attrs, to=contact_jid)
        items = Node('items', attrs={'node': NS_BUNDLES + str(device_id),
                                     'max_items': 1})
        pubsub = PubsubNode(items)
        self.addChild(node=pubsub)


class BundleInformationAnnouncement(Iq):
    def __init__(self, state_bundle, device_id):
        id_ = gajim.get_an_id()
        attrs = {'id': id_}
        Iq.__init__(self, typ='set', attrs=attrs)
        bundle_node = self.make_bundle_node(state_bundle)
        publish = PublishNode(NS_BUNDLES + str(device_id), bundle_node)
        pubsub = PubsubNode(publish)
        self.addChild(node=pubsub)

    def make_bundle_node(self, state_bundle):
        result = Node('bundle', attrs={'xmlns': NS_OMEMO})
        prekey_pub_node = result.addChild(
            'signedPreKeyPublic',
            attrs={'signedPreKeyId': state_bundle['signedPreKeyId']})
        prekey_pub_node.addData(state_bundle['signedPreKeyPublic'])

        prekey_sig_node = result.addChild('signedPreKeySignature')
        prekey_sig_node.addData(state_bundle['signedPreKeySignature'])

        identity_key_node = result.addChild('identityKey')
        identity_key_node.addData(state_bundle['identityKey'])
        prekeys = result.addChild('prekeys')

        for key in state_bundle['prekeys']:
            prekeys.addChild('preKeyPublic',
                             attrs={'preKeyId': key[0]}).addData(key[1])
        return result


class DevicelistQuery(Iq):
    def __init__(self, contact_jid,):
        id_ = gajim.get_an_id()
        attrs = {'id': id_}
        Iq.__init__(self, typ='get', attrs=attrs, to=contact_jid)
        items = Node('items', attrs={'node': NS_DEVICE_LIST, 'max_items': 1})
        pubsub = PubsubNode(items)
        self.addChild(node=pubsub)


class DevicelistPEP(AbstractPEP):
    type_ = 'headline'
    namespace = NS_DEVICE_LIST

    def _extract_info(self, items):
        return ({}, [])


@log_calls('OmemoPlugin')
def unpack_device_bundle(bundle, device_id):
    pubsub = bundle.getTag('pubsub', namespace=NS_PUBSUB)
    if not pubsub:
        log.warning('OMEMO device bundle has no pubsub node')
        return
    items = pubsub.getTag('items', attrs={'node': NS_BUNDLES + str(device_id)})
    if not items:
        log.warning('OMEMO device bundle has no items node')
        return

    item = items.getTag('item', namespace=NS_PUBSUB)
    if not item:
        log.warning('OMEMO device bundle has no item node')
        return

    bundle = item.getTag('bundle', namespace=NS_OMEMO)
    if not bundle:
        log.warning('OMEMO device bundle has no bundle node')
        return

    signed_prekey_node = bundle.getTag('signedPreKeyPublic',
                                       namespace=NS_OMEMO)
    if not signed_prekey_node:
        log.warning('OMEMO device bundle has no signedPreKeyPublic node')
        return

    result = {}
    result['signedPreKeyPublic'] = decode_data(signed_prekey_node)
    if not result['signedPreKeyPublic']:
        log.warning('OMEMO device bundle has no signedPreKeyPublic data')
        return

    if not signed_prekey_node.getAttr('signedPreKeyId'):
        log.warning('OMEMO device bundle has no signedPreKeyId')
        return
    result['signedPreKeyId'] = int(signed_prekey_node.getAttr(
        'signedPreKeyId'))

    signed_signature_node = bundle.getTag('signedPreKeySignature',
                                          namespace=NS_OMEMO)
    if not signed_signature_node:
        log.warning('OMEMO device bundle has no signedPreKeySignature node')
        return

    result['signedPreKeySignature'] = decode_data(signed_signature_node)
    if not result['signedPreKeySignature']:
        log.warning('OMEMO device bundle has no signedPreKeySignature data')
        return

    identity_key_node = bundle.getTag('identityKey', namespace=NS_OMEMO)
    if not identity_key_node:
        log.warning('OMEMO device bundle has no identityKey node')
        return

    result['identityKey'] = decode_data(identity_key_node)
    if not result['identityKey']:
        log.warning('OMEMO device bundle has no identityKey data')
        return

    prekeys = bundle.getTag('prekeys', namespace=NS_OMEMO)
    if not prekeys or len(prekeys.getChildren()) == 0:
        log.warning('OMEMO device bundle has no prekys')
        return

    picked_key_node = random.SystemRandom().choice(prekeys.getChildren())

    if not picked_key_node.getAttr('preKeyId'):
        log.warning('OMEMO PreKey has no id set')
        return
    result['preKeyId'] = int(picked_key_node.getAttr('preKeyId'))

    result['preKeyPublic'] = decode_data(picked_key_node)
    if not result['preKeyPublic']:
        return
    return result


@log_calls('OmemoPlugin')
def unpack_encrypted(encrypted_node):
    """ Unpacks the encrypted node, decodes the data and returns a msg_dict.
    """
    if not encrypted_node.getNamespace() == NS_OMEMO:
        log.warning("Encrypted node with wrong NS")
        return

    header_node = encrypted_node.getTag('header', namespace=NS_OMEMO)
    if not header_node:
        log.warning("OMEMO message without header")
        return

    if not header_node.getAttr('sid'):
        log.warning("OMEMO message without sid in header")
        return

    sid = int(header_node.getAttr('sid'))

    iv_node = header_node.getTag('iv', namespace=NS_OMEMO)
    if not iv_node:
        log.warning("OMEMO message without iv")
        return

    iv = decode_data(iv_node)
    if not iv:
        log.warning("OMEMO message without iv data")

    payload_node = encrypted_node.getTag('payload', namespace=NS_OMEMO)
    payload = None
    if payload_node:
        payload = decode_data(payload_node)

    key_nodes = header_node.getTags('key')
    if len(key_nodes) < 1:
        log.warning("OMEMO message without keys")
        return

    keys = {}
    for kn in key_nodes:
        rid = kn.getAttr('rid')
        if not rid:
            log.warning('Omemo key without rid')
            continue

        if not kn.getData():
            log.warning('Omemo key without data')
            continue

        keys[int(rid)] = decode_data(kn)

    result = {'sid': sid, 'iv': iv, 'keys': keys, 'payload': payload}
    return result


def unpack_device_list_update(stanza, account):
    """ Unpacks the device list from a stanza

        Parameters
        ----------
        stanza

        Returns
        -------
        [int]
            List of device ids or empty list if nothing found
    """
    event_node = stanza.getTag('event', namespace=NS_PUBSUB_EVENT)
    if not event_node:
        event_node = stanza.getTag('pubsub', namespace=NS_PUBSUB)
    result = []

    if not event_node:
        log.warning(account + ' => Device list update event node empty!')
        return result

    items = event_node.getTag('items', {'node': NS_DEVICE_LIST})
    if not items or len(items.getChildren()) != 1:
        log.debug(
            account +
            ' => Device list update items node empty or not omemo device update')
        return result

    list_node = items.getChildren()[0].getTag('list')
    if not list_node or len(list_node.getChildren()) == 0:
        log.warning(account + ' => Device list update list node empty!')
        return result

    devices_nodes = list_node.getChildren()

    for dn in devices_nodes:
        _id = dn.getAttr('id')
        if _id:
            result.append(int(_id))

    return result


def decode_data(node):
    """ Fetch the data from specified node and b64decode it. """
    data = node.getData()

    if not data:
        log.warning("No node data")
        return
    try:
        return b64decode(data)
    except:
        log.warning('b64decode broken')
        return


def successful(stanza):
    """ Check if stanza type is result.  """
    return stanza.getAttr('type') == 'result'
