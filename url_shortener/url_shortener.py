# -*- coding: utf-8 -*-

import gtk
import json
import urllib
import urllib2
from common import gajim
from common import ged
from plugins import GajimPlugin
from plugins.helpers import log_calls
from plugins.gui import GajimPluginConfigDialog

APIKEY  = 'R_fcba926fc7978bd19acbca73ec82b2be'
USER = 'dicson'

class UrlShortenerPlugin(GajimPlugin):
    @log_calls('UrlShortenerPlugin')
    def init(self):
        self.config_dialog = UrlShortenerPluginConfigDialog(self)
        self.gui_extension_points = {
                'chat_control_base': (self.connect_with_chat_control,
                                       self.disconnect_from_chat_control),
                'print_special_text': (self.print_special_text,
                                       self.print_special_text1),}
        self.config_default_values = {
                'MAX_CHARS': (50, ('MAX_CHARS(30-...)')),
                'IN_MAX_CHARS': (50, ('MAX_CHARS(30-...)')),
                'SHORTEN_OUTGOING': (False, ''),}
        self.events_handlers = {'message-outgoing': (ged.OUT_PRECORE,
                                                    self.handle_outgoing_msg),
                                'gc-message-outgoing': (ged.OUT_PRECORE,
                                                    self.handle_outgoing_msg)}
        self.chat_control = None
        self.controls = []

    def handle_outgoing_msg(self, event):
        if not self.active:
            return
        if not event.message:
            return
        if not self.config['SHORTEN_OUTGOING']:
            return
        if hasattr(event, 'shortened'):
            return

        iterator = gajim.interface.basic_pattern_re.finditer(event.message)
        for match in iterator:
            start, end = match.span()
            link = event.message[start:end]
            if len(link) < self.config['MAX_CHARS']:
                continue
            short_link = None
            try:
                params = urllib.urlencode({'longUrl': link,
                                            'login': USER,
                                            'apiKey': APIKEY,
                                            'format': 'json'})
                req = urllib2.Request('http://api.bit.ly/v3/shorten?%s' % params)
                response = urllib2.urlopen(req)
                j = json.load(response)
                if j['status_code'] == 200:
                    short_link =  j['data']['url']
            except urllib2.HTTPError, e:
                pass
            if short_link:
                event.message = event.message.replace(link, short_link)
        event.callback_args[1] = event.message
        event.shortened = True

    @log_calls('UrlShortenerPlugin')
    def connect_with_chat_control(self, chat_control):
        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)

    @log_calls('UrlShortenerPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []

    def print_special_text(self, tv, special_text, other_tags, graphics=True):
        for control in self.controls:
            if control.chat_control.conv_textview != tv:
                continue
            control.print_special_text(special_text, other_tags, graphics=True)

    def print_special_text1(self, chat_control, special_text, other_tags=None,
        graphics=True):
        for control in self.controls:
            if control.chat_control == chat_control:
                control.disconnect_from_chat_control()
                self.controls.remove(control)


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview

        self.id_ = self.textview.tv.connect('motion_notify_event',
        self.on_textview_motion_notify_event)
        self.chat_control.handlers[self.id_] = self.textview.tv

    def print_special_text(self, special_text, other_tags, graphics=True):
        if not self.plugin.active:
            return
        is_xhtml_link = None
        text_is_valid_uri = False
        buffer_ = self.textview.tv.get_buffer()

        # Detect XHTML-IM link
        ttt = buffer_.get_tag_table()
        tags_ = [(ttt.lookup(t) if isinstance(t, str) else t) for t in other_tags]
        for t in tags_:
            is_xhtml_link = getattr(t, 'href', None)
            if is_xhtml_link:
                break
        # Check if we accept this as an uri
        schemes = gajim.config.get('uri_schemes').split()
        for scheme in schemes:
            if special_text.startswith(scheme):
                text_is_valid_uri = True
        if special_text.startswith('www.') or special_text.startswith('ftp.') \
        or text_is_valid_uri and not is_xhtml_link:
            if len(special_text) < self.plugin.config['IN_MAX_CHARS']:
                return
            end_iter = buffer_.get_end_iter()
            mark = buffer_.create_mark(None, end_iter, True)
            gajim.thread_interface(self.insert_hyperlink, [mark, special_text,
                ttt])
            self.textview.plugin_modified = True

    def insert_hyperlink(self, mark, special_text, ttt):
        try:
            params = urllib.urlencode({'longUrl': special_text,
                                        'login': USER,
                                        'apiKey': APIKEY,
                                        'format': 'json'})
            req = urllib2.Request('http://api.bit.ly/v3/shorten?%s' % params)
            response = urllib2.urlopen(req)
            j = json.load(response)
            if j['status_code'] == 200:
                special_text =  j['data']['url']
        except urllib2.HTTPError, e:
            pass

        buffer_ = mark.get_buffer()
        end_iter = buffer_.get_iter_at_mark(mark)
        buffer_.insert_with_tags(end_iter, special_text, ttt.lookup('url'))

    def on_textview_motion_notify_event(self, widget, event):
        pointer_x, pointer_y = self.textview.tv.window.get_pointer()[0:2]
        x, y = self.textview.tv.window_to_buffer_coords(gtk.TEXT_WINDOW_TEXT,
                pointer_x, pointer_y)
        tags = self.textview.tv.get_iter_at_location(x, y).get_tags()
        tag_table = self.textview.tv.get_buffer().get_tag_table()
        buffer_ = self.textview.tv.get_buffer()
        for tag in tags:
            if tag != tag_table.lookup('url'):
                continue
            it = self.textview.tv.get_iter_at_location(x, y)
            st = it.copy()
            st.backward_to_tag_toggle(tag_table.lookup('url'))
            it.forward_to_tag_toggle(tag_table.lookup('url'))
            text = buffer_.get_text(st, it, include_hidden_chars=True)
            if text.startswith('http://bit.ly/'):
                try:
                    params = urllib.urlencode({'shortUrl': text,
                                                'login': USER,
                                                'apiKey': APIKEY,
                                                'format': 'json'})
                    req = urllib2.Request('http://api.bit.ly/v3/expand?%s' \
                        % params)
                    response = urllib2.urlopen(req)
                    j = json.load(response)
                    if j['status_code'] != 200:
                        raise Exception('%s'%j['status_txt'])
                    txt = j['data']['expand'][0]['long_url']
                    self.textview.tv.set_tooltip_text(txt)
                    self.textview.on_textview_motion_notify_event(widget, event)
                    return
                except Exception, e:
                    break

        self.textview.tv.set_tooltip_text('')
        self.textview.on_textview_motion_notify_event(widget, event)

    def disconnect_from_chat_control(self):
        pass


class UrlShortenerPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.max_chars_spinbutton = self.xml.get_object('max_chars')
        self.max_chars_spinbutton.get_adjustment().set_all(30, 30, 99999, 1,
            10, 0)
        self.in_max_chars_spinbutton = self.xml.get_object('in_max_chars')
        self.in_max_chars_spinbutton.get_adjustment().set_all(30, 30, 99999, 1,
            10, 0)
        self.shorten_outgoing = self.xml.get_object('shorten_outgoing')
        hbox = self.xml.get_object('vbox1')
        self.child.pack_start(hbox)

        self.xml.connect_signals(self)

    def on_run(self):
        self.max_chars_spinbutton.set_value(self.plugin.config['MAX_CHARS'])
        self.in_max_chars_spinbutton.set_value(self.plugin.config['IN_MAX_CHARS'])
        self.shorten_outgoing.set_active(self.plugin.config['SHORTEN_OUTGOING'])

    def avatar_size_value_changed(self, spinbutton):
        self.plugin.config['MAX_CHARS'] = spinbutton.get_value()

    def on_in_max_chars_value_changed(self, spinbutton):
        self.plugin.config['IN_MAX_CHARS'] = spinbutton.get_value()

    def shorten_outgoing_toggled(self, checkbutton):
        self.plugin.config['SHORTEN_OUTGOING'] = checkbutton.get_active()
