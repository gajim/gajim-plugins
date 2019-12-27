from gi.repository import Gtk
from gi.repository import Gdk

from gajim.common import app

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _

from gajim.gtk.util import get_cursor


class ClickableNicknames(GajimPlugin):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        self.description = _('Clickable nicknames '
                             'in the conversation textview.')
        self.config_dialog = None
        self.gui_extension_points = {
            'chat_control_base': (self._on_connect_chat_control,
                                  self._on_disconnect_chat_control)}

        self._pointer_active = {}
        self._event_ids = {}

    def _on_connect_chat_control(self, control):
        if not control.type.is_groupchat:
            return

        textview = control.conv_textview.tv
        nickname_tag = self._get_nickname_tag(textview)

        tag_table = textview.get_buffer().get_tag_table()
        tag = tag_table.lookup('nickname')
        event_id = tag.connect('event',
                               self._on_nickname_clicked,
                               control.msg_textview)

        motion_id = textview.connect('motion-notify-event',
                                     self._on_textview_motion_notify,
                                     nickname_tag)

        self._event_ids[control.control_id] = (event_id, motion_id)

    def _on_disconnect_chat_control(self, control):
        if not control.type.is_groupchat:
            return

        textview = control.conv_textview.tv
        nickname_tag = self._get_nickname_tag(textview)

        event_id, motion_id = self._event_ids.pop(control.control_id)
        textview.disconnect(motion_id)
        nickname_tag.disconnect(event_id)
        self._pointer_active.pop(id(textview), None)

    @staticmethod
    def _get_nickname_tag(textview):
        tag_table = textview.get_buffer().get_tag_table()
        return tag_table.lookup('nickname')

    def _is_pointer_active(self, textview):
        return self._pointer_active.get(id(textview), False)

    def _set_pointer_state(self, textview, state):
        self._pointer_active[id(textview)] = state

    def _on_textview_motion_notify(self, textview, event, nickname_tag):
        window = textview.get_window(Gtk.TextWindowType.TEXT)
        x_pos, y_pos = textview.window_to_buffer_coords(Gtk.TextWindowType.TEXT,
                                                        event.x,
                                                        event.y)

        iter_ = textview.get_iter_at_position(x_pos, y_pos)[1]
        if iter_.has_tag(nickname_tag):
            window.set_cursor(get_cursor('pointer'))
            self._set_pointer_state(textview, True)

        elif self._is_pointer_active(textview):
            window.set_cursor(get_cursor('default'))
            self._set_pointer_state(textview, False)

    @staticmethod
    def _on_nickname_clicked(text_tag, textview, event, iter_, message_input):
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return
        if event.button.button != 1:
            return

        start = iter_.copy()
        end = iter_.copy()

        start.backward_to_tag_toggle(text_tag)
        end.forward_to_tag_toggle(text_tag)

        nickname = textview.get_buffer().get_text(start, end, False)

        # Remove Space
        nickname = nickname[:-1]
        nickname = nickname.rstrip(app.config.get('after_nickname'))
        # Remove direction mark
        nickname = nickname[:-1]
        nickname = nickname.lstrip(app.config.get('before_nickname'))

        message_input.grab_focus()
        if not message_input.has_text():
            # There is no text add refer char
            nickname = '%s%s ' % (nickname,
                                  app.config.get('gc_refer_to_nick_char'))
        else:
            input_buffer = message_input.get_buffer()
            start, end = input_buffer.get_bounds()
            text = input_buffer.get_text(start, end, False)
            if text[:-1] != ' ':
                # Add space in front
                nickname = ' %s' % nickname

        message_input.insert_text(nickname)
