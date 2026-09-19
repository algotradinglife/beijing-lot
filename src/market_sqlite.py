"""Transactional storage of structured market records; never retain page bodies.

Input records are already parsed by source adapters. This module does not fetch,
infer availability, select quotes, or delete source files.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def canonical_market_record(value):
    """Return deterministic UTF-8 JSON; reject nonfinite numbers/page bodies."""
    if isinstance(value, dict):
        if {"body_base64", "raw_html", "raw_body", "html_body"}.intersection(value):
            raise ValueError("page bodies are not allowed in structured storage")
        for child in value.values():
            canonical_market_record(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            canonical_market_record(child)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def open_market_database(path):
    """Open/create a structured market DB. Caller owns/ closes the connection.

    Uses durable rollback journaling suitable for the mounted storage. Existing
    unknown schemas fail closed. No scraping, source deletion or hidden paths.
    """
    connection = sqlite3.connect(Path(path), timeout=30)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise ValueError("unsupported market database schema")
        if version == 1 and connection.execute("PRAGMA application_id").fetchone()[0] != 1112165715:
            raise ValueError("unrelated database identity")
        if version == 0:
            if connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError("refuse unrelated database")
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE migration_batch (
                    batch_id TEXT PRIMARY KEY, input_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state='IMPORTED_PENDING_ACCEPTANCE'),
                    receipt_json TEXT NOT NULL CHECK(json_valid(receipt_json))
                );
                CREATE TABLE batch_issue (
                    issue TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES migration_batch(batch_id)
                );
                CREATE TABLE market_record (
                    batch_id TEXT NOT NULL REFERENCES migration_batch(batch_id),
                    kind TEXT NOT NULL CHECK(kind IN ('capture','quote','fixture_market','anomaly','evidence')),
                    record_key TEXT NOT NULL, issue TEXT NOT NULL REFERENCES batch_issue(issue),
                    provider_id TEXT, market TEXT, source_url TEXT,
                    source_sha256 TEXT, record_json TEXT NOT NULL CHECK(json_valid(record_json)),
                    record_sha256 TEXT NOT NULL,
                    PRIMARY KEY(batch_id, kind, record_key)
                );
                CREATE INDEX market_record_issue ON market_record(issue,kind);
                CREATE INDEX market_record_provider ON market_record(provider_id,market);
                PRAGMA user_version=1;
                PRAGMA application_id=1112165715;
                COMMIT;
            """)
        return connection
    except BaseException:
        connection.close()
        raise


