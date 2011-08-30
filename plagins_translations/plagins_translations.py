# -*- coding: utf-8 -*-
##

import gobject
import os

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls
from plugins.plugins_i18n import _


class PlaginsTranslationsPlugin(GajimPlugin):

    @log_calls('PlaginsTranslationsPlugin')
    def init(self):
        self.config_dialog = None
        self.config_default_values = {'last_version': '0'}
        self.locale_dir = os.path.join(gajim.PLUGINS_DIRS[1], 'locale')

    @log_calls('PlaginsTranslationsPlugin')
    def activate(self):
        if self.config['last_version'] == self.version:
            return

        from glob import glob
        import shutil
        files = glob(self.__path__ + '/*.mo')

        # remove old data
        self.remove_translations()

        # create dirs and copy files
        os.mkdir(self.locale_dir)
        locales = [os.path.splitext(os.path.basename(name))[0] for name in files]
        for locale in locales:
            dst = os.path.join(os.path.join(self.locale_dir, locale),
                'LC_MESSAGES/gajim_plugins.mo')
            os.makedirs(os.path.split(dst)[0])
            shutil.copy2(os.path.join(self.__path__, '%s.mo' % locale), dst)

        self.config['last_version'] = self.version

    def remove_translations(self):
        if os.path.isdir(self.locale_dir):
            import shutil
            shutil.rmtree(self.locale_dir)

    @log_calls('PlaginsTranslationsPlugin')
    def deactivate(self):
        self.remove_translations()
