# Copyright (C) 2019 Philipp Hörist <philipp AT hoerist.com>
# Copyright (C) 2015 Tarek Galal <tare2.galal@gmail.com>
#
# This file is part of OMEMO Gajim Plugin.
#
# OMEMO Gajim Plugin is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# OMEMO Gajim Plugin is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OMEMO Gajim Plugin. If not, see <http://www.gnu.org/licenses/>.


import logging
import sqlite3
from collections import namedtuple

from axolotl.state.axolotlstore import AxolotlStore
from axolotl.state.signedprekeyrecord import SignedPreKeyRecord
from axolotl.state.sessionrecord import SessionRecord
from axolotl.state.prekeyrecord import PreKeyRecord
from axolotl.invalidkeyidexception import InvalidKeyIdException
from axolotl.ecc.djbec import DjbECPrivateKey
from axolotl.ecc.djbec import DjbECPublicKey
from axolotl.identitykey import IdentityKey
from axolotl.identitykeypair import IdentityKeyPair
from axolotl.util.medium import Medium
from axolotl.util.keyhelper import KeyHelper


log = logging.getLogger('gajim.plugin_system.omemo')

DEFAULT_PREKEY_AMOUNT = 100
MIN_PREKEY_AMOUNT = 80
SPK_ARCHIVE_TIME = 86400 * 15  # 15 Days
SPK_CYCLE_TIME = 86400         # 24 Hours

UNDECIDED = 2
TRUSTED = 1
UNTRUSTED = 0


