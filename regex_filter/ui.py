# -*- coding: utf-8 -*-

import gtk
import gobject
from common import gajim
from plugins.gui import GajimPluginConfigDialog

class RegexFilterPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_from_file(self.GTK_BUILDER_FILE_PATH)

        self.rules_model = gtk.ListStore(gobject.TYPE_INT,
                                       gobject.TYPE_STRING,
                                       gobject.TYPE_STRING)

        self.rules_view = self.xml.get_object('rules_view')
        self.rules_view.set_model(self.rules_model)
        self.rules_view.get_selection().set_mode(gtk.SELECTION_MULTIPLE)

        self.child.pack_start(self.xml.get_object('vbox1'))

        self.child.parent.set_geometry_hints(None,
                                             min_width=512, min_height=400,
                                             max_width=1024, max_height=800)

        self.xml.connect_signals(self)

    def open_dialog_window(self, dialog_title, parent=None, values=None):
        dialog = gtk.MessageDialog(
            parent,
            gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
            gtk.MESSAGE_OTHER,
            gtk.BUTTONS_OK_CANCEL,
            None)
        dialog.set_position(gtk.WIN_POS_CENTER_ALWAYS)
        dialog.set_title(dialog_title)

        hbox = gtk.HBox(False, 4)
        hbox.show()

        label1 = gtk.Label("Search:")
        label1.show()
        hbox.pack_start(label1, False, False, 0)

        searchEntry = gtk.Entry()
        searchEntry.show()
        hbox.pack_start(searchEntry, True, False, 1)

        label2 = gtk.Label("Replace:")
        label2.show()
        hbox.pack_start(label2, False, False, 2)

        replaceEntry = gtk.Entry()
        replaceEntry.show()
        hbox.pack_start(replaceEntry, True, False, 3)

        dialog.vbox.add(hbox)

        if values:
            searchEntry.set_text(values[0])
            replaceEntry.set_text(values[1])

        searchEntry.connect('activate',
                            lambda _: dialog.response(gtk.RESPONSE_OK))
        replaceEntry.connect('activate',
                             lambda _: dialog.response(gtk.RESPONSE_OK))

        dialog.set_default_response(gtk.RESPONSE_OK)
        while True:
            response = dialog.run()
            search = searchEntry.get_text().decode('utf8')
            replace = replaceEntry.get_text().decode('utf8')
            if response == gtk.RESPONSE_OK:
                if self.plugin.is_valid_regex(search):
                    dialog.destroy()
                    return [search, replace]
                else:
                    searchEntry.grab_focus()
            else:
                break
        dialog.destroy()

    def add_button_clicked_cb(self, button, *args):
        title = 'Add new filter rule'
        response = self.open_dialog_window(title, self.parent, None)
        if response:
            self.plugin.add_rule(response[0], response[1])

    def edit_button_clicked_cb(self, button, *args):
        model, rules = self.rules_view.get_selection().get_selected_rows()

        for rule in rules:
            it = model.get_iter(rule)
            ruleNum, search, replace = model.get(it, 0, 1, 2)
            title = 'Edit filter rule #%d' % ruleNum
            response = self.open_dialog_window(title, self.parent,
                                               [search, replace])
            if response:
                self.plugin.edit_rule(ruleNum, response[0], response[1])

    def remove_button_clicked_cb(self, button, *args):
        model, rules = self.rules_view.get_selection().get_selected_rows()

        for rule in reversed(rules):
            it = model.get_iter(rule)
            ruleNum = model.get(it, 0)
            self.plugin.remove_rule("%d" % ruleNum)

    def move_up_button_clicked_cb(self, button, *args):
        model, rules = self.rules_view.get_selection().get_selected_rows()

        for rule in rules:
            it = model.get_iter(rule)
            ruleNum = model.get(it, 0)
            self.plugin.swap_rules("%d" % ruleNum, int("%d" % ruleNum) - 1)


    def move_down_button_clicked_cb(self, button, *args):
        model, rules = self.rules_view.get_selection().get_selected_rows()

        for rule in rules:
            it = model.get_iter(rule)
            ruleNum = model.get(it, 0)
            self.plugin.swap_rules("%d" % ruleNum, int("%d" % ruleNum) + 1)
