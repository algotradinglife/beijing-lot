"""Transactional owner-approved SP update with SQLite backup and in-database audit."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.settlement_sp_supplement import build_sp_supplement, parse_500_bf


def apply_sp_update(database, ledger_path, raw_path, backup_path, *, approval_note):
    """Apply exact missing-only ledger; backup before changes, rollback on failure.

    Paths are explicit. Original observation payloads/findings are retained as
    source evidence. option_sp becomes corrected data; audit tables retain both
    values and the original build receipt. Repeating the same ledger is a no-op
    only after verifying all corrected rows. No fetching or historical learning.
    """
    database, ledger_path, raw_path, backup_path = map(Path, (database, ledger_path, raw_path, backup_path))
    if not isinstance(approval_note, str) or not approval_note.strip():
        raise ValueError('Explicit approval note required')
    if len({p.resolve() for p in (database, ledger_path, raw_path, backup_path)}) != 4:
        raise ValueError('Database, backup and evidence paths must be distinct')
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    batch = hashlib.sha256(ledger_bytes).hexdigest()
    if ledger['play'] != 'bf' or ledger['receipt']['source_url'] != (
            'https://trade.500.com/bjdc/project_fq_bf.php?expect=' + ledger['issue']):
        raise ValueError('Wrong correction play or source identity')
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ledger['receipt']['source_sha256']:
        raise ValueError('Raw evidence hash mismatch')
    con = sqlite3.connect(database.resolve().as_uri() + '?mode=rw', uri=True, timeout=30)
    try:
        con.execute('BEGIN IMMEDIATE')
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='sp_correction_batch'").fetchone():
            prior = con.execute('SELECT row_count FROM sp_correction_batch WHERE batch_id=?', (batch,)).fetchone()
            if prior:
                rows = con.execute('''SELECT a.new_raw_sp,a.new_sp,p.raw_sp,p.sp FROM sp_correction a
                    JOIN option_sp p ON p.observation_id=a.observation_id AND p.option=a.option
                    WHERE a.batch_id=?''', (batch,)).fetchall()
                if len(rows) != prior[0] or any(a != c or b != d for a,b,c,d in rows):
                    raise ValueError('Previously applied values changed')
                con.rollback()
                return {'status':'already_applied','updated':prior[0]}
        observations = [dict(json.loads(r), expected_option=e) for r,e in con.execute(
            'SELECT payload_json,expected_option FROM observation WHERE issue=? AND play=? ORDER BY slot',
            (ledger['issue'],ledger['play']))]
        replay = build_sp_supplement(observations, parse_500_bf(raw), issue=ledger['issue'],
            source_sha256=ledger['receipt']['source_sha256'], aliases=ledger['aliases'])
        if replay['corrections'] != ledger['corrections'] or not replay['corrections']:
            raise ValueError('Ledger does not replay exactly')
        targets = []
        for z in ledger['corrections']:
            rows = con.execute('''SELECT o.observation_id,p.raw_sp,p.sp,o.source_sha256,o.native_match_id,o.score
              FROM observation o JOIN option_sp p USING(observation_id)
              WHERE o.issue=? AND o.slot=? AND o.play=? AND p.option=?''',
              (z['issue'],z['slot'],z['play'],z['option'])).fetchall()
            if len(rows)!=1 or rows[0][1:] != ('',None,z['original_source_sha256'],z['native_match_id'],z['score']):
                raise ValueError('Target is no longer the approved missing original')
            targets.append((rows[0][0],z))
        original_receipts = con.execute('SELECT payload_json FROM receipt').fetchall()
        if len(original_receipts)!=1:
            raise ValueError('Expected one original build receipt')
        # Reserve writer lock first; a second read-only connection can back up
        # the stable committed snapshot without backing up an active writer.
        with backup_path.open('xb'):
            pass
        source = sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)
        dest = sqlite3.connect(backup_path)
        try:
            source.backup(dest)
            if dest.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('Backup integrity check failed')
        finally:
            dest.close()
            source.close()
        con.execute('''CREATE TABLE IF NOT EXISTS sp_correction_batch (
            batch_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL,
            row_count INTEGER NOT NULL, original_receipt_json TEXT NOT NULL,
            ledger_json TEXT NOT NULL, raw_html BLOB NOT NULL, backup_path TEXT NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS sp_correction (
            observation_id INTEGER NOT NULL, option TEXT NOT NULL, batch_id TEXT NOT NULL,
            issue TEXT NOT NULL, slot INTEGER NOT NULL, play TEXT NOT NULL,
            old_raw_sp TEXT, old_sp REAL, new_raw_sp TEXT NOT NULL, new_sp REAL NOT NULL,
            source TEXT NOT NULL, source_url TEXT NOT NULL, source_sha256 TEXT NOT NULL,
            original_source_sha256 TEXT NOT NULL, note TEXT NOT NULL, applied_at TEXT NOT NULL,
            PRIMARY KEY (observation_id,option))''')
        now = datetime.now(timezone.utc).isoformat()
        note = approval_note.strip()
        con.execute('INSERT INTO sp_correction_batch VALUES (?,?,?,?,?,?,?,?)',
            (batch,now,note,len(targets),original_receipts[0][0],ledger_bytes.decode(),raw,str(backup_path.resolve())))
        for oid,z in targets:
            con.execute('INSERT INTO sp_correction VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (oid,z['option'],batch,z['issue'],z['slot'],z['play'],'',None,z['replacement_raw_sp'],
                 z['replacement_sp'],'500.com',ledger['receipt']['source_url'],z['replacement_source_sha256'],
                 z['original_source_sha256'],note,now))
            updated = con.execute("UPDATE option_sp SET raw_sp=?,sp=? WHERE observation_id=? AND option=? AND raw_sp='' AND sp IS NULL",
                (z['replacement_raw_sp'],z['replacement_sp'],oid,z['option']))
            if updated.rowcount != 1:
                raise ValueError('Conditional update did not affect exactly one row')
        receipt = json.loads(original_receipts[0][0])
        receipt.update(source_pure=False,effective_source='nowscore_with_audited_500_corrections',
                       correction_batch_id=batch,corrected_options=len(targets),corrected_at=now,
                       correction_note='Original build hashes describe the pre-correction snapshot; see sp_correction_batch.original_receipt_json and SQLite backup.')
        con.execute('UPDATE receipt SET payload_json=?',(json.dumps(receipt,ensure_ascii=False),))
        con.commit()
        return {'status':'applied','updated':len(targets),'batch_id':batch,'backup':str(backup_path)}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
