"""Offline26105 company8 line-history parsing; no historical admission implied."""
if __name__ == '__main__':
    import argparse, hashlib, json
    from dataclasses import asdict
    from datetime import datetime
    from pathlib import Path
    from beidan_backend.catalog.paths import location
    from beidan_backend.extraction_cache import CacheMissError,CaptureIntegrityError,CapturePinError
    from beidan_backend.unified_sources import SourceClient, document_bytes
    from beidan_backend.market_capture.history import parse_asian_handicap_history_json, parse_over_under_history_json,over_under_history_url
    from beidan_backend.versioning import write_json_atomically
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    source=Path(a.inventory);inventory=json.loads(source.read_bytes())
    fixtures={r['fixture_id']:r for r in inventory['fixtures']}
    channels=inventory['channels']
    if inventory['issue_id']!='26105' or len(fixtures)!=365 or len(channels)!=730 or len({(r['fixture_id'],r['kind']) for r in channels})!=730:
        raise ValueError('Exact365-fixture730-channel inventory required')
    if any(r['fixture_id'] not in fixtures or r['kind'] not in {'asian','total'} for r in channels):raise ValueError('Invalid channel identity')
    for channel in channels:
        fixture=fixtures[channel['fixture_id']]
        total=over_under_history_url(fixture['provider_id'],8,datetime.fromisoformat(fixture['kickoff_at']))
        expected=total if channel['kind']=='total' else total.replace('oddskind=1','oddskind=0')
        if channel['provider_id']!=fixture['provider_id'] or channel['url']!=expected:raise ValueError('Native channel route differs')
    out=location(a.output,require_exists=False)
    if out.exists():raise ValueError('Immutable output exists')
    out.mkdir(parents=True);client=SourceClient();records=[]
    for channel in channels:
        record={k:channel[k] for k in ('fixture_id','provider_id','kind','url')}
        try:
            cap=client.cache.extract('titan',channel['url'],document_bytes,max_age=0,min_interval=5,cache_only=True,reuse_raw=True)
        except CacheMissError:
            record.update(state='CACHE_MISS');records.append(record);continue
        except (CaptureIntegrityError,CapturePinError):raise
        except ValueError as error:
            if not hasattr(error,'extraction_receipt'):raise
            if channel.get('receipt') and error.extraction_receipt['sha256']!=channel['receipt']['sha256']:raise ValueError('Inventory raw identity changed') from error
            record.update(state='DOCUMENT_REJECTED',raw_receipt=error.extraction_receipt,error_type=type(error).__name__,error=str(error))
            records.append(record);continue
        if cap['receipt']['network_attempts']!=0:raise ValueError('Offline extraction performed network request')
        if channel.get('receipt') and cap['receipt']['sha256']!=channel['receipt']['sha256']:raise ValueError('Inventory raw identity changed')
        record['raw_receipt']=cap['receipt']
        try:
            body=cap['data'];kickoff=datetime.fromisoformat(fixtures[channel['fixture_id']]['kickoff_at'])
            if kickoff.utcoffset() is None:raise ValueError('Timezone-aware kickoff required')
            if json.loads(body)==[]:record.update(state='OBSERVED_EMPTY',snapshots=[],counters={'observed_empty':True})
            else:
                parser=parse_asian_handicap_history_json if channel['kind']=='asian' else parse_over_under_history_json
                snapshots,counters=parser(body,kickoff_hkt=kickoff)
                record.update(state='PARSED',snapshots=[asdict(r) for r in snapshots],counters=counters)
        except (ValueError,KeyError,TypeError) as error:
            record.update(state='PARSE_REJECTED',error_type=type(error).__name__,error=str(error))
        records.append(record)
    result=dict(issue_id='26105',inventory_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),network_attempts=0,
        historical_admission=False,records=records)
    write_json_atomically(value=result,path=out/'parsed.json')
    print(json.dumps({state:sum(r['state']==state for r in records) for state in sorted({r['state'] for r in records})}),flush=True)
