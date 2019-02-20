# Copyright (C) 2015 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
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

import binascii
import textwrap
from enum import IntEnum

DEFAULT_PREKEY_AMOUNT = 100
MIN_PREKEY_AMOUNT = 80
SPK_ARCHIVE_TIME = 86400 * 15  # 15 Days
SPK_CYCLE_TIME = 86400         # 24 Hours


class Trust(IntEnum):
    UNTRUSTED = 0
    TRUSTED = 1
    UNDECIDED = 2


def get_fingerprint(identity_key, formatted=False):
    public_key = identity_key.getPublicKey().serialize()
    fingerprint = binascii.hexlify(public_key).decode()[2:]
    if not formatted:
        return fingerprint
    fplen = len(fingerprint)
    wordsize = fplen // 8
    buf = ''
    for w in range(0, fplen, wordsize):
        buf += '{0} '.format(fingerprint[w:w + wordsize])
    buf = textwrap.fill(buf, width=36)
    return buf.rstrip().upper()