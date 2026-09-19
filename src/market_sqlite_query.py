"""Read structured market records without opening source response files."""
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def query_market_records(database, *, issue, kind=None, source_sha256=None, source_url=None):
    """Return verified records for a string issue, optionally filtered by kind.

    Opens SQLite read-only; never creates a missing database. Returns a list of
    dictionaries with parsed ``data`` and indexed provenance columns. Empty
    results are valid. Import status is included: callers must not confuse a
    pending storage import with accepted data. Corrupt record hashes fail closed.
    """
    if not isinstance(issue, str) or not issue.isascii() or not issue.isdigit():
        raise ValueError('string issue identifier required')
    if kind is not None and kind not in {'capture','quote','fixture_market','anomaly','evidence'}:
        raise ValueError('unknown market record kind')
    uri=Path(database).resolve(strict=True).as_uri()+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True)) as connection:
        if (connection.execute('PRAGMA application_id').fetchone()[0],
            connection.execute('PRAGMA user_version').fetchone()[0]) != (1112165715,1):
            raise ValueError('unsupported market database identity')
        connection.row_factory=sqlite3.Row
        sql='''SELECT r.*, b.state AS import_state FROM market_record r
               JOIN migration_batch b USING(batch_id) WHERE r.issue=?'''
        params=[issue]
        if kind is not None:
            sql+=' AND r.kind=?'; params.append(kind)
        if source_sha256 is not None:
            sql+=' AND r.source_sha256=?'; params.append(source_sha256)
        if source_url is not None:
            sql+=' AND r.source_url=?'; params.append(source_url)
        sql+=' ORDER BY r.kind,r.record_key' 
        records=[]
        for row in connection.execute(sql,params):
            record=dict(row)
            encoded=record.pop('record_json')
            if hashlib.sha256(encoded.encode()).hexdigest()!=record['record_sha256']:
                raise ValueError('stored market record hash mismatch')
            record['data']=json.loads(encoded)
            records.append(record)
        return records


def query_market_capture(database, *, issue, source_sha256, source_url):
    """Read one issue's extracted response and retries, retaining failures.

    Requires exact source hash and URL rather than choosing latest by provider.
    Raises on missing/ambiguous main response. Body reconstruction is unsupported.
    Returns capture, retry captures, quote rows, normalized evidence and anomalies.
    All underlying record hashes are checked by query_market_records.
    """
    if not isinstance(source_sha256,str) or len(source_sha256)!=64 or any(
            c not in '0123456789abcdef' for c in source_sha256):
        raise ValueError('source SHA256 required')
    selected=query_market_records(database,issue=issue,source_sha256=source_sha256,source_url=source_url)
    main=[r for r in selected if r['kind']=='capture' and r['record_key'].endswith('/response')]
    if len(main)!=1:
        raise ValueError('exactly one stored source response required')
    return dict(capture=main[0],
                retries=[r for r in selected if r['kind']=='capture' and r is not main[0]],
                quotes=[r for r in selected if r['kind']=='quote'],
                evidence=[r for r in selected if r['kind']=='evidence'],
                anomalies=[r for r in selected if r['kind']=='anomaly'])


def query_market_audit_evidence(database, *, batch_id):
    """Read complete preserved cleaning ledgers; missing table means not stored.

    Requires explicit batch identity and checks each document hash. Missing
    evidence raises rather than reporting an empty, apparently clean ledger.
    Opens read-only and performs no writes or network operations.
    """
    if not isinstance(batch_id,str) or not batch_id:
        raise ValueError('batch identity required')
    uri=Path(database).resolve(strict=True).as_uri()+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True)) as connection:
        if connection.execute('PRAGMA application_id').fetchone()[0]!=1112165715:
            raise ValueError('unsupported market database identity')
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_audit_evidence'").fetchone():
            raise ValueError('cleaning audit evidence not stored')
        result=[]
        for content,digest in connection.execute(
                'SELECT evidence_json,evidence_sha256 FROM market_audit_evidence WHERE batch_id=? ORDER BY acceptance_path',(batch_id,)):
            if hashlib.sha256(content.encode()).hexdigest()!=digest:
                raise ValueError('cleaning audit evidence hash mismatch')
            result.append(json.loads(content))
        if not result:
            raise ValueError('cleaning audit evidence not stored')
        return result


