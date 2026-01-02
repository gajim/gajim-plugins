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

from typing import Any
from typing import NamedTuple

import logging
import sqlite3
from collections import namedtuple
from collections.abc import Iterator
from pathlib import Path

from nbxmpp.protocol import JID

from openpgp.modules.util import Trust

log = logging.getLogger("gajim.p.openpgp.sql")

TABLE_LAYOUT = """
    CREATE TABLE contacts (
        jid TEXT,
        fingerprint TEXT,
        active BOOLEAN,
        trust INTEGER,
        timestamp INTEGER,
        comment TEXT
        );
    CREATE UNIQUE INDEX jid_fingerprint ON contacts (jid, fingerprint);"""


class ContactRow(NamedTuple):
    jid: JID
    fingerprint: str
    active: bool
    trust: Trust
    timestamp: float


class Storage:
    def __init__(self, folder_path: Path) -> None:
        self._con = sqlite3.connect(
            str(folder_path / "contacts.db"), detect_types=sqlite3.PARSE_COLNAMES
        )

        self._con.row_factory = self._namedtuple_factory
        self._create_database()
        self._migrate_database()
        self._con.execute("PRAGMA synchronous=FULL;")
        self._con.commit()

    @staticmethod
    def _namedtuple_factory(cursor: sqlite3.Cursor, row: Any) -> Any:
        fields = [col[0] for col in cursor.description]
        Row = namedtuple("Row", fields)  # pyright: ignore
        named_row = Row(*row)
        return named_row

    def _user_version(self) -> int:
        return self._con.execute("PRAGMA user_version").fetchone()[0]

    def _create_database(self) -> None:
        if not self._user_version():
            log.info("Create contacts.db")
            self._execute_query(TABLE_LAYOUT)

    def _execute_query(self, query: str) -> None:
        transaction = """
            BEGIN TRANSACTION;
            %s
            PRAGMA user_version=1;
            END TRANSACTION;
            """ % (query)
        self._con.executescript(transaction)

    def _migrate_database(self) -> None:
        pass

    def load_contacts(self) -> list[ContactRow]:
        sql = """SELECT jid as "jid [jid]",
                        fingerprint,
                        active,
                        trust,
                        timestamp
                FROM contacts"""

        return self._con.execute(sql).fetchall()

    def save_contact(
        self, db_values: Iterator[tuple[JID, str, bool, Trust, float]]
    ) -> None:
        sql = """REPLACE INTO
                 contacts(jid, fingerprint, active, trust, timestamp)
                 VALUES(?, ?, ?, ?, ?)"""
        for values in db_values:
            log.info("Store key: %s", values)
            self._con.execute(sql, values)
        self._con.commit()

    def set_trust(self, jid: JID, fingerprint: str, trust: Trust) -> None:
        sql = "UPDATE contacts SET trust = ? WHERE jid = ? AND fingerprint = ?"
        log.info("Set Trust: %s %s %s", trust, jid, fingerprint)
        self._con.execute(sql, (trust, jid, fingerprint))
        self._con.commit()

    def delete_key(self, jid: JID, fingerprint: str) -> None:
        sql = "DELETE from contacts WHERE jid = ? AND fingerprint = ?"
        log.info("Delete Key: %s %s", jid, fingerprint)
        self._con.execute(sql, (jid, fingerprint))
        self._con.commit()

    def cleanup(self) -> None:
        self._con.close()
