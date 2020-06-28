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
    def init(self):
        self.description = _('This plugin contains translations for other '
                             'Gajim plugins. Please restart Gajim after '
                             'enabling this plugin.')
        self.config_dialog = None
        self.config_default_values = {'last_version': '0'}
        self.locale_dir = Path(configpaths.get('PLUGINS_USER')) / 'locale'

    def activate(self):
        if self.config['last_version'] == self.version:
            return

        files = glob(self.__path__ + '/*.mo')

        self._remove_translations()

        self.locale_dir.mkdir()
        locales = [
            os.path.splitext(os.path.basename(name))[0] for name in files
        ]
        log.info('Installing new translations...')
        for locale in locales:
            dst = self.locale_dir / locale / 'LC_MESSAGES' / 'gajim_plugins.mo'
            dst.mkdir(parents=True)
            shutil.copy2(os.path.join(self.__path__, '%s.mo' % locale),
                         str(dst))

        self.config['last_version'] = self.version

    def _remove_translations(self):
        log.info('Removing old translations...')
        if self.locale_dir.exists():
            shutil.rmtree(str(self.locale_dir))

    def deactivate(self):
        self._remove_translations()
        self.config['last_version'] = '0'
