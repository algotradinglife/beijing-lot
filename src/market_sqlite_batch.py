"""Bind published market audit issues to complete source extraction for SQLite."""
import hashlib
import json
import re
from pathlib import Path

from src.data_archive import read_archive_members
from src.fundamentals_census import validate_response_record
from src.fundamentals_market_history import market_key
from src.market_sqlite_extract import extract_market_source
from src.market_sqlite_sources import read_archived_market_sources


def verified_market_json(path, digest):
    """Read a hash-bound JSON artifact. Mismatch/missing bytes abort migration."""
    content=Path(path).read_bytes()
    if hashlib.sha256(content).hexdigest()!=digest:
        raise ValueError(f'input hash mismatch: {path}')
    return json.loads(content)


def market_transport_attempts(receipt):
    """Yield outer and embedded retry metadata/bodies, validating each response.

    Bodies exist only during parsing. Metadata contains no encoded body or nested
    receipts; nested attempts become individual records with explicit ordinals.
    Transport errors without bodies remain evidence with a None body.
    """
    pending=[('response',receipt)]
    while pending:
        identity,record=pending.pop(0)
        nested=record.get('attempt_receipts',[])
        if not isinstance(nested,list) or any(not isinstance(r,dict) for r in nested):
            raise ValueError('invalid embedded attempt receipts')
        plain={k:v for k,v in record.items() if k!='attempt_receipts'}
        if 'body_base64' in plain:
            meta,body=validate_response_record(plain)
        elif plain.get('error'):
            meta,body=plain,None
        else:
            raise ValueError('transport receipt has neither body nor error')
        meta=dict(meta,embedded_attempt_count=len(nested))
        yield identity,meta,body
        pending.extend((f'{identity}/attempt-{i}',child) for i,child in enumerate(nested))


def market_batch_records(data_root, issue_sources, *, archive_receipts=()):
    """Yield source quotes, audit results and actionable anomalies for issue files.

    ``issue_sources`` binds each published issue JSON to SHA256. Audit fields and
    every source market response named in its provenance are retained. Nonmarket
    roster inputs are not retired by this adapter. No writes/deletions/network.
    Publication acceptance must be checked by the caller before calling this.
    """
    root=Path(data_root).resolve(strict=True)
    audits=load_market_issue_audits(root,issue_sources)
    bindings={}
    stored={}
    for rows in audits.values():
        for row in rows:
            if row.get('storage') is not None:
                name=row['capture_path']
                reference=row['storage']
                if name in stored and stored[name]!=reference:
                    raise ValueError('conflicting stored source binding')
                stored[name]=reference
            for name,digest in row.get('source_hashes',{}).items():
                if name in bindings and bindings[name]!=digest:
                    raise ValueError('conflicting source hash')
                bindings[name]=digest
    archived=read_archived_market_sources(root,{k:v for k,v in bindings.items() if k not in stored},archive_receipts)
    for source in issue_sources:
        issue=source['issue']
        rows=audits[issue]
        if not rows:
            raise ValueError('empty issue audit requires explicit issue evidence')
        seen_captures=set()
        seen_research=set()
        seen_paths=set()
        aliases={}
        for row in rows:
            for name,digest in row.get('source_hashes',{}).items():
                aliases.setdefault(digest,set()).add(name)
        for row in rows:
            if row['issue']!=issue:
                raise ValueError('audit issue mismatch')
            fixture_key=f"{issue}/{row['slot']}/{row['market']}"
            common=dict(issue=issue,provider_id=row['provider_id'],market=row['market'])
            yield dict(common,kind='fixture_market',key=fixture_key,data=row)
            if row['status']!='QUOTES_PRIOR_DIAGNOSTIC':
                yield dict(common,kind='anomaly',key='audit/'+fixture_key,data=row)
            capture=row.get('capture_path')
            hashes=row.get('source_hashes',{})
            if not capture or capture not in hashes:
                raise ValueError('audit is missing source capture binding')
            # Peers/replacements matter for subsequent anomaly investigation.
            # Keep all market receipts in the audit provenance, not just chosen one.
            for name,digest in hashes.items():
                if name in seen_paths:
                    continue
                if name in stored:
                    copied=list(reuse_market_source_records(stored[name],expected_sha256=digest,
                                issue=issue,fixture_key=fixture_key,path=name,aliases=aliases[digest]))
                    seen_paths.add(name)
                    if digest not in seen_captures:
                        seen_captures.add(digest)
                        yield from copied
                    continue
                if name in archived:
                    content=archived[name]
                else:
                    path=(root/name).resolve(strict=True)
                    if not path.is_relative_to(root):
                        raise ValueError('source outside persistent root')
                    content=path.read_bytes()
                    if hashlib.sha256(content).hexdigest()!=digest:
                        raise ValueError(f'input hash mismatch: {path}')
                if Path(name).suffix.lower()=='.txt' and name!=capture:
                    # Independent research is evidence, not a transport receipt.
                    # Retain its text and links for future anomaly investigation.
                    text=content.decode('utf-8')
                    seen_paths.add(name)
                    if digest not in seen_research:
                        seen_research.add(digest)
                        yield dict(common,kind='evidence',key=f'research/{issue}/{digest}',
                            data=dict(source_sha256=digest,
                                evidence_type='INDEPENDENT_RESEARCH_TEXT',text=text,
                                source_urls=sorted(set(re.findall(r'https?://[^\s<>"\']+',text))),
                                path=name,path_aliases=sorted(aliases[digest]),
                                linked_fixture_key=fixture_key))
                    continue
                receipt=json.loads(content)
                seen_paths.add(name)
                if digest in seen_captures:
                    continue
                key=market_storage_source_key(receipt.get('url','')) if isinstance(receipt,dict) else None
                if key is None:
                    continue
                seen_captures.add(digest)
                source_market,pid=key.split(':',1)
                for attempt_identity,meta,body in market_transport_attempts(receipt):
                    if market_storage_source_key(meta.get('url',''))!=key:
                        raise ValueError('embedded attempt source mismatch')
                    capture_key=f'{issue}/{digest}/{attempt_identity}'
                    metadata=dict(issue=issue,provider_id=pid,market=source_market,
                                  source_url=meta['url'],source_sha256=digest)
                    capture_data=dict(path=name,path_aliases=sorted(aliases[digest]),metadata=meta,linked_fixture_key=fixture_key)
                    yield dict(metadata,kind='capture',key=capture_key,data=capture_data)
                    if meta.get('status')!=200 or meta.get('error'):
                        yield dict(metadata,kind='anomaly',key='transport/'+capture_key,
                                   data=dict(capture_data,code='TRANSPORT_OR_HTTP_FAILURE'))
                        continue
                    try:
                        parsed=extract_market_source(body,market=source_market)
                    except (ValueError,UnicodeError) as exc:
                        yield dict(metadata,kind='anomaly',key='extract/'+capture_key,
                                   data=dict(capture_data,code='SOURCE_EXTRACTION_FAILED',error=str(exc)))
                        continue
                    for ordinal,record in enumerate(parsed['records']):
                        yield dict(metadata,kind='quote',key=f'{capture_key}/{ordinal}',data=record)
                    for ordinal,anomaly in enumerate(parsed['anomalies']):
                        yield dict(metadata,kind='anomaly',key=f'extract/{capture_key}/{ordinal}',
                                   data=dict(anomaly,capture_path=name,linked_fixture_key=fixture_key))
                    yield dict(metadata,kind='evidence',key='parsed/'+capture_key,
                               data=dict(normalized=parsed['normalized'],source_identity=parsed['source_identity'],encoding=parsed['encoding'],
                                         capture_path=name,source_record_count=len(parsed['records'])))


