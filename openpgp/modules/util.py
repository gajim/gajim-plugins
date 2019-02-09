# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the OpenPGP Gajim Plugin.
#
# OpenPGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OpenPGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OpenPGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

from enum import IntEnum
from collections import namedtuple

import nbxmpp


ENCRYPTION_NAME = 'OpenPGP'

NOT_ENCRYPTED_TAGS = [
    ('no-store', nbxmpp.NS_MSG_HINTS),
    ('store', nbxmpp.NS_MSG_HINTS),
    ('no-copy', nbxmpp.NS_MSG_HINTS),
    ('no-permanent-store', nbxmpp.NS_MSG_HINTS),
    ('origin-id', nbxmpp.NS_SID),
    ('thread', None)
]

Key = namedtuple('Key', 'fingerprint date')


class Trust(IntEnum):
    NOT_TRUSTED = 0
    UNKNOWN = 1
    BLIND = 2
    VERIFIED = 3


def prepare_stanza(stanza, payload):
    delete_nodes(stanza, 'openpgp', nbxmpp.NS_OPENPGP)
    delete_nodes(stanza, 'body')

    nodes = [(node.getName(), node.getNamespace()) for node in payload]
    for name, namespace in nodes:
        delete_nodes(stanza, name, namespace)

    for node in payload:
        stanza.addChild(node=node)


def delete_nodes(stanza, name, namespace=None):
    attrs = None
    if namespace is not None:
        attrs = {'xmlns': nbxmpp.NS_OPENPGP}
    nodes = stanza.getTags(name, attrs)
    for node in nodes:
        stanza.delChild(node)


def add_additional_data(data, fingerprint):
    data['encrypted'] = {'name': ENCRYPTION_NAME,
                         'fingerprint': fingerprint}


class VerifyFailed(Exception):
    pass


class DecryptionFailed(Exception):
    pass
