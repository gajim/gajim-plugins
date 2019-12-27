from functools import partial

from gajim.plugins import GajimPlugin
from gajim.plugins.plugins_i18n import _
from message_box_size.config_dialog import MessageBoxSizeConfigDialog


class MsgBoxSizePlugin(GajimPlugin):
    def init(self):
        # pylint: disable=attribute-defined-outside-init
        self.description = _('Allows you to adjust the height'
                             ' of the message input.')
        self.config_dialog = partial(MessageBoxSizeConfigDialog, self)
        self.gui_extension_points = {
            'chat_control_base': (self._on_connect_chat_control,
                                  self._on_disconnect_chat_control)
        }
        self.config_default_values = {'HEIGHT': (20, ''),}

    def _on_connect_chat_control(self, control):
        control.msg_textview.set_size_request(-1, self.config['HEIGHT'])

    @staticmethod
    def _on_disconnect_chat_control(control):
        control.msg_textview.set_size_request(-1, -1)
