"""Independent latest-SP, actual-state rank and all-plan settlement replay.

CLI: project-python scripts/check_n7_expanded_settlement.py CONFIG
Post-freeze audit only. R remains the authoritative SQLite query implementation.
"""
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from src.n7_core_check import core_replay_surface

cfg=json.loads(Path(sys.argv[1]).read_text());study=Path(cfg['study']);output=study/'evaluation/independent-replay.json'
if output.exists():raise ValueError('Settlement replay exists')
receipt=json.loads((study/'evaluation/receipt.json').read_text())
for name,sha in receipt['files'].items():assert hashlib.sha256((study/'evaluation'/name).read_bytes()).hexdigest()==sha
for path,sha in receipt['source_hashes'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha
rank_dir=Path(cfg['output_dir']);rr=json.loads((rank_dir/'receipt.json').read_text())
for name,sha in rr['files'].items():assert hashlib.sha256((rank_dir/name).read_bytes()).hexdigest()==sha
catalog=json.loads((study/'settlement-inputs/catalog.json').read_text())
rank_rows=list(csv.DictReader((rank_dir/'ranks.csv').open()))
ranks={(r['issue'],int(r['sleeve_id'])):r for r in rank_rows}
assert len(ranks)==len(rank_rows)
checked=0
for item in catalog['issues']:
    issue=item['issue']
    if not any(k[0]==issue for k in ranks):continue
    raw=Path(item['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256']
    b=json.loads(gzip.decompress(raw));surface=core_replay_surface(b,dict(core_open_coverage=.25),cutoffs=b['cutoffs'])
    a=json.loads((rank_dir/f'audit-{issue}.json').read_text())
    audit={(str(r['issue']),int(r['slot']),str(r['provider_id'])):r for r in a['fixtures']}
    fixtures=[]
    for f in b['expanded_pool']['fixtures']:
        row=audit[str(f['issue']),int(f['slot']),str(f['provider_id'])]
        assert row['handicap']==f['handicap']
        net=row['actual_home']-row['actual_away']+f['handicap']
        direction='W' if net>0 else 'D' if net==0 else 'L'
        assert row['actual_direction']==direction and row['spf_sp']>0
        candidates=[z for z in a['settlement'] if str(z['issue'])==issue and int(z['slot'])==int(f['slot']) and z['play']=='spf']
        assert candidates and all(str(z['native_match_id'])==str(f['provider_id']) for z in candidates)
        assert all(z['score'].replace(':','-')==f"{int(row['actual_home'])}-{int(row['actual_away'])}" for z in candidates)
        winner=[z for z in candidates if z['option']==dict(W='胜',D='平',L='负')[direction]]
        assert len(winner)==1 and winner[0]['sp']==row['spf_sp'] and winner[0]['source_sha256']==row['spf_source_sha256']
        fixtures.append(row)
    for sid,z in surface.items():
        actual=[fixtures[i] for i in z['f']]
        state=sum('WDL'.index(r['actual_direction'])*3**(6-j) for j,r in enumerate(actual))
        rank=int(np.flatnonzero(z['rank']==state)[0])+1
        gross=2*.65*math.prod(r['spf_sp'] for r in actual)
        r=ranks[issue,int(sid)]
        assert rank==int(r['actual_rank']) and int(r['actual_state_id'])==state
        assert math.isclose(gross,float(r['actual_gross_cny']),rel_tol=1e-10,abs_tol=1e-7)
        checked+=1
assert checked==len(ranks)
funded=defaultdict(list)
for r in csv.DictReader((study/'evaluation/funded.csv').open()):funded[r['issue'],r['arm'],r['seed']].append(r)
groups={(r['issue'],r['arm'],r['seed'],r['sleeve_id']):r for r in csv.DictReader((study/'evaluation/settled-groups.csv').open())}
seen=set();group_count=0
for r in csv.DictReader((study/'evaluation/results.csv').open()):
    key=r['issue'],r['arm'],r['seed'];assert key not in seen;seen.add(key)
    stake=gross=hits=0
    for f in funded[key]:
        rank=ranks[r['issue'],int(f['sleeve_id'])];depth=int(f['depth'])
        assert int(f['copies'])==1 and float(f['stake'])==2*depth
        hit=depth>=int(rank['actual_rank']);paid=float(rank['actual_gross_cny']) if hit else 0
        g=groups[*key,f['sleeve_id']]
        assert (g['hit'].lower()=='true')==hit
        assert math.isclose(float(g['gross']),paid,rel_tol=1e-10,abs_tol=1e-7)
        assert math.isclose(float(g['net']),paid-2*depth,rel_tol=1e-10,abs_tol=1e-7)
        stake+=2*depth;gross+=paid;hits+=hit;group_count+=1
    assert stake==float(r['stake'])<=float(r['budget_cny']) and float(r['cash'])==float(r['budget_cny'])-stake
    assert hits==int(r['hits']) and len(funded[key])==int(r['groups'])
    assert math.isclose(gross,float(r['gross']),rel_tol=1e-10,abs_tol=1e-6)
    assert math.isclose(gross-stake,float(r['net']),rel_tol=1e-10,abs_tol=1e-6)
assert len(seen)==receipt['plans'] and group_count==len(groups)
output.write_text(json.dumps(dict(status='PASS',plans=len(seen),groups=group_count,candidate_ranks=checked,
    evaluation_receipt_sha256=hashlib.sha256((study/'evaluation/receipt.json').read_bytes()).hexdigest(),
    implementation={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in
      ['scripts/check_n7_expanded_settlement.py','src/n7_core_check.py']},historical_admission=False),indent=2))
print('PASS current SQLite rows, actual ranks,',len(seen),'plans and',group_count,'funded groups')
