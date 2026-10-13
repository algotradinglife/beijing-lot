"""Independent provider-listed roster inventory for exact future-ID exclusion."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from beidan_backend.catalog.paths import location
from beidan_backend.opponent_roster import parse_exclusion_roster
from beidan_backend.versioning import write_json_atomically
from beidan_backend.temporal_learning.provenance import implementation_closure


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f"file:{location('hot:source-extraction/raw.sqlite')}?mode=ro",uri=True) as con:
        rows=con.execute("select capture_id,source,url,observed_at,sha256,body,content_type from captures where url like '%/buy/DanChang.aspx%' order by capture_id").fetchall()
    packets=[];ledger=[]
    for cid,source,url,at,sha,body,ctype in rows:
        if source!='nowscore':continue
        if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('Exclusion roster raw digest mismatch')
        receipt=dict(capture_id=cid,url=url,observed_at=at,sha256=sha,content_type=ctype)
        try:packet=parse_exclusion_roster(body,source_url=url,observed_at=at,content_type=ctype)
        except ValueError as e:
            ledger.append({**receipt,'state':'REJECTED','error':str(e)});continue
        packets.append({**receipt,**packet});ledger.append({**receipt,'state':'PARSED','error':''})
        p=out/'raw'/f'{sha}.html';p.parent.mkdir(exist_ok=True)
        if not p.exists():p.write_bytes(body)
    if not packets:raise ValueError('No independently parsed roster inventory')
    result=dict(packets=packets,ledger=ledger,network_attempts=0,
        availability='HISTORICAL_IDENTITY_EXCLUSION_ONLY',
        implementation=implementation_closure(Path.cwd(),('beidan_backend.opponent_roster',),distributions=('beautifulsoup4',)),
        parser_sha256=hashlib.sha256(Path('packages/beidan/inst/python/beidan_backend/opponent_roster.py').read_bytes()).hexdigest(),
        client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    path=out/'rosters.json'
    if path.exists():
        if json.loads(path.read_bytes())!=result:raise ValueError('Immutable exclusion roster replay differs')
    else:write_json_atomically(result,path)
    print(json.dumps(dict(packets=len(packets),selected_issues=sorted({p['selected_issue'] for p in packets}))))
