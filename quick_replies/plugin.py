import gtk
import gtkgui_helpers

from plugins import GajimPlugin
from plugins.gui import GajimPluginConfigDialog
from plugins.helpers import log_calls


class QuickRepliesPlugin(GajimPlugin):

    @log_calls('QuickRepliesPlugin')
    def init(self):

        self.description = _('Plugin for quick replies')
        self.config_dialog = QuickRepliesPluginConfigDialog(self)
        self.chat_control = None
        self.gui_extension_points = {
            'chat_control_base': (self.connect_with_chat_control,
                                    self.disconnect_from_chat_control),}
        self.config_default_values = {
            'entry1': ('Hello!', ''),
            'entry2': ('How are you?', ''),
            'entry3': ('Good bye.', ''),
            'entry4': ('', ''),
            'entry5': ('', ''),
            'entry6': ('', ''),
            'entry7': ('', ''),
            'entry8': ('', ''),
            'entry9': ('', ''),
            'entry10': ('', ''),
            }
        self.controls = []

    @log_calls('QuickRepliesPlugin')
    def connect_with_chat_control(self, chat_control):

        self.chat_control = chat_control
        control = Base(self, self.chat_control)
        self.controls.append(control)

    @log_calls('QuickRepliesPlugin')
    def disconnect_from_chat_control(self, chat_control):

        for control in self.controls:
            control.disconnect_from_chat_contro()
        self.controls = []

class Base(object):

    def __init__(self, plugin, chat_control):

        self.plugin = plugin
        self.chat_control = chat_control
        self.create_menu()
        self.create_button()


    def create_button(self):

        actions_hbox = self.chat_control.xml.get_object('actions_hbox')
        self.button = gtk.Button(label=None, stock=None, use_underline=True)
        self.button.set_property('relief', gtk.RELIEF_NONE)
        self.button.set_property('can-focus', False)
        img = gtk.Image()
        img_path = self.plugin.local_file_path('quick_replies.png')
        pixbuf = gtk.gdk.pixbuf_new_from_file(img_path)
        iconset = gtk.IconSet(pixbuf=pixbuf)
        factory = gtk.IconFactory()
        factory.add('quickreplies', iconset)
        factory.add_default()
        img.set_from_stock('quickreplies', gtk.ICON_SIZE_MENU)
        self.button.set_image(img)
        self.button.set_tooltip_text(_('Quick replies'))
        send_button = self.chat_control.xml.get_object('send_button')
        send_button_pos = actions_hbox.child_get_property(send_button,
            'position')
        actions_hbox.add_with_properties(self.button, 'position',
            send_button_pos - 1, 'expand', False)
        id_ = self.button.connect('clicked', self.on_button_cliecked)
        self.chat_control.handlers[id_] = self.button
        self.button.show()


    def on_button_cliecked(self, widget):

        gtkgui_helpers.popup_emoticons_under_button(self.menu, widget,
                                                self.chat_control.parent_win)


    def on_insert(self, widget, text):

        text = text.rstrip() + ' '
        message_buffer = self.chat_control.msg_textview.get_buffer()
        message_buffer.insert_at_cursor(text)
        self.chat_control.msg_textview.grab_focus()

    def create_menu(self):

        self.menu = gtk.Menu()

        for count in xrange(1, 11):
            text = self.plugin.config['entry' + str(count)]
            if not text:
                continue
            item = gtk.MenuItem(text)
            item.connect('activate', self.on_insert, text)
            self.menu.append(item)
        self.menu.show_all()

class QuickRepliesPluginConfigDialog(GajimPluginConfigDialog):

    def init(self):

        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['table1'])
        hbox = self.xml.get_object('table1')
        self.child.pack_start(hbox)
        self.xml.connect_signals(self)

    def on_run(self):

        for count in xrange(1, 11):
            self.xml.get_object('entry' + str(count)).set_text(
                self.plugin.config['entry' + str(count)])

    def entry_changed(self, widget):

        name = gtk.Buildable.get_name(widget)
        self.plugin.config[name] = widget.get_text()
        for control in self.plugin.controls:
            control.create_menu()

