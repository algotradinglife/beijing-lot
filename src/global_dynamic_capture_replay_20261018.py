"""Independently reparse every sealed Asian/total channel from pinned raw bytes."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from beidan_backend.catalog.paths import location
from beidan_backend.unified_sources import SourceClient
from beidan_backend.market_capture.history import parse_asian_handicap_history_json, parse_over_under_history_json
from beidan_backend.versioning import write_json_atomically

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--issue',choices=['26103','26104'],required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();root=a.root.resolve(strict=True)
    if a.issue=='26103':
        work=location('hot:fm171-26103-full-recalc-20261017')/'markets-v3-5s'
        fixtures=json.loads((root/'results/fm171-26103-draw-20261017/inputs.json').read_bytes())['fixtures']
    else:
        work=location('hot:global-dynamic-26104-20261018')
        fixtures=json.loads((work/'inputs.json').read_bytes())['fixtures']
    expected={f['fixture_id']:f for f in fixtures};client=SourceClient();n=empty=0
    for path in sorted(work.glob('*-*.json')):
        if not path.name.endswith(('-asian.json','-total.json')): continue
        envelope=json.loads(path.read_bytes());payload=envelope['payload']
        if hashlib.sha256(payload.encode()).hexdigest()!=envelope['sha256']: raise ValueError('Corrupt parsed envelope')
        x=json.loads(payload);f=expected[x['fixture_id']]
        if x['state'] not in {'PARSED','OBSERVED_EMPTY'}: raise ValueError('Unresolved capture failure')
        ref=x['raw_receipt']
        if x.get('origin')=='EXISTING_PINNED_CAPTURE':
            body=(root/ref['raw_path']).read_bytes()
        else:
            cap=client.request('titan',x['url'],max_age=0,cache_only=True,capture_id=ref['capture_id'])
            if cap['receipt']['network_attempts']!=0: raise ValueError('Replay attempted network')
            body=cap['data']
        if hashlib.sha256(body).hexdigest()!=x['raw_sha256']: raise ValueError('Raw SHA differs')
        if json.loads(body)==[]:
            if x['state']!='OBSERVED_EMPTY' or x['snapshots']: raise ValueError('Empty/source failure conflation')
            empty+=1
        else:
            kickoff=datetime.fromisoformat(f['kickoff_at']).replace(tzinfo=timezone.utc)
            parse=parse_asian_handicap_history_json if x['kind']=='asian' else parse_over_under_history_json
            snapshots,counters=parse(body,kickoff_hkt=kickoff)
            if [asdict(s) for s in snapshots]!=x['snapshots'] or counters!=x['counters']:
                raise ValueError('Independent raw parser replay differs: '+path.name)
        n+=1
    if n!=len(fixtures)*2: raise ValueError('Incomplete full-issue replay')
    write_json_atomically(dict(status='FULL_RAW_PARSER_IDENTICAL_REPLAY',issue=a.issue,channels=n,
        observed_empty=empty,network_attempts=0,client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),a.output)
    print(n,'channels identical',flush=True)
