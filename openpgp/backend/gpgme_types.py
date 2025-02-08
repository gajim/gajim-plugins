# Copyright (C) 2025 Philipp Hörist <philipp AT hoerist.com>
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

from __future__ import annotations

from typing import Any


class UID:
    address: Any | None
    comment: str
    email: str
    invalid: int
    last_update: int
    name: str
    origin: int
    revoked: int
    signatures: list[Any]
    thisown: bool
    tofu: list[Any]
    uid: str
    uidhash: str
    validity: int


class SubKey:
    can_authenticate: int
    can_certify: int
    can_encrypt: int
    can_sign: int
    card_number: Any | None
    curve: Any | None
    disabled: int
    expired: int
    expires: int
    fpr: str
    invalid: int
    is_cardkey: int
    is_de_vs: int
    is_qualified: int
    keygrip: Any | None
    keyid: str
    length: int
    pubkey_algo: int
    revoked: int
    secret: int
    thisown: bool
    timestamp: int


class Key:
    can_authenticate: int
    can_certify: int
    can_encrypt: int
    can_sign: int
    chain_id: Any | None
    disabled: int
    expired: int
    fpr: str
    invalid: int
    is_qualified: int
    issuer_name: str | None
    issuer_serial: str | None
    keylist_mode: int
    last_update: int
    origin: int
    owner_trust: int
    protocol: int
    revoked: int
    secret: int
    subkeys: list[SubKey]
    thisown: bool
    uids: list[UID]
