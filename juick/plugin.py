# -*- coding: utf-8 -*-

from gi.repository import Pango
from gi.repository import Gtk
from gi.repository import GdkPixbuf
from gi.repository import Gdk
import re
import os
import time
import locale
import sqlite3

from gajim.common import helpers
from gajim.common import app
from gajim.common import configpaths
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls, log
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.conversation_textview import TextViewImage
from gajim import gtkgui_helpers

import nbxmpp


class JuickPlugin(GajimPlugin):
    @log_calls('JuickPlugin')
    def init(self):
        self.description = _('Clickable Juick links , Juick nicks, '
            'preview Juick picturs.\nThe key combination alt + up in the '
            'textbox allow insert the number of last message '
            '(comment or topic).')
        self.config_dialog = JuickPluginConfigDialog(self)
        self.gui_extension_points = {
                'chat_control_base': (self.connect_with_chat_control,
                                       self.disconnect_from_chat_control),
                'print_special_text': (self.print_special_text,
                                       self.print_special_text1),}
        self.config_default_values = {'SHOW_AVATARS': (False, ''),
                    'AVATAR_SIZE': (20, 'Avatar size(10-32)'),
                    'avatars_old': (2419200, 'Update avatars '
                        'who are older 28 days'),
                    'SHOW_PREVIEW': (False, ''),
                    'PREVIEW_SIZE': (150, 'Preview size(10-512)'),
                    'LINK_COLOR': ('#B8833E', 'Juick link color'),
                    'SHOW_TAG_BUTTON': (True, ''),
                    'ONLY_AUTHOR_AVATAR': (True, ''),
                    'ONLY_FIRST_AVATAR': (False, ''),
                    'MENUITEM1': ('tune', ''), 'MENUITEM_TEXT1': ('*tune', ''),
                    'MENUITEM2': ('geo', ''), 'MENUITEM_TEXT2': ('*geo', ''),
                    'MENUITEM3': ('gajim', ''),
                    'MENUITEM_TEXT3': ('*gajim', ''),
                    'MENUITEM4': ('me', ''), 'MENUITEM_TEXT4': ('/me', ''),
                    'MENUITEM5': ('', ''), 'MENUITEM_TEXT5': ('', ''),
                    'MENUITEM6': ('', ''), 'MENUITEM_TEXT6': ('', ''),
                    'MENUITEM7': ('', ''), 'MENUITEM_TEXT7': ('', ''),
                    'MENUITEM8': ('', ''), 'MENUITEM_TEXT8': ('', ''),
                    'MENUITEM9': ('', ''), 'MENUITEM_TEXT9': ('', ''),
                    'MENUITEM10': ('', ''), 'MENUITEM_TEXT10': ('', ''), }
        self.chat_control = None
        self.controls = []
        self.conn = None
        self.cache_path = os.path.join(configpaths.get('AVATAR'), 'juick')
        if not os.path.isdir(self.cache_path):
            os.makedirs(self.cache_path)

    @log_calls('JuickPlugin')
    def connect_with_chat_control(self, chat_control):
        if chat_control.contact.jid != 'juick@juick.com':
            return

        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)
        self.conn = sqlite3.connect(os.path.join(self.cache_path, 'juick_db'))
        self.conn.execute('create table if not exists person'
            '(nick, id, last_modified)')
        self.cursor = self.conn.cursor()

    @log_calls('JuickPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for control in self.controls:
            control.disconnect_from_chat_control()
        self.controls = []
        if self.conn:
            self.conn.close()

    def print_special_text(self, tv, special_text, other_tags, graphics,
        additional_data, iter_):
        for control in self.controls:
            if control.chat_control.conv_textview != tv:
                continue
            control.print_special_text(special_text, other_tags, graphics,
                additional_data, iter_)

    def print_special_text1(self, tv, special_text, other_tags, graphics,
        additional_data, iter_):
        for control in self.controls:
            if control.chat_control == tv:
                control.disconnect_from_chat_control()
                self.controls.remove(control)

class Base(object):
    def __init__(self, plugin, chat_control):
        self.last_juick_num = ''
        self.plugin = plugin
        self.chat_control = chat_control
        self.textview = self.chat_control.conv_textview
        self.change_cursor = False

        id_ = self.textview.tv.connect('button_press_event',
            self.on_textview_button_press_event, self.textview)
        chat_control.handlers[id_] = self.textview.tv

        id_ = self.chat_control.msg_textview.connect('key_press_event',
            self.mykeypress_event)
        chat_control.handlers[id_] = self.chat_control.msg_textview

        self.id_ = self.textview.tv.connect('motion_notify_event',
            self.on_textview_motion_notify_event)
        self.chat_control.handlers[self.id_] = self.textview.tv

        # new buffer tags
        color = self.plugin.config['LINK_COLOR']
        buffer_ = self.textview.tv.get_buffer()
        self.textview.tagSharpSlash = buffer_.create_tag('sharp_slash')
        self.textview.tagSharpSlash.set_property('foreground', color)
        self.textview.tagSharpSlash.set_property('underline',
            Pango.Underline.SINGLE)
        id_ = self.textview.tagSharpSlash.connect('event',
            self.juick_hyperlink_handler, 'sharp_slash')
        chat_control.handlers[id_] = self.textview.tagSharpSlash

        self.textview.tagJuickNick = buffer_.create_tag('juick_nick')
        self.textview.tagJuickNick.set_property('foreground', color)
        self.textview.tagJuickNick.set_property('underline',
            Pango.Underline.SINGLE)
        id_ = self.textview.tagJuickNick.connect('event',
            self.juick_hyperlink_handler, 'juick_nick')
        chat_control.handlers[id_] = self.textview.tagJuickNick
        self.textview.tagJuickPic = buffer_.create_tag('juick_pic')

        self.create_patterns()
        self.create_link_menu()
        self.create_buttons()
        self.create_juick_menu()
        self.create_tag_menu()

    def create_patterns(self):
        self.juick_post_uid = self.juick_nick = ''
        self.juick_post_re = re.compile(r'#(\d+)')
        self.juick_post_comment_re = re.compile(r'#(\d+)/(\d+)')
        sharp_slash = r'#\d+(\/\d+)?'
        juick_nick = r'@[a-zA-Z0-9_@:\.-]+'
        juick_pic = r'http://i\.juick\.com/.+/[0-9-]+\.[JPG|jpg]'
        interface = app.interface
        interface.sharp_slash_re = re.compile(sharp_slash)
        self.juick_nick_re = interface.juick_nick_re = re.compile(juick_nick)
        self.juick_pic_re = interface.juick_pic_re = re.compile(juick_pic)
        juick_pattern = '|' + sharp_slash + '|' + juick_nick + '|' + juick_pic
        interface.basic_pattern = interface.basic_pattern + juick_pattern
        interface.emot_and_basic = interface.emot_and_basic + juick_pattern
        interface._basic_pattern_re = re.compile(interface.basic_pattern,
            re.IGNORECASE)
        interface._emot_and_basic_re = re.compile(interface.emot_and_basic,
            re.IGNORECASE + re.UNICODE)

    def create_buttons(self):
        # create juick button
        actions_hbox = self.chat_control.xml.get_object('hbox')
        self.button = Gtk.MenuButton(label=None, stock=None, use_underline=True)
        self.button.get_style_context().add_class(
            'chatcontrol-actionbar-button')
        self.button.set_property('relief', Gtk.ReliefStyle.NONE)
        self.button.set_property('can-focus', False)
        img = Gtk.Image()
        img_path = self.plugin.local_file_path('juick.png')
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(img_path)
        #img.set_from_pixbuf(pixbuf)
        iconset = Gtk.IconSet(pixbuf=pixbuf)
        factory = Gtk.IconFactory()
        factory.add('juick', iconset)
        factory.add_default()
        img.set_from_stock('juick', Gtk.IconSize.MENU)
        self.button.set_image(img)
        self.button.set_tooltip_text(_('Juick commands'))

        actions_hbox.pack_start(self.button, False, False , 0)
        actions_hbox.reorder_child(self.button,
            len(actions_hbox.get_children()) - 2)
        self.button.show()
        # create juick tag button
        self.tag_button = Gtk.MenuButton(label=None, stock=None, use_underline=True)
        self.tag_button.get_style_context().add_class(
            'chatcontrol-actionbar-button')
        self.tag_button.set_property('relief', Gtk.ReliefStyle.NONE)
        self.tag_button.set_property('can-focus', False)
        img = Gtk.Image()
        img_path = self.plugin.local_file_path('juick_tag_button.png')
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(img_path)
        #img.set_from_pixbuf(pixbuf)
        iconset = Gtk.IconSet(pixbuf=pixbuf)
        factory.add('juick_tag', iconset)
        factory.add_default()
        img.set_from_stock('juick_tag', Gtk.IconSize.MENU)
        self.tag_button.set_image(img)
        actions_hbox.pack_start(self.tag_button, False, False , 0)
        actions_hbox.reorder_child(self.tag_button,
            len(actions_hbox.get_children()) - 3)
        self.tag_button.set_no_show_all(True)
        self.tag_button.set_tooltip_text(_('Juick tags'))
        self.tag_button.set_property('visible', self.plugin.config[
            'SHOW_TAG_BUTTON'])

    def create_link_menu(self):
        """
        Create juick link context menu
        """
        self.juick_link_menu = Gtk.Menu()

        item = Gtk.MenuItem(_('Reply to message'))
        item.connect('activate', self.on_reply)
        self.juick_link_menu.append(item)

        menuitems = ((_('Unsubscribe from comments'), 'U #WORD'),
                     (_('Subscribe to message replies'), 'S #WORD'),
                     (_('Recommend post'), '! #WORD'),
                     (_('Show message with replies'), '#WORD+'),
                     (_('Delete post'), 'D #WORD'),)
        for menuitem in menuitems:
            item = Gtk.MenuItem(menuitem[0])
            item.connect('activate', self.send, menuitem[1])
            self.juick_link_menu.append(item)

        item = Gtk.MenuItem(_('Open in browser'))
        item.connect('activate', self.open_in_browser)
        self.juick_link_menu.append(item)

        menuitems = ((_('Show user\'s info'), 'NICK'),
                     (_('Show user\'s info and last 10 messages'), 'NICK+'),
                     (_('Subscribe to user\'s blog'), 'S NICK'),
                     (_('Unsubscribe from user\'s blog'), 'U NICK'),
                     (_('Add/delete user to/from your blacklist'), 'BL NICK'),)
        for menuitem in menuitems:
            item =Gtk.MenuItem(menuitem[0])
            item.connect('activate', self.send, menuitem[1])
            self.juick_link_menu.append(item)

        item = Gtk.MenuItem(_('Send personal message'))
        item.connect('activate', self.on_pm)
        self.juick_link_menu.append(item)

    def create_tag_menu(self):
        """
        Create juick tag button menu
        """
        self.menu = Gtk.Menu()
        for num in range(1, 11):
            menuitem = self.plugin.config['MENUITEM' + str(num)]
            text = self.plugin.config['MENUITEM_TEXT' + str(num)]
            if not menuitem or not text:
                continue
            item = Gtk.MenuItem(menuitem)
            item.connect('activate', self.on_insert, text)
            self.menu.append(item)
        self.menu.show_all()
        self.tag_button.set_popup(self.menu)

    def juick_hyperlink_handler(self, texttag, widget, event, iter_, kind):
        # handle message links( #12345 or #12345/6) and juick nicks
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button.button == 3:
            # show popup menu (right mouse button clicked)
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
            self.juick_post = word

            post = self.juick_post_re.search(word)
            nick = self.juick_nick_re.search(word)
            if post is None and nick is None:
                return
            childs = self.juick_link_menu.get_children()
            if post:
                self.juick_post_full = app.interface.sharp_slash_re\
                                                    .search(word).group(0)
                self.juick_post_uid = post.group(1)
                for menuitem in range(7):
                    childs[menuitem].show()
                for menuitem in range(7, 13):
                    childs[menuitem].hide()
            if nick:
                self.juick_nick = nick.group(0)
                for menuitem in range(7):
                    childs[menuitem].hide()
                for menuitem in range(7, 13):
                    childs[menuitem].show()
            self.juick_link_menu.popup(None, None, None, None,
                event.button.button, event.time)
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button.button == 1:
            # insert message num or nick (left mouse button clicked)
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
            if kind == 'sharp_slash':
                self.on_insert(widget, word)
            if kind == 'juick_nick':
                self.on_insert(widget, 'PM %s' % word.rstrip(':'))

    def print_special_text(self, special_text, other_tags, graphics, additional_data, iter_):
        self.textview.plugin_modified = True
        buffer_ = self.textview.tv.get_buffer()
        if not iter_:
            iter_ = buffer_.get_end_iter()
        if app.interface.sharp_slash_re.match(special_text):
            # insert post num #123456//
            tag = self.get_iter_and_tag('sharp_slash', buffer_)
            buffer_.insert_with_tags(iter_, special_text, tag)
            self.last_juick_num = special_text
            return
        if app.interface.juick_nick_re.match(special_text):
            # insert juick nick @nickname////
            tag = self.get_iter_and_tag('juick_nick', buffer_)
            mark = buffer_.create_mark(None, iter_, True)
            nick = special_text[1:].rstrip(':')
            buffer_.insert_with_tags(iter_, special_text, tag)
            # insert avatars
            if not self.plugin.config['SHOW_AVATARS']:
                return
            b_nick = buffer_.get_text(buffer_.get_start_iter(),
                buffer_.get_iter_at_mark(mark),False)
            if self.plugin.config['ONLY_AUTHOR_AVATAR'] and not \
            special_text.endswith(':') and b_nick[-9:] not in ('Subscribed to '
            ):
                return
            if self.plugin.config['ONLY_FIRST_AVATAR']:
                if b_nick[-9:] not in ('Reply by ', 'message from ', 'ended by ',
                'Subscribed to '):
                    if b_nick[-2] != app.config.get('after_nickname'):
                        return
                    elif b_nick[-1] == '\n':
                        return
            conn = app.connections[self.chat_control.account]
            if not conn.connected:
                return
            # search id in the db
            query = "select nick, id from person where nick = :nick"
            self.plugin.cursor.execute(query, {'nick':nick})
            db_item = self.plugin.cursor.fetchone()
            if db_item:
                # nick in the db
                pixbuf = self.get_avatar(db_item[1], nick, True)
                if not pixbuf:
                    return
                end_iter = buffer_.get_iter_at_mark(mark)
                anchor = buffer_.create_child_anchor(end_iter)
                img = TextViewImage(anchor, nick)
                img.set_from_pixbuf(pixbuf)
                img.show()
                self.textview.tv.add_child_at_anchor(img, anchor)
                return
            else:
                # nick not in the db
                id_ = conn.connection.getAnID()
                to = 'juick@juick.com'
                iq = nbxmpp.Iq('get', to=to)
                a = iq.addChild(name='query',
                    namespace='http://juick.com/query#users')
                a.addChild(name='user', namespace='http://juick.com/user',
                    attrs={'uname': nick})
                iq.setID(id_)
                conn.connection.SendAndCallForResponse(iq, self._on_response,
                    {'mark': mark, 'special_text': special_text})
                return
        if app.interface.juick_pic_re.match(special_text) and \
            self.plugin.config['SHOW_PREVIEW']:
            # show pics preview
            tag = self.get_iter_and_tag('url', buffer_)
            mark = buffer_.create_mark(None, iter_, True)
            buffer_.insert_with_tags(iter_, special_text, tag)
            uid = special_text.split('/')[-1]
            url = "http://i.juick.com/photos-512/%s" % uid
            app.thread_interface(self.insert_pic_preview, [mark, special_text,
                url])
            return
        self.textview.plugin_modified = False

    def insert_pic_preview(self, mark, special_text, url):
        pixbuf = self.get_pixbuf_from_url( url, self.plugin.config[
            'PREVIEW_SIZE'])
        if pixbuf:
            # insert image
            buffer_ = mark.get_buffer()
            end_iter = buffer_.get_iter_at_mark(mark)
            anchor = buffer_.create_child_anchor(end_iter)
            img = TextViewImage(anchor, special_text)
            img.set_from_pixbuf(pixbuf)
            img.show()
            self.textview.tv.add_child_at_anchor(img, anchor)

    def get_iter_and_tag(self, tag_name, buffer_):
        ttable = buffer_.get_tag_table()
        tag = ttable.lookup(tag_name)
        return tag

    def _on_response(self, a, resp, **kwargs):
        # insert avatar to text mark
        mark = kwargs['mark']
        buffer_ = mark.get_buffer()
        end_iter = buffer_.get_iter_at_mark(mark)
        tags = resp.getTag('query')
        nick = kwargs['special_text'][1:].rstrip(':')
        if tags:
            user = tags.getTag('user')
            if not user:
                return
            uid = user.getAttr('uid')
            pixbuf = self.get_avatar(uid, nick)
            anchor = buffer_.create_child_anchor(end_iter)
            img = TextViewImage(anchor, nick)
            img.set_from_pixbuf(pixbuf)
            img.show()
            self.textview.tv.add_child_at_anchor(img, anchor)



    def get_avatar(self, uid, nick, need_check=None):
        # search avatar in cache or download from juick.com
        pic = uid + '.png'
        pic_path = os.path.join(self.plugin.cache_path, pic)
        #pic_path = pic_path.decode(locale.getpreferredencoding())
        url = 'http://i.juick.com/as/%s.png' % uid
        if need_check and os.path.isfile(pic_path):
            max_old = self.plugin.config['avatars_old']
            if (time.time() - os.stat(pic_path).st_mtime) < max_old:
                return GdkPixbuf.Pixbuf.new_from_file(pic_path)

        avatar_size = self.plugin.config['AVATAR_SIZE']
        pixbuf = self.get_pixbuf_from_url(url, avatar_size)
        if pixbuf:
             # save to cache
            pixbuf.savev(pic_path, 'png', [], [])
            if need_check:
                return pixbuf
            query = "select nick, id from person where nick = :nick"
            self.plugin.cursor.execute(query, {'nick':nick})
            db_item = self.plugin.cursor.fetchone()
            if not db_item:

                data = (nick, uid)
                self.plugin.cursor.execute('insert into person(nick, id)'
                    ' values (?, ?)', data)
                self.plugin.conn.commit()
        else:
            img_path = self.plugin.local_file_path('unknown.png')
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(img_path)
            pixbuf, w, h = self.get_pixbuf_of_size(pixbuf, avatar_size)
        return pixbuf

    def get_pixbuf_from_url(self, url, size):
        # download avatar and resize him
        try:
            data, alt = helpers.download_image(self.textview.account,
                {'src': url})
            pix = GdkPixbuf.PixbufLoader()
            if data:
                pix.write(data)
                pix.close()
                pixbuf = pix.get_pixbuf()
                pixbuf, w, h = self.get_pixbuf_of_size(pixbuf, size)
            else:
                pix.close()
                return
        except Exception as e:
            pix.close()
            return
        return pixbuf

    def get_pixbuf_of_size(self, pixbuf, size):
        # Creates a pixbuf that fits in the specified square of sizexsize
        # while preserving the aspect ratio
        # Returns tuple: (scaled_pixbuf, actual_width, actual_height)
        image_width = pixbuf.get_width()
        image_height = pixbuf.get_height()

        if image_width > image_height:
            if image_width > size:
                image_height = int(size / float(image_width) * image_height)
                image_width = int(size)
        else:
            if image_height > size:
                image_width = int(size / float(image_height) * image_width)
                image_height = int(size)

        crop_pixbuf = pixbuf.scale_simple(image_width, image_height,
            GdkPixbuf.InterpType.BILINEAR)
        return (crop_pixbuf, image_width, image_height)

    def on_textview_button_press_event(self, widget, event, obj):
        obj.selected_phrase = ''

        if event.button != 3:
            return False

        x, y = obj.tv.window_to_buffer_coords(Gtk.TextWindowType.TEXT,
            int(event.x), int(event.y))
        iter_ = obj.tv.get_iter_at_location(x, y)[1]
        tags = iter_.get_tags()

        if tags:
            for tag in tags:
                tag_name = tag.get_property('name')
                if tag_name in ('juick_nick', 'sharp_slash'):
                    return True

        self.textview.on_textview_button_press_event(widget, event)

    def on_textview_motion_notify_event(self, widget, event):
        # Change the cursor to a hand when we are over a nicks or an post nums
        tag_table = self.textview.tv.get_buffer().get_tag_table()
        window = self.textview.tv.get_window(Gtk.TextWindowType.TEXT)
        x_pos, y_pos = self.textview.tv.window_to_buffer_coords(
            Gtk.TextWindowType.TEXT, event.x, event.y)
        if Gtk.MINOR_VERSION > 18:
            iter_ = self.textview.tv.get_iter_at_position(x_pos, y_pos)[1]
        else:
            iter_ = self.textview.tv.get_iter_at_position(x_pos, y_pos)[0]
        tags = iter_.get_tags()
        if self.change_cursor:
            window.set_cursor(gtkgui_helpers.get_cursor('XTERM'))
            self.change_cursor = False
        for tag in tags:
            tag_name = tag.get_property('name')
            if tag_name in ('juick_nick', 'sharp_slash'):
                window.set_cursor(gtkgui_helpers.get_cursor('HAND2'))
            self.change_cursor = True

    def create_juick_menu(self):
        """
        Popup juick menu
        """
        menu = Gtk.Menu()
        menuitems = ((_('Show last messages from public timeline'), '#+'),
                     (_('Show last messages from your feed'), '#'),
                     (_('Show popular personal blogs'), '@'),
                     (_('Show your tags'), '*'),
                     (_('Show your subscriptions'), 'S'),
                     (_('Delete last message'), 'D LAST'),
                     (_('Enable subscriptions delivery'), 'ON'),
                     (_('Disable subscriptions delivery'), 'OFF'),
                     (_('Show your blacklist'), 'BL'),
                     (_('Update "About" info from Jabber vCard'), 'VCARD'),
                     (_('Ping'), 'PING'),
                     (_('Login'), 'LOGIN'),
                     (_('HELP'), 'HELP'),)
        for menuitem in menuitems:
            item = Gtk.MenuItem(menuitem[0])
            item.connect('activate', self.send, menuitem[1])
            menu.append(item)

        menu.show_all()
        self.button.set_popup(menu)

    def send(self, widget, text):
        msg = text.replace('WORD', self.juick_post_uid).replace(
            'NICK', self.juick_nick.rstrip(':'))
        self.chat_control.send_message(msg)
        self.chat_control.msg_textview.grab_focus()

    def on_insert(self, widget, text):
        """
        Insert text to conversation input box, at cursor position
        """
        self.chat_control.msg_textview.remove_placeholder()
        text = text.rstrip() + ' '
        message_buffer = self.chat_control.msg_textview.get_buffer()
        message_buffer.insert_at_cursor(text)
        self.chat_control.msg_textview.grab_focus()

    def on_reply(self, widget):
        self.on_insert(widget, self.juick_post_full)

    def on_pm(self, widget):
        self.on_insert(widget, 'PM %s' % self.juick_nick.rstrip(':'))

    def open_in_browser(self, widget):
        post = self.juick_post_comment_re.search(self.juick_post)
        url = None
        if post is not None:
            url = 'http://juick.com/%s#%s' % (post.group(1), post.group(2))
        else:
            post = self.juick_post_re.search(self.juick_post)
            if post is not None:
                url = 'http://juick.com/%s' % post.group(1)
        if url is not None:
            helpers.launch_browser_mailer('url', url)

    def disconnect_from_chat_control(self):
        buffer_ = self.textview.tv.get_buffer()
        tag_table = buffer_.get_tag_table()
        if tag_table.lookup('sharp_slash'):
            tag_table.remove(self.textview.tagSharpSlash)
            tag_table.remove(self.textview.tagJuickNick)
            tag_table.remove(self.textview.tagJuickPic)
        actions_hbox = self.chat_control.xml.get_object('hbox')
        actions_hbox.remove(self.button)
        actions_hbox.remove(self.tag_button)

    def mykeypress_event(self, widget, event):
        if event.keyval == Gdk.KEY_Up:
            if event.state & Gdk.ModifierType.MOD1_MASK:  # Alt+UP
                self.on_insert(widget, self.last_juick_num)
                return True


class JuickPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.checkbutton = self.xml.get_object('checkbutton')
        self.only_first_avatar = self.xml.get_object('only_first_avatar')
        self.avatar_size_spinbutton = self.xml.get_object('avatar_size')
        self.avatar_size_spinbutton.get_adjustment().configure(20, 10, 32, 1,
            10, 0)
        self.avatars_old = self.xml.get_object('avatars_old')
        self.avatars_old.get_adjustment().configure(20, 1, 3650, 1, 10, 0)
        self.show_pic = self.xml.get_object('show_pic')
        self.preview_size_spinbutton = self.xml.get_object('preview_size')
        self.preview_size_spinbutton.get_adjustment().configure(20, 10, 512, 1,
            10, 0)
        self.link_colorbutton = self.xml.get_object('link_colorbutton')
        vbox = self.xml.get_object('vbox1')
        self.get_child().pack_start(vbox, True, True, 0)

        self.xml.connect_signals(self)

    def on_run(self):
        self.checkbutton.set_active(self.plugin.config['SHOW_AVATARS'])
        self.only_first_avatar.set_active(self.plugin.config[
            'ONLY_FIRST_AVATAR'])
        self.xml.get_object('only_author_avatar').set_active(
                                    self.plugin.config['ONLY_AUTHOR_AVATAR'])
        self.avatar_size_spinbutton.set_value(self.plugin.config['AVATAR_SIZE'])
        self.avatars_old.set_value(self.plugin.config['avatars_old'] / 86400)
        self.show_pic.set_active(self.plugin.config['SHOW_PREVIEW'])
        self.preview_size_spinbutton.set_value(self.plugin.config[
            'PREVIEW_SIZE'])
        self.link_colorbutton.set_color(Gdk.color_parse(
            self.plugin.config['LINK_COLOR']))
        self.xml.get_object('show_tag_button').set_active(self.plugin.config[
            'SHOW_TAG_BUTTON'])
        for num in range(1, 11):
            self.xml.get_object('menuitem' + str(num)).set_text(
                self.plugin.config['MENUITEM' + str(num)])
            self.xml.get_object('menuitem_text' + str(num)).set_text(
                self.plugin.config['MENUITEM_TEXT' + str(num)])

    def on_checkbutton_toggled(self, checkbutton):
        self.plugin.config['SHOW_AVATARS'] = checkbutton.get_active()

    def on_only_author_ava_toggled(self, checkbutton):
        self.plugin.config['ONLY_AUTHOR_AVATAR'] = checkbutton.get_active()

    def on_only_first_avatar_toggled(self, checkbutton):
        self.plugin.config['ONLY_FIRST_AVATAR'] = checkbutton.get_active()

    def avatar_size_value_changed(self, spinbutton):
        self.plugin.config['AVATAR_SIZE'] = spinbutton.get_value()

    def on_avatars_old_value_changed(self, spinbutton):
        self.plugin.config['avatars_old'] = spinbutton.get_value() * 86400

    def on_show_pic_toggled(self, checkbutton):
        self.plugin.config['SHOW_PREVIEW'] = checkbutton.get_active()

    def on_show_tag_button_toggled(self, checkbutton):
        self.plugin.config['SHOW_TAG_BUTTON'] = checkbutton.get_active()
        for control in self.plugin.controls:
            control.tag_button.set_property('visible', checkbutton.get_active())

    def preview_size_value_changed(self, spinbutton):
        self.plugin.config['PREVIEW_SIZE'] = spinbutton.get_value()

    def on_link_colorbutton_color_set(self, colorbutton):
        color = colorbutton.get_color().to_string()
        self.plugin.config['LINK_COLOR'] = color
        for control in self.plugin.controls:
            control.textview.tagSharpSlash.set_property('foreground', color)
            control.textview.tagJuickNick.set_property('foreground', color)

    def menuitem_changed(self, widget):
        name = (Gtk.Buildable.get_name(widget)).upper()
        self.plugin.config[name] = widget.get_text()
        for control in self.plugin.controls:
            control.create_tag_menu()
