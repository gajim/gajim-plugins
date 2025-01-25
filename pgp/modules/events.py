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

from __future__ import annotations

from typing import Any
from typing import Callable

from dataclasses import dataclass
from dataclasses import field

from gajim.common.events import ApplicationEvent


@dataclass
class PGPNotTrusted(ApplicationEvent):
    name: str = field(init=False, default="pgp-not-trusted")
    on_yes: Callable[..., Any]
    on_no: Callable[..., Any]


@dataclass
class PGPFileEncryptionError(ApplicationEvent):
    name: str = field(init=False, default="pgp-file-encryption-error")
    error: str
