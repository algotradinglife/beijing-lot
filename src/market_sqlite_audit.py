"""Read hash-bound cleaning decisions for persistent anomaly retention."""
import hashlib
import json
from pathlib import Path

from src.market_sqlite import canonical_market_record


def collect_market_audit_evidence(data_root, acceptance_paths, *, issues):
    """Return complete linked anomaly/decision documents for intersecting batches.

    Explicit acceptance paths only; never infer current versions by file age.
    Preserve whole documents so cross-issue findings and narrative decisions are
    not lost by row filtering. Every referenced JSON is hash checked. This reader
    performs no writes and confers no raw-file deletion permission.
    """
    root=Path(data_root).resolve(strict=True)
    wanted=set(issues)
    output=[]
    for name in acceptance_paths:
        path=(root/name).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError('acceptance outside data root')
        content=path.read_bytes()
        acceptance=json.loads(content)
        overlap=sorted(wanted.intersection(acceptance.get('issues',[])))
        if not overlap:
            continue
        if acceptance.get('status')!='ACCEPTED_DIAGNOSTIC_BATCH':
            raise ValueError('cleaning acceptance required')
        documents={}
        for field in ('anomaly_ledger','anomaly_review','followup_queue','request_uncertainty','issue_status'):
            binding=acceptance.get(field)
            if binding is None:
                continue
            linked=(root/binding['path']).resolve(strict=True)
            if not linked.is_relative_to(root):
                raise ValueError('audit evidence outside data root')
            payload=linked.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=binding['sha256']:
                raise ValueError('audit evidence hash mismatch')
            value=json.loads(payload)
            canonical_market_record(value)
            documents[field]=dict(path=str(linked.relative_to(root)),sha256=binding['sha256'],data=value)
        if 'anomaly_ledger' not in documents:
            raise ValueError('accepted batch missing anomaly ledger')
        output.append(dict(acceptance_path=str(path.relative_to(root)),
                           acceptance_sha256=hashlib.sha256(content).hexdigest(),
                           issues=overlap,acceptance=acceptance,documents=documents))
    return output


def store_market_audit_evidence(connection, *, batch_id, evidence):
    """Atomically bind complete cleaning evidence to an already imported batch.

    Exact replays are allowed; changed evidence or extra/missing documents fail.
    Each acceptance must intersect the imported scope, and the union must cover
    all 50 issues. No deletion or promotion to content acceptance takes place.
    """
    if connection.in_transaction:
        raise ValueError('caller transaction must be closed')
    issues={r[0] for r in connection.execute('SELECT issue FROM batch_issue WHERE batch_id=?',(batch_id,))}
    if len(issues)!=50:
        raise ValueError('imported 50-issue batch required')
    covered=set()
    rows=[]
    for item in evidence:
        overlap=set(item['issues'])
        if not overlap or not overlap.issubset(issues):
            raise ValueError('audit outside imported scope')
        covered.update(overlap)
        encoded=canonical_market_record(item)
        rows.append((batch_id,item['acceptance_path'],encoded,hashlib.sha256(encoded.encode()).hexdigest()))
    if covered!=issues or len({r[1] for r in rows})!=len(rows):
        raise ValueError('incomplete or duplicate audit coverage')
    try:
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('''CREATE TABLE IF NOT EXISTS market_audit_evidence (
            batch_id TEXT NOT NULL REFERENCES migration_batch(batch_id),
            acceptance_path TEXT NOT NULL, evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
            evidence_sha256 TEXT NOT NULL, PRIMARY KEY(batch_id,acceptance_path))''')
        previous=connection.execute('SELECT * FROM market_audit_evidence WHERE batch_id=? ORDER BY acceptance_path',(batch_id,)).fetchall()
        if previous:
            if previous!=sorted(rows,key=lambda r:r[1]):
                raise ValueError('audit evidence replay changed')
        else:
            connection.executemany('INSERT INTO market_audit_evidence VALUES (?,?,?,?)',rows)
        connection.commit()
        return len(rows)
    except BaseException:
        connection.rollback()
        raise


def collect_archived_market_audit(data_root, *, archive, archive_sha256,
                                  acceptance_member, document_members, issues):
    """Retain a legacy batch's acceptance and anomaly documents from its archive.

    Caller supplies explicit member names; whole-archive SHA binds all members.
    Returns the same evidence shape as collect_market_audit_evidence, with the
    original acceptance unchanged. This is archival evidence, not a new approval.
    """
    from src.data_archive import read_archive_members
    root=Path(data_root).resolve(strict=True)
    path=(root/archive).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError('audit archive outside root')
    scope_roles=set(document_members).intersection({'manifest','market_summary'})
    if 'anomaly_ledger' not in document_members or len(scope_roles)!=1:
        raise ValueError('anomaly ledger and exactly one scope document required')
    members=[acceptance_member,*document_members.values()]
    payloads=read_archive_members(path,members,expected_sha256=archive_sha256)
    acceptance=json.loads(payloads[acceptance_member])
    if acceptance.get('status')!='ACCEPTED_DIAGNOSTIC_BATCH':
        raise ValueError('cleaning acceptance required')
    scope_role=next(iter(scope_roles))
    manifest_bytes=payloads[document_members[scope_role]]
    if hashlib.sha256(manifest_bytes).hexdigest()!=acceptance[scope_role]['sha256']:
        raise ValueError('accepted manifest hash mismatch')
    manifest=json.loads(manifest_bytes)
    accepted_issues=(manifest['issues'] if scope_role=='manifest'
                     else [row['issue'] for row in manifest['issues']])
    if not issues or not set(issues).issubset(accepted_issues):
        raise ValueError('audit issues outside accepted manifest')
    documents={}
    for role,member in document_members.items():
        content=payloads[member];data=json.loads(content)
        if role in acceptance and isinstance(acceptance[role],dict) and 'sha256' in acceptance[role]:
            if hashlib.sha256(content).hexdigest()!=acceptance[role]['sha256']:
                raise ValueError('accepted audit document hash mismatch')
        canonical_market_record(data)
        documents[role]=dict(path=member,sha256=hashlib.sha256(content).hexdigest(),data=data)
    canonical_market_record(acceptance)
    return dict(acceptance_path=archive+'#'+acceptance_member,
                acceptance_sha256=hashlib.sha256(payloads[acceptance_member]).hexdigest(),
                archive_sha256=archive_sha256,issues=list(issues),acceptance=acceptance,documents=documents)
