# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of Form Handler.
#
# Form Handler is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Form Handler is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Form Handler. If not, see <http://www.gnu.org/licenses/>.

import logging

import nbxmpp

from gajim.common import ged
from gajim.common.modules.dataforms import extend_form

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from form_handler.gtk.util import get_button
from form_handler.gtk.form import FormDialog

log = logging.getLogger('gajim.p.form_handler')


class FormHandlerPlugin(GajimPlugin):
    def init(self):

        self.config_dialog = None

        self.events_handlers = {
            'decrypted-message-received': (ged.CORE,
                                           self._on_message_received),
        }

        self.gui_extension_points = {
            'print_real_text': (self._print_text, None),
        }

    def _on_message_received(self, event):
        form = event.stanza.getTag('x', namespace=nbxmpp.NS_DATA)
        if form is None:
            return

        if form.getAttr('type') != 'form':
            return

        data = self._parse_form(form)

        data['form'] = str(form)
        data['jid'] = event.jid

        event.additional_data['form_handler'] = data

    @staticmethod
    def _parse_form(form):
        dataform = extend_form(node=form)
        result = {}
        try:
            result['submit-text'] = dataform['submit-button-text'].value
        except KeyError:
            result['submit-text'] = _('Submit')

        try:
            result['open-text'] = dataform['open-button-text'].value
        except KeyError:
            result['open-text'] = _('Open')

        return result

    def _print_text(self, tv, _real_text, _text_tags, _graphics,
                    iter_, additional_data):
        if 'form_handler' not in additional_data:
            return

        data = additional_data['form_handler']
        data['account'] = tv.account

        button = get_button(data['open-text'], data, self._show_form)

        buffer_ = tv.tv.get_buffer()
        anchor = buffer_.create_child_anchor(iter_)
        anchor.plaintext = ''

        button.show_all()
        tv.tv.add_child_at_anchor(button, anchor)

    @staticmethod
    def _show_form(_button, data):
        FormDialog(data)