def query_market_batch_counts(database, *, batch_id):
    """Return one count row per issue/kind for an explicit imported batch.

    Summary counts alone do not establish record integrity or deletion readiness.
    Requires the registered 50-issue scope and preserves the import state.
    """
    uri=Path(database).resolve(strict=True).as_uri()+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True)) as connection:
        if connection.execute('PRAGMA application_id').fetchone()[0]!=1112165715:
            raise ValueError('unsupported market database identity')
        scope=connection.execute('SELECT count(*) FROM batch_issue WHERE batch_id=?',(batch_id,)).fetchone()[0]
        if scope!=50:
            raise ValueError('imported 50-issue batch required')
        connection.row_factory=sqlite3.Row
        return [dict(row) for row in connection.execute('''
            SELECT i.issue, r.kind, count(r.record_key) AS records, b.state AS import_state
            FROM batch_issue i JOIN migration_batch b USING(batch_id)
            LEFT JOIN market_record r ON r.batch_id=i.batch_id AND r.issue=i.issue
            WHERE i.batch_id=? GROUP BY i.issue,r.kind ORDER BY i.issue,r.kind''',(batch_id,))]


def verify_market_fixture_views(database, *, batch_id, issue_audits):
    """Compare all 50 imported fixture views with verified published audit rows.

    Caller supplies hash-verified originals keyed by issue. Returns per-issue
    content hashes and counts. Record integrity and batch identity are checked;
    row order is immaterial but duplicate multiplicities must match. Read-only.
    This does not verify quote extraction or authorize retirement.
    """
    from src.market_sqlite import canonical_market_record
    counts=query_market_batch_counts(database,batch_id=batch_id)
    if set(issue_audits)!={row['issue'] for row in counts}:
        raise ValueError('fixture comparison must cover exact batch scope')
    result=[]
    for issue,expected in sorted(issue_audits.items()):
        actual=query_market_records(database,issue=issue,kind='fixture_market')
        if any(row['batch_id']!=batch_id for row in actual):
            raise ValueError('fixture comparison batch mismatch')
        left=sorted(canonical_market_record(row) for row in expected)
        right=sorted(canonical_market_record(row['data']) for row in actual)
        if left!=right:
            raise ValueError('published fixture view mismatch: '+issue)
        result.append(dict(issue=issue,records=len(right),
                           sha256=hashlib.sha256(canonical_market_record(right).encode()).hexdigest()))
    return result


def market_source_inventory(records):
    """Hash the complete verified record membership of one captured source.

    Input is the unfiltered source result from query_market_records, including
    every retry, quote, evidence and anomaly. Returned count/hash must be frozen
    in acceptance before raw retirement; computing it later is not verification.
    Includes indexed identity columns as well as payload hashes. No writes.
    """
    from src.market_sqlite import canonical_market_record
    if not records:
        raise ValueError('empty source inventory')
    fields=('batch_id','issue','kind','record_key','provider_id','market',
            'source_url','source_sha256','record_sha256')
    entries=[{k:r[k] for k in fields} for r in records]
    identities={(r['batch_id'],r['issue'],r['source_url'],r['source_sha256']) for r in entries}
    if len(identities)!=1 or len({(r['kind'],r['record_key']) for r in entries})!=len(entries):
        raise ValueError('ambiguous source inventory')
    if sum(r['kind']=='capture' and r['record_key'].endswith('/response') for r in entries)!=1:
        raise ValueError('source inventory requires one main response')
    entries.sort(key=lambda r:(r['kind'],r['record_key']))
    return dict(records=len(entries),sha256=hashlib.sha256(canonical_market_record(entries).encode()).hexdigest())


def verify_market_source_inventory(records, expected):
    """Reject missing, added or modified source membership against frozen proof."""
    actual=market_source_inventory(records)
    if actual!=expected:
        raise ValueError('stored source inventory mismatch')
    return actual


def query_market_batch_source_inventories(database, *, batch_id):
    """Build source membership proofs for all captures in an exact 50-issue batch.

    Verifies every record payload hash through the query API. Result alone is
    not acceptance: caller must compare with the independently verified backup.
    Processes one issue at a time; no network, writes or body reconstruction.
    """
    from collections import defaultdict
    counts=query_market_batch_counts(database,batch_id=batch_id)
    result={}
    for issue in sorted({r['issue'] for r in counts}):
        groups=defaultdict(list)
        for row in query_market_records(database,issue=issue):
            if row['batch_id']!=batch_id:raise ValueError('inventory batch mismatch')
            if row['source_sha256'] is not None:
                groups[(row['source_sha256'],row['source_url'])].append(row)
        for rows in groups.values():
            inventory=market_source_inventory(rows)
            key=next(r['record_key'] for r in rows if r['kind']=='capture' and r['record_key'].endswith('/response'))
            if key in result:raise ValueError('duplicate source inventory key')
            result[key]=inventory
    if not result:raise ValueError('batch has no source inventories')
    return result
