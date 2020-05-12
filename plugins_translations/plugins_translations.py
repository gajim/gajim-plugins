import logging
import os

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
        self.locale_dir = os.path.join(
            configpaths.get('PLUGINS_USER'), 'locale')

    def activate(self):
        if self.config['last_version'] == self.version:
            return

        from glob import glob
        import shutil
        files = glob(self.__path__ + '/*.mo')

        # remove old data
        self._remove_translations()

        # create dirs and copy files
        os.mkdir(self.locale_dir)
        locales = [
            os.path.splitext(os.path.basename(name))[0] for name in files
        ]
        log.info('Installing new translations...')
        for locale in locales:
            dst = os.path.join(os.path.join(self.locale_dir, locale),
                               'LC_MESSAGES/gajim_plugins.mo')
            os.makedirs(os.path.split(dst)[0])
            shutil.copy2(os.path.join(self.__path__, '%s.mo' % locale), dst)

        self.config['last_version'] = self.version

    def _remove_translations(self):
        log.info('Removing old translations...')
        if os.path.isdir(self.locale_dir):
            import shutil
            shutil.rmtree(self.locale_dir)

    def deactivate(self):
        self._remove_translations()
        self.config['last_version'] = '0'
