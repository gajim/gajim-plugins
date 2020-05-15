import logging
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import configparser
from configparser import ConfigParser
from packaging.version import Version as V

from gi.repository import Gtk
from gi.repository import GdkPixbuf

from gajim.common import app
from gajim.common import configpaths

from plugin_installer.remote import PLUGINS_DIR_URL

log = logging.getLogger('gajim.p.installer.utils')

MANDATORY_FIELDS = {'name', 'short_name', 'version',
                    'description', 'authors', 'homepage'}
FALLBACK_ICON = Gtk.IconTheme.get_default().load_icon(
    'preferences-system', Gtk.IconSize.MENU, 0)


class PluginInfo:
    def __init__(self, config, icon):
        self.icon = icon
        self.name = config.get('info', 'name')
        self.short_name = config.get('info', 'short_name')
        self.version = V(config.get('info', 'version'))
        self._installed_version = None
        self.min_gajim_version = V(config.get('info', 'min_gajim_version'))
        self.max_gajim_version = V(config.get('info', 'max_gajim_version'))
        self.description = config.get('info', 'description')
        self.authors = config.get('info', 'authors')
        self.homepage = config.get('info', 'homepage')


    @classmethod
    def from_zip_file(cls, zip_file, manifest_path):
        config = ConfigParser()
        # ZipFile can only handle posix paths
        with zip_file.open(manifest_path.as_posix()) as manifest_file:
            try:
                config.read_string(manifest_file.read().decode())
            except configparser.Error as error:
                log.warning(error)
                raise ValueError('Invalid manifest: %s' % manifest_path)

        if not is_manifest_valid(config):
            raise ValueError('Invalid manifest: %s' % manifest_path)

        short_name = config.get('info', 'short_name')
        png_filename = '%s.png' % short_name
        png_path = manifest_path.parent / png_filename
        icon = load_icon_from_zip(zip_file, png_path) or FALLBACK_ICON

        return cls(config, icon)

    @classmethod
    def from_path(cls, manifest_path):
        config = ConfigParser()
        with open(manifest_path, encoding='utf-8') as conf_file:
            try:
                config.read_file(conf_file)
            except configparser.Error as error:
                log.warning(error)
                raise ValueError('Invalid manifest: %s' % manifest_path)

        if not is_manifest_valid(config):
            raise ValueError('Invalid manifest: %s' % manifest_path)

        return cls(config, None)

    @property
    def remote_uri(self):
        return '%s/%s.zip' % (PLUGINS_DIR_URL, self.short_name)

    @property
    def download_path(self):
        return Path(configpaths.get('PLUGINS_DOWNLOAD'))

    @property
    def installed_version(self):
        if self._installed_version is None:
            self._installed_version = self._get_installed_version()
        return self._installed_version

    def has_valid_version(self):
        gajim_version = V(app.config.get('version'))
        return self.min_gajim_version <= gajim_version <= self.max_gajim_version

    def _get_installed_version(self):
        for plugin in app.plugin_manager.plugins:
            if plugin.name == self.name:
                return plugin.version

        # Fallback:
        # If the plugin has errors and is not loaded by the
        # PluginManager. Look in the Gajim config if the plugin is
        # known and active, if yes load the manifest from the Plugin
        # dir and parse the version
        active = app.config.get_per('plugins', self.short_name, 'active')
        if not active:
            return None

        manifest_path = (Path(configpaths.get('PLUGINS_USER')) /
                         self.short_name /
                         'manifest.ini')
        if not manifest_path.exists():
            return None
        try:
            return PluginInfo.from_path(manifest_path).version
        except Exception as error:
            log.warning(error)
        return None

    def needs_update(self):
        if self.installed_version is None:
            return False
        return self.installed_version < self.version

    @property
    def fields(self):
        return [self.icon,
                self.name,
                str(self.installed_version or ''),
                str(self.version),
                self.needs_update(),
                self]


def parse_manifests_zip(bytes_):
    plugins = []
    with ZipFile(BytesIO(bytes_)) as zip_file:
        files = list(map(Path, zip_file.namelist()))
        for manifest_path in filter(is_manifest, files):
            try:
                plugin = PluginInfo.from_zip_file(zip_file, manifest_path)
            except Exception as error:
                log.warning(error)
                continue

            if not plugin.has_valid_version():
                continue
            plugins.append(plugin)

    return plugins


def is_manifest(path):
    if path.name == 'manifest.ini':
        return True
    return False


def is_manifest_valid(config):
    if not config.has_section('info'):
        log.warning('Manifest is missing INFO section')
        return False

    opts = config.options('info')
    if not MANDATORY_FIELDS.issubset(opts):
        log.warning('Manifest is missing mandatory fields %s.',
                    MANDATORY_FIELDS.difference(opts))
        return False
    return True


def load_icon_from_zip(zip_file, icon_path):
    # ZipFile can only handle posix paths
    try:
        zip_file.getinfo(icon_path.as_posix())
    except KeyError:
        return None

    with zip_file.open(icon_path.as_posix()) as png_file:
        data = png_file.read()

    pixbuf = GdkPixbuf.PixbufLoader()
    pixbuf.set_size(16, 16)
    try:
        pixbuf.write(data)
    except Exception:
        log.exception('Can\'t load icon: %s', icon_path)
        pixbuf.close()
        return None

    pixbuf.close()
    return pixbuf.get_pixbuf()
