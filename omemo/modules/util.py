# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of OMEMO.
#
# OMEMO is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO. If not, see <http://www.gnu.org/licenses/>.

# XEP-0384: OMEMO Encryption

import logging

import nbxmpp

from gajim.common.exceptions import StanzaMalformed


log = logging.getLogger('gajim.plugin_system.omemo')

NS_OMEMO = 'eu.siacs.conversations.axolotl'
NS_DEVICE_LIST = NS_OMEMO + '.devicelist'


def unpack_devicelist(item):
    list_ = item.getTag('list', namespace=NS_OMEMO)
    if list_ is None:
        raise StanzaMalformed('No list node')

    device_list = list_.getTags('device')

    devices = []
    for device in device_list:
        id_ = device.getAttr('id')
        if id_ is None:
            raise StanzaMalformed('No id for device found')

        devices.append(int(id_))
    return devices
