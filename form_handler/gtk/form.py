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

import nbxmpp
from nbxmpp.modules.dataforms import extend_form

from gi.repository import Gtk

from gajim.common import app
from gajim.common.connection_handlers_events import MessageOutgoingEvent

from gajim.gtk.dataform import DataFormWidget

from form_handler.gtk.util import find_control


class FormDialog(Gtk.ApplicationWindow):
    def __init__(self, data):
        transient = app.app.get_active_window()
        Gtk.ApplicationWindow.__init__(self, title="Data Form Test")
        self.set_transient_for(transient)
        self.set_default_size(600, 400)

        self._account = data['account']
        self._jid = data['jid']

        self._form_widget = DataFormWidget(
            extend_form(node=nbxmpp.Node(node=data['form'])))
        box = Gtk.Box(orientation='vertical', spacing=12)
        box.add(self._form_widget)

        button = Gtk.Button(label=data['submit-text'])
        button.connect('clicked', self._on_send_clicked)
        button.set_halign(Gtk.Align.END)
        box.add(button)

        self.add(box)
        self.show_all()

    def _on_send_clicked(self, _button):
        form = self._form_widget.get_submit_form()
        app.nec.push_outgoing_event(MessageOutgoingEvent(None,
                                                         account=self._account,
                                                         jid=self._jid,
                                                         form_node=form,
                                                         is_loggable=False))
        control = find_control(self._account, self._jid)
        if control is None:
            return
        control.print_conversation('Form has successfully been sent', 'info')
        self.destroy()