class LiteAxolotlStore(AxolotlStore):
    def __init__(self, db_path):
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.row_factory = self._namedtuple_factory
        self.createDb()
        self.migrateDb()

        self._con.execute("PRAGMA secure_delete=1")
        self._con.execute("PRAGMA synchronous=NORMAL;")
        mode = self._con.execute("PRAGMA journal_mode;").fetchone()[0]

        # WAL is a persistent DB mode, don't override it if user has set it
        if mode != 'wal':
            self._con.execute("PRAGMA journal_mode=MEMORY;")
        self._con.commit()

        if not self.getLocalRegistrationId():
            log.info("Generating OMEMO keys")
            self._generate_axolotl_keys()

    @staticmethod
    def _namedtuple_factory(cursor, row):
        fields = []
        for col in cursor.description:
            if col[0] == '_id':
                fields.append('id')
            elif 'strftime' in col[0]:
                fields.append('formated_time')
            elif 'MAX' in col[0] or 'COUNT' in col[0]:
                col_name = col[0].replace('(', '_')
                col_name = col_name.replace(')', '')
                fields.append(col_name.lower())
            else:
                fields.append(col[0])
        return namedtuple("Row", fields)(*row)

    def _generate_axolotl_keys(self):
        identity_key_pair = KeyHelper.generateIdentityKeyPair()
        registration_id = KeyHelper.generateRegistrationId()
        pre_keys = KeyHelper.generatePreKeys(KeyHelper.getRandomSequence(),
                                             DEFAULT_PREKEY_AMOUNT)
        self.storeLocalData(registration_id, identity_key_pair)

        signed_pre_key = KeyHelper.generateSignedPreKey(
            identity_key_pair, KeyHelper.getRandomSequence(65536))

        self.storeSignedPreKey(signed_pre_key.getId(), signed_pre_key)

        for pre_key in pre_keys:
            self.storePreKey(pre_key.getId(), pre_key)

    def user_version(self):
        return self._con.execute('PRAGMA user_version').fetchone()[0]

    def createDb(self):
        if self.user_version() == 0:

            create_tables = '''
                CREATE TABLE IF NOT EXISTS identities (
                    _id INTEGER PRIMARY KEY AUTOINCREMENT, recipient_id TEXT,
                    registration_id INTEGER, public_key BLOB, private_key BLOB,
                    next_prekey_id INTEGER, timestamp INTEGER, trust INTEGER,
                    shown INTEGER DEFAULT 0);

                CREATE UNIQUE INDEX IF NOT EXISTS
                    public_key_index ON identities (public_key, recipient_id);

                CREATE TABLE IF NOT EXISTS prekeys(
                    _id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prekey_id INTEGER UNIQUE, sent_to_server BOOLEAN,
                    record BLOB);

                CREATE TABLE IF NOT EXISTS signed_prekeys (
                    _id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prekey_id INTEGER UNIQUE,
                    timestamp NUMERIC DEFAULT CURRENT_TIMESTAMP, record BLOB);

                CREATE TABLE IF NOT EXISTS sessions (
                    _id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recipient_id TEXT, device_id INTEGER,
                    record BLOB, timestamp INTEGER, active INTEGER DEFAULT 1,
                    UNIQUE(recipient_id, device_id));

                CREATE TABLE IF NOT EXISTS encryption_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    jid TEXT UNIQUE,
                    encryption INTEGER
                    );
                '''

            create_db_sql = """
                BEGIN TRANSACTION;
                %s
                PRAGMA user_version=5;
                END TRANSACTION;
                """ % (create_tables)
            self._con.executescript(create_db_sql)

    def migrateDb(self):
        """ Migrates the DB
        """

        # Find all double entries and delete them
        if self.user_version() < 2:
            delete_dupes = """ DELETE FROM identities WHERE _id not in (
                                SELECT MIN(_id)
                                FROM identities
                                GROUP BY
                                recipient_id, public_key
                                );
                            """

            self._con.executescript(
                """ BEGIN TRANSACTION;
                    %s
                    PRAGMA user_version=2;
                    END TRANSACTION;
                """ % (delete_dupes))

        if self.user_version() < 3:
            # Create a UNIQUE INDEX so every public key/recipient_id tuple
            # can only be once in the db
            add_index = """ CREATE UNIQUE INDEX IF NOT EXISTS
                            public_key_index
                            ON identities (public_key, recipient_id);
                        """

            self._con.executescript(
                """ BEGIN TRANSACTION;
                    %s
                    PRAGMA user_version=3;
                    END TRANSACTION;
                """ % (add_index))

        if self.user_version() < 4:
            # Adds column "active" to the sessions table
            add_active = """ ALTER TABLE sessions
                             ADD COLUMN active INTEGER DEFAULT 1;
                         """

            self._con.executescript(
                """ BEGIN TRANSACTION;
                    %s
                    PRAGMA user_version=4;
                    END TRANSACTION;
                """ % (add_active))

        if self.user_version() < 5:
            # Adds DEFAULT Timestamp
            add_timestamp = """
                DROP TABLE signed_prekeys;
                CREATE TABLE IF NOT EXISTS signed_prekeys (
                    _id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prekey_id INTEGER UNIQUE,
                    timestamp NUMERIC DEFAULT CURRENT_TIMESTAMP, record BLOB);
                ALTER TABLE identities ADD COLUMN shown INTEGER DEFAULT 0;
                UPDATE identities SET shown = 1;
            """

            self._con.executescript(
                """ BEGIN TRANSACTION;
                    %s
                    PRAGMA user_version=5;
                    END TRANSACTION;
                """ % (add_timestamp))


    def loadSignedPreKey(self, signedPreKeyId):
        query = 'SELECT record FROM signed_prekeys WHERE prekey_id = ?'
        result = self._con.execute(query, (signedPreKeyId, )).fetchone()
        if result is None:
            raise InvalidKeyIdException("No such signedprekeyrecord! %s " %
                                        signedPreKeyId)
        return SignedPreKeyRecord(serialized=result.record)

    def loadSignedPreKeys(self):
        query = 'SELECT record FROM signed_prekeys'
        results = self._con.execute(query).fetchall()
        return [SignedPreKeyRecord(serialized=row.record) for row in results]

    def storeSignedPreKey(self, signedPreKeyId, signedPreKeyRecord):
        query = 'INSERT INTO signed_prekeys (prekey_id, record) VALUES(?,?)'
        self._con.execute(query, (signedPreKeyId,
                                  signedPreKeyRecord.serialize()))
        self._con.commit()

    def containsSignedPreKey(self, signedPreKeyId):
        query = 'SELECT record FROM signed_prekeys WHERE prekey_id = ?'
        result = self._con.execute(query, (signedPreKeyId,)).fetchone()
        return result is not None

    def removeSignedPreKey(self, signedPreKeyId):
        query = 'DELETE FROM signed_prekeys WHERE prekey_id = ?'
        self._con.execute(query, (signedPreKeyId,))
        self._con.commit()

    def getNextSignedPreKeyId(self):
        result = self.getCurrentSignedPreKeyId()
        if result is None:
            return 1  # StartId if no SignedPreKeys exist
        return (result % (Medium.MAX_VALUE - 1)) + 1

    def getCurrentSignedPreKeyId(self):
        query = 'SELECT MAX(prekey_id) FROM signed_prekeys'
        result = self._con.execute(query).fetchone()
        return result.max_prekey_id if result is not None else None

    def getSignedPreKeyTimestamp(self, signedPreKeyId):
        query = '''SELECT strftime('%s', timestamp) FROM
                   signed_prekeys WHERE prekey_id = ?'''

        result = self._con.execute(query, (signedPreKeyId,)).fetchone()
        if result is None:
            raise InvalidKeyIdException('No such signedprekeyrecord! %s' %
                                        signedPreKeyId)

        return result.formated_time

    def removeOldSignedPreKeys(self, timestamp):
        query = '''DELETE FROM signed_prekeys
                   WHERE timestamp < datetime(?, "unixepoch")'''
        self._con.execute(query, (timestamp,))
        self._con.commit()

    def loadSession(self, recipientId, deviceId):
        query = '''SELECT record FROM sessions WHERE
                   recipient_id = ? AND device_id = ?'''
        result = self._con.execute(query, (recipientId, deviceId)).fetchone()
        if result is None:
            return SessionRecord()
        return SessionRecord(serialized=result.record)

    def getJidFromDevice(self, device_id):
        query = 'SELECT recipient_id from sessions WHERE device_id = ?'
        result = self._con.execute(query, (device_id, )).fetchone()
        return result.recipient_id if result is not None else None

    def getActiveDeviceTuples(self):
        query = 'SELECT recipient_id, device_id FROM sessions WHERE active = 1'
        return self._con.execute(query).fetchall()

    def storeSession(self, recipientId, deviceId, sessionRecord):
        self.deleteSession(recipientId, deviceId)

        query = '''INSERT INTO sessions(recipient_id, device_id, record)
                   VALUES(?,?,?)'''
        self._con.execute(query, (recipientId,
                                  deviceId,
                                  sessionRecord.serialize()))
        self._con.commit()

    def containsSession(self, recipientId, deviceId):
        query = '''SELECT record FROM sessions
                   WHERE recipient_id = ? AND device_id = ?'''
        result = self._con.execute(query, (recipientId, deviceId)).fetchone()
        return result is not None

    def deleteSession(self, recipientId, deviceId):
        query = "DELETE FROM sessions WHERE recipient_id = ? AND device_id = ?"
        self._con.execute(query, (recipientId, deviceId))
        self._con.commit()

    def deleteAllSessions(self, recipientId):
        query = 'DELETE FROM sessions WHERE recipient_id = ?'
        self._con.execute(query, (recipientId,))
        self._con.commit()

    def getSessionsFromJid(self, recipientId):
        query = '''SELECT _id, recipient_id, device_id, record, active
                   from sessions WHERE recipient_id = ?'''
        return self._con.execute(query, (recipientId,)).fetchall()

    def getSessionsFromJids(self, recipientIds):
        query = '''SELECT _id, recipient_id, device_id, record, active from sessions
                   WHERE recipient_id IN ({})'''.format(
                       ', '.join(['?'] * len(recipientIds)))
        return self._con.execute(query, recipientIds).fetchall()

    def setActiveState(self, deviceList, jid):
        query = '''UPDATE sessions SET active = 1
                   WHERE recipient_id = ? AND device_id IN ({})'''.format(
                       ', '.join(['?'] * len(deviceList)))
        self._con.execute(query, (jid,) + tuple(deviceList))

        query = '''UPDATE sessions SET active = 0
                   WHERE recipient_id = ? AND device_id NOT IN ({})'''.format(
                       ', '.join(['?'] * len(deviceList)))
        self._con.execute(query, (jid,) + tuple(deviceList))
        self._con.commit()

    def getInactiveSessionsKeys(self, recipientId):
        query = '''SELECT record FROM sessions
                   WHERE active = 0 AND recipient_id = ?'''
        result = self._con.execute(query, (recipientId,)).fetchall()

        results = []
        for row in result:
            public_key = (SessionRecord(serialized=row.record).
                          getSessionState().getRemoteIdentityKey().
                          getPublicKey())
            results.append(public_key.serialize())
        return results

    def loadPreKey(self, preKeyId):
        query = '''SELECT record FROM prekeys WHERE prekey_id = ?'''

        result = self._con.execute(query, (preKeyId,)).fetchone()
        if result is None:
            raise Exception("No such prekeyRecord!")
        return PreKeyRecord(serialized=result.record)

    def loadPendingPreKeys(self):
        query = '''SELECT record FROM prekeys'''
        result = self._con.execute(query).fetchall()
        return [PreKeyRecord(serialized=row.record) for row in result]

    def storePreKey(self, preKeyId, preKeyRecord):
        query = 'INSERT INTO prekeys (prekey_id, record) VALUES(?,?)'
        self._con.execute(query, (preKeyId, preKeyRecord.serialize()))
        self._con.commit()

    def containsPreKey(self, preKeyId):
        query = 'SELECT record FROM prekeys WHERE prekey_id = ?'
        result = self._con.execute(query, (preKeyId,)).fetchone()
        return result is not None

    def removePreKey(self, preKeyId):
        query = 'DELETE FROM prekeys WHERE prekey_id = ?'
        self._con.execute(query, (preKeyId,))
        self._con.commit()

    def getCurrentPreKeyId(self):
        query = 'SELECT MAX(prekey_id) FROM prekeys'
        return self._con.execute(query).fetchone().max_prekey_id

    def getPreKeyCount(self):
        query = 'SELECT COUNT(prekey_id) FROM prekeys'
        return self._con.execute(query).fetchone().count_prekey_id

    def generateNewPreKeys(self, count):
        start_id = self.getCurrentPreKeyId() + 1
        pre_keys = KeyHelper.generatePreKeys(start_id, count)

        for pre_key in pre_keys:
            self.storePreKey(pre_key.getId(), pre_key)

    def getIdentityKeyPair(self):
        query = '''SELECT public_key, private_key FROM identities
                   WHERE recipient_id = -1'''
        result = self._con.execute(query).fetchone()

        return IdentityKeyPair(
            IdentityKey(DjbECPublicKey(result.public_key[1:])),
            DjbECPrivateKey(result.private_key))

    def getLocalRegistrationId(self):
        query = 'SELECT registration_id FROM identities WHERE recipient_id = -1'
        result = self._con.execute(query).fetchone()
        return result.registration_id if result is not None else None

    def storeLocalData(self, registrationId, identityKeyPair):
        query = '''INSERT INTO identities(
                   recipient_id, registration_id, public_key, private_key) 
                   VALUES(-1, ?, ?, ?)'''

        public_key = identityKeyPair.getPublicKey().getPublicKey().serialize()
        private_key = identityKeyPair.getPrivateKey().serialize()
        self._con.execute(query, (registrationId, public_key, private_key))
        self._con.commit()

    def saveIdentity(self, recipientId, identityKey):
        query = '''INSERT INTO identities (recipient_id, public_key, trust)
                   VALUES(?, ?, ?)'''
        if not self.containsIdentity(recipientId, identityKey):
            self._con.execute(query, (recipientId,
                                      identityKey.getPublicKey().serialize(),
                                      UNDECIDED))
            self._con.commit()

    def containsIdentity(self, recipientId, identityKey):
        query = '''SELECT * FROM identities WHERE recipient_id = ?
                   AND public_key = ?'''

        public_key = identityKey.getPublicKey().serialize()
        result = self._con.execute(query, (recipientId,
                                           public_key)).fetchone()

        return result is not None

    def deleteIdentity(self, recipientId, identityKey):
        query = '''DELETE FROM identities
                   WHERE recipient_id = ? AND public_key = ?'''
        public_key = identityKey.getPublicKey().serialize()
        self._con.execute(query, (recipientId, public_key))
        self._con.commit()

    def isTrustedIdentity(self, recipientId, identityKey):
        query = '''SELECT trust FROM identities WHERE recipient_id = ?
                   AND public_key = ?'''
        public_key = identityKey.getPublicKey().serialize()
        result = self._con.execute(query, (recipientId, public_key)).fetchone()
        if result is None:
            return True

        states = [UNTRUSTED, TRUSTED, UNDECIDED]
        if result.trust in states:
            return result.trust
        return False

    def getAllFingerprints(self):
        query = '''SELECT _id, recipient_id, public_key, trust FROM identities
                   WHERE recipient_id != -1 ORDER BY recipient_id ASC'''
        return self._con.execute(query).fetchall()

    def getFingerprints(self, jid):
        query = '''SELECT _id, recipient_id, public_key, trust FROM identities
                   WHERE recipient_id =? ORDER BY trust ASC'''
        return self._con.execute(query, (jid,)).fetchall()

    def getTrustedFingerprints(self, jid):
        query = '''SELECT public_key FROM identities
                   WHERE recipient_id = ? AND trust = ?'''
        result = self._con.execute(query, (jid, TRUSTED)).fetchall()
        return [row.public_key for row in result]

    def getUndecidedFingerprints(self, jid):
        query = '''SELECT trust FROM identities
                   WHERE recipient_id = ? AND trust = ?'''
        return self._con.execute(query, (jid, UNDECIDED)).fetchall()

    def getNewFingerprints(self, jid):
        query = '''SELECT _id FROM identities WHERE shown = 0
                   AND recipient_id = ?'''

        result = self._con.execute(query, (jid,)).fetchall()
        return [row.id for row in result]

    def setShownFingerprints(self, fingerprints):
        query = 'UPDATE identities SET shown = 1 WHERE _id IN ({})'.format(
            ', '.join(['?'] * len(fingerprints)))
        self._con.execute(query, fingerprints)
        self._con.commit()

    def setTrust(self, identityKey, trust):
        query = 'UPDATE identities SET trust = ? WHERE public_key = ?'
        public_key = identityKey.getPublicKey().serialize()
        self._con.execute(query, (trust, public_key))
        self._con.commit()

    def activate(self, jid):
        query = '''INSERT OR REPLACE INTO encryption_state (jid, encryption)
                   VALUES (?, 1)'''

        self._con.execute(query, (jid,))
        self._con.commit()

    def deactivate(self, jid):
        query = '''INSERT OR REPLACE INTO encryption_state (jid, encryption)
                   VALUES (?, 0)'''

        self._con.execute(query, (jid, ))
        self._con.commit()

    def is_active(self, jid):
        query = 'SELECT encryption FROM encryption_state where jid = ?'
        result = self._con.execute(query, (jid,)).fetchone()
        return result.encryption if result is not None else False

    def exist(self, jid):
        query = 'SELECT encryption FROM encryption_state where jid = ?'
        result = self._con.execute(query, (jid,)).fetchone()
        return result is not None
