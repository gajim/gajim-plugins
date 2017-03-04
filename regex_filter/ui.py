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

    def add_button_clicked_cb(self, button, *args):
        message = "Add a new filter for incoming messages"
        dialog = gtk.MessageDialog(self.parent,
                              gtk.DIALOG_MODAL|gtk.DIALOG_DESTROY_WITH_PARENT,
                              gtk.MESSAGE_OTHER,
                              gtk.BUTTONS_OK_CANCEL,
                              message)
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

        searchEntry.connect('activate',
                            lambda _: dialog.response(gtk.RESPONSE_OK))
        replaceEntry.connect('activate',
                             lambda _: dialog.response(gtk.RESPONSE_OK))

        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()
        search = searchEntry.get_text().decode('utf8')
        replace = replaceEntry.get_text().decode('utf8')
        dialog.destroy()

        if response == gtk.RESPONSE_OK:
            if search.strip():
                self.plugin.add_rule(search, replace)

    def remove_button_clicked_cb(self, button, *args):
        model, rules = self.rules_view.get_selection().get_selected_rows()

        for rule in reversed(rules):
            it = model.get_iter(rule)
            ruleNum = model.get(it, 0)
            self.plugin.remove_rule("%d" % ruleNum)
