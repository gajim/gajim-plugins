# This file is part of Gajim.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from typing import cast

import logging
import os
import shutil
from glob import glob
from pathlib import Path

from gajim.common import configpaths

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

log = logging.getLogger('gajim.p.plugins_translations')


class PluginsTranslationsPlugin(GajimPlugin):
    def init(self) -> None:
        self.description = _('This plugin contains translations for other '
                             'Gajim plugins. Please restart Gajim after '
                             'enabling this plugin.')
        self.config_dialog = None
        self.config_default_values = {'last_version': ('0', '')}
        self.locale_dir = Path(configpaths.get('PLUGINS_USER')) / 'locale'

    def activate(self) -> None:
        current_version = str(self.manifest.version)
        if cast(str, self.config['last_version']) == current_version:
            return

        files = glob(self.__path__ + '/*.mo')

        self._remove_translations()

        self.locale_dir.mkdir()
        locales = [
            os.path.splitext(os.path.basename(name))[0] for name in files
        ]
        log.info('Installing new translations...')
        for locale in locales:
            dst = self.locale_dir / locale / 'LC_MESSAGES'
            dst.mkdir(parents=True)
            shutil.copy2(os.path.join(self.__path__, '%s.mo' % locale),
                         dst / 'gajim_plugins.mo')

        self.config['last_version'] = current_version

    def _remove_translations(self) -> None:
        log.info('Removing old translations...')
        if self.locale_dir.exists():
            shutil.rmtree(str(self.locale_dir))

    def deactivate(self) -> None:
        self._remove_translations()
        self.config['last_version'] = '0'
