"""Atomic THQ cloud storage and signed-principal mailbox permissions.

Gift payloads stay unchanged in SQLite. MAP_GET responses use the original
SDK entry wrapper with per-key last-writer metadata. Authentication is handled
by the service before supplying the signed principal to this module.
"""
import json
import os
import sqlite3
import threading
import time
import re
import base64
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from service_limits import RateLimit


GIFT_DOCUMENTS = frozenset({'TomeGift', 'TomeGiftJP'})
SUPPORTED_DOCUMENTS = GIFT_DOCUMENTS | {'GameToWeb'}


def empty_inbox_reply(method, path):
    parts = urlsplit(path)
    if method != "GET" or parts.path != "/thqconnect/cloud/execute":
        return None
    query = parse_qs(parts.query, keep_blank_values=True)
    if query.get('docKeys') not in ([name] for name in GIFT_DOCUMENTS):
        return None
    expected = {"ops": "MAP_GET", "keys": "",
                "values": "", "version": "1", "platform": "PS3_PSN",
                "title": "Darksiders2"}
    if any(query.get(key) != [value] for key, value in expected.items()):
        return None
    profiles = query.get("profileNames", [])
    if len(profiles) != 1 or not profiles[0].startswith("/psn/"):
        return None
    if len(profiles[0]) <= len("/psn/") or "," in profiles[0]:
        return None
    # version=1 uses positional JSON arrays. The reader ignores field labels:
    # 0x67d0e4: [resultCode, data]; 0x1220aa4: array of documents;
    # 0x67ce30: [status, document, docPolicyBits, lastModifiedTime,
    #            lastModifiedProfileName]. This only specifies the wire format;
    # gameplay compatibility is recorded separately in the documentation.
    payload = [0, [[0, "{}", 0, 0, ""]]]
    return json.dumps(payload, separators=(",", ":")).encode("ascii") + b"\n"


