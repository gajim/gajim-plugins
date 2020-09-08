# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
# Copyright (C) 2003-2014 Yann Leboulanger <asterix AT lagaule.org>
# Copyright (C) 2005 Alex Mauer <hawke AT hawkesnest.net>
# Copyright (C) 2005-2006 Nikos Kouremenos <kourem AT gmail.com>
# Copyright (C) 2007 Stephan Erb <steve-e AT h3c.de>
# Copyright (C) 2008 Jean-Marie Traissard <jim AT lapin.org>
#                    Jonathan Schleifer <js-gajim AT webkeks.org>
#
# This file is part of PGP Gajim Plugin.
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
import logging
from functools import lru_cache

import gnupg

from gajim.common.helpers import Singleton

from pgp.exceptions import SignError


logger = logging.getLogger('gajim.p.pgplegacy')
if logger.getEffectiveLevel() == logging.DEBUG:
    logger = logging.getLogger('gnupg')
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.DEBUG)


class PGP(gnupg.GPG, metaclass=Singleton):
    def __init__(self, binary, encoding=None):
        super().__init__(gpgbinary=binary,
                         use_agent=True)

        if encoding is not None:
            self.encoding = encoding
        self.decode_errors = 'replace'

    def encrypt(self, payload, recipients, always_trust=False):
        if not always_trust:
            # check that we'll be able to encrypt
            result = self.get_key(recipients[0])
            for key in result:
                if key['trust'] not in ('f', 'u'):
                    return '', 'NOT_TRUSTED ' + key['keyid'][-8:]

        result = super().encrypt(
            payload.encode('utf8'),
            recipients,
            always_trust=always_trust)

        if result.ok:
            error = ''
        else:
            error = result.status

        return self._strip_header_footer(str(result)), error

    def decrypt(self, payload):
        data = self._add_header_footer(payload, 'MESSAGE')
        result = super().decrypt(data.encode('utf8'))

        return result.data.decode('utf8')

    @lru_cache(maxsize=8)
    def sign(self, payload, key_id):
        if payload is None:
            payload = ''
        result = super().sign(payload.encode('utf8'),
                              keyid=key_id,
                              detach=True)

        if result.fingerprint:
            return self._strip_header_footer(str(result))
        raise SignError(result.status)

    def verify(self, payload, signed):
        # Hash algorithm is not transfered in the signed
        # presence stanza so try all algorithms.
        # Text name for hash algorithms from RFC 4880 - section 9.4

        if payload is None:
            payload = ''

        hash_algorithms = ['SHA512', 'SHA384', 'SHA256',
                           'SHA224', 'SHA1', 'RIPEMD160']
        for algo in hash_algorithms:
            data = os.linesep.join(
                ['-----BEGIN PGP SIGNED MESSAGE-----',
                 'Hash: ' + algo,
                 '',
                 payload,
                 self._add_header_footer(signed, 'SIGNATURE')]
                )
            result = super().verify(data.encode('utf8'))
            if result.valid:
                return result.fingerprint

    def get_key(self, key_id):
        return super().list_keys(keys=[key_id])

    def get_keys(self, secret=False):
        keys = {}
        result = super().list_keys(secret=secret)

        for key in result:
            # Take first not empty uid
            keys[key['fingerprint']] = next(uid for uid in key['uids'] if uid)
        return keys

    @staticmethod
    def _strip_header_footer(data):
        """
        Remove header and footer from data
        """
        if not data:
            return ''
        lines = data.splitlines()
        while lines[0] != '':
            lines.remove(lines[0])
        while lines[0] == '':
            lines.remove(lines[0])
        i = 0
        for line in lines:
            if line:
                if line[0] == '-':
                    break
            i = i+1
        line = '\n'.join(lines[0:i])
        return line

    @staticmethod
    def _add_header_footer(data, type_):
        """
        Add header and footer from data
        """
        out = "-----BEGIN PGP %s-----" % type_ + os.linesep
        out = out + "Version: PGP" + os.linesep
        out = out + os.linesep
        out = out + data + os.linesep
        out = out + "-----END PGP %s-----" % type_ + os.linesep
        return out
