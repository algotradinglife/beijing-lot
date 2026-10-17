"""Replay saved Asian/total histories for the last25 fixtures, no HTTP/admission."""
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit,parse_qs
from beidan_backend.market_capture.history import parse_over_under_history_json,parse_asian_handicap_history_json
from beidan_backend.temporal_learning import implementation_closure

root=Path(sys.argv[1]).resolve();out=root/'results/fm171-26103-draw-20261017'
inputs=json.loads((out/'inputs.json').read_text())
fixtures={f['fixture_id']:f for f in inputs['fixtures']}
packets=[]
for path in sorted((root/'results/fm16-upcoming-20261013/market-captures').glob('26103_*.json')):
    saved=json.loads(path.read_text());id=saved['fixture']['fixture_id'];f=fixtures[id]
    assert saved['fixture']['provider_id_nowscore']==f['provider_id']
    packet=dict(fixture_id=id,path=str(path.relative_to(root)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),quotes=[],receipts=[])
    kickoff=datetime.fromisoformat(f['kickoff_at']).replace(tzinfo=datetime.fromisoformat('2000-01-01T00:00:00+00:00').tzinfo)
    for kind in ('asian','total'):
        caps=[c for c in saved['captures'] if c['kind']==kind]
        if not caps:continue
        assert len(caps)==1
        cap=caps[0]
        if not cap.get('sha256'):
            packet.setdefault('gaps',[]).append(dict(kind=kind,state='NO_SUCCESSFUL_RAW'));continue
        raw=root/cap['raw_path'];body=raw.read_bytes();assert hashlib.sha256(body).hexdigest()==cap['sha256']
        url=urlsplit(cap['url']);query=parse_qs(url.query)
        assert url.hostname=='m.titan007.com' and query['scheid']==[f['provider_id']] and query['oddskind']==['0' if kind=='asian' else '1'] and query['isHalf']==['0']
        parser=parse_asian_handicap_history_json if kind=='asian' else parse_over_under_history_json
        snapshots,counters=parser(body,kickoff_hkt=kickoff)
        packet['receipts'].append(dict(kind=kind,raw_path=cap['raw_path'],sha256=cap['sha256'],url=cap['url'],observed_at=cap['observed_at'],counters=counters))
        for s in snapshots:
            packet['quotes'].append(dict(kind=kind,fixture_id=id,company_id=query['companyid'][0],quote_at=s.snapshot_ts_hkt,line=s.line_value,
               home_decimal=None if (s.odds['home'] if kind=='asian' else s.odds['over']) is None else 1+(s.odds['home'] if kind=='asian' else s.odds['over']),
               away_decimal=None if (s.odds['away'] if kind=='asian' else s.odds['under']) is None else 1+(s.odds['away'] if kind=='asian' else s.odds['under']),
               phase=s.phase,complete=s.complete,raw_row_sha256=s.raw_row_sha256))
    packets.append(packet)
result=dict(packets=packets,network_attempts=0,implementation=implementation_closure(root,('beidan_backend.market_capture.history',),distributions=()),
            client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(out/'market-inputs.json').write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')))
print('saved market fixtures',len(packets),'raw Asian/total quotes',sum(len(p['quotes']) for p in packets))
