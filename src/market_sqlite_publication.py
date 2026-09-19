"""Prepare a publication reader cutover without mutating the live registry."""
import hashlib
from copy import deepcopy
from pathlib import Path
from src.market_sqlite import canonical_market_record
from src.market_sqlite_query import query_market_records, query_market_batch_counts
from src.n7_published_markets import read_n7_published_markets


def prepare_market_sqlite_publication(data_root, *, merged_path, merged_sha256, database, batch_id):
    """Return an unchanged quote publication with exactly 50 source pointers replaced.

    Verifies old detail views through the published reader and compares every
    fixture audit field against SQLite. No acceptance, writes or deletion occur.
    Caller must publish immutably, read back and bind registry changes separately.
    """
    import json
    root=Path(data_root).resolve(strict=True)
    db=(root/database).resolve(strict=True);db.relative_to(root)
    path=(root/merged_path).resolve(strict=True);path.relative_to(root)
    content=path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=merged_sha256:
        raise ValueError('publication hash mismatch')
    merged=json.loads(content)
    counts=query_market_batch_counts(db,batch_id=batch_id)
    issues=sorted({r['issue'] for r in counts})
    if len(issues)!=50:raise ValueError('fifty-issue batch required')
    original=read_n7_published_markets(data_root=root,merged_path=merged_path,
                                     expected_sha256=merged_sha256,issues=issues)
    if any(r['status']!='PUBLISHED_DETAIL_VERIFIED' for r in original['coverage']):
        raise ValueError('batch issue not published')
    replacements={}
    for issue in issues:
        records=query_market_records(db,issue=issue,kind='fixture_market')
        if not records or any(r['batch_id']!=batch_id for r in records):
            raise ValueError('publication batch mismatch')
        actual=sorted((r['data'] for r in records),key=lambda r:(r['slot'],r['market']))
        expected=sorted((r for r in original['rows'] if r['issue']==issue),key=lambda r:(r['slot'],r['market']))
        if canonical_market_record(actual)!=canonical_market_record(expected):
            raise ValueError('publication SQLite detail mismatch')
        replacements[issue]=dict(issue=issue,sqlite=db.relative_to(root).as_posix(),batch_id=batch_id,
            structured_sha256=hashlib.sha256(canonical_market_record(actual).encode()).hexdigest())
    result=deepcopy(merged)
    result['issue_sources']=[replacements.get(s['issue'],s) for s in result['issue_sources']]
    return result


def market_sqlite_release_reference(registry, previous_receipt, *, staged_receipt, acceptance,
                                    acceptance_reference, publication_path, receipt_path):
    """Build replacement registry/receipt while preserving data acceptance lineage.

    Pure function. Caller hash-verifies artifacts, compares registry under lock,
    publishes immutable release artifacts and atomically swaps the registry last.
    Storage conversion never promotes historical admission or authorizes deletion.
    """
    for name in (publication_path,receipt_path):
        path=Path(name)
        if path.is_absolute() or '..' in path.parts or not path.is_relative_to('markets/releases'):
            raise ValueError('formal publication must be under markets/releases')
    if (acceptance.get('state')!='SQLITE_BATCH_ACCEPTED' or
            staged_receipt.get('state')!='PUBLICATION_STAGED_READBACK_VERIFIED_NOT_ACTIVATED' or
            acceptance['batch_id']!=staged_receipt['batch_id'] or
            set(acceptance['issues'])!=set(staged_receipt['issues']) or len(set(acceptance['issues']))!=50):
        raise ValueError('accepted staged batch required')
    current=registry['current_release']
    if (previous_receipt.get('status')!='ACCEPTED_DIAGNOSTIC_BATCH_PUBLISHED' or
            previous_receipt['merged_sha256']!=current['sha256'] or registry.get('historical_admission') is not False):
        raise ValueError('prior publication binding mismatch')
    result=deepcopy(registry)
    result['current_release']=dict(path=publication_path,sha256=staged_receipt['sha256'],receipt=receipt_path)
    receipt=deepcopy(previous_receipt)
    receipt.update(merged_sha256=staged_receipt['sha256'],
                   storage_conversion=dict(batch_id=acceptance['batch_id'],acceptance=acceptance_reference,
                       prior_release=deepcopy(current),historical_admission=False,raw_deletion_authorized=False))
    return dict(registry=result,receipt=receipt)


def verify_market_publication_activation(registry, receipt, *, staged_receipt,
                                          acceptance_reference, publication_path, receipt_path):
    """Verify already-activated pointers and lineage for an idempotent restart.

    Caller must separately hash-verify and read back the publication and storage
    acceptance. Returns True or raises; never changes registry or data.
    """
    expected=dict(path=publication_path,sha256=staged_receipt['sha256'],receipt=receipt_path)
    conversion=receipt.get('storage_conversion',{})
    if (registry.get('current_release')!=expected or registry.get('historical_admission') is not False or
            receipt.get('status')!='ACCEPTED_DIAGNOSTIC_BATCH_PUBLISHED' or
            receipt.get('merged_sha256')!=staged_receipt['sha256'] or
            conversion.get('batch_id')!=staged_receipt['batch_id'] or
            conversion.get('acceptance')!=acceptance_reference or
            conversion.get('historical_admission') is not False or not conversion.get('prior_release')):
        raise ValueError('activated publication binding mismatch')
    return True
