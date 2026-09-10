"""Build tiny deterministic offline report inputs, without network or model fitting."""
import argparse
import hashlib
import json
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = Path(args.output);out.mkdir(parents=True, exist_ok=True)
    grid = [dict(home_goals=h,away_goals=a,probability=p,outcome=d) for h,a,p,d in [(0,0,.2,'D'),(1,0,.5,'W'),(0,1,.3,'L')]]
    fixtures=[]
    for name in ['previous','next']:
        data=json.loads((root/f'tests/fixtures/fundamentals_returns/{name}.json').read_text())
        f=data['fixtures'][0];f['handicap']=0
        rows=[dict(f,scenario=s) for s in ['baseline','both_half']];fixtures.extend(rows)
        scores=[dict(g,issue=f['issue'],slot=f['slot'],provider_id=f['provider_id'],scenario=s) for s in ['baseline','both_half'] for g in grid]
        data=dict(fixtures=rows,scores=scores,predictions={s:dict(grids={f"{f['slot']}/raw":grid}) for s in ['baseline','adjusted']})
        (out/f'{name}.json').write_text(json.dumps(data))
    cutoffs={f['issue']:{str(f['slot']):'2010-01-01T00:00:00Z'} for f in fixtures}
    (out/'inventories.json').write_text(json.dumps([dict(issue=i,cutoffs=c) for i,c in cutoffs.items()]))
    capture=out/'capture.txt';capture.write_text('deterministic synthetic market fixture')
    rows=[dict(issue=f['issue'],slot=f['slot'],provider_id=f['provider_id'],status='OK_DIAGNOSTIC',cutoff_utc=cutoffs[f['issue']][str(f['slot'])],capture_path=str(capture.resolve()),capture_sha256=hashlib.sha256(capture.read_bytes()).hexdigest(),odds_W=2,odds_D=4,odds_L=4) for f in fixtures if f['scenario']=='baseline']
    euro=dict(rows=rows,implementation_hashes={})
    canonical=json.dumps(euro);seal=hashlib.sha256(canonical.encode()).hexdigest()
    (out/'euro.json').write_text(json.dumps(dict(canonical_json=canonical,seal=seal)))
    total=dict(rows=rows,euro_seal=seal,cutoffs=cutoffs,capture_hashes={},implementation_hashes={},selected=[dict(issue=f['issue'],slot=f['slot'],provider_id=f['provider_id'],company='synthetic',line=2.5,over_hk=1,under_hk=1) for f in rows])
    canonical=json.dumps(total)
    (out/'total.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
