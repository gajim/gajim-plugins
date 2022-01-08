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

from typing import Optional

import logging
from dataclasses import dataclass

log = logging.getLogger('gajim.p.triggers')


def log_result(func):
  def wrapper(self, event, rule):
      res = func(self, event, rule)
      log.info(f'{event.name} -> {func.__name__} -> {res}')
      return res
  return wrapper


@dataclass
class RuleResult:
    show_notification: Optional[bool] = None
    command: Optional[str] = None
    sound: Optional[bool] = None
    sound_file: Optional[str] = None
