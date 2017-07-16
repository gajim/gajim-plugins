import sqlite3
from common import app
import sys
import os

class FilesharingDatabase:
    def __init__(self, plugin):
        self.plugin = plugin
        path_l = os.path.split(plugin.config.FILE_PATH)
        path = os.path.join(path_l[0], 'shared_files.db')
        db_exist = os.path.exists(path)
        self.conn = sqlite3.connect(path)
        # Enable foreign keys contraints
        self.conn.cursor().execute("pragma foreign_keys = on")
        if not db_exist:
            self.create_database()

    # NOTE: Make sure we are getting and setting the requester without its
    # resource
    def create_database(self):
        c = self.conn.cursor()
        # Create tables
        c.execute("CREATE TABLE permissions" +
            "(fid integer REFERENCES files(fid) ON DELETE CASCADE, " +
            "account text, requester text)")
        c.execute("CREATE TABLE files" +
            "(fid INTEGER PRIMARY KEY AUTOINCREMENT," +
            " file_path text, relative_path text, hash_sha1 text," +
            "size numeric, description text, mod_date text, is_dir boolean)")
        # Save (commit) the changes
        self.conn.commit()
        c.close()

    def get_toplevel_files(self, account, requester):
        c = self.conn.cursor()
        data = (account, requester)
        c.execute("SELECT relative_path, hash_sha1, size, description, " +
            "mod_date, is_dir FROM (files JOIN permissions ON" +
            " files.fid=permissions.fid) WHERE account=? AND requester=?" +
            " AND relative_path NOT LIKE '%/%'", data)
        result = c.fetchall()
        c.close()
        return result

    def get_files_from_dir(self, account, requester, dir_):
        c = self.conn.cursor()
        data = (account, requester, dir_ + '/%')
        c.execute("SELECT relative_path, hash_sha1, size, description, " +
            "mod_date, is_dir FROM (files JOIN permissions ON" +
            " files.fid=permissions.fid) WHERE account=? AND requester=?" +
            " AND relative_path LIKE ?", data)
        result = c.fetchall()
        c.close()
        fresult = []
        for r in result:
            name = r[0][len(dir_) + 1:]
            if '/' not in name:
                fresult.append(r)
        return fresult

    def get_files(self, account, requester):
        """
        >>> file_ = ('file_path', 'relative_path', 'hash', 999, 'description', \
                     'date', False)
        >>> foo = add_file('account@gajim', 'requester@jabber', file_)
        >>> result = get_files('account@gajim', 'requester@jabber')
        >>> len(result)
        1
        >>> _delete_file(1)
        """
        c = self.conn.cursor()
        data = (account, requester)
        c.execute("SELECT relative_path, hash_sha1, size, description, " +
            "mod_date, is_dir FROM (files JOIN permissions ON" +
            " files.fid=permissions.fid) WHERE account=? AND requester=?", data)
        result = c.fetchall()
        c.close()
        return result

    def get_file(self, account, requester, hash_, name):
        c = self.conn.cursor()
        if hash_:
            data = (account, requester, hash_)
            sql = "SELECT relative_path, hash_sha1, size, description, " + \
                "mod_date, file_path FROM (files JOIN permissions ON" + \
                " files.fid=permissions.fid) WHERE account=? AND requester=?" +\
                " AND hash_sha1=?"
        else:
            data = (account, requester, name)
            sql = "SELECT relative_path, hash_sha1, size, description, " + \
                "mod_date, file_path FROM (files JOIN permissions ON" + \
                " files.fid=permissions.fid) WHERE account=? AND requester=?" +\
                " AND relative_path=?"
        c.execute(sql, data)
        result = c.fetchall()
        c.close()
        if result == []:
            return None
        else:
            return result[0]

    def get_files_name(self, account, requester):
        result = self.get_files(account, requester)
        flist = []
        for r in result:
            flist.append(r[0])
        return flist

    def add_file(self, account, requester, file_):
        """
        >>> file_ = ('file_path', 'relative_path', 'hash', 999, 'description', \
                     'date', False)
        >>> add_file('account@gajim', 'requester@jabber', file_)
        1
        >>> _delete_file(1)
        """
        self._check_duplicate(account, requester, file_)
        requester = app.get_jid_without_resource(requester)
        c = self.conn.cursor()
        c.execute("INSERT INTO files (file_path, " +
            "relative_path, hash_sha1, size, description, mod_date, " +
            " is_dir) VALUES (?,?,?,?,?,?,?)", file_)
        fid = c.lastrowid
        permission_data = (fid, account, requester)
        c.execute("INSERT INTO permissions VALUES (?,?,?)", permission_data)
        self.conn.commit()
        c.close()
        return fid

    def _check_duplicate(self, account, requester, file_):
        c = self.conn.cursor()
        data = (account, requester, file_[1])
        c.execute("SELECT * FROM (files JOIN permissions ON" +
            " files.fid=permissions.fid) WHERE account=? AND requester=?" +
            " AND relative_path=? ", data)
        result = c.fetchall()
        if file_[2] != '':
            data = (account, requester, file_[2])
            c.execute("SELECT * FROM (files JOIN permissions ON" +
                " files.fid=permissions.fid) WHERE account=? AND requester=?" +
                " AND hash_sha1=?)", data)
            result.extend(c.fetchall())
        if len(result) > 0:
            raise Exception('Duplicated entry')
        c.close()

    def _delete_file(self, fid):
        c = self.conn.cursor()
        data = (fid, )
        c.execute("DELETE FROM files WHERE fid=?", data)
        self.conn.commit()
        c.close()

    def _delete_dir(self, dir_, account, requester):
        c = self.conn.cursor()
        data = (account, requester, dir_, dir_ + '/%')
        sql = "DELETE FROM files WHERE fid IN " + \
            " (SELECT files.fid FROM files, permissions WHERE" + \
            " files.fid=permissions.fid AND account=?"+ \
            " AND requester=? AND (relative_path=? OR relative_path LIKE ?))"
        c.execute(sql, data)
        self.conn.commit()
        c.close()

    def delete(self, account, requester, relative_path):
        c = self.conn.cursor()
        data = (account, requester, relative_path)
        c.execute("SELECT files.fid, is_dir FROM (files JOIN permissions ON" +
            " files.fid=permissions.fid) WHERE account=? AND requester=? AND " +
            "relative_path=? ", data)
        result = c.fetchone()
        c.close()
        if result[1] == 0:
            self._delete_file(result[0])
        else:
            self._delete_dir(relative_path, account, requester)

    def delete_all(self, account, requester):
        c = self.conn.cursor()
        data = (account, requester)
        sql = "DELETE FROM files WHERE fid IN (SELECT fid FROM permissions" + \
            " WHERE account=? AND requester=?)"
        c.execute(sql, data)
        self.conn.commit()
        c.close()


if __name__ == "__main__":
    """
    DELETE DATABASE FILE BEFORE RUNNING TESTS
    """
    import doctest
    path = sys.path[0]
    path = path + '/' + 'shared_files.db'
    conn = sqlite3.connect(path)
    # Enable foreign keys contraints
    conn.cursor().execute("pragma foreign_keys = on")
    FilesharingDatabase.create_database()
    doctest.testmod()
