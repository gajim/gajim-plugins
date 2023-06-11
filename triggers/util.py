# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import TYPE_CHECKING

import logging
from dataclasses import dataclass

if TYPE_CHECKING:
    from .triggers import ProcessableEventsT
    from .triggers import RuleT

log = logging.getLogger('gajim.p.triggers')


def log_result(func: Callable[..., Any]) -> Callable[..., bool]:
    def wrapper(self: Any, event: ProcessableEventsT, rule: RuleT):
        res = func(self, event, rule)
        log.info(f'{event.name} -> {func.__name__} -> {res}')
        return res
    return wrapper


@dataclass
class RuleResult:
    show_notification: bool | None = None
    command: str | None = None
    sound: bool | None = None
    sound_file: str | None = None
