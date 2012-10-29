import gtk
import gobject
from common import gajim
from common import helpers
from common.file_props import FilesProp
import fshare
import os
import fshare_protocol

class FileShareWindow(gtk.Window):

    def __init__(self, plugin):
        self.plugin = plugin
        gtk.Window.__init__(self)
        self.set_title('File Share')
        self.connect('delete_event', self.delete_event)
        self.set_position(gtk.WIN_POS_CENTER)
        self.set_default_size(400, 400)
        # Children
        self.notebook = gtk.Notebook()
        # Browse page
        self.bt_search =  gtk.Button('Search')
        self.bt_search.connect('clicked', self.on_bt_search_clicked)
        self.entry_search = gtk.Entry(max=0)
        self.entry_search.set_size_request(300, -1)
        self.exp_advance = gtk.Expander('Advance')
        self.ts_search = gtk.TreeStore(gobject.TYPE_STRING)
        self.tv_search = gtk.TreeView(self.ts_search)
        self.tv_search.connect('row-expanded', self.row_expanded)
        self.tv_search.connect('button-press-event',
            self.on_treeview_button_press_event)
        self.browse_popup = gtk.Menu()
        mi_download = gtk.MenuItem('Download')
        mi_property = gtk.MenuItem('Property')
        mi_download.show()
        mi_property.show()
        mi_download.connect('activate', self.on_download_clicked)
        self.browse_popup.append(mi_download)
        self.browse_popup.append(mi_property)
        self.browse_sw = gtk.ScrolledWindow()
        self.browse_sw.add(self.tv_search)
        self.tvcolumn_browse = gtk.TreeViewColumn('')
        self.tv_search.append_column(self.tvcolumn_browse)
        self.cell_browse = gtk.CellRendererText()
        self.tvcolumn_browse.pack_start(self.cell_browse, True)
        self.tvcolumn_browse.add_attribute(self.cell_browse, 'text', 0)
        self.lbl_browse = gtk.Label('Browse')
        self.browse_hbox = gtk.HBox()
        self.browse_hbox2 = gtk.HBox()
        self.browse_vbox = gtk.VBox()
        self.browse_hbox.pack_start(self.entry_search, True, True, 10)
        self.browse_hbox.pack_start(self.bt_search, False, False, 10)
        self.browse_vbox.pack_start(self.browse_hbox, False, False, 10)
        self.browse_vbox.pack_start(self.exp_advance, False, False, 10)
        self.browse_vbox.pack_start(self.browse_sw, True, True, 10)
        self.notebook.append_page(self.browse_vbox, self.lbl_browse)
        # file references for tv_search
        self.browse_fref = {}
        # contact references for tv_search
        self.browse_jid = {}
        # Information of the files inserted in the treeview: name, size, etc
        self.brw_file_info = {}
        # dummy row children so that we can get expanders
        self.empty_row_child = {}
        # Manage page
        self.bt_add_file = gtk.Button('Add file')
        self.bt_add_file.connect('clicked', self.add_file)
        self.bt_add_dir = gtk.Button('Add directory')
        self.bt_add_dir.connect('clicked', self.add_directory)
        self.bt_remove = gtk.Button('Remove')
        self.bt_remove.connect('clicked', self.remove_file_clicked)
        self.bt_remove_all = gtk.Button('Remove all')
        self.bt_remove_all.connect('clicked', self.remove_all_clicked)
        self.ts_contacts = gtk.TreeStore(gobject.TYPE_STRING)
        self.cbb_contacts = gtk.ComboBoxEntry(self.ts_contacts)
        self.cbb_contacts.connect('changed', self.__check_combo_edit)
        cbb_entry = self.cbb_contacts.child
        self.cbb_completion = gtk.EntryCompletion()
        cbb_entry.set_completion(self.cbb_completion)
        self.cbb_completion.set_model(self.ts_contacts)
        self.cbb_completion.set_text_column(0)
        self.bt_stophash = gtk.Button('Calculating hash')
        self.lbl_manage = gtk.Label('Manage Shared Files')
        self.ts_files = gtk.TreeStore(gobject.TYPE_STRING)
        self.tv_files = gtk.TreeView(self.ts_files)
        self.treeSelection_files = self.tv_files.get_selection()
        self.treeSelection_files.connect('changed', self.row_selected)
        self.manage_sw = gtk.ScrolledWindow()
        self.manage_sw.add(self.tv_files)
        self.tvcolumn = gtk.TreeViewColumn('')
        self.tv_files.append_column(self.tvcolumn)
        self.cell = gtk.CellRendererText()
        self.tvcolumn.pack_start(self.cell, True)
        self.tvcolumn.add_attribute(self.cell, 'text', 0)
        self.pb_filehash = gtk.ProgressBar()
        self.manage_hbox = gtk.HBox()
        self.manage_hbox2 = gtk.HBox()
        self.manage_vbox = gtk.VBox()
        self.manage_vbox2 = gtk.VBox()
        self.manage_hbox.pack_start(self.bt_stophash , False, False, 10)
        self.manage_hbox.pack_start(self.pb_filehash, True, True, 10)
        self.manage_hbox.set_sensitive(False)
        self.manage_vbox.pack_start(self.cbb_contacts, False, False, 10)
        self.manage_vbox.pack_start(self.manage_hbox, False, False, 10)
        self.manage_hbox2.pack_start(self.manage_sw, True, True, 10)
        self.manage_hbox2.pack_start(self.manage_vbox2, False, False, 10)
        self.manage_vbox2.pack_start(self.bt_add_file, False, False, 10)
        self.manage_vbox2.pack_start(self.bt_add_dir, False, False, 10)
        self.manage_vbox2.pack_start(self.bt_remove, False, False, 10)
        self.manage_vbox2.pack_start(self.bt_remove_all, False, False, 10)
        self.manage_vbox2.set_sensitive(False)
        self.manage_vbox.pack_start(self.manage_hbox2, True, True, 10)
        self.notebook.append_page(self.manage_vbox, self.lbl_manage)
        # Preferences page
        self.lbl_pref = gtk.Label('Preferences')
        self.entry_dir_pref = gtk.Entry(max=0)
        self.entry_dir_pref.set_text(self.plugin.config['incoming_dir'])
        self.bt_sel_dir_pref = gtk.Button('Select dir', gtk.STOCK_OPEN)
        self.bt_sel_dir_pref.connect('clicked', self.on_bt_sel_dir_pref_clicked)
        self.frm_dir_pref = gtk.Frame('Incoming files directory')
        self.frm_dir_pref.set_shadow_type(gtk.SHADOW_IN)
        self.pref_hbox = gtk.HBox()
        self.pref_vbox = gtk.VBox()
        self.pref_hbox.pack_start(self.entry_dir_pref, True, True, 10)
        self.pref_hbox.pack_start(self.bt_sel_dir_pref, False, False, 10)
        self.frm_dir_pref.add(self.pref_hbox)
        self.pref_vbox.pack_start(self.frm_dir_pref, False, False, 10)
        self.notebook.append_page(self.pref_vbox , self.lbl_pref)
        self.add(self.notebook)
        self.show_all()

    def set_account(self, account):
        self.account = account
        # connect window to protocol
        pro = fshare.FileSharePlugin.prohandler[self.account]
        pro.set_window(self)

    def add_file(self, widget):
        dialog = gtk.FileChooserDialog('Add file to be shared', self,
            gtk.FILE_CHOOSER_ACTION_OPEN,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN,
            gtk.RESPONSE_OK)
            )
        dialog.set_select_multiple(True)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            file_list = dialog.get_filenames()
            self.add_items_tvcontacts(file_list)
        dialog.destroy()

    def add_directory(self, widget):
        dialog = gtk.FileChooserDialog('Add directory to be shared', self,
            gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN,
            gtk.RESPONSE_ACCEPT)
            )
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            file_list = []
            file_list.append(dialog.get_filename())
            self.add_items_tvcontacts(file_list)
        dialog.destroy()

    def add_file_list(self, flist, treestore, fref = {}, root = None):
        # file references to their in the treeStore
        for f in flist:
            # keeps track of the relative dir path
            tail = ''
            # keeps track of the parent row
            parent = None
            dirpath = f.split('/')
            if len(dirpath) == 1:
                # Top level file, it doesnt have parent, add it right away
                fref[dirpath[0]] = treestore.insert(root, 0, (dirpath[0],))
            else:
                for dir_ in dirpath:
                    if tail + dir_ not in fref:
                        fref[tail + dir_] =  treestore.append(parent, (dir_,))
                    parent = fref[tail + dir_]
                    tail = tail + dir_ + '/'
        return fref

    def __convert_date(self, epoch):
        # Converts date-time from seconds from epoch to iso 8601
        import time, datetime
        ts = time.gmtime(epoch)
        dt = datetime.datetime(ts.tm_year, ts.tm_mon, ts.tm_mday, ts.tm_hour,
            ts.tm_min,  ts.tm_sec)
        return dt.isoformat()

    def add_items_tvcontacts(self, file_list, parentdir = None, parent = None):
        # TODO: execute this method inside of a thread
        for f in file_list:
            # Relative name to be used internally in the shared folders
            relative_name = f.split('/')[-1]
            if parentdir:
                relative_name = parentdir + '/'  + relative_name
            short_name = relative_name.split('/')[-1]
            if short_name[0] == '.':
                # Return if it is a hidden file
                return
            if parent:
                row = self.ts_files.append(parent, (short_name,))
            else:
                row = self.ts_files.insert(None, 0, (short_name,))
            # File info
            size = os.path.getsize(f)
            is_dir = os.path.isdir(f)
            mod_date = os.path.getmtime(f)
            mod_date = self.__convert_date(mod_date)
            # TODO: add hash
            file_ = (f, relative_name, '', size, '', mod_date, is_dir)
            requester = self.cbb_contacts.get_active_text()
            try:
                fid = self.plugin.database.add_file(self.account, requester,
                    file_)
            except Exception, e:
                if e == 'Duplicated entry':
                    print 'Error: ' + e
                    continue
                else:
                    raise Exception(e)
            if is_dir:
                tmpfl = os.listdir(f)
                fl = []
                for item in tmpfl:
                    fl.append(f + '/' + item)
                self.add_items_tvcontacts(fl, relative_name, row)

    def add_contact_browse(self, contact):
        fjid = contact.get_full_jid()
        jid = gajim.get_jid_without_resource(fjid)
        contacts = gajim.contacts.get_contacts(self.account, jid)
        for con in contacts:
            if con.show in ('offline', 'error') and not \
            con.supports(fshare_protocol.NS_FILE_SHARING):
                break
            cjid = con.get_full_jid()
            r = self.ts_search.insert(None, 0, (cjid, ))
            self.browse_jid[cjid] = r
            pro = fshare.FileSharePlugin.prohandler[self.account]
            # Request list of files from peer
            stanza = pro.request(cjid)
            if pro.conn.connection:
                pro.conn.connection.send(stanza)

    def add_contact_manage(self, contact):
        self.contacts_rows = []
        self.cbb_contacts.grab_focus()
        for c in gajim.contacts.iter_contacts(self.account):
            jid = gajim.get_jid_without_resource(c.get_full_jid())
            r = self.ts_contacts.insert(None, len(self.ts_contacts), (jid, ))
            if c.get_full_jid() == contact.get_full_jid():
                self.cbb_contacts.set_active_iter(r)
            self.contacts_rows.append(r)
        self.manage_vbox2.set_sensitive(True)
        self.bt_remove.set_sensitive(False)
        self.add_file_list(self.plugin.database.get_files_name(self.account,
            gajim.get_jid_without_resource(contact.get_full_jid())),
            self.ts_files)

    def delete_event(self, widget, data=None):
        fshare.FileSharePlugin.filesharewindow = {}
        return False

    def __check_combo_edit(self, widget, data=None):
        self.ts_files.clear()
        entry = self.cbb_contacts.child
        contact = entry.get_text()
        self.manage_vbox2.set_sensitive(False)
        for i in self.contacts_rows:
            # If the contact in the comboboxentry is include inside of the
            # combobox
            if contact == self.ts_contacts.get_value(i, 0):
                self.add_file_list(self.plugin.database.get_files_name(
                    self.account, contact), self.ts_files)
                self.manage_vbox2.set_sensitive(True)
                self.bt_remove.set_sensitive(False)
                break

    def remove_file_clicked(self, widget, data=None):
        entry = self.cbb_contacts.child
        contact = entry.get_text()
        sel = self.treeSelection_files.get_selected()
        relative_name = self.ts_files.get_value(sel[1], 0)
        self.ts_files.remove(sel[1])
        self.plugin.database.delete(self.account, contact, relative_name)
        widget.set_sensitive(False)

    def remove_all_clicked(self, widget, data=None):
        entry = self.cbb_contacts.child
        contact = entry.get_text()
        self.plugin.database.delete_all(self.account, contact)
        self.ts_files.clear()

    def row_selected(self, widget, data=None):
        # When row is selected in tv_files
        sel = self.treeSelection_files.get_selected()
        if not sel[1]:
            return
        depth = self.ts_files.iter_depth(sel[1])
        # Don't remove file and dirs that aren't at the root level
        if depth == 0:
            self.bt_remove.set_sensitive(True)
        else:
            self.bt_remove.set_sensitive(False)

    def row_expanded(self, widget, iter_, path, data=None):
        name = None
        for key in self.empty_row_child:
            parent = self.ts_search.iter_parent(self.empty_row_child[key])
            p = self.ts_search.get_path(parent)
            if p == path:
                name = key
                break
        if name:
            # if we found that the expanded row is the parent of the empty row
            # remove it from the treestore and empty_row dictionary. Then ask
            # peer for list of files of that directory
            i = self.empty_row_child[name]
            pro = fshare.FileSharePlugin.prohandler[self.account]
            contact = self.get_contact_from_iter(self.ts_search, i)
            contact = gajim.contacts.get_contact_with_highest_priority(
                self.account, contact)
            stanza = pro.request(contact.get_full_jid(), name, isFile=False)
            if pro.conn.connection:
                pro.conn.connection.send(stanza)
            self.ts_search.remove(i)
            del self.empty_row_child[name]

    def get_contact_from_iter(self, treestore, iter_):
        toplevel = treestore.get_iter_root()
        while toplevel:
            if treestore.is_ancestor(toplevel, iter_):
                return gajim.get_jid_without_resource(treestore.get_value(
                    toplevel, 0))
            toplevel = treestore.iter_next(toplevel)

    def on_treeview_button_press_event(self, treeview, event):
        if event.button == 3:
            x = int(event.x)
            y = int(event.y)
            time = event.time
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None:
                path, col, cellx, celly = pthinfo
                treeview.grab_focus()
                treeview.set_cursor( path, col, 0)
                treestore = treeview.get_model()
                it = treestore.get_iter(path)
                if treestore.iter_depth(it) != 0:
                    self.browse_popup.popup(None, None, None, event.button, time)
            return True

    def on_bt_search_clicked(self, widget, data=None):
        pass

    def on_download_clicked(self, widget, data=None):
        tree, row = self.tv_search.get_selection().get_selected()
        path = tree.get_path(row)
        file_info = self.brw_file_info[path]
        fjid = self.get_contact_from_iter(tree, row)
        # Request the file
        file_path = os.path.join(self.plugin.config['incoming_dir'],
            file_info[0])
        sid = helpers.get_random_string_16()
        new_file_props = FilesProp.getNewFileProp(self.account, sid)
        new_file_props.file_name = file_path
        print file_path
        new_file_props.name = file_info[0]
        new_file_props.desc = file_info[4]
        new_file_props.size = file_info[2]
        new_file_props.date = file_info[1]
        new_file_props.hash_ = None if file_info[3] == '' else file_info[3]
        new_file_props.type_ = 'r'
        tsid = gajim.connections[self.account].start_file_transfer(fjid,
            new_file_props, True)
        new_file_props.transport_sid = tsid
        ft_window = gajim.interface.instances['file_transfers']
        contact = gajim.contacts.get_contact_from_full_jid(self.account, fjid)
        ft_window .add_transfer(self.account, contact, new_file_props)

    def on_bt_sel_dir_pref_clicked(self, widget, data=None):
        chooser = gtk.FileChooserDialog(title='Incoming files directory',
            action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
            buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN,
            gtk.RESPONSE_OK))
        response = chooser.run()
        if response == gtk.RESPONSE_OK:
            file_name = chooser.get_filename()
            self.entry_dir_pref.set_text(file_name)
            self.plugin.config['incoming_dir'] = file_name
        chooser.destroy()


if __name__ == "__main__":
    f = FileShareWindow(None)
    f.show()
    gtk.main()