def reuse_market_source_records(reference, *, expected_sha256, issue, fixture_key, path, aliases):
    """Copy verified source records to another issue without reading retired bodies.

    Preserves complete quote/retry/anomaly data and binds each copied record to
    its prior database identity/hash. No parsing, network or writes occur.
    """
    from copy import deepcopy
    from src.market_sqlite_capture import read_market_storage_receipt
    from src.market_sqlite_query import query_market_records, verify_market_source_inventory
    url=reference['source_url']
    read_market_storage_receipt(reference,expected_sha256=expected_sha256,expected_url=url)
    records=query_market_records(reference['database'],issue=reference['issue'],
                                 source_sha256=expected_sha256,source_url=url)
    accepted=verified_market_json(reference['acceptance']['path'],reference['acceptance']['sha256'])
    expected=accepted.get('source_inventories',{}).get(reference['capture_key'])
    if expected is None:
        raise ValueError('accepted source inventory missing')
    verify_market_source_inventory(records,expected)
    old=reference['capture_key']
    new=f'{issue}/{expected_sha256}/response'
    for record in records:
        key=record['record_key']
        if record['batch_id']!=reference['batch_id'] or old not in key:
            raise ValueError('stored source record binding mismatch')
        data=deepcopy(record['data'])
        data['reused_source']=dict(database=reference['database'],batch_id=record['batch_id'],
                                  issue=record['issue'],record_key=key,record_sha256=record['record_sha256'])
        if record['kind']=='capture':
            data.update(path=path,path_aliases=sorted(aliases),linked_fixture_key=fixture_key)
        else:
            if 'capture_path' in data:data['capture_path']=path
            if 'linked_fixture_key' in data:data['linked_fixture_key']=fixture_key
        yield dict(issue=issue,kind=record['kind'],key=key.replace(old,new,1),
                   provider_id=record['provider_id'],market=record['market'],source_url=url,
                   source_sha256=expected_sha256,data=data)


def load_market_issue_audits(data_root, issue_sources):
    """Preflight all published audit inputs, including hash-bound archive members.

    Archive reads are grouped to avoid repeated full archive scans. Returns issue
    to decoded audit rows; duplicate issues and any content hash mismatch fail.
    No extraction, fetching or writes.
    """
    root=Path(data_root).resolve(strict=True)
    result={}
    groups={}
    for source in issue_sources:
        issue=source['issue']
        if issue in result:
            raise ValueError('duplicate issue audit')
        result[issue]=None
        if 'archive' in source:
            groups.setdefault((source['archive'],source['archive_sha256']),[]).append(source)
        else:
            path=(root/source['path']).resolve(strict=True)
            if not path.is_relative_to(root):
                raise ValueError('audit outside persistent root')
            result[issue]=verified_market_json(path,source['sha256'])
    for (name,digest),sources in groups.items():
        path=(root/name).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError('archive outside persistent root')
        payloads=read_archive_members(path,[s['member'] for s in sources],expected_sha256=digest)
        for source in sources:
            payload=payloads[source['member']]
            if hashlib.sha256(payload).hexdigest()!=source['sha256']:
                raise ValueError('archived audit hash mismatch')
            result[source['issue']]=json.loads(payload)
    return result


def market_storage_source_key(url):
    """Identify Titan market responses and matching Nowscore Euro peer scripts."""
    key=market_key(url)
    if key is not None:
        return key
    match=re.fullmatch(r'https://1x2\.nowscore\.com/(\d+)\.js',url)
    return 'euro:'+match[1] if match else None
