from typing import Any

import functools
import json
import os
import sys
from collections.abc import Iterator
from ftplib import FTP_TLS
from pathlib import Path
from shutil import make_archive

import requests
from rich.console import Console

PackageT = tuple[dict[str, Any], Path]
ManifestT = dict[str, Any]
PackageIndexT = dict[str, Any]


FTP_URL = "panoramix.gajim.org"
FTP_USER = os.environ["FTP_USER"]
FTP_PASS = os.environ["FTP_PASS"]

REPOSITORY_FOLDER = "plugins/master"
PACKAGE_INDEX_URL = "https://ftp.gajim.org/plugins/master/package_index.json"
REPO_ROOT = Path(__file__).parent.parent
BUILD_PATH = REPO_ROOT / "build"


REQUIRED_KEYS = {
    "authors",
    "description",
    "homepage",
    "name",
    "platforms",
    "requirements",
    "short_name",
    "version",
}


console = Console()


def ftp_connection(func: Any) -> Any:
    @functools.wraps(func)
    def func_wrapper(*args: Any) -> None:
        ftp = FTP_TLS(FTP_URL, FTP_USER, FTP_PASS)  # noqa: S321
        console.print("Successfully connected to", FTP_URL)
        func(ftp, *args)
        ftp.quit()
        console.print("Quit")

    return func_wrapper


def is_manifest_valid(manifest: ManifestT) -> bool:
    manifest_keys = set(manifest.keys())
    return REQUIRED_KEYS.issubset(manifest_keys)


def download_package_index() -> ManifestT:
    console.print("Download package index")
    r = requests.get(PACKAGE_INDEX_URL, timeout=30)
    if r.status_code == 404:
        return {}

    r.raise_for_status()
    index = r.json()
    return index


def iter_manifests() -> Iterator[PackageT]:
    for path in REPO_ROOT.rglob("plugin-manifest.json"):
        with path.open() as f:
            manifest = json.load(f)
        yield manifest, path.parent


def find_plugins_to_publish(index: PackageIndexT) -> list[PackageT]:
    packages_to_publish: list[PackageT] = []
    for manifest, path in iter_manifests():
        if not is_manifest_valid(manifest):
            sys.exit("Invalid manifest found")

        short_name = manifest["short_name"]
        version = manifest["version"]

        try:
            index["plugins"][short_name][version]
        except KeyError:
            packages_to_publish.append((manifest, path))
            console.print("Found package to publish:", path.stem)

    return packages_to_publish


def get_release_zip_name(manifest: ManifestT) -> str:
    short_name = manifest["short_name"]
    version = manifest["version"]
    return f"{short_name}_{version}"


def get_dir_list(ftp: FTP_TLS) -> set[str]:
    return {x[0] for x in ftp.mlsd()}


def upload_file(ftp: FTP_TLS, filepath: Path) -> None:

    name = filepath.name
    console.print("Upload file", name)
    with open(filepath, "rb") as f:
        ftp.storbinary("STOR " + name, f)


def create_release_folder(ftp: FTP_TLS, packages_to_publish: list[PackageT]) -> None:

    folders = {manifest["short_name"] for manifest, _ in packages_to_publish}
    dir_list = get_dir_list(ftp)
    missing_folders = folders - dir_list
    for folder in missing_folders:
        ftp.mkd(folder)


@ftp_connection
def deploy(ftp: FTP_TLS, packages_to_publish: list[PackageT]) -> None:
    ftp.cwd(REPOSITORY_FOLDER)
    create_release_folder(ftp, packages_to_publish)

    for manifest, path in packages_to_publish:
        package_name = manifest["short_name"]
        zip_name = get_release_zip_name(manifest)
        zip_path = BUILD_PATH / f"{zip_name}.zip"
        image_path = path / f"{package_name}.png"

        make_archive(str(BUILD_PATH / zip_name), "zip", path)

        ftp.cwd(package_name)
        upload_file(ftp, zip_path)
        if image_path.exists():
            upload_file(ftp, image_path)
        ftp.cwd("..")

        console.print("Deployed", package_name)


if __name__ == "__main__":
    index = download_package_index()
    packages_to_publish = find_plugins_to_publish(index)
    if not packages_to_publish:
        console.print("No new packages deployed")
    else:
        deploy(packages_to_publish)
