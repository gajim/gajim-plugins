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
import os
from subprocess import Popen
from subprocess import PIPE

from gajim.plugins.plugins_i18n import _

log = logging.getLogger('gajim.p.latex')

BLACKLIST = [
    '\def',
    '\\let',
    '\\futurelet',
    '\\newcommand',
    '\\renewcomment',
    '\\else',
    '\\fi',
    '\\write',
    '\\input',
    '\\include',
    '\\chardef',
    '\\catcode',
    '\\makeatletter',
    '\\noexpand',
    '\\toksdef',
    '\\every',
    '\\errhelp',
    '\\errorstopmode',
    '\\scrollmode',
    '\\nonstopmode',
    '\\batchmode',
    '\\read',
    '\\csname',
    '\\newhelp',
    '\\relax',
    '\\afterground',
    '\\afterassignment',
    '\\expandafter',
    '\\noexpand',
    '\\special',
    '\\command',
    '\\loop',
    '\\repeat',
    '\\toks',
    '\\output',
    '\\line',
    '\\mathcode',
    '\\name',
    '\\item',
    '\\section',
    '\\mbox',
    '\\DeclareRobustCommand',
    '\\[',
    '\\]',
]


def try_run(argv, directory):
    try:
        proc = popen_nt_friendly(argv, directory)
        out = proc.communicate()[0]
        log.info(out)
        return proc.wait()
    except Exception as err:
        return _('Error executing "%(command)s": %(error)s') % {
            'command': " ".join(argv),
            'error': str(err)}


def popen_nt_friendly(command, directory):
    if os.name == 'nt':
        # CREATE_NO_WINDOW
        return Popen(command, creationflags=0x08000000, cwd=directory,
                     stdout=PIPE)
    return Popen(command, cwd=directory, stdout=PIPE)


def write_latex(filename, string):
    texstr = _get_latex_template(string)

    file_ = open(filename, 'w+')
    file_.write(texstr)
    file_.flush()
    file_.close()


def _get_latex_template(code):
    template = '''
        \\documentclass[12pt]{article}
        \\usepackage[dvips]{graphicx}
        \\usepackage{amsmath}
        \\usepackage{amssymb}
        \\pagestyle{empty}
        \\begin{document}
        \\begin{large}
        \\begin{gather*}
        %s
        \\end{gather*}
        \\end{large}
        \\end{document}''' % (code)
    return template
