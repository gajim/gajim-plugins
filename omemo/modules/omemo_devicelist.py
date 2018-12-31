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

from gajim.common import app
from gajim.common.modules.pep import AbstractPEPModule, AbstractPEPData

from omemo.modules.util import NS_OMEMO
from omemo.modules.util import NS_DEVICE_LIST
from omemo.modules.util import unpack_devicelist

log = logging.getLogger('gajim.plugin_system.omemo.pep')

# Module name
name = 'OMEMODevicelist'
zeroconf = False


class OMEMODevicelistData(AbstractPEPData):

    type_ = 'omemo-devicelist'


class OMEMODevicelist(AbstractPEPModule):
    '''
    <item>
        <list xmlns='eu.siacs.conversations.axolotl'>
            <device id='12345' />
            <device id='4223' />
        </list>
    </item>
    '''

    name = 'omemo-devicelist'
    namespace = NS_DEVICE_LIST
    pep_class = OMEMODevicelistData
    store_publish = True
    _log = log

    @staticmethod
    def _extract_info(item):
        return unpack_devicelist(item)

    def _notification_received(self, jid, devicelist):
        con = app.connections[self._account]
        con.get_module('OMEMO').device_list_received(devicelist.data,
                                                     jid.getStripped())
    @staticmethod
    def _build_node(devicelist):
        list_node = nbxmpp.Node('list', {'xmlns': NS_OMEMO})
        if devicelist is None:
            return list_node
        for device in devicelist:
            list_node.addChild('device', attrs={'id': device})
        return list_node


def get_instance(*args, **kwargs):
    return OMEMODevicelist(*args, **kwargs), 'OMEMODevicelist'
