# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
#
# This file is part of the OpenPGP Gajim Plugin.
#
# OpenPGP Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OpenPGP Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OpenPGP Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.

import sqlite3
import logging
from collections import namedtuple

from nbxmpp import JID

log = logging.getLogger('gajim.p.openpgp.sql')

TABLE_LAYOUT = '''
    CREATE TABLE contacts (
        jid JID,
        fingerprint TEXT,
        active BOOLEAN,
        trust INTEGER,
        timestamp INTEGER,
        comment TEXT
        );
    CREATE UNIQUE INDEX jid_fingerprint ON contacts (jid, fingerprint);'''


def _jid_adapter(jid):
    return str(jid)


def _jid_converter(jid):
    return JID(jid.decode())


sqlite3.register_adapter(JID, _jid_adapter)
sqlite3.register_converter('JID', _jid_converter)


class Storage:
    def __init__(self, folder_path):
        self._con = sqlite3.connect(str(folder_path / 'contacts.db'),
                                    detect_types=sqlite3.PARSE_DECLTYPES)



        self._con.row_factory = self._namedtuple_factory
        self._create_database()
        self._migrate_database()
        self._con.execute("PRAGMA synchronous=FULL;")
        self._con.commit()

    @staticmethod
    def _namedtuple_factory(cursor, row):
        fields = [col[0] for col in cursor.description]
        Row = namedtuple("Row", fields)
        named_row = Row(*row)
        return named_row

    def _user_version(self):
        return self._con.execute('PRAGMA user_version').fetchone()[0]

    def _create_database(self):
        if not self._user_version():
            log.info('Create contacts.db')
            self._execute_query(TABLE_LAYOUT)

    def _execute_query(self, query):
        transaction = """
            BEGIN TRANSACTION;
            %s
            PRAGMA user_version=1;
            END TRANSACTION;
            """ % (query)
        self._con.executescript(transaction)

    def _migrate_database(self):
        pass

    def load_contacts(self):
        return self._con.execute('SELECT * from contacts').fetchall()

    def save_contact(self, db_values):
        sql = '''REPLACE INTO
                 contacts(jid, fingerprint, active, trust, timestamp, comment)
                 VALUES(?, ?, ?, ?, ?, ?)'''
        for values in db_values:
            log.info('Store key: %s', values)
            self._con.execute(sql, values)
        self._con.commit()

    def set_trust(self, jid, fingerprint, trust):
        sql = 'UPDATE contacts SET trust = ? WHERE jid = ? AND fingerprint = ?'
        log.info('Set Trust: %s %s %s', trust, jid, fingerprint)
        self._con.execute(sql, (trust, jid, fingerprint))
        self._con.commit()

    def delete_key(self, jid, fingerprint):
        sql = 'DELETE from contacts WHERE jid = ? AND fingerprint = ?'
        log.info('Delete Key: %s %s', jid, fingerprint)
        self._con.execute(sql, (jid, fingerprint))
        self._con.commit()

    def cleanup(self):
        self._con.close()
