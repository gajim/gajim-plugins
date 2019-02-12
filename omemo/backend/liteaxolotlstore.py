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
    def __init__(self, connection):
        self.dbConn = connection
        self.dbConn.text_factory = bytes
        self.createDb()
        self.migrateDb()
        c = self.dbConn.cursor()
        c.execute("PRAGMA synchronous=NORMAL;")
        c.execute("PRAGMA journal_mode;")
        mode = c.fetchone()[0]
        # WAL is a persistent DB mode, don't override it if user has set it
        if mode != 'wal':
            c.execute("PRAGMA journal_mode=MEMORY;")
        self.dbConn.commit()

        if not self.getLocalRegistrationId():
            log.info("Generating OMEMO keys")
            self._generate_axolotl_keys()

    def _generate_axolotl_keys(self):
        identityKeyPair = KeyHelper.generateIdentityKeyPair()
        registrationId = KeyHelper.generateRegistrationId()
        preKeys = KeyHelper.generatePreKeys(KeyHelper.getRandomSequence(),
                                            DEFAULT_PREKEY_AMOUNT)
        self.storeLocalData(registrationId, identityKeyPair)

        signedPreKey = KeyHelper.generateSignedPreKey(
            identityKeyPair, KeyHelper.getRandomSequence(65536))

        self.storeSignedPreKey(signedPreKey.getId(), signedPreKey)

        for preKey in preKeys:
            self.storePreKey(preKey.getId(), preKey)

    def user_version(self):
        return self.dbConn.execute('PRAGMA user_version').fetchone()[0]

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
            self.dbConn.executescript(create_db_sql)

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

            self.dbConn.executescript(""" BEGIN TRANSACTION;
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

            self.dbConn.executescript(""" BEGIN TRANSACTION;
                                          %s
                                          PRAGMA user_version=3;
                                          END TRANSACTION;
                                      """ % (add_index))

        if self.user_version() < 4:
            # Adds column "active" to the sessions table
            add_active = """ ALTER TABLE sessions
                             ADD COLUMN active INTEGER DEFAULT 1;
                         """

            self.dbConn.executescript(""" BEGIN TRANSACTION;
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

            self.dbConn.executescript(""" BEGIN TRANSACTION;
                                          %s
                                          PRAGMA user_version=5;
                                          END TRANSACTION;
                                      """ % (add_timestamp))



    def loadSignedPreKey(self, signedPreKeyId):
        q = "SELECT record FROM signed_prekeys WHERE prekey_id = ?"

        cursor = self.dbConn.cursor()
        cursor.execute(q, (signedPreKeyId, ))

        result = cursor.fetchone()
        if not result:
            raise InvalidKeyIdException("No such signedprekeyrecord! %s " %
                                        signedPreKeyId)

        return SignedPreKeyRecord(serialized=result[0])

    def loadSignedPreKeys(self):
        q = "SELECT record FROM signed_prekeys"

        cursor = self.dbConn.cursor()
        cursor.execute(q, )
        result = cursor.fetchall()
        results = []
        for row in result:
            results.append(SignedPreKeyRecord(serialized=row[0]))

        return results

    def storeSignedPreKey(self, signedPreKeyId, signedPreKeyRecord):
        q = "INSERT INTO signed_prekeys (prekey_id, record) VALUES(?,?)"
        cursor = self.dbConn.cursor()
        cursor.execute(q, (signedPreKeyId, signedPreKeyRecord.serialize()))
        self.dbConn.commit()

    def containsSignedPreKey(self, signedPreKeyId):
        q = "SELECT record FROM signed_prekeys WHERE prekey_id = ?"
        cursor = self.dbConn.cursor()
        cursor.execute(q, (signedPreKeyId, ))
        return cursor.fetchone() is not None

    def removeSignedPreKey(self, signedPreKeyId):
        q = "DELETE FROM signed_prekeys WHERE prekey_id = ?"
        cursor = self.dbConn.cursor()
        cursor.execute(q, (signedPreKeyId, ))
        self.dbConn.commit()

    def getNextSignedPreKeyId(self):
        result = self.getCurrentSignedPreKeyId()
        if not result:
            return 1  # StartId if no SignedPreKeys exist
        else:
            return (result % (Medium.MAX_VALUE - 1)) + 1

    def getCurrentSignedPreKeyId(self):
        q = "SELECT MAX(prekey_id) FROM signed_prekeys"

        cursor = self.dbConn.cursor()
        cursor.execute(q)
        result = cursor.fetchone()
        if not result:
            return None
        else:
            return result[0]

    def getSignedPreKeyTimestamp(self, signedPreKeyId):
        q = "SELECT strftime('%s', timestamp) FROM " \
            "signed_prekeys WHERE prekey_id = ?"

        cursor = self.dbConn.cursor()
        cursor.execute(q, (signedPreKeyId, ))

        result = cursor.fetchone()
        if not result:
            raise InvalidKeyIdException("No such signedprekeyrecord! %s " %
                                        signedPreKeyId)

        return result[0]

    def removeOldSignedPreKeys(self, timestamp):
        q = "DELETE FROM signed_prekeys " \
            "WHERE timestamp < datetime(?, 'unixepoch')"
        cursor = self.dbConn.cursor()
        cursor.execute(q, (timestamp, ))
        self.dbConn.commit()

    def loadSession(self, recipientId, deviceId):
        q = "SELECT record FROM sessions WHERE recipient_id = ? AND device_id = ?"
        c = self.dbConn.cursor()
        c.execute(q, (recipientId, deviceId))
        result = c.fetchone()

        if result:
            return SessionRecord(serialized=result[0])
        else:
            return SessionRecord()

    def getSubDeviceSessions(self, recipientId):
        q = "SELECT device_id from sessions WHERE recipient_id = ?"
        c = self.dbConn.cursor()
        c.execute(q, (recipientId, ))
        result = c.fetchall()

        deviceIds = [r[0] for r in result]
        return deviceIds

    def getJidFromDevice(self, device_id):
        q = "SELECT recipient_id from sessions WHERE device_id = ?"
        c = self.dbConn.cursor()
        c.execute(q, (device_id, ))
        result = c.fetchone()

        return result[0].decode('utf-8') if result else None

    def getActiveDeviceTuples(self):
        q = "SELECT recipient_id, device_id FROM sessions WHERE active = 1"
        c = self.dbConn.cursor()
        result = []
        for row in c.execute(q):
            result.append((row[0].decode('utf-8'), row[1]))
        return result

    def storeSession(self, recipientId, deviceId, sessionRecord):
        self.deleteSession(recipientId, deviceId)

        q = "INSERT INTO sessions(recipient_id, device_id, record) VALUES(?,?,?)"
        c = self.dbConn.cursor()
        c.execute(q, (recipientId, deviceId, sessionRecord.serialize()))
        self.dbConn.commit()

    def containsSession(self, recipientId, deviceId):
        q = "SELECT record FROM sessions WHERE recipient_id = ? AND device_id = ?"
        c = self.dbConn.cursor()
        c.execute(q, (recipientId, deviceId))
        result = c.fetchone()

        return result is not None

    def deleteSession(self, recipientId, deviceId):
        q = "DELETE FROM sessions WHERE recipient_id = ? AND device_id = ?"
        self.dbConn.cursor().execute(q, (recipientId, deviceId))
        self.dbConn.commit()

    def deleteAllSessions(self, recipientId):
        q = "DELETE FROM sessions WHERE recipient_id = ?"
        self.dbConn.cursor().execute(q, (recipientId, ))
        self.dbConn.commit()

    def getAllSessions(self):
        q = "SELECT _id, recipient_id, device_id, record, active from sessions"
        c = self.dbConn.cursor()
        result = []
        for row in c.execute(q):
            result.append((row[0], row[1].decode('utf-8'), row[2], row[3], row[4]))
        return result

    def getSessionsFromJid(self, recipientId):
        q = "SELECT _id, recipient_id, device_id, record, active from sessions" \
            " WHERE recipient_id = ?"
        c = self.dbConn.cursor()
        result = []
        for row in c.execute(q, (recipientId,)):
            result.append((row[0], row[1].decode('utf-8'), row[2], row[3], row[4]))
        return result

    def getSessionsFromJids(self, recipientId):
        q = "SELECT _id, recipient_id, device_id, record, active from sessions" \
            " WHERE recipient_id IN ({})" \
            .format(', '.join(['?'] * len(recipientId)))
        c = self.dbConn.cursor()
        result = []
        for row in c.execute(q, recipientId):
            result.append((row[0], row[1].decode('utf-8'), row[2], row[3], row[4]))
        return result

    def setActiveState(self, deviceList, jid):
        c = self.dbConn.cursor()

        q = "UPDATE sessions SET active = {} " \
            "WHERE recipient_id = '{}' AND device_id IN ({})" \
            .format(1, jid, ', '.join(['?'] * len(deviceList)))
        c.execute(q, deviceList)

        q = "UPDATE sessions SET active = {} " \
            "WHERE recipient_id = '{}' AND device_id NOT IN ({})" \
            .format(0, jid, ', '.join(['?'] * len(deviceList)))
        c.execute(q, deviceList)
        self.dbConn.commit()

    def getInactiveSessionsKeys(self, recipientId):
        q = "SELECT record FROM sessions WHERE active = 0 AND recipient_id = ?"
        c = self.dbConn.cursor()
        result = []
        for row in c.execute(q, (recipientId,)):
            public_key = (SessionRecord(serialized=row[0]).
                          getSessionState().getRemoteIdentityKey().
                          getPublicKey())
            result.append(public_key.serialize())
        return result

    def loadPreKey(self, preKeyId):
        q = "SELECT record FROM prekeys WHERE prekey_id = ?"

        cursor = self.dbConn.cursor()
        cursor.execute(q, (preKeyId, ))

        result = cursor.fetchone()
        if not result:
            raise Exception("No such prekeyRecord!")

        return PreKeyRecord(serialized=result[0])

    def loadPendingPreKeys(self):
        q = "SELECT record FROM prekeys"
        cursor = self.dbConn.cursor()
        cursor.execute(q)
        result = cursor.fetchall()

        return [PreKeyRecord(serialized=r[0]) for r in result]

    def storePreKey(self, preKeyId, preKeyRecord):
        q = "INSERT INTO prekeys (prekey_id, record) VALUES(?,?)"
        cursor = self.dbConn.cursor()
        cursor.execute(q, (preKeyId, preKeyRecord.serialize()))
        self.dbConn.commit()

    def containsPreKey(self, preKeyId):
        q = "SELECT record FROM prekeys WHERE prekey_id = ?"
        cursor = self.dbConn.cursor()
        cursor.execute(q, (preKeyId, ))
        return cursor.fetchone() is not None

    def removePreKey(self, preKeyId):
        q = "DELETE FROM prekeys WHERE prekey_id = ?"
        cursor = self.dbConn.cursor()
        cursor.execute(q, (preKeyId, ))
        self.dbConn.commit()

    def getCurrentPreKeyId(self):
        q = "SELECT MAX(prekey_id) FROM prekeys"
        cursor = self.dbConn.cursor()
        cursor.execute(q)
        return cursor.fetchone()[0]

    def getPreKeyCount(self):
        q = "SELECT COUNT(prekey_id) FROM prekeys"
        cursor = self.dbConn.cursor()
        cursor.execute(q)
        return cursor.fetchone()[0]

    def generateNewPreKeys(self, count):
        startId = self.getCurrentPreKeyId() + 1
        preKeys = KeyHelper.generatePreKeys(startId, count)

        for preKey in preKeys:
            self.storePreKey(preKey.getId(), preKey)

    def getIdentityKeyPair(self):
        q = "SELECT public_key, private_key FROM identities " + \
            "WHERE recipient_id = -1"
        c = self.dbConn.cursor()
        c.execute(q)
        result = c.fetchone()

        publicKey, privateKey = result
        return IdentityKeyPair(
            IdentityKey(DjbECPublicKey(publicKey[1:])),
            DjbECPrivateKey(privateKey))

    def getLocalRegistrationId(self):
        q = "SELECT registration_id FROM identities WHERE recipient_id = -1"
        c = self.dbConn.cursor()
        c.execute(q)
        result = c.fetchone()
        return result[0] if result else None

    def storeLocalData(self, registrationId, identityKeyPair):
        q = "INSERT INTO identities( " + \
            "recipient_id, registration_id, public_key, private_key) " + \
            "VALUES(-1, ?, ?, ?)"
        c = self.dbConn.cursor()
        c.execute(q,
                  (registrationId,
                   identityKeyPair.getPublicKey().getPublicKey().serialize(),
                   identityKeyPair.getPrivateKey().serialize()))

        self.dbConn.commit()

    def saveIdentity(self, recipientId, identityKey):
        q = "INSERT INTO identities (recipient_id, public_key, trust) " \
            "VALUES(?, ?, ?)"
        c = self.dbConn.cursor()

        if not self.getIdentity(recipientId, identityKey):
            c.execute(q, (recipientId,
                          identityKey.getPublicKey().serialize(),
                          UNDECIDED))
            self.dbConn.commit()

    def getIdentity(self, recipientId, identityKey):
        q = "SELECT * FROM identities WHERE recipient_id = ? " \
            "AND public_key = ?"
        c = self.dbConn.cursor()

        c.execute(q, (recipientId, identityKey.getPublicKey().serialize()))
        result = c.fetchone()

        return result is not None

    def deleteIdentity(self, recipientId, identityKey):
        q = "DELETE FROM identities WHERE recipient_id = ? AND public_key = ?"
        c = self.dbConn.cursor()
        c.execute(q, (recipientId,
                      identityKey.getPublicKey().serialize()))
        self.dbConn.commit()

    def isTrustedIdentity(self, recipientId, identityKey):
        q = "SELECT trust FROM identities WHERE recipient_id = ? " \
            "AND public_key = ?"
        c = self.dbConn.cursor()

        c.execute(q, (recipientId, identityKey.getPublicKey().serialize()))
        result = c.fetchone()

        states = [UNTRUSTED, TRUSTED, UNDECIDED]

        if result and result[0] in states:
            return result[0]
        else:
            return True

    def getAllFingerprints(self):
        q = "SELECT _id, recipient_id, public_key, trust FROM identities " \
            "WHERE recipient_id != -1 ORDER BY recipient_id ASC"
        c = self.dbConn.cursor()

        result = []
        for row in c.execute(q):
            result.append((row[0], row[1], row[2], row[3]))
        return result

    def getFingerprints(self, jid):
        q = "SELECT _id, recipient_id, public_key, trust FROM identities " \
            "WHERE recipient_id =? ORDER BY trust ASC"
        c = self.dbConn.cursor()

        result = []
        c.execute(q, (jid,))
        rows = c.fetchall()
        for row in rows:
            result.append((row[0], row[1], row[2], row[3]))
        return result

    def getTrustedFingerprints(self, jid):
        q = "SELECT public_key FROM identities WHERE recipient_id = ? AND trust = ?"
        c = self.dbConn.cursor()

        result = []
        c.execute(q, (jid, TRUSTED))
        rows = c.fetchall()
        for row in rows:
            result.append(row[0])
        return result

    def getUndecidedFingerprints(self, jid):
        q = "SELECT trust FROM identities WHERE recipient_id = ? AND trust = ?"
        c = self.dbConn.cursor()

        result = []
        c.execute(q, (jid, UNDECIDED))
        result = c.fetchall()

        return result

    def getNewFingerprints(self, jid):
        q = "SELECT _id FROM identities WHERE shown = 0 AND " \
            "recipient_id = ?"
        c = self.dbConn.cursor()
        result = []
        for row in c.execute(q, (jid,)):
            result.append(row[0])
        return result

    def setShownFingerprints(self, fingerprints):
        q = "UPDATE identities SET shown = 1 WHERE _id IN ({})" \
            .format(', '.join(['?'] * len(fingerprints)))
        c = self.dbConn.cursor()
        c.execute(q, fingerprints)
        self.dbConn.commit()

    def setTrust(self, identityKey, trust):
        q = "UPDATE identities SET trust = ? WHERE public_key = ?"
        c = self.dbConn.cursor()
        c.execute(q, (trust, identityKey.getPublicKey().serialize()))
        self.dbConn.commit()

    def activate(self, jid):
        q = """INSERT OR REPLACE INTO encryption_state (jid, encryption)
               VALUES (?, 1) """

        c = self.dbConn.cursor()
        c.execute(q, (jid, ))
        self.dbConn.commit()

    def deactivate(self, jid):
        q = """INSERT OR REPLACE INTO encryption_state (jid, encryption)
               VALUES (?, 0)"""

        c = self.dbConn.cursor()
        c.execute(q, (jid, ))
        self.dbConn.commit()

    def is_active(self, jid):
        q = 'SELECT encryption FROM encryption_state where jid = ?;'
        c = self.dbConn.cursor()
        c.execute(q, (jid, ))
        result = c.fetchone()
        if result is None:
            return False
        return result[0]

    def exist(self, jid):
        q = 'SELECT encryption FROM encryption_state where jid = ?;'
        c = self.dbConn.cursor()
        c.execute(q, (jid, ))
        result = c.fetchone()
        if result is None:
            return False
        else:
            return True
