# Copyright (C) 2018 Philipp Hörist <philipp AT hoerist.com>
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

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from gajim.common import app
from gajim.common.helpers import play_sound_file
from gajim.common.util.status import get_uf_show
from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _
from gi.repository import Gdk, Gtk

if TYPE_CHECKING:
    from ..triggers import Triggers

EVENTS: dict[str, Any] = {
    'message_received': [],
}

RECIPIENT_TYPES = [
    'contact',
    'group',
    'groupchat',
    'all'
]


class ConfigDialog(Gtk.ApplicationWindow):
    def __init__(self, plugin: Triggers, transient: Gtk.Window) -> None:
        Gtk.ApplicationWindow.__init__(self)
        self.set_application(app.app)
        self.set_show_menubar(False)
        self.set_title(_('Triggers Configuration'))
        self.set_transient_for(transient)
        self.set_default_size(600, 800)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_modal(True)
        self.set_destroy_with_parent(True)

        ui_path = Path(__file__).parent
        self._ui = get_builder(str(ui_path.resolve() / 'config.ui'))

        self._plugin = plugin

        self.add(self._ui.box)
        self.show_all()

        self._active_num = -1
        self._config: dict[int, Any] = {}

        self._initialize()

        self._ui.connect_signals(self)
        self.connect('destroy', self._on_destroy)

    def _on_destroy(self, *args: Any) -> None:
        for num in list(self._plugin.config.keys()):
            del self._plugin.config[num]
        for num in self._config:
            self._plugin.config[str(num)] = self._config[num]

    def _initialize(self) -> None:
        # Fill window
        widgets = [
            'conditions_treeview',
            'config_box',
            'event_combobox',
            'recipient_type_combobox',
            'recipient_list_entry',
            'delete_button',
            'online_cb',
            'away_cb',
            'xa_cb',
            'dnd_cb',
            'use_sound_cb',
            'disable_sound_cb',
            'use_popup_cb',
            'disable_popup_cb',
            'tab_opened_cb',
            'not_tab_opened_cb',
            'has_focus_cb',
            'not_has_focus_cb',
            'filechooser',
            'sound_file_box',
            'up_button',
            'down_button',
            'run_command_cb',
            'command_entry',
            'one_shot_cb'
        ]
        for widget in widgets:
            self._ui.__dict__[widget] = self._ui.get_object(widget)

        self._config = {}
        for num in self._plugin.config.keys():
            self._config[int(num)] = self._plugin.config[num]

        if not self._ui.conditions_treeview.get_column(0):
            # Window never opened
            model = Gtk.ListStore(int, str)
            model.set_sort_column_id(0, Gtk.SortType.ASCENDING)
            self._ui.conditions_treeview.set_model(model)

            # '#' Means number
            col = Gtk.TreeViewColumn(_('#'))
            self._ui.conditions_treeview.append_column(col)
            renderer = Gtk.CellRendererText()
            col.pack_start(renderer, expand=False)
            col.add_attribute(renderer, 'text', 0)

            col = Gtk.TreeViewColumn(_('Condition'))
            self._ui.conditions_treeview.append_column(col)
            renderer = Gtk.CellRendererText()
            col.pack_start(renderer, expand=True)
            col.add_attribute(renderer, 'text', 1)
        else:
            model = self._ui.conditions_treeview.get_model()

        model.clear()

        # Fill conditions_treeview
        num = 0
        while num in self._config:
            iter_ = model.append((num, ''))
            path = model.get_path(iter_)
            self._ui.conditions_treeview.set_cursor(path)
            self._active_num = num
            self._initiate_rule_state()
            self._set_treeview_string()
            num += 1

        # No rule selected at init time
        self._ui.conditions_treeview.get_selection().unselect_all()
        self._active_num = -1
        self._ui.config_box.set_sensitive(False)
        self._ui.delete_button.set_sensitive(False)
        self._ui.down_button.set_sensitive(False)
        self._ui.up_button.set_sensitive(False)

        filter_ = Gtk.FileFilter()
        filter_.set_name(_('All Files'))
        filter_.add_pattern('*')
        self._ui.filechooser.add_filter(filter_)

        filter_ = Gtk.FileFilter()
        filter_.set_name(_('Wav Sounds'))
        filter_.add_pattern('*.wav')
        self._ui.filechooser.add_filter(filter_)
        self._ui.filechooser.set_filter(filter_)

    def _initiate_rule_state(self) -> None:
        """
        Set values for all widgets
        """
        if self._active_num < 0:
            return

        # event
        value = self._config[self._active_num]['event']
        legacy_values = [
            'contact_connected',
            'contact_disconnected',
            'contact_status_change']
        if value and value not in legacy_values:
            self._ui.event_combobox.set_active(
                list(EVENTS.keys()).index(value))
        else:
            self._ui.event_combobox.set_active(-1)

        # recipient_type
        value = self._config[self._active_num]['recipient_type']
        if value:
            self._ui.recipient_type_combobox.set_active(
                RECIPIENT_TYPES.index(value))
        else:
            self._ui.recipient_type_combobox.set_active(-1)

        # recipient
        value = self._config[self._active_num]['recipients']
        if not value:
            value = ''
        self._ui.recipient_list_entry.set_text(value)

        # status
        value = self._config[self._active_num]['status']
        if value == 'all':
            self._ui.all_status_rb.set_active(True)
        else:
            self._ui.special_status_rb.set_active(True)
            values = value.split()
            for val in ('online', 'away', 'xa', 'dnd'):
                if val in values:
                    self._ui.__dict__[val + '_cb'].set_active(True)
                else:
                    self._ui.__dict__[val + '_cb'].set_active(False)

        self._on_status_radiobutton_toggled(self._ui.all_status_rb)

        # tab_opened
        value = self._config[self._active_num]['tab_opened']
        self._ui.tab_opened_cb.set_active(True)
        self._ui.not_tab_opened_cb.set_active(True)
        if value == 'no':
            self._ui.tab_opened_cb.set_active(False)
        elif value == 'yes':
            self._ui.not_tab_opened_cb.set_active(False)

        # has_focus
        if 'has_focus' not in self._config[self._active_num]:
            self._config[self._active_num]['has_focus'] = 'both'
        value = self._config[self._active_num]['has_focus']
        self._ui.has_focus_cb.set_active(True)
        self._ui.not_has_focus_cb.set_active(True)
        if value == 'no':
            self._ui.has_focus_cb.set_active(False)
        elif value == 'yes':
            self._ui.not_has_focus_cb.set_active(False)

        # sound_file
        value = self._config[self._active_num]['sound_file']
        if value is None:
            self._ui.filechooser.unselect_all()
        else:
            self._ui.filechooser.set_filename(value)

        # sound, popup, auto_open, systray, roster
        for option in ('sound', 'popup'):
            value = self._config[self._active_num][option]
            if value == 'yes':
                self._ui.__dict__['use_' + option + '_cb'].set_active(True)
            else:
                self._ui.__dict__['use_' + option + '_cb'].set_active(False)
            if value == 'no':
                self._ui.__dict__['disable_' + option + '_cb'].set_active(True)
            else:
                self._ui.__dict__['disable_' + option + '_cb'].set_active(False)

        # run_command
        value = self._config[self._active_num]['run_command']
        self._ui.run_command_cb.set_active(value)

        # command
        value = self._config[self._active_num]['command']
        self._ui.command_entry.set_text(value)

        # one shot
        if 'one_shot' in self._config[self._active_num]:
            value = self._config[self._active_num]['one_shot']
        else:
            value = False
        self._ui.one_shot_cb.set_active(value)

    def _set_treeview_string(self) -> None:
        selection = self._ui.conditions_treeview.get_selection()
        (model, iter_) = selection.get_selected()
        if not iter_:
            return
        ind = self._ui.event_combobox.get_active()
        event = ''
        if ind > -1:
            event = self._ui.event_combobox.get_model()[ind][0]
        ind = self._ui.recipient_type_combobox.get_active()
        recipient_type = ''
        if ind > -1:
            recipient_type_model = self._ui.recipient_type_combobox.get_model()
            recipient_type = recipient_type_model[ind][0]
        recipient = ''
        if recipient_type != 'everybody':
            recipient = self._ui.recipient_list_entry.get_text()
        if self._ui.all_status_rb.get_active():
            status = ''
        else:
            status = _('and I am ')
            for st in ('online', 'away', 'xa', 'dnd'):
                if self._ui.__dict__[st + '_cb'].get_active():
                    status += get_uf_show(st) + ' '
        model[iter_][1] = _('%(event)s (%(recipient_type)s) %(recipient)s '
                            '%(status)s') % {
                                'event': event,
                                'recipient_type': recipient_type,
                                'recipient': recipient,
                                'status': status}

    def _on_conditions_treeview_cursor_changed(self,
                                               widget: Gtk.TreeView
                                               ) -> None:

        (model, iter_) = widget.get_selection().get_selected()
        if not iter_:
            self._active_num = -1
            return
        self._active_num = model[iter_][0]
        if self._active_num == 0:
            self._ui.up_button.set_sensitive(False)
        else:
            self._ui.up_button.set_sensitive(True)
        model = widget.get_model()
        assert model is not None
        _max = model.iter_n_children(None)
        if self._active_num == _max - 1:
            self._ui.down_button.set_sensitive(False)
        else:
            self._ui.down_button.set_sensitive(True)
        self._initiate_rule_state()
        self._ui.config_box.set_sensitive(True)
        self._ui.delete_button.set_sensitive(True)

    def _on_new_button_clicked(self, _button: Gtk.Button) -> None:
        model = self._ui.conditions_treeview.get_model()
        num = self._ui.conditions_treeview.get_model().iter_n_children(None)
        self._config[num] = {
            'event': 'message_received',
            'recipient_type': 'all',
            'recipients': '',
            'status': 'all',
            'tab_opened': 'both',
            'has_focus': 'both',
            'sound': '',
            'sound_file': '',
            'popup': '',
            'run_command': False,
            'command': '',
            'one_shot': False,
        }
        iter_ = model.append((num, ''))
        path = model.get_path(iter_)
        self._ui.conditions_treeview.set_cursor(path)
        self._active_num = num
        self._set_treeview_string()
        self._ui.config_box.set_sensitive(True)

    def _on_delete_button_clicked(self, button: Gtk.Button) -> None:
        selection = self._ui.conditions_treeview.get_selection()
        (model, iter_) = selection.get_selected()
        if not iter_:
            return
        # up all others
        iter2 = model.iter_next(iter_)
        num = self._active_num
        while iter2:
            num = model[iter2][0]
            model[iter2][0] = num - 1
            self._config[num - 1] = self._config[num].copy()
            iter2 = model.iter_next(iter2)
        model.remove(iter_)
        del self._config[num]
        self._active_num = -1
        button.set_sensitive(False)
        self._ui.up_button.set_sensitive(False)
        self._ui.down_button.set_sensitive(False)
        self._ui.config_box.set_sensitive(False)

    def _on_up_button_clicked(self, _button: Gtk.Button) -> None:
        selection = self._ui.conditions_treeview.get_selection()
        (model, iter_) = selection.get_selected()
        if not iter_:
            return
        conf = self._config[self._active_num].copy()
        self._config[self._active_num] = self._config[self._active_num - 1]
        self._config[self._active_num - 1] = conf

        model[iter_][0] = self._active_num - 1
        # get previous iter
        path = model.get_path(iter_)
        iter_ = model.get_iter((path[0] - 1,))
        model[iter_][0] = self._active_num
        self._on_conditions_treeview_cursor_changed(
            self._ui.conditions_treeview)

    def _on_down_button_clicked(self, _button: Gtk.Button) -> None:
        selection = self._ui.conditions_treeview.get_selection()
        (model, iter_) = selection.get_selected()
        if not iter_:
            return
        conf = self._config[self._active_num].copy()
        self._config[self._active_num] = self._config[self._active_num + 1]
        self._config[self._active_num + 1] = conf

        model[iter_][0] = self._active_num + 1
        iter_ = model.iter_next(iter_)
        model[iter_][0] = self._active_num
        self._on_conditions_treeview_cursor_changed(
            self._ui.conditions_treeview)

    def _on_event_combobox_changed(self, combo: Gtk.ComboBox) -> None:
        if self._active_num < 0:
            return
        active = combo.get_active()
        if active == -1:
            return
        event = list(EVENTS.keys())[active]
        self._config[self._active_num]['event'] = event
        for widget in EVENTS[event]:
            self._ui.__dict__[widget].set_sensitive(False)
            self._ui.__dict__[widget].set_state(False)
        self._set_treeview_string()

    def _on_recipient_type_combobox_changed(self,
                                            widget: Gtk.ComboBox
                                            ) -> None:

        if self._active_num < 0:
            return
        recipient_type = RECIPIENT_TYPES[widget.get_active()]
        self._config[self._active_num]['recipient_type'] = recipient_type
        if recipient_type == 'all':
            self._ui.recipient_list_entry.set_sensitive(False)
        else:
            self._ui.recipient_list_entry.set_sensitive(True)
        self._set_treeview_string()

    def _on_recipient_list_entry_changed(self, widget: Gtk.Entry) -> None:
        if self._active_num < 0:
            return
        recipients = widget.get_text()
        # TODO: do some check
        self._config[self._active_num]['recipients'] = recipients
        self._set_treeview_string()

    def _set_status_config(self) -> None:
        if self._active_num < 0:
            return
        status = ''
        for st in ('online', 'away', 'xa', 'dnd'):
            if self._ui.__dict__[st + '_cb'].get_active():
                status += st + ' '
        if status:
            status = status[:-1]
        self._config[self._active_num]['status'] = status
        self._set_treeview_string()

    def _on_status_radiobutton_toggled(self, _widget: Gtk.RadioButton) -> None:
        if self._active_num < 0:
            return
        if self._ui.all_status_rb.get_active():
            self._ui.status_expander.set_expanded(False)
            self._config[self._active_num]['status'] = 'all'
            # 'All status' clicked
            for st in ('online', 'away', 'xa', 'dnd'):
                self._ui.__dict__[st + '_cb'].set_sensitive(False)
        else:
            self._ui.status_expander.set_expanded(True)
            self._set_status_config()
            # 'special status' clicked
            for st in ('online', 'away', 'xa', 'dnd'):
                self._ui.__dict__[st + '_cb'].set_sensitive(True)

        self._set_treeview_string()

    def _on_status_cb_toggled(self, _widget: Gtk.CheckButton) -> None:
        if self._active_num < 0:
            return
        self._set_status_config()

    # tab_opened OR (not xor) not_tab_opened must be active
    def _on_tab_opened_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        if self._active_num < 0:
            return
        if widget.get_active():
            self._ui.has_focus_cb.set_sensitive(True)
            self._ui.not_has_focus_cb.set_sensitive(True)
            if self._ui.not_tab_opened_cb.get_active():
                self._config[self._active_num]['tab_opened'] = 'both'
            else:
                self._config[self._active_num]['tab_opened'] = 'yes'
        else:
            self._ui.has_focus_cb.set_sensitive(False)
            self._ui.not_has_focus_cb.set_sensitive(False)
            self._ui.not_tab_opened_cb.set_active(True)
            self._config[self._active_num]['tab_opened'] = 'no'

    def _on_not_tab_opened_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        if self._active_num < 0:
            return
        if widget.get_active():
            if self._ui.tab_opened_cb.get_active():
                self._config[self._active_num]['tab_opened'] = 'both'
            else:
                self._config[self._active_num]['tab_opened'] = 'no'
        else:
            self._ui.tab_opened_cb.set_active(True)
            self._config[self._active_num]['tab_opened'] = 'yes'

    # has_focus OR (not xor) not_has_focus must be active
    def _on_has_focus_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        if self._active_num < 0:
            return
        if widget.get_active():
            if self._ui.not_has_focus_cb.get_active():
                self._config[self._active_num]['has_focus'] = 'both'
            else:
                self._config[self._active_num]['has_focus'] = 'yes'
        else:
            self._ui.not_has_focus_cb.set_active(True)
            self._config[self._active_num]['has_focus'] = 'no'

    def _on_not_has_focus_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        if self._active_num < 0:
            return
        if widget.get_active():
            if self._ui.has_focus_cb.get_active():
                self._config[self._active_num]['has_focus'] = 'both'
            else:
                self._config[self._active_num]['has_focus'] = 'no'
        else:
            self._ui.has_focus_cb.set_active(True)
            self._config[self._active_num]['has_focus'] = 'yes'

    def _on_use_it_toggled(self,
                           widget: Gtk.CheckButton,
                           opposite_widget: Gtk.CheckButton,
                           option: str
                           ) -> None:

        if widget.get_active():
            if opposite_widget.get_active():
                opposite_widget.set_active(False)
            self._config[self._active_num][option] = 'yes'
        elif opposite_widget.get_active():
            self._config[self._active_num][option] = 'no'
        else:
            self._config[self._active_num][option] = ''

    def _on_disable_it_toggled(self,
                               widget: Gtk.CheckButton,
                               opposite_widget: Gtk.CheckButton,
                               option: str
                               ) -> None:

        if widget.get_active():
            if opposite_widget.get_active():
                opposite_widget.set_active(False)
            self._config[self._active_num][option] = 'no'
        elif opposite_widget.get_active():
            self._config[self._active_num][option] = 'yes'
        else:
            self._config[self._active_num][option] = ''

    def _on_use_sound_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        self._on_use_it_toggled(widget, self._ui.disable_sound_cb, 'sound')
        if widget.get_active():
            self._ui.sound_file_box.set_sensitive(True)
        else:
            self._ui.sound_file_box.set_sensitive(False)

    def _on_sound_file_set(self, widget: Gtk.FileChooserButton) -> None:
        self._config[self._active_num]['sound_file'] = widget.get_filename()

    def _on_play_button_clicked(self, _button: Gtk.Button) -> None:
        play_sound_file(self._ui.filechooser.get_filename())

    def _on_disable_sound_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        self._on_disable_it_toggled(widget, self._ui.use_sound_cb, 'sound')

    def _on_use_popup_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        self._on_use_it_toggled(widget, self._ui.disable_popup_cb, 'popup')

    def _on_disable_popup_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        self._on_disable_it_toggled(widget, self._ui.use_popup_cb, 'popup')

    def _on_run_command_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        self._config[self._active_num]['run_command'] = widget.get_active()
        if widget.get_active():
            self._ui.command_entry.set_sensitive(True)
        else:
            self._ui.command_entry.set_sensitive(False)

    def _on_command_entry_changed(self, widget: Gtk.Entry) -> None:
        self._config[self._active_num]['command'] = widget.get_text()

    def _on_one_shot_cb_toggled(self, widget: Gtk.CheckButton) -> None:
        self._config[self._active_num]['one_shot'] = widget.get_active()
        self._ui.command_entry.set_sensitive(widget.get_active())
