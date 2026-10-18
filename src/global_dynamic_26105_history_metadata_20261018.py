"""Replay365 validated Titan headers into opponent-history metadata, offline."""
if __name__ == '__main__':
    import argparse,hashlib,json
    from pathlib import Path
    from beidan_backend.catalog.paths import location
    from beidan_backend.unified_sources import SourceClient
    from beidan_backend.extraction_cache import CaptureIntegrityError,CapturePinError,CacheMissError
    from beidan_backend.opponent_history import parse_opponent_history
    from beidan_backend.versioning import write_json_atomically
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inventory',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    path=Path(a.inventory);x=json.loads(path.read_bytes());headers=x['headers']
    if x['issue_id']!='26105' or len(headers)!=365 or len({h['fixture_id'] for h in headers})!=365 or any(h['state']!='HEADER_VALIDATED' for h in headers):raise ValueError('365 validated headers required')
    out=location(a.output,require_exists=False)
    if out.exists():raise ValueError('Immutable output exists')
    out.mkdir(parents=True);client=SourceClient();packets=[]
    for h in headers:
        receipt=h['analysis_receipt'];identity=h['identity'];item=dict(fixture_id=h['fixture_id'],source='titan',state='NOT_CHECKED')
        try:
            cap=client.request('titan',receipt['url'],max_age=0,cache_only=True,reuse_raw=True)
        except (CaptureIntegrityError,CapturePinError):raise
        except (CacheMissError,ValueError) as error:
            item.update(state='REJECTED',error_type=type(error).__name__,error=str(error));packets.append(item);continue
        if cap['receipt']['sha256']!=receipt['sha256'] or cap['receipt']['network_attempts']!=0:raise ValueError('Frozen raw identity or offline contract differs')
        item['receipt']=cap['receipt']
        try:
            item.update(state='PARSED',result=parse_opponent_history(cap['data'],source='titan',provider_id=identity['provider_id'],expected_identity=identity))
        except (ValueError,KeyError) as error:item.update(state='REJECTED',error_type=type(error).__name__,error=str(error))
        packets.append(item)
    result=dict(issue_id='26105',scope=365,network_attempts=0,historical_admission=False,
        inventory_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),packets=packets)
    write_json_atomically(value=result,path=out/'metadata.json')
    print(json.dumps({state:sum(p['state']==state for p in packets) for state in sorted({p['state'] for p in packets})}),flush=True)
