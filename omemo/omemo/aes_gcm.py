# -*- coding: utf-8 -*-
#
# Copyright 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
#
# This file is part of python-omemo library.
#
# The python-omemo library is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# python-omemo is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# the python-omemo library.  If not, see <http://www.gnu.org/licenses/>.
#


import sys
import logging

from .aes_gcm_native import aes_decrypt
from .aes_gcm_native import aes_encrypt

log = logging.getLogger('gajim.plugin_system.omemo')

def encrypt(key, iv, plaintext):
    return aes_encrypt(key, iv, plaintext)


def decrypt(key, iv, ciphertext, raw_mode=None):
    plaintext = aes_decrypt(key, iv, ciphertext)
    if raw_mode:
        return plaintext
    plaintext = plaintext.decode('utf-8')
    if sys.version_info < (3, 0):
        return unicode(plaintext)
    else:
        return plaintext


class NoValidSessions(Exception):
    pass