class CloudStore:
    """Cloud document/map operations; a batch commits before reporting success."""

    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.mutations = RateLimit(1, 10, 20, 40)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = None
        if fd is not None:
            try:
                if os.getuid() == 0 and "SUDO_UID" in os.environ:
                    os.fchown(fd, int(os.environ["SUDO_UID"]), int(os.environ["SUDO_GID"]))
            finally:
                os.close(fd)
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS documents (
                profile TEXT NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL,
                policy INTEGER NOT NULL, modified INTEGER NOT NULL,
                modified_by TEXT NOT NULL, PRIMARY KEY (profile, name))""")
            connection.execute('''CREATE TABLE IF NOT EXISTS profile_owners (
                profile TEXT PRIMARY KEY, account_id TEXT NOT NULL)''')
            connection.execute('''CREATE TABLE IF NOT EXISTS map_metadata (
                profile TEXT NOT NULL, name TEXT NOT NULL, key TEXT NOT NULL,
                modified INTEGER NOT NULL, modified_by TEXT NOT NULL,
                PRIMARY KEY (profile, name, key))''')

    def reply(self, method, path, body, actor=None):
        parts = urlsplit(path)
        if method not in {"GET", "POST"} or parts.path != "/thqconnect/cloud/execute":
            return None
        query = parse_qs(parts.query, keep_blank_values=True)
        if method == "POST":
            try:
                posted = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            except UnicodeDecodeError:
                return None
            for key, values in posted.items():
                query.setdefault(key, []).extend(values)
        required = {"version": "1", "platform": "PS3_PSN", "title": "Darksiders2"}
        if any(query.get(key) != [value] for key, value in required.items()):
            return None
        fields = {}
        for key in ("profileNames", "ops", "docKeys", "keys", "values"):
            values = query.get(key, [])
            if len(values) != 1:
                return None
            fields[key] = values[0]
        operations = fields["ops"].split(",")
        count = len(operations)
        if not 1 <= count <= 64:
            return None
        vectors = {key: (value.split(",") if count > 1 else [value])
                   for key, value in fields.items()}
        if any(len(values) != count for values in vectors.values()):
            return None
        parameters = {}
        for name, default in (("policy", "0"), ("worldPerms", "-1"), ("friendPerms", "-1")):
            values = query.get(name, [default])
            if len(values) != 1:
                return None
            split = values[0].split(",")
            if len(split) == 1:
                split *= count
            if len(split) != count:
                return None
            try:
                parameters[name] = [int(value) for value in split]
            except ValueError:
                return None
        if any(not 0 <= value <= 0x7fffffff for value in parameters['policy']):
            return None
        if any(not -1 <= value <= 0x7fffffff for name in ('worldPerms', 'friendPerms') for value in parameters[name]):
            return None
        prepared = []
        for index, operation in enumerate(operations):
            profile, document, key, value = (vectors[name][index] for name in
                                            ('profileNames', 'docKeys', 'keys', 'values'))
            if not re.fullmatch(r'/psn/[A-Za-z0-9_-]{1,32}', profile):
                return None
            if document not in SUPPORTED_DOCUMENTS:
                return None
            if operation not in {'GET', 'SET', 'REMOVE', 'MAP_GET', 'MAP_SET', 'MAP_REMOVE', 'SET_PERM'}:
                return None
            if operation in {'GET', 'SET', 'REMOVE', 'SET_PERM'} and key:
                return None
            if operation in {'GET', 'REMOVE', 'MAP_REMOVE', 'SET_PERM'} and value:
                return None
            if operation == 'MAP_GET' and (key or value):
                return None  # Full map reads have been observed; keyed reads are not guessed.
            if operation in {'MAP_SET', 'MAP_REMOVE'} and (not key or ',' in key or len(key) > 256):
                return None
            replacement = None
            if operation == 'SET' and value:
                try:
                    replacement = json.loads(value)
                except ValueError:
                    return None
                if not isinstance(replacement, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                           for k, v in replacement.items()):
                    return None
            prepared.append((profile.lower(), operation, document, key, value, parameters['policy'][index], replacement))
        if actor is not None:
            for profile, operation, document, key, value, policy, replacement in prepared:
                sending = operation == 'MAP_SET' and document in GIFT_DOCUMENTS
                if profile != actor.profile and not sending:
                    raise ValueError('Cross-profile operation denied')
                if document in GIFT_DOCUMENTS and operation == 'SET' and value:
                    raise ValueError('Gift document replacement denied')
                if sending:
                    try:
                        item = base64.b64decode(value, validate=True)
                    except ValueError as exc:
                        raise ValueError('Invalid gift encoding') from exc
                    if not 32 <= len(item) <= 32768 or item[:4] != b'BOD\xfd':
                        raise ValueError('Unsupported gift envelope')
                if len(value) > 65536:
                    raise ValueError('Cloud value quota exceeded')
            if any(operation not in {'GET','MAP_GET'} for _,operation,*_ in prepared):
                if not self.mutations.allow(actor.account_id):
                    raise ValueError('Account mutation rate exceeded')
        results = []
        with self.lock, sqlite3.connect(self.path, timeout=10) as connection:
            # Prevent concurrent readers/writers losing another batch's changes.
            connection.execute('BEGIN IMMEDIATE')
            if actor is not None:
                owner = connection.execute('SELECT account_id FROM profile_owners WHERE profile=?', (actor.profile,)).fetchone()
                if owner and owner[0] != actor.account_id:
                    raise ValueError('Profile belongs to another PSN account')
                if not owner and connection.execute('SELECT COUNT(*) FROM profile_owners').fetchone()[0] >= 20000:
                    raise ValueError('Service profile quota exceeded')
                connection.execute('INSERT OR IGNORE INTO profile_owners VALUES (?,?)',(actor.profile,actor.account_id))
                total_bytes, document_count = connection.execute(
                    'SELECT COALESCE(SUM(length(CAST(data AS BLOB))),0),COUNT(*) FROM documents').fetchone()
            for profile, operation, document, key, value, policy, replacement in prepared:
                row = connection.execute(
                    'SELECT data, policy, modified, modified_by FROM documents WHERE profile=? AND name=?',
                    (profile, document)).fetchone()
                mapping, stored_policy, modified, modified_by = ({}, 0, 0, '') if row is None else (json.loads(row[0]), *row[1:])
                if not isinstance(mapping, dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in mapping.items()):
                    raise ValueError('Invalid stored cloud document')
                # Preserve the last writer per key, including legacy entries,
                # before document initialization changes its outer metadata.
                connection.executemany('INSERT OR IGNORE INTO map_metadata VALUES (?,?,?,?,?)',
                    [(profile, document, k, modified, modified_by) for k in mapping])
                changed = operation not in {'GET', 'MAP_GET'}
                if operation == 'MAP_SET':
                    if actor is not None and document in GIFT_DOCUMENTS and key in mapping:
                        if mapping[key] != value:
                            raise ValueError('Existing gift overwrite denied')
                        changed = False  # Identical retries preserve the existing gift.
                    mapping[key] = value
                elif operation == 'MAP_REMOVE':
                    mapping.pop(key, None)  # Retry after a received item is safe.
                    connection.execute('DELETE FROM map_metadata WHERE profile=? AND name=? AND key=?',
                                       (profile, document, key))
                elif operation == 'SET' and replacement is not None:
                    mapping = replacement
                    connection.execute('DELETE FROM map_metadata WHERE profile=? AND name=?', (profile, document))
                elif operation == 'REMOVE':
                    connection.execute('DELETE FROM documents WHERE profile=? AND name=?', (profile, document))
                    connection.execute('DELETE FROM map_metadata WHERE profile=? AND name=?', (profile, document))
                    mapping, stored_policy = {}, 0
                # Captured initialization SETs carry empty values and policy1.
                # They initialize/update metadata, preserving any queued gifts.
                if changed:
                    modified = int(time.time())  # Client's signed32-bit seconds reader.
                    modified_by = actor.profile if actor is not None else profile
                    if operation == 'MAP_SET':
                        connection.execute('''INSERT INTO map_metadata VALUES (?,?,?,?,?)
                            ON CONFLICT(profile,name,key) DO UPDATE SET
                            modified=excluded.modified,modified_by=excluded.modified_by''',
                            (profile, document, key, modified, modified_by))
                    elif operation == 'SET' and replacement is not None:
                        connection.executemany('INSERT INTO map_metadata VALUES (?,?,?,?,?)',
                            [(profile, document, k, modified, modified_by) for k in mapping])
                    if operation != 'REMOVE':
                        stored_policy = policy
                        encoded = json.dumps(mapping, ensure_ascii=True, separators=(',', ':'))
                        if actor is not None:
                            new_size = len(encoded.encode('ascii'))
                            if new_size > 512*1024 or (document in GIFT_DOCUMENTS and len(mapping)>128):
                                raise ValueError('Mailbox quota exceeded')
                            total_bytes += new_size - (len(row[0].encode('utf-8')) if row else 0)
                            document_count += int(row is None)
                            if total_bytes > 64*1024*1024 or document_count > 20000:
                                raise ValueError('Service storage quota exceeded')
                        connection.execute('''INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)
                            ON CONFLICT(profile,name) DO UPDATE SET data=excluded.data,policy=excluded.policy,
                            modified=excluded.modified,modified_by=excluded.modified_by''',
                            (profile, document, encoded, stored_policy, modified, modified_by))
                    elif actor is not None and row:
                        total_bytes -= len(row[0].encode('utf-8'))
                        document_count -= 1
                if actor is not None and profile != actor.profile:
                    # A sender receives only its own entry, never the recipient's inbox.
                    mapping = {key: value}
                    stored_policy, modified, modified_by = policy, int(time.time()), actor.profile
                wire = mapping
                if operation == 'MAP_GET' and mapping:
                    # Version 1 ignores field labels: GetMap reads an array
                    # of [key,[value,lastModifiedName,lastModifiedDate]].
                    # Keep {} for the already-tested empty representation.
                    metadata = {k:(date,who) for k,date,who in connection.execute(
                        'SELECT key,modified,modified_by FROM map_metadata WHERE profile=? AND name=?',
                        (profile, document))}
                    wire = [[k, [v, metadata[k][1], metadata[k][0]]]
                        for k,v in mapping.items()]
                encoded = json.dumps(wire, ensure_ascii=True, separators=(',', ':'))
                results.append([0, encoded, stored_policy, modified, modified_by])
            connection.commit()
        payload = [0, results]
        return json.dumps(payload, separators=(",", ":")).encode("ascii") + b"\n"
