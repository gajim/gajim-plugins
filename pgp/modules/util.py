# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the PGP Gajim Plugin.
#
# PGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# PGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import os
import subprocess

import nbxmpp


def prepare_stanza(stanza, plaintext):
    delete_nodes(stanza, 'encrypted', nbxmpp.NS_ENCRYPTED)
    delete_nodes(stanza, 'body')
    stanza.setBody(plaintext)


def delete_nodes(stanza, name, namespace=None):
    nodes = stanza.getTags(name, namespace=namespace)
    for node in nodes:
        stanza.delChild(node)


def find_gpg():
    def _search(binary):
        if os.name == 'nt':
            gpg_cmd = binary + ' -h >nul 2>&1'
        else:
            gpg_cmd = binary + ' -h >/dev/null 2>&1'
        if subprocess.call(gpg_cmd, shell=True):
            return False
        return True

    if _search('gpg2'):
        return 'gpg2'

    if _search('gpg'):
        return 'gpg'
