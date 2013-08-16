# -*- coding: utf-8 -*-

import gtk
from common import helpers
from common import gajim

from plugins import GajimPlugin
from plugins.helpers import log_calls, log


class WrongLayoutPlugin(GajimPlugin):
    @log_calls('WrongLayoutPlugin')
    def init(self):
        self.config_dialog = None
        self.gui_extension_points = {
                'chat_control_base': (self.connect_with_chat_control,
                                       self.disconnect_from_chat_control)}
        self.chat_control = None
        self.controls = []
        self.dict_eng = {'`': 'ё', 'q': 'й', 'w': 'ц', 'e': 'у', 'r': 'к',
                't': 'е',
                'y': 'н', 'u': 'г', 'i': 'ш', 'o': 'щ', 'p': 'з', '[': 'х',
                ']': 'ъ', 'a': 'ф', 's': 'ы', 'd': 'в', 'f': 'а', 'g': 'п',
                'h': 'р', 'j': 'о', 'k': 'л', 'l': 'д', ';': 'ж', '\'': 'э',
                'z': 'я', 'x': 'ч', 'c': 'с', 'v': 'м', 'b': 'и', 'n': 'т',
                'm': 'ь', ',': 'б', '.': 'ю', '/': '.',
                '\\': '\\', '~': 'Ё', '@': '"', '$': ';', '^': ':', '&': '?',
                'Q': 'Й', 'W': 'Ц', 'E': 'У', 'R': 'К', 'T': 'Е', 'Y': 'Н',
                'U': 'Г', 'I': 'Ш', 'O': 'Щ', 'P': 'З', '{': 'Х', '}': 'Ъ',
                '|': '/', 'A': 'Ф', 'S': 'Ы', 'D': 'В', 'F': 'А', 'G': 'П',
                'H': 'Р', 'J': 'О', 'K': 'Л', 'L': 'Д', '"': 'Э', 'Z': 'Я',
                'X': 'Ч', 'C': 'С', 'V': 'М', 'B': 'И', 'N': 'Т', 'M': 'Ь',
                '<': 'Б', '>': 'Ю', '?': ',', ':': 'Ж'}
        self.dict_ru = {}
        for key in self.dict_eng.keys():
            self.dict_ru[self.dict_eng[key]] = key

    @log_calls('WrongLayoutPlugin')
    def activate(self):
        pass

    @log_calls('WrongLayoutPlugin')
    def deactivate(self):
        pass

    @log_calls('WrongLayoutPlugin')
    def connect_with_chat_control(self, chat_control):
        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)

    @log_calls('WrongLayoutPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview

        self.id_ = self.chat_control.msg_textview.connect('key_press_event',
                                                        self.mykeypress_event)
        self.chat_control.handlers[self.id_] = self.chat_control.msg_textview

    def disconnect_from_chat_control(self):
        if self.chat_control.msg_textview.handler_is_connected(self.id_):
            self.chat_control.msg_textview.disconnect(self.id_)

    def mykeypress_event(self, widget, event):
        if event.keyval == gtk.keysyms.r or event.keyval == 1739:
            if event.state & gtk.gdk.MOD1_MASK:  # alt+r
                start, end, iter_ = self.get_start_end()
                count_eng = count_rus = 0
                c = iter_.get_char().decode('utf-8')
                while ((c != 0) & iter_.in_range(start, end)):
                    if ((ord(c) > 65) & (ord(c) < 122)) | \
                        (c == '@') | (c == '#') | (c == '$') | (c == '^') | \
                        (c == '&') | (c == '|') | (c == '~') | \
                        (c == '{') | (c == '}') | (c == '[') | (c == ']') | \
                        (c == '<') | (c == '>'):
                        count_eng += 1
                    if ((ord(c) > 1040) & (ord(c) < 1103)) | (c == 'ё') | \
                        (c == 'Ё') | (c == '№'):
                        count_rus += 1
                    iter_.forward_char()
                    c = iter_.get_char().decode('utf-8')
                is_russian = (count_rus >= count_eng)
                start, end, iter_ = self.get_start_end()
                c = iter_.get_char().decode('utf-8')
                text = ''
                while ((c != 0) & iter_.in_range(start, end)):
                    if not is_russian:
                        conv = self.plugin.dict_eng.get(c, c)
                    else:
                        conv = self.plugin.dict_ru.get(c.encode('utf-8'), c)
                    text = text + conv
                    iter_.forward_char()
                    c = iter_.get_char().decode('utf-8')
                start, end, iter_ = self.get_start_end()
                message_buffer = self.chat_control.msg_textview.get_buffer()
                message_buffer.delete(start, end)
                message_buffer.insert_at_cursor(text)
                self.chat_control.msg_textview.grab_focus()
                return True

    def get_start_end(self):
        message_buffer = self.chat_control.msg_textview.get_buffer()
        sel = message_buffer.get_selection_bounds()
        if sel != ():
            start, end = sel
        else:
            start = message_buffer.get_start_iter()
            end = message_buffer.get_end_iter()
            stext = gajim.config.get('gc_refer_to_nick_char')
            res = start.forward_search(stext, gtk.TEXT_SEARCH_TEXT_ONLY)
            if res:
                first, start = res
        start.order(end)
        iter_ = start
        return start, end, iter_
