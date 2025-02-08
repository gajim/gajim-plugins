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

from nbxmpp import Node
from nbxmpp.namespaces import Namespace

ENCRYPTION_NAME = "OpenPGP"

NOT_ENCRYPTED_TAGS = [
    ("no-store", Namespace.HINTS),
    ("store", Namespace.HINTS),
    ("no-copy", Namespace.HINTS),
    ("no-permanent-store", Namespace.HINTS),
    ("origin-id", Namespace.SID),
    ("thread", ""),
]


class Trust(IntEnum):
    NOT_TRUSTED = 0
    UNKNOWN = 1
    BLIND = 2
    VERIFIED = 3


def prepare_stanza(stanza: Node, payload: list[Node | str]) -> None:
    delete_nodes(stanza, "openpgp", Namespace.OPENPGP)
    delete_nodes(stanza, "body")

    nodes: list[Node] = []
    for node in payload:
        if isinstance(node, str):
            continue
        name, namespace = node.getName(), node.getNamespace()
        delete_nodes(stanza, name, namespace)
        nodes.append(node)

    for node in nodes:
        stanza.addChild(node=node)


def delete_nodes(stanza: Node, name: str, namespace: str | None = None) -> None:
    attrs = None
    if namespace is not None:
        attrs = {"xmlns": Namespace.OPENPGP}
    nodes = stanza.getTags(name, attrs)
    for node in nodes:
        stanza.delChild(node)


class VerifyFailed(Exception):
    pass


class DecryptionFailed(Exception):
    pass
