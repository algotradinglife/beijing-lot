"""Bounded offline metadata replay; no source replacement or temporal learning."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from beidan_backend.catalog.paths import location
from beidan_backend.opponent_history import parse_opponent_history
from beidan_backend.versioning import write_json_atomically


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--fixture',action='append',help='Bounded fixture selection for deterministic integration tests')
    args=parser.parse_args()
    inp=Path(args.input);out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    inputs=json.loads(inp.read_bytes())
    fixtures={f['fixture_id']:f for f in inputs['fixtures']}
    if args.fixture:
        if not set(args.fixture)<=set(fixtures):raise ValueError('Unknown requested fixture')
        fixtures={k:v for k,v in fixtures.items() if k in args.fixture}
    # One stable read transaction; never initialize, refresh or mutate this cache.
    with sqlite3.connect(f"file:{location('hot:source-extraction/raw.sqlite')}?mode=ro",uri=True) as con:
        con.execute('BEGIN')
        rows=con.execute('select source,url,observed_at,sha256,body from captures').fetchall()
    captures={}
    for source,url,at,sha,body in rows:
        if hashlib.sha256(body).hexdigest()!=sha:raise ValueError('Raw capture digest mismatch')
        captures[(source,url,sha)]=(body,at)
    parsed=[];ledger=[]
    for fid,f in fixtures.items():
        evidence=[p for p in inputs['provenance'] if p['fixture_id']==fid]
        for source in ('titan','nowscore'):
            ps=[p for p in evidence if p['source']==source and '/analysis/' in p['url']]
            if len(ps)!=1:continue
            p=ps[0];capture=captures.get((source,p['url'],p['sha256']))
            state=dict(fixture_id=fid,source=source,url=p['url'],sha256=p['sha256'],observed_at=p['observed_at'])
            if not f['kickoff_utc']:
                ledger.append({**state,'state':'MISSING_FROZEN_CLOCK','error':''});continue
            if capture is None:
                ledger.append({**state,'state':'RAW_NOT_IN_CACHE','error':''});continue
            body,at=capture
            aux=[q for q in evidence if q['source']==source and 'analysisJs/' in q['url']]
            auxbody=None;auxsha=None
            if aux:
                if len(aux)!=1:raise ValueError('Ambiguous auxiliary provenance')
                a=aux[0];ac=captures.get((source,a['url'],a['sha256']))
                if ac is None:
                    ledger.append({**state,'state':'AUXILIARY_NOT_IN_CACHE','error':''});continue
                auxbody=ac[0];auxsha=a['sha256']
            identity={k:f[k] for k in ('provider_id','home','away','home_id','away_id','kickoff_utc')}
            # Existing source parser returns canonical ISO with +00:00.
            identity['kickoff_utc']=identity['kickoff_utc'].replace('Z','+00:00')
            try:
                result=parse_opponent_history(body,source=source,provider_id=f['provider_id'],
                    expected_identity=identity,auxiliary_raw=auxbody)
            except ValueError as error:
                ledger.append({**state,'state':'PARSER_OR_IDENTITY_REJECTED','error':str(error)});continue
            # Preserve original bytes in short-lived declared NVMe evidence.
            writepath=out/'raw'/f"{p['sha256']}.html";writepath.parent.mkdir(exist_ok=True)
            if not writepath.exists():writepath.write_bytes(body)
            if auxbody is not None:
                ap=out/'raw'/f'{auxsha}.js'
                if not ap.exists():ap.write_bytes(auxbody)
            parsed.append({**state,'auxiliary_sha256':auxsha,'result':result})
            ledger.append({**state,'state':'PARSED','error':''})
    result=dict(input_sha256=hashlib.sha256(inp.read_bytes()).hexdigest(),parsed=parsed,ledger=ledger,
        parser_sha256=hashlib.sha256(Path('packages/beidan/inst/python/beidan_backend/opponent_history.py').read_bytes()).hexdigest(),
        source_parser_sha256=hashlib.sha256(Path('packages/beidan/inst/python/beidan_backend/fundamentals.py').read_bytes()).hexdigest(),
        client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),availability='HISTORICAL_PROXY',network_attempts=0)
    target=out/'metadata.json'
    if target.exists():
        if json.loads(target.read_bytes())!=result:raise ValueError('Immutable replay differs')
    else:write_json_atomically(result,target)
    print(json.dumps(dict(parsed=len(parsed),states={s:sum(l['state']==s for l in ledger) for s in sorted({l['state'] for l in ledger})})))
