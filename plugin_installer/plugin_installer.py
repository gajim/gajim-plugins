# Copyright (C) 2010-2012 Denis Fomin <fominde AT gmail.com>
# Copyright (C) 2011-2012 Yann Leboulanger <asterix AT lagaule.org>
# Copyright (C) 2017-2019 Philipp Hörist <philipp AT hoerist.com>
#
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

import logging
from functools import partial
from io import BytesIO
from zipfile import ZipFile

from gi.repository import GLib
from gi.repository import Soup

from gajim.common import app

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from gajim.gtk.dialogs import DialogButton
from gajim.gtk.dialogs import InformationDialog
from gajim.gtk.dialogs import ConfirmationCheckDialog

from plugin_installer.config_dialog import PluginInstallerConfigDialog
from plugin_installer.widget import AvailablePage
from plugin_installer.utils import parse_manifests_zip
from plugin_installer.remote import MANIFEST_URL
from plugin_installer.remote import MANIFEST_IMAGE_URL


log = logging.getLogger('gajim.p.installer')


class PluginInstaller(GajimPlugin):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        self.description = _('Install and upgrade plugins for Gajim')
        self.config_dialog = partial(PluginInstallerConfigDialog, self)
        self.config_default_values = {'check_update': (True, ''),
                                      'auto_update': (False, ''),
                                      'auto_update_feedback': (True, '')}
        self.gui_extension_points = {
            'plugin_window': (self._on_connect_plugin_window,
                              self._on_disconnect_plugin_window)}

        self._check_update_id = None
        self._available_page = None

        self._update_in_progress = False
        self._download_in_progress = False
        self._download_queue = 0
        self._needs_restart = False

        self._session = Soup.Session()

    @property
    def download_in_progress(self):
        return self._download_in_progress

    def activate(self):
        if self.config['check_update']:
            # Check for updates X seconds after Gajim was started
            self._check_update_id = GLib.timeout_add_seconds(
                10, self._check_for_updates)

    def deactivate(self):
        if self._check_update_id is not None:
            GLib.source_remove(self._check_update_id)
            self._check_update_id = None

    def _set_download_in_progress(self, state):
        self._download_in_progress = state
        if self._available_page is not None:
            self._available_page.set_download_in_progress(state)

    def _check_for_updates(self):
        if self._download_in_progress:
            log.info('Abort checking for updates because '
                     'other downloads are in progress')
            return
        log.info('Checking for Updates...')
        message = Soup.Message.new('GET', MANIFEST_URL)
        self._session.queue_message(message,
                                    self._on_check_for_updates_finished)

    def _on_check_for_updates_finished(self, _session, message):
        if message.status_code != Soup.Status.OK:
            log.warning('Download failed: %s', MANIFEST_URL)
            log.warning(Soup.Status.get_phrase(message.status_code))
            return

        data = message.props.response_body_data.get_data()
        if data is None:
            return

        plugin_list = parse_manifests_zip(data)
        for plugin in list(plugin_list):
            if plugin.needs_update():
                log.info('Update available for: %s - %s',
                         plugin.name, plugin.version)
            else:
                plugin_list.remove(plugin)

        if not plugin_list:
            log.info('No updates available')
            return

        if self.config['auto_update']:
            self._update_in_progress = True
            self._download_plugins(plugin_list)
        else:
            self._notify_about_update(plugin_list)

    def _notify_about_update(self, plugins):
        def _open_update(is_checked):
            if is_checked:
                self.config['auto_update'] = True
            self._download_plugins(plugins)

        plugins_str = '\n' + '\n'.join([plugin.name for plugin in plugins])
        ConfirmationCheckDialog(
            _('Plugin Updates'),
            _('Plugin Updates Available'),
            _('There are updates for your plugins:\n'
              '<b>%s</b>') % plugins_str,
            _('Update plugins automatically next time'),
            [DialogButton.make('Cancel'),
             DialogButton.make('Accept',
                               text=_('_Update'),
                               is_default=True,
                               callback=_open_update)]).show()

    def _download_plugin_list(self):
        log.info('Download plugin list...')
        message = Soup.Message.new('GET', MANIFEST_IMAGE_URL)
        self._session.queue_message(message,
                                    self._on_download_plugin_list_finished)

    def _on_download_plugin_list_finished(self, _session, message):
        if message.status_code != Soup.Status.OK:
            log.warning('Download failed: %s', MANIFEST_IMAGE_URL)
            log.warning(Soup.Status.get_phrase(message.status_code))
            return

        data = message.props.response_body_data.get_data()
        if data is None:
            return

        plugin_list = parse_manifests_zip(data)
        if not plugin_list:
            log.warning('No plugins found in zip')

        if self._available_page is None:
            return
        self._available_page.append_plugins(plugin_list)
        log.info('Downloading plugin list finished')

    def _on_download_plugins(self, _available_page, _signal_name, plugin_list):
        self._download_plugins(plugin_list)

    def _download_plugins(self, plugin_list):
        if self._download_in_progress:
            log.warning('Download started while other download in progress')
            return

        self._set_download_in_progress(True)
        self._download_queue = len(plugin_list)
        for plugin in plugin_list:
            self._download_plugin(plugin)

    def _download_plugin(self, plugin):
        log.info('Download plugin %s', plugin.name)
        message = Soup.Message.new('GET', plugin.remote_uri)
        self._session.queue_message(message,
                                    self._on_download_plugin_finished,
                                    plugin)

    def _on_download_plugin_finished(self, _session, message, plugin):
        self._download_queue -= 1
        if message.status_code != Soup.Status.OK:
            log.warning('Download failed: %s', plugin.remote_uri)
            log.warning(Soup.Status.get_phrase(message.status_code))
            return

        data = message.props.response_body_data.get_data()
        if data is None:
            return

        log.info('Finished downloading %s', plugin.name)

        if not plugin.download_path.exists():
            plugin.download_path.mkdir(mode=0o700)

        with ZipFile(BytesIO(data)) as zip_file:
            zip_file.extractall(str(plugin.download_path))

        activated = app.plugin_manager.update_plugins(
            replace=False, activate=True, plugin_name=plugin.short_name)
        if activated:
            if self._available_page is not None:
                self._available_page.update_plugin(plugin)

        else:
            self._needs_restart = True
            log.info('Plugin %s needs restart', plugin.name)

        if self._download_queue == 0:
            self._set_download_in_progress(False)
            self._notify_about_download_finished()
            self._update_in_progress = False
            self._needs_restart = False

    def _notify_about_download_finished(self):
        if not self._update_in_progress:
            if self._needs_restart:
                InformationDialog(
                    _('Plugins Downloaded'),
                    _('Updates will be installed next time Gajim is '
                      'started.'))
            else:
                InformationDialog(_('Plugins Downloaded'))

        elif self.config['auto_update_feedback']:
            def _on_ok(is_checked):
                if is_checked:
                    self.config['auto_update_feedback'] = False
            ConfirmationCheckDialog(
                _('Plugins Updated'),
                _('Plugins Updated'),
                _('Plugin updates have successfully been downloaded.\n'
                  'Updates will be installed next time Gajim is started.'),
                _('Do not show this message again'),
                [DialogButton.make('OK',
                                   callback=_on_ok)]).show()

    def _on_connect_plugin_window(self, plugin_window):
        self._available_page = AvailablePage(
            self.local_file_path('installer.ui'), plugin_window.get_notebook())
        self._available_page.set_download_in_progress(
            self._download_in_progress)
        self._available_page.connect('download-plugins',
                                     self._on_download_plugins)
        self._download_plugin_list()

    def _on_disconnect_plugin_window(self, _plugin_window):
        self._session.abort()
        self._available_page.destroy()
        self._available_page = None
