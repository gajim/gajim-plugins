# -*- coding: utf-8 -*-

from gi.repository import Gtk
from gi.repository import Gdk

from gajim.common import app
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls


class ClickableNicknames(GajimPlugin):

    @log_calls('ClickableNicknamesPlugin')
    def init(self):
        self.description = _('Clickable nicknames '
            'in the conversation textview.')
        self.config_dialog = None  # ClickableNicknamesPluginConfigDialog(self)
        self.gui_extension_points = {
                'chat_control_base': (self.connect_with_chat_control,
                                       self.disconnect_from_chat_control)}

        self.is_active = None
        self.gc_controls = {}

        self.tag_names = []
        colors = app.config.get('gc_nicknames_colors')
        colors = colors.split(':')
        for i, color in enumerate(colors):
            tagname = 'gc_nickname_color_' + str(i)
            self.tag_names.append(tagname)

    @log_calls('ClickableNicknamesPlugin')
    def activate(self):
        for gc_control in app.interface.msg_win_mgr.get_controls('gc'):
            # TODO support minimized groupchat
            if gc_control not in self.gc_controls.keys():
                control = Base(self, gc_control)
                self.gc_controls[gc_control] = control
            else:
                self.gc_controls[gc_control].connect_signals()
        self.is_active = True

    @log_calls('ClickableNicknamesPlugin')
    def deactivate(self):
        for control in self.gc_controls.keys():
            self.gc_controls[control].disconnect_from_chat_control()
        self.gc_controls.clear()
        self.is_active = None

    @log_calls('ClickableNicknamesPlugin')
    def connect_with_chat_control(self, chat_control):
        if chat_control.widget_name != 'groupchat_control':
            return
        if self.is_active:
            control = Base(self, chat_control)
            self.gc_controls[chat_control] = control

    @log_calls('ClickableNicknamesPlugin')
    def disconnect_from_chat_control(self, chat_control):
        pass


class Base(object):

    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview
        self.tags_id = []
        self.change_cursor = False
        self.connect_signals()

    def connect_signals(self):
        # connect signals with textbuffer tags
        self.tag_names = self.plugin.tag_names
        tag_table = self.textview.tv.get_buffer().get_tag_table()
        for name in self.tag_names:
            tag = tag_table.lookup(name)
            if tag:
                id_ = tag.connect('event', self.insert_nick, name)
                self.chat_control.handlers[id_] = tag
                self.tags_id.append((id_, tag))

        self.id_ = self.textview.tv.connect('motion_notify_event',
                self.on_textview_motion_notify_event)
        self.chat_control.handlers[self.id_] = self.textview.tv

    def on_textview_motion_notify_event(self, widget, event):
        # change cursor on the nicks
        pointer_x, pointer_y = self.textview.tv.get_window(
            Gtk.TextWindowType.TEXT).get_pointer()[1:3]
        x, y = self.textview.tv.window_to_buffer_coords(Gtk.TextWindowType.TEXT,
            pointer_x, pointer_y)
        tags = self.textview.tv.get_iter_at_location(x, y)[1].get_tags()
        tag_table = self.textview.tv.get_buffer().get_tag_table()
        if self.change_cursor:
            self.textview.tv.get_window(Gtk.TextWindowType.TEXT).set_cursor(
                    Gdk.Cursor.new(Gdk.CursorType.XTERM))
            self.change_cursor = False
        for tag in tags:
            if tag in [x[1] for x in self.tags_id]:
                self.textview.tv.get_window(Gtk.TextWindowType.TEXT).set_cursor(
                    Gdk.Cursor.new(Gdk.CursorType.HAND2))
            self.change_cursor = True

    def insert_nick(self, texttag, widget, event, iter_, kind):
        # insert nickname to message buffer
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button.button == 1:
            # left mouse button clicked
            begin_iter = iter_.copy()
            # we get the begining of the tag
            while not begin_iter.begins_tag(texttag):
                begin_iter.backward_char()
            end_iter = iter_.copy()
            # we get the end of the tag
            while not end_iter.ends_tag(texttag):
                end_iter.forward_char()
            buffer_ = self.textview.tv.get_buffer()
            word = buffer_.get_text(begin_iter, end_iter, True)
            nick = word.rstrip().rstrip(app.config.get('after_nickname'))
            if nick.startswith('* '):
                nick = nick.lstrip('* ').split(' ')[0] + ' '
            nick = nick.lstrip(app.config.get('before_nickname'))
            nicks = app.contacts.get_nick_list(self.chat_control.account,
                self.chat_control.room_jid)
            if nick[:-1] not in nicks:
                return

            message_buffer = self.chat_control.msg_textview.get_buffer()
            # delete PLACEHOLDER
            start, end = message_buffer.get_bounds()
            placeholder = self.chat_control.msg_textview.PLACEHOLDER
            text = message_buffer.get_text(start, end, False)
            if text == placeholder or len(text) == 0:
                message_buffer.set_text('', -1)
                nick = nick + app.config.get('gc_refer_to_nick_char')
            elif len(text) > 0 and text[-1] != ' ':
                nick = ' ' + nick
            nick += ' '
            message_buffer.insert_at_cursor(nick)
            self.chat_control.msg_textview.grab_focus()

    def disconnect_from_chat_control(self):
        # disconnect signals from textbuffer tags
        for item in self.tags_id:
            if item[1].handler_is_connected(item[0]):
                item[1].disconnect(item[0])
        if self.textview.tv.handler_is_connected(self.id_):
            self.textview.tv.disconnect(self.id_)
