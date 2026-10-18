"""Capture the frozen308 missing company8 Asian/total URLs with bounded retries."""
if __name__ == '__main__':
    import argparse,hashlib,json
    from datetime import datetime
    from pathlib import Path
    from filelock import FileLock
    from beidan_backend.catalog.paths import location
    from beidan_backend.unified_sources import SourceClient,document_bytes
    from beidan_backend.market_capture.history import over_under_history_url
    from beidan_backend.transport import FetchError
    from beidan_backend.extraction_cache import CaptureIntegrityError,CapturePinError
    from beidan_backend.versioning import write_json_atomically
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();source=Path(a.inventory);x=json.loads(source.read_bytes())
    rows=[r for r in x['channels'] if r['state']=='CACHE_MISS'];fixtures={f['fixture_id']:f for f in x['fixtures']}
    if x['issue_id']!='26105' or len(fixtures)!=365 or len(rows)!=308 or len({r['url'] for r in rows})!=308 or len({r['fixture_id'] for r in rows})!=154:
        raise ValueError('Exact frozen365-fixture308-gap inventory required')
    for row in rows:
        f=fixtures[row['fixture_id']];total=over_under_history_url(f['provider_id'],8,datetime.fromisoformat(f['kickoff_at']))
        expected={'total':total,'asian':total.replace('oddskind=1','oddskind=0')}
        if row['provider_id']!=f['provider_id'] or row['url']!=expected.get(row['kind']):raise ValueError('Native route differs')
    if not a.output.startswith('hot:'):raise ValueError('Explicit hot output required')
    work=location(a.output,require_exists=False);work.mkdir(parents=True,exist_ok=True)
    binding=dict(inventory_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope=308,min_interval_seconds=5,maximum_passes=2)
    with FileLock(str(work/'capture.lock'),timeout=0):
        bp=work/'binding.json'
        if bp.exists():
            if json.loads(bp.read_bytes())!=binding:raise ValueError('Immutable capture binding differs')
        else:write_json_atomically(value=binding,path=bp)
        client=SourceClient();records=[]
        for i,row in enumerate(rows):
            target=work/(row['fixture_id'].replace(':','_')+'-'+row['kind']+'.json')
            prior=json.loads(target.read_bytes()) if target.exists() else None
            if prior and (prior['state']=='CAPTURED_RAW_ONLY' or prior['passes']>=2):records.append(prior);continue
            if prior:write_json_atomically(value=prior,path=work/(target.stem+'-failed-pass1.json'))
            result={k:row[k] for k in ('fixture_id','provider_id','kind','url')};result['passes']=1 if prior is None else prior['passes']+1
            try:
                with client.cache.lock.acquire(poll_interval=0.001,timeout=120):
                    cap=client.cache.extract('titan',row['url'],document_bytes,max_age=0,min_interval=5,retries=1,reuse_raw=True)
                result.update(state='CAPTURED_RAW_ONLY',receipt=cap['receipt'])
            except FetchError as error:
                result.update(state='REQUEST_FAILED',error=str(error),network_attempts=error.network_attempts)
            except (CaptureIntegrityError,CapturePinError):raise
            except ValueError as error:
                if not hasattr(error,'extraction_receipt'):raise
                result.update(state='DOCUMENT_REJECTED',receipt=error.extraction_receipt,error_type=type(error).__name__,error=str(error))
            write_json_atomically(value=result,path=target);records.append(result)
            if (i+1)%10==0:print('PROGRESS',i+1,'/308',flush=True)
        summary=dict(total=len(records),captured=sum(r['state']=='CAPTURED_RAW_ONLY' for r in records),failed=sum(r['state']!='CAPTURED_RAW_ONLY' for r in records),prices_validated=False)
        write_json_atomically(value=summary,path=work/'completion.json');print(json.dumps(summary),flush=True)
        raise SystemExit(0 if summary['failed']==0 else 2)
