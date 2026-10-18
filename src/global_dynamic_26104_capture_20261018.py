"""Bounded26104 cache metadata replay and source-specific5s Asian/total capture.

Thin domain client: shared SourceClient owns transport/cache/retries; existing
parsers own metadata and line conventions. Raw bytes never enter this repository.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from filelock import FileLock
from beidan_backend.catalog.paths import location
from beidan_backend.unified_sources import SourceClient, canonical, document_bytes
from beidan_backend.fundamentals import analysis_record
from beidan_backend.opponent_history import parse_opponent_history
from beidan_backend.market_capture.history import (
    over_under_history_url, parse_asian_handicap_history_json,
    parse_over_under_history_json,
)
from beidan_backend.versioning import write_json_atomically
from beidan_backend.temporal_learning import implementation_closure

if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--min-interval-seconds',type=float,choices=[5.0],required=True)
    ap.add_argument('--cache-only',action='store_true')
    ap.add_argument('--maximum-channel-attempts',type=int,choices=[2],required=True)
    a=ap.parse_args();root=a.root.resolve(strict=True)
    if not a.output.startswith('hot:'): raise ValueError('Explicit hot: output required')
    out=location(a.output);source=out/'inputs.json';x=json.loads(source.read_bytes())
    fixtures=x['fixtures']
    if x['issue_id']!='26104' or len(fixtures)!=109 or len({f['fixture_id'] for f in fixtures})!=109:
        raise ValueError('Exact109-fixture26104 input required')
    inputs_sha=hashlib.sha256(source.read_bytes()).hexdigest()
    implementation=implementation_closure(root,('beidan_backend.unified_sources',
        'beidan_backend.fundamentals','beidan_backend.opponent_history',
        'beidan_backend.market_capture.history','beidan_backend.versioning'),
        distributions=('beautifulsoup4','json5','filelock'))
    binding=dict(inputs_sha256=inputs_sha,client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        implementation=implementation,min_interval_seconds=a.min_interval_seconds,cache_only=a.cache_only,maximum_channel_attempts=a.maximum_channel_attempts)
    client=SourceClient();packets=[];states=[]
    with FileLock(str(out/'capture.lock'),timeout=0):
        path=out/'capture-binding.json'
        if path.exists():
            if json.loads(path.read_bytes())!=binding: raise ValueError('Changed binding requires new output')
        else: write_json_atomically(binding,path)
        for f in fixtures:
            pid=f['provider_id'];id=f['fixture_id'];refs=[r for r in x['provenance'] if r['fixture_id']==id and r['source']=='titan']
            packet=dict(fixture_id=id,source='titan',state='NOT_CHECKED',receipts=[])
            try:
                analyses=[r for r in refs if '/analysis/' in r['url']]
                if len(analyses)!=1: raise ValueError('Unique accepted analysis provenance required')
                ref=analyses[0];cap=client.request('titan',ref['url'],max_age=0,cache_only=True,reuse_raw=True)
                if cap['receipt']['sha256']!=ref['sha256']: raise ValueError('Published analysis SHA differs')
                packet['receipts'].append(cap['receipt']);aux=None
                auxiliaries=[r for r in refs if '/analysisJs/' in r['url']]
                if auxiliaries:
                    if len(auxiliaries)!=1: raise ValueError('Unique auxiliary provenance required')
                    ac=client.request('titan',auxiliaries[0]['url'],max_age=0,cache_only=True,reuse_raw=True)
                    if ac['receipt']['sha256']!=auxiliaries[0]['sha256']: raise ValueError('Published auxiliary SHA differs')
                    aux=ac['data'];packet['receipts'].append(ac['receipt'])
                head=analysis_record(cap['data'],source='titan',provider_id=pid,auxiliary_raw=aux,identity_only=True)
                expected={k:head[k] for k in ['provider_id','home','away','home_id','away_id','kickoff_utc']}
                if expected['home_id']!=f['home_id'] or expected['away_id']!=f['away_id']:
                    raise ValueError('Published oriented identity differs')
                packet.update(state='PARSED',result=parse_opponent_history(cap['data'],source='titan',provider_id=pid,expected_identity=expected,auxiliary_raw=aux))
            except (ValueError,RuntimeError,OSError,KeyError) as exc:
                packet.update(state='REJECTED',error_type=type(exc).__name__,error=str(exc))
            packets.append(packet)
            kickoff=datetime.fromisoformat(f['kickoff_at']).replace(tzinfo=timezone.utc)
            total=over_under_history_url(pid,8,kickoff)
            for kind,url,parse in [('asian',total.replace('oddskind=1','oddskind=0'),parse_asian_handicap_history_json),('total',total,parse_over_under_history_json)]:
                target=out/(id.replace(':','_')+'-'+kind+'.json')
                attempt=1;needs_capture=not target.exists()
                if target.exists():
                    envelope=json.loads(target.read_bytes());payload=envelope['payload']
                    if hashlib.sha256(payload.encode()).hexdigest()!=envelope['sha256']: raise ValueError('Receipt corrupt')
                    result=json.loads(payload)
                    if result['inputs_sha256']!=inputs_sha or result['url']!=url: raise ValueError('Receipt binding differs')
                    if result['state']=='FAILED' and result.get('attempt',1)<a.maximum_channel_attempts:
                        history=out/'failed-attempts';history.mkdir(exist_ok=True)
                        archive=history/(target.stem+'-'+envelope['sha256']+'.json')
                        if not archive.exists(): write_json_atomically(envelope,archive)
                        attempt=result.get('attempt',1)+1;needs_capture=True
                if needs_capture:
                    result=dict(fixture_id=id,provider_id=pid,home_id=f['home_id'],away_id=f['away_id'],kind=kind,url=url,
                        cutoff_utc=f['cutoff_utc'],inputs_sha256=inputs_sha,state='NOT_CHECKED',historical_admission=False,network_attempts=0,attempt=attempt)
                    try:
                        cap=client.cache.extract('titan',url,document_bytes,max_age=0,min_interval=a.min_interval_seconds,
                            cache_only=a.cache_only,reuse_raw=True)
                        body=cap['data'];result['raw_receipt']=cap['receipt'];result['raw_sha256']=hashlib.sha256(body).hexdigest()
                        result['network_attempts']=cap['receipt']['network_attempts']
                        if json.loads(body)==[]: result.update(state='OBSERVED_EMPTY',snapshots=[],counters={'observed_empty':True})
                        else:
                            snapshots,counters=parse(body,kickoff_hkt=kickoff)
                            result.update(state='PARSED',snapshots=[asdict(s) for s in snapshots],counters=counters)
                    except (ValueError,RuntimeError,OSError,KeyError) as exc:
                        result.update(state='FAILED',error_type=type(exc).__name__,error=str(exc),network_attempts=getattr(exc,'network_attempts',result['network_attempts']))
                    payload=canonical(result)
                    write_json_atomically(dict(payload=payload,sha256=hashlib.sha256(payload.encode()).hexdigest()),target)
                states.append(dict(fixture_id=id,kind=kind,state=result['state']))
                print(id,kind,result['state'],flush=True)
        complete=all(s['state'] in {'PARSED','OBSERVED_EMPTY'} for s in states)
        # Metadata is published only after full traversal; processing clocks are not facts.
        for packet in packets:
            for receipt in packet['receipts']:
                receipt.pop('processed_at',None)
        metadata=dict(packets=packets,inputs_sha256=inputs_sha,implementation=implementation)
        metadata_path=out/'metadata.json'
        if complete:
            if metadata_path.exists():
                if json.loads(metadata_path.read_bytes())!=metadata: raise ValueError('Immutable metadata differs')
            else: write_json_atomically(metadata,metadata_path)
        write_json_atomically(dict(fixtures=109,channels=len(states),states=states,
            metadata_parsed=sum(p['state']=='PARSED' for p in packets),collection_complete=complete,
            historical_admission=False,full_fm_analysis_accepted=False),out/'capture-status.json')
        if not complete: raise SystemExit(2)
