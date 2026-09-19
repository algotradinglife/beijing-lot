"""Verify an explicitly migrated collection receipt without raw page bytes."""
import hashlib
import json
from pathlib import Path
from src.market_sqlite_query import query_market_records


class MarketNormalizationUnavailable(ValueError):
    """Verified source was captured but could not produce normalized quotes."""


def read_market_storage_receipt(reference, *, expected_sha256, expected_url):
    """Read metadata from an accepted SQLite capture reference.

    The reference binds database, issue, batch, capture key, record hash and an
    acceptance file/hash. Refuses pending batches, changed records and source
    mismatches. Returned metadata contains no page body and cannot be passed to
    legacy page parsers. No implicit fallback to raw files or network.
    """
    receipt_path=Path(reference['acceptance']['path'])
    content=receipt_path.read_bytes()
    if hashlib.sha256(content).hexdigest()!=reference['acceptance']['sha256']:
        raise ValueError('storage acceptance hash mismatch')
    accepted=json.loads(content)
    if accepted.get('state')!='SQLITE_BATCH_ACCEPTED' or accepted.get('batch_id')!=reference['batch_id']:
        raise ValueError('accepted storage batch required')
    if reference['issue'] not in accepted.get('issues',[]):
        raise ValueError('capture issue outside accepted storage scope')
    if Path(accepted['database']).resolve()!=Path(reference['database']).resolve():
        raise ValueError('storage database binding mismatch')
    records=query_market_records(reference['database'],issue=reference['issue'],kind='capture',
                                 source_sha256=expected_sha256,source_url=expected_url)
    main=[r for r in records if r['record_key'].endswith('/response')]
    if len(main)!=1 or main[0]['record_key']!=reference['capture_key']:
        raise ValueError('selected main capture binding missing or invalid')
    matches=main
    if len(matches)!=1 or matches[0]['batch_id']!=reference['batch_id']:
        raise ValueError('stored capture binding missing')
    record=matches[0]
    if record['record_sha256']!=reference['record_sha256']:
        raise ValueError('stored capture binding changed')
    from src.market_sqlite_query import verify_market_source_inventory
    expected=accepted.get('source_inventories',{}).get(reference['capture_key'])
    if expected is None:
        raise ValueError('accepted source inventory missing')
    complete=query_market_records(reference['database'],issue=reference['issue'],
                                  source_sha256=expected_sha256,source_url=expected_url)
    verify_market_source_inventory(complete,expected)
    metadata=record['data']['metadata']
    if metadata.get('url')!=expected_url:
        raise ValueError('stored capture URL mismatch')
    return metadata


def read_market_storage_parsed(reference, *, expected_sha256, expected_url):
    """Return original transport metadata and the stored normalized market view.

    The main response is selected explicitly, never a successful retry in place
    of a failure. Unavailable/failed normalization raises with retained anomaly
    codes; callers may isolate it, not treat it as a valid empty market.
    """
    from src.market_sqlite_query import query_market_capture
    metadata=read_market_storage_receipt(reference,expected_sha256=expected_sha256,expected_url=expected_url)
    source=query_market_capture(reference['database'],issue=reference['issue'],
                                source_sha256=expected_sha256,source_url=expected_url)
    key='parsed/'+reference['capture_key']
    evidence=[r for r in source['evidence'] if r['record_key']==key]
    extraction_failed=any(r['record_key']=='extract/'+reference['capture_key'] and
                          r['data'].get('code')=='SOURCE_EXTRACTION_FAILED'
                          for r in source['anomalies'])
    transport_failed=metadata.get('status')!=200 or bool(metadata.get('error'))
    if len(evidence)>1 or (not transport_failed and not evidence and not extraction_failed):
        raise ValueError('stored normalization evidence missing or ambiguous')
    if transport_failed or not evidence or evidence[0]['data'].get('normalized') is None:
        codes=sorted({r['data'].get('code','UNKNOWN') for r in source['anomalies']})
        raise MarketNormalizationUnavailable('stored market normalization unavailable: '+','.join(codes))
    return metadata,evidence[0]['data']['normalized']


def bind_market_capture_index(index, captures, *, database, acceptance):
    """Return a copied capture index with exact imported responses bound to SQLite.

    Matches collector market key and original response hash, retaining old path,
    transport state and attempts. Does not publish the result or remove files.
    Capture records must be obtained from the verified SQLite query API.
    """
    from copy import deepcopy
    from src.fundamentals_market_history import market_key
    lookup={}
    for record in captures:
        if record['kind']!='capture' or not record['record_key'].endswith('/response'):
            continue
        key=market_key(record['source_url'])
        if key is None:
            continue
        identity=(key,record['source_sha256'])
        reference=dict(database=str(database),issue=record['issue'],batch_id=record['batch_id'],
                       capture_key=record['record_key'],record_sha256=record['record_sha256'],
                       source_url=record['source_url'],acceptance=acceptance)
        previous=lookup.get(identity)
        if previous is None or reference['issue']<previous['issue']:
            lookup[identity]=reference
    result=deepcopy(index);changed=0
    for key,entry in result.items():
        references=list(entry.get('attempts',[]))
        if entry.get('selected') is not None:references.append(entry['selected'])
        for item in references:
            reference=lookup.get((key,item.get('sha256')))
            if reference is None or item.get('storage')==reference:
                continue
            item['storage']=deepcopy(reference);changed+=1
    return dict(index=result,changed_references=changed)
