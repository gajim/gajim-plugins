# -*- coding: utf-8 -*-
##

from gi.repository import Gtk
from gi.repository import GdkPixbuf
from gi.repository import Pango
from gi.repository import GObject
import io
import configparser
import os
import zipfile
import tempfile
from shutil import rmtree
import sys
import imp
from enum import IntEnum
from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls
from htmltextview import HtmlTextView
from conversation_textview import ConversationTextview
from dialogs import WarningDialog, HigDialog


class Column(IntEnum):
    PIXBUF = 0
    NAME = 1
    DESCRIPTION = 2
    AUTHORS = 3
    CONVERTER = 4
    HOMEPAGE = 5
    UPGRADE = 6


class EmoticonsPackPlugin(GajimPlugin):

    @log_calls('EmoticonsPackPlugin')
    def init(self):
        self.description = _('Install, update and view detailed legend '
            'of emoticons')
        self.config_dialog = None  # EmoticonsPackPluginConfigDialog(self)
        self.gui_extension_points = {'plugin_window': (self.on_activate, None)}
        self.window = None
        self.model = None
        self.connected_ids = {}
        self.tmp_dir = ''

    @log_calls('EmoticonsPackPlugin')
    def activate(self):
        if 'plugins' in gajim.interface.instances:
            self.on_activate(gajim.interface.instances['plugins'])

    @log_calls('EmoticonsPackPlugin')
    def deactivate(self):
        if hasattr(self, 'page_num'):
            self.notebook.remove_page(self.notebook.page_num(self.hpaned))
            self.notebook.set_current_page(0)
            for id_, widget in list(self.connected_ids.items()):
                widget.disconnect(id_)
            del self.page_num

    def on_activate(self, plugin_win):
        if hasattr(self, 'page_num'):
            # 'Available' tab exists
            return
        self.notebook = plugin_win.plugins_notebook
        id_ = self.notebook.connect(
            'switch-page', self.on_notebook_switch_page)
        self.connected_ids[id_] = self.notebook
        self.window = plugin_win.window
        id_ = self.window.connect('destroy', self.on_win_destroy)
        self.connected_ids[id_] = self.window
        self.Gtk_BUILDER_FILE_PATH = self.local_file_path('config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.Gtk_BUILDER_FILE_PATH, ['hpaned2'])
        self.hpaned = self.xml.get_object('hpaned2')
        self.page_num = self.notebook.append_page(self.hpaned, Gtk.Label(_(
            'Emoticons')))

        widgets_to_extract = (
            'set_name', 'available_treeview', 'homepage_linkbutton',
            'inslall_upgrade_button', 'authors_label', 'converter_label',)

        for widget_name in widgets_to_extract:
            setattr(self, widget_name, self.xml.get_object(widget_name))

        self.model = Gtk.ListStore(
            GdkPixbuf.Pixbuf, GObject.TYPE_STRING,
            GObject.TYPE_STRING, GObject.TYPE_STRING,
            GObject.TYPE_STRING, GObject.TYPE_STRING, GObject.TYPE_BOOLEAN)
        self.available_treeview.set_model(self.model)
        self.available_treeview.set_rules_hint(True)
        self.model.set_sort_column_id(1, Gtk.SortType.ASCENDING)

        #self.progressbar.set_property('no-show-all', True)
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(_('Name'))
        cell = Gtk.CellRendererPixbuf()
        col.pack_start(cell, False)
        col.add_attribute(cell, 'pixbuf', Column.PIXBUF)
        col.pack_start(renderer, True)
        col.add_attribute(renderer, 'text', Column.NAME)
        col.set_property('expand', True)
        col.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)
        self.available_treeview.append_column(col)

        renderer = Gtk.CellRendererToggle()
        renderer.set_property('activatable', True)
        renderer.connect('toggled', self.available_emoticons_toggled_cb)
        col = Gtk.TreeViewColumn(
            _('Install /\nUpgrade'), renderer,  active=Column.UPGRADE)
        col.set_property('expand', False)
        col.set_resizable(False)
        self.available_treeview.append_column(col)

        selection = self.available_treeview.get_selection()
        selection.connect('changed', self.emoticons_treeview_selection_changed)
        selection.set_mode(Gtk.SelectionMode.SINGLE)

        self.emoticons_description_textview = ConversationTextview(None)
        sw = self.xml.get_object('scrolledwindow1')
        sw.add(self.emoticons_description_textview.tv)
        self.xml.connect_signals(self)
        self.window.show_all()

    def on_legend_button_clicked(self, widget):
        self.xml.get_object('scrolledwindow1').get_children()[0].destroy()

        treeview_selection = self.available_treeview.get_selection()
        model, iter = treeview_selection.get_selected()
        name = model.get_value(iter, Column.NAME)

        label = self.xml.get_object('label2')
        if label.get_text() == _('Legend'):
            label.set_text(_('Description'))
            sys.path.append(os.path.join(self.tmp_dir, name))

            import emoticons
            imp.reload(emoticons)

            self.emoticons_description_textview = Gtk.TextView()
            sw = self.xml.get_object('scrolledwindow1')
            sw.add(self.emoticons_description_textview)
            sw.show_all()

            buff = self.emoticons_description_textview.get_buffer()
            for icon in emoticons.emoticons:
                icon_file = os.path.join(self.tmp_dir, name, icon)
                with open(icon_file, 'rb') as _file:
                    data = _file.read()
                pbl = GdkPixbuf.PixbufLoader()
                pbl.write(data)
                pbl.close()
                if icon.endswith('.gif'):
                    img = Gtk.Image()
                    img.set_from_animation(pbl.get_animation())
                    img.show()
                    anchor = buff.create_child_anchor(buff.get_end_iter())
                    self.emoticons_description_textview.add_child_at_anchor(
                        img, anchor)
                else:
                    buff.insert_pixbuf(buff.get_end_iter(), pbl.get_pixbuf())
                text = ' , '.join(emoticons.emoticons[icon])
                buff.insert(buff.get_end_iter(), text + '\n', -1)

            self.emoticons_description_textview.set_property('sensitive', True)
            sys.path.remove(os.path.join(self.tmp_dir, name))

        else:
            self.emoticons_description_textview = ConversationTextview(None)
            sw = self.xml.get_object('scrolledwindow1')
            sw.add(self.emoticons_description_textview.tv)
            sw.show_all()
            label.set_text(_('Legend'))
            desc = _(model.get_value(iter, Column.DESCRIPTION))
            if not desc.startswith('<body  '):
                desc = '<body  xmlns=\'http://www.w3.org/1999/xhtml\'>' + \
                    desc + ' </body>'
            desc = desc.replace('preview.image', ('file:' + os.path.join(
                    self.tmp_dir, name, 'preview.png'))).replace('\n', '<br/>')
            self.emoticons_description_textview.tv.display_html(
                desc, self.emoticons_description_textview)
            self.emoticons_description_textview.tv.set_property(
                'sensitive', True)

    def on_inslall_upgrade_clicked(self, widget):
        self.inslall_upgrade_button.set_property('sensitive', False)
        self.errors = ''

        def on_error(func, path, error):
            if func == os.path.islink:
            # if symlink
                os.unlink(path)
                return
            # access is denied or other
            # WarningDialog(_('Can\'t remove dir'), error[1], self.window)
            self.errors += str(error[1])

        name_list = []
        for i in range(len(self.model)):
            if self.model[i][Column.UPGRADE]:
                name_list.append(self.model[i][Column.NAME])
        for name in name_list:
            # remove dirs
            target_dir = os.path.join(gajim.MY_EMOTS_PATH, name)
            if os.path.isdir(target_dir):
                rmtree(target_dir, False, on_error)

            # unzip new files
            zip_file = os.path.join(self.__path__, 'emoticons_pack.zip')
            with zipfile.ZipFile(zip_file, 'r') as myzip:
                namelist = myzip.namelist()
                for n in namelist:
                    if not n.startswith(name):
                        continue
                    try:
                        icon_file = myzip.extract(n, path=gajim.MY_EMOTS_PATH)
                    except Exception as e:
                        self.errors += str(e)
        # unset all checkbattons
        for i in range(len(self.model)):
            self.model[i][Column.UPGRADE] = False

        if self.errors:
            WarningDialog(
                _('Not fully installed'),
                'Access is denied or other', self.window)
        else:
            # show dialog
            dialog = HigDialog(
                None, Gtk.MessageType.INFO, Gtk.ButtonsType.OK, '',
                _('All selected emoticons installed(upgraded)'))
            dialog.set_modal(False)
            dialog.set_transient_for(self.window)
            dialog.popup()

    def on_win_destroy(self, widget):
        if hasattr(self, 'page_num'):
            del self.page_num

    def available_emoticons_toggled_cb(self, cell, path):
        is_active = self.model[path][Column.UPGRADE]
        self.model[path][Column.UPGRADE] = not is_active
        dir_list = []
        for i in range(len(self.model)):
            if self.model[i][Column.UPGRADE]:
                dir_list.append(self.model[i][Column.NAME])
        if not dir_list:
            self.inslall_upgrade_button.set_property('sensitive', False)
        else:
            self.inslall_upgrade_button.set_property('sensitive', True)

    def on_notebook_switch_page(self, widget, page, page_num):
        tab_label_text = self.notebook.get_tab_label_text(self.hpaned)
        if tab_label_text != (_('Emoticons')):
            return

        self.model.clear()
        self.fill_table()
        self.select_root_iter()

    def fill_table(self):
        conf = configparser.ConfigParser()
        # read metadata from contents.ini
        contents_path = os.path.join(self.__path__, 'contents.ini')
        with open(contents_path) as _file:
            conf.read_file(_file)
        for section in conf.sections():
            # get icon
            filename = conf.get(section, 'icon')
            filename = os.path.join(section, filename)
            zip_file = os.path.join(self.__path__, 'emoticons_pack.zip')
            with zipfile.ZipFile(zip_file, 'r') as myzip:
                icon_file = myzip.open(filename, mode='r')
                data = icon_file.read()
            pbl = GdkPixbuf.PixbufLoader()
            pbl.set_size(16, 16)
            pbl.write(data)
            pbl.close()
            icon = pbl.get_pixbuf()

            self.model.append(
                [icon, section,
                    conf.get(section, 'description'),
                    conf.get(section, 'authors', fallback=_('Unknown')),
                    conf.get(section, 'converter', fallback=_('Unknown')),
                    conf.get(section, 'homepage'), False])
            conf.remove_section(section)

    def emoticons_treeview_selection_changed(self, treeview_selection):
        model, iter = treeview_selection.get_selected()
        label = self.xml.get_object('label2')
        label.set_text(_('Legend'))
        if iter:
            set_name = model.get_value(iter, Column.NAME)
            if os.path.isdir(self.tmp_dir):
                rmtree(self.tmp_dir, True)
            self.tmp_dir = tempfile.mkdtemp()
             # unzip new files
            zip_file = os.path.join(self.__path__, 'emoticons_pack.zip')
            with zipfile.ZipFile(zip_file, 'r') as myzip:
                namelist = myzip.namelist()
                for n in namelist:
                    if not n.startswith(set_name):
                        continue
                    myzip.extract(n, path=self.tmp_dir)

            self.set_name.set_text(set_name)
            self.authors_label.set_text(model.get_value(iter, Column.AUTHORS))
            self.converter_label.set_text(model.get_value(iter, Column.CONVERTER))
            self.homepage_linkbutton.set_uri(
                model.get_value(iter, Column.HOMEPAGE))
            self.homepage_linkbutton.set_label(
                model.get_value(iter, Column.HOMEPAGE))
            label = self.homepage_linkbutton.get_children()[0]
            label.set_ellipsize(Pango.EllipsizeMode.END)
            self.homepage_linkbutton.set_property('sensitive', True)

            self.xml.get_object('scrolledwindow1').get_children()[0].destroy()
            self.emoticons_description_textview = ConversationTextview(None)
            sw = self.xml.get_object('scrolledwindow1')
            sw.add(self.emoticons_description_textview.tv)
            sw.show_all()
            desc = _(model.get_value(iter, Column.DESCRIPTION))
            if not desc.startswith('<body '):
                desc = '<body  xmlns=\'http://www.w3.org/1999/xhtml\'>' + \
                    desc + ' </body>'
            else:
                desc = desc.replace('preview.image', ('file:' + os.path.join(
                    self.tmp_dir, set_name, 'preview.png')))
            self.emoticons_description_textview.tv.display_html(
                desc, self.emoticons_description_textview)
            self.emoticons_description_textview.tv.set_property(
                'sensitive', True)
        else:
            self.set_name.set_text('')
            self.authors_label.set_text('')
            self.homepage_linkbutton.set_uri('')
            self.homepage_linkbutton.set_label('')
            self.homepage_linkbutton.set_property('sensitive', False)

    def select_root_iter(self):
        if hasattr(self, 'page_num'):
            selection = self.available_treeview.get_selection()
            if selection.count_selected_rows() == 0:
                root_iter = self.model.get_iter_first()
                selection.select_iter(root_iter)
        scr_win = self.xml.get_object('scrolledwindow2')
        vadjustment = scr_win.get_vadjustment()
        if vadjustment:
            vadjustment.set_value(0)
        #GObject.idle_add(self.available_treeview.grab_focus)
