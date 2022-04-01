#!/usr/bin/env python3

import re
import subprocess
from pathlib import Path
import sys


REPO_DIR = Path(__file__).parent.parent
TRANS_DIR = REPO_DIR / 'po'
TRANS_TEMPLATE = TRANS_DIR / 'gajim_plugins.pot'
BUILD_DIR = REPO_DIR / 'plugins_translations'
TRANSLATABLE_FILES = [
    '*.py',
    '*.ui',
]


def template_is_equal(old_template_path: Path, new_template: str) -> bool:
    with open(old_template_path, 'r') as f:
        old_template = f.read()

    pattern = r'"POT-Creation-Date: .*\n"'

    old_template = re.sub(pattern, '', old_template, count=1)
    new_template = re.sub(pattern, '', new_template, count=1)

    return old_template == new_template


def update_translation_template() -> bool:
    paths: list[Path] = []
    for file_path in TRANSLATABLE_FILES:
        paths += list(REPO_DIR.rglob(file_path))

    cmd = [
        'xgettext',
        '-o', '-',
        '-c#',
        '--from-code=utf-8',
        '--keyword=Q_',
        '--no-location',
        '--sort-output',
        '--package-name=Gajim Plugins'
    ]

    for path in paths:
        cmd.append(str(path))

    result = subprocess.run(cmd,
                            cwd=REPO_DIR,
                            text=True,
                            check=True,
                            capture_output=True)

    template = result.stdout

    if (TRANS_TEMPLATE.exists() and
            template_is_equal(TRANS_TEMPLATE, template)):
        # No new strings were discovered
        return False

    with open(TRANS_TEMPLATE, 'w') as f:
        f.write(template)
    return True


def update_translation_files() -> None:
    for file in TRANS_DIR.glob('*.po'):
        subprocess.run(['msgmerge',
                        '-U',
                        '--sort-output',
                        str(file),
                        TRANS_TEMPLATE],
                       cwd=REPO_DIR,
                       check=True)


def build_translations() -> None:
    for po_file in TRANS_DIR.glob('*.po'):
        lang = po_file.stem
        po_file = TRANS_DIR / f'{lang}.po'
        mo_file = BUILD_DIR / f'{po_file.stem}.mo'

        subprocess.run(['msgfmt',
                        str(po_file),
                        '-o',
                        str(mo_file)],
                       cwd=REPO_DIR,
                       check=True)


if __name__ == '__main__':

    build = False
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'build':
            build = True
        else:
            exit('Unknown commands found: %s' % sys.argv)

    update_translation_template()
    update_translation_files()
    if build:
        build_translations()
