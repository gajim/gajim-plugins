# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of OMEMO Gajim Plugin.
#
# OMEMO Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.


from nbxmpp.namespaces import Namespace


def prepare_stanza(stanza, plaintext):
    delete_nodes(stanza, 'encrypted', Namespace.OMEMO_TEMP)
    delete_nodes(stanza, 'body')
    stanza.setBody(plaintext)


def delete_nodes(stanza, name, namespace=None):
    nodes = stanza.getTags(name, namespace=namespace)
    for node in nodes:
        stanza.delChild(node)