def import_market_batch(connection, *, batch_id, issues, records, receipt):
    """Atomically insert exactly 50 issues and an iterable of structured records.

    Each record has kind/key/issue and a data object retaining source fields and
    quote order. Optional provider_id/market/source_url/source_sha256 are indexed.
    Receipt must bind a lowercase SHA-256 input identity. Repeated identical
    batches are replay-checked; changed rows/receipts fail and roll back.
    Return record count. Import alone does NOT authorize any source deletion.
    """
    if not isinstance(batch_id, str) or not batch_id:
        raise ValueError("batch identity required")
    if len(issues) != 50 or len(set(issues)) != 50 or any(not isinstance(i, str) or not i.isascii() or not i.isdigit() for i in issues):
        raise ValueError("exactly 50 unique string issue identifiers required")
    digest = receipt.get("input_sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("input hash required")
    receipt_json = canonical_market_record(receipt)
    if connection.in_transaction:
        raise ValueError("caller transaction must be closed")
    try:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute("SELECT input_sha256,receipt_json FROM migration_batch WHERE batch_id=?", (batch_id,)).fetchone()
        if previous is not None and previous != (digest, receipt_json):
            raise ValueError("batch receipt changed")
        if previous is None:
            connection.execute("INSERT INTO migration_batch VALUES (?,?,'IMPORTED_PENDING_ACCEPTANCE',?)", (batch_id,digest,receipt_json))
            connection.executemany("INSERT INTO batch_issue VALUES (?,?)", [(i,batch_id) for i in issues])
        elif {r[0] for r in connection.execute("SELECT issue FROM batch_issue WHERE batch_id=?", (batch_id,))} != set(issues):
            raise ValueError("batch scope changed")
        seen, represented = set(), set()
        for row in records:
            identity = (row['kind'],row['key'])
            if identity in seen or row['issue'] not in issues:
                raise ValueError("duplicate record or issue outside batch")
            if not isinstance(row['key'], str) or not row['key']:
                raise ValueError("nonempty record key required")
            seen.add(identity)
            represented.add(row['issue'])
            encoded = canonical_market_record(row['data'])
            values = (batch_id,row['kind'],row['key'],row['issue'],row.get('provider_id'),row.get('market'),
                      row.get('source_url'),row.get('source_sha256'),encoded,hashlib.sha256(encoded.encode()).hexdigest())
            if previous is None:
                connection.execute("INSERT INTO market_record VALUES (?,?,?,?,?,?,?,?,?,?)",values)
            else:
                found = connection.execute("SELECT * FROM market_record WHERE batch_id=? AND kind=? AND record_key=?",(batch_id,*identity)).fetchone()
                if found != values:
                    raise ValueError("replayed record changed")
        if represented != set(issues):
            raise ValueError("missing issue records")
        count = connection.execute("SELECT count(*) FROM market_record WHERE batch_id=?",(batch_id,)).fetchone()[0]
        if count != len(seen):
            raise ValueError("replayed record count changed")
        connection.commit()
        return count
    except BaseException:
        connection.rollback()
        raise


def backup_market_database(connection, destination):
    """Create a new independent SQLite backup and verify integrity; return SHA256.

    Existing destinations are refused. Backup does not grant deletion approval.
    SQLite backup API supplies a consistent snapshot, including committed data.
    """
    destination = Path(destination)
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(destination)) as backup:
            connection.backup(backup)
            if backup.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('backup integrity failure')
            if backup.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('backup foreign key failure')
        with destination.open('rb') as stream:
            os.fsync(stream.fileno())
            parent_fd = os.open(destination.parent, os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            return hashlib.file_digest(stream,'sha256').hexdigest()
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def verify_market_batch_backup(connection, backup_path, *, batch_id, stage='complete'):
    """Verify an existing read-only backup against every row of one live batch.

    Allows interrupted post-backup receipt publication to resume without replacing
    the backup. Additional live batches need not exist in the older snapshot.
    Returns backup file SHA256; missing/corrupt/different batch content fails.
    stage='import' compares imported tables only and requires the backup to have
    no audit rows for this batch. Use only for the immutable pre-audit snapshot;
    acceptance and retirement must use the default complete comparison.
    """
    from itertools import zip_longest
    if stage not in {'import','complete'}:
        raise ValueError('unknown backup verification stage')
    path=Path(backup_path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as backup:
        if backup.execute('PRAGMA application_id').fetchone()[0]!=1112165715:
            raise ValueError('backup database identity mismatch')
        if backup.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or backup.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('backup integrity failure')
        if not connection.execute('SELECT 1 FROM migration_batch WHERE batch_id=?',(batch_id,)).fetchone():
            raise ValueError('live batch missing')
        tables=[('migration_batch','batch_id'),('batch_issue','issue'),('market_record','kind,record_key')]
        audit_table='market_audit_evidence'
        live_has=connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(audit_table,)).fetchone()
        saved_has=backup.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(audit_table,)).fetchone()
        if stage=='import':
            if saved_has and backup.execute('SELECT 1 FROM market_audit_evidence WHERE batch_id=?',(batch_id,)).fetchone():
                raise ValueError('import backup contains audit evidence')
        elif live_has or saved_has:
            if bool(live_has)!=bool(saved_has):
                existing=connection if live_has else backup
                if existing.execute('SELECT 1 FROM market_audit_evidence WHERE batch_id=?',(batch_id,)).fetchone():
                    raise ValueError('backup audit evidence table mismatch')
            else:
                tables.append((audit_table,'acceptance_path'))
        for table,order in tables:
            sql=f'SELECT * FROM {table} WHERE batch_id=? ORDER BY {order}'
            for live,saved in zip_longest(connection.execute(sql,(batch_id,)),backup.execute(sql,(batch_id,))):
                if live!=saved:
                    raise ValueError('backup batch content mismatch')
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def backup_market_batch(connection, destination, *, batch_id):
    """Create an independently readable backup containing exactly one 50-issue batch.

    Avoids quadratic storage growth from retaining a whole-history backup after
    every batch. Takes a read transaction, reuses authoritative import contracts,
    retains any audit ledger, verifies every batch row, then fsyncs the result.
    Caller must have no open transaction; existing destinations are refused.
    """
    if connection.in_transaction:
        raise ValueError('caller transaction must be closed')
    destination=Path(destination)
    with destination.open('xb'):
        pass
    try:
        connection.execute('BEGIN')
        row=connection.execute('SELECT receipt_json FROM migration_batch WHERE batch_id=?',(batch_id,)).fetchone()
        if row is None:
            raise ValueError('batch missing')
        issues=[r[0] for r in connection.execute('SELECT issue FROM batch_issue WHERE batch_id=? ORDER BY issue',(batch_id,))]
        records=(dict(kind=r[0],key=r[1],issue=r[2],provider_id=r[3],market=r[4],
                      source_url=r[5],source_sha256=r[6],data=json.loads(r[7]))
                 for r in connection.execute('''SELECT kind,record_key,issue,provider_id,market,
                     source_url,source_sha256,record_json FROM market_record WHERE batch_id=?''',(batch_id,)))
        with closing(open_market_database(destination)) as backup:
            import_market_batch(backup,batch_id=batch_id,issues=issues,records=records,receipt=json.loads(row[0]))
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_audit_evidence'").fetchone():
                schema=connection.execute("SELECT sql FROM sqlite_master WHERE name='market_audit_evidence'").fetchone()[0]
                backup.execute(schema)
                backup.executemany('INSERT INTO market_audit_evidence VALUES (?,?,?,?)',
                    connection.execute('SELECT * FROM market_audit_evidence WHERE batch_id=?',(batch_id,)))
                backup.commit()
        digest=verify_market_batch_backup(connection,destination,batch_id=batch_id)
        connection.commit()
        with destination.open('rb') as stream:
            os.fsync(stream.fileno())
        parent_fd=os.open(destination.parent,os.O_DIRECTORY)
        try:os.fsync(parent_fd)
        finally:os.close(parent_fd)
        return digest
    except BaseException:
        connection.rollback()
        destination.unlink(missing_ok=True)
        raise
