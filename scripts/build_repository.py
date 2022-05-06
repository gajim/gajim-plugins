
# Keep this file python 3.7 compatible because it is executed on the server

from typing import Any
from typing import Dict
from typing import Iterator
from typing import Set
from typing import Dict

import sys
import json
import logging
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile


FORMAT = '%(asctime)s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)
log = logging.getLogger()


REQUIRED_KEYS: Set[str] = {
    'authors',
    'description',
    'homepage',
    'config_dialog',
    'name',
    'platforms',
    'requirements',
    'short_name',
    'version'
}

PACKAGE_INDEX: Dict[str, Any] = {
    'metadata': {
        'repository_name': 'master',
        'image_url': 'images.zip',
    },
    'plugins': defaultdict(dict)
}


def is_manifest_valid(manifest: Dict[str, Any]) -> bool:
    manifest_keys = set(manifest.keys())
    return REQUIRED_KEYS.issubset(manifest_keys)


def iter_releases(release_folder: Path) -> Iterator[Dict[str, Any]]:
    for path in release_folder.rglob('*.zip'):
        with ZipFile(path) as release_zip:
            try:
                with release_zip.open('manifest.json') as file:
                    manifest = json.load(file)
                    yield manifest
            except Exception:
                log.error('Error loading manifest')
                log.exception('')


def build_package_index(release_folder: Path) -> None:
    log.info('Build package index')
    for manifest in iter_releases(release_folder):
        if not is_manifest_valid(manifest):
            log.warning('Invalid manifest')
            log.warning(manifest)
            continue

        short_name = manifest.pop('short_name')
        version = manifest.pop('version')
        PACKAGE_INDEX['plugins'][short_name][version] = manifest
        log.info('Found manifest: %s - %s', short_name, version)

    path = release_folder / 'package_index.json'
    with path.open('w') as f:
        json.dump(PACKAGE_INDEX, f)


def build_image_zip(release_folder: Path) -> None:
    log.info('Build images.zip')
    with ZipFile(release_folder / 'images.zip', mode='w') as image_zip:
        for path in release_folder.iterdir():
            if not path.is_dir():
                continue

            image = path / f'{path.name}.png'
            if not image.exists():
                continue
            image_zip.write(image, arcname=image.name)


if __name__ == '__main__':
    path = Path(sys.argv[1])
    build_package_index(path)
    build_image_zip(path)
    log.info('Finished')
