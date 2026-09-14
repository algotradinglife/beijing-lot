"""Independent frozen-plan budget/settlement replay, no fitting or selection.

Usage: project-python scripts/check_n7_funding_modes.py STUDY OUTPUT_JSON
The payout in rank evidence already includes one ticket-level 0.65 factor.
"""
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from itertools import product
from pathlib import Path

study, output = map(Path, sys.argv[1:])
assert not output.exists()
raw = (study / 'plans-frozen.json').read_bytes()
freeze = json.loads(raw)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.n7_union_inputs import verify_union_binding
assert verify_union_binding(freeze['input_binding'],freeze['config']['catalog'],
    freeze['config']['rank_dir'],freeze['config']['repository_root'])
ev = json.loads((study / 'evaluation-receipt.json').read_text())
assert ev['ranks_sha256']==json.loads(freeze['input_binding'])['ranks_sha256']
assert hashlib.sha256(raw).hexdigest() == ev['freeze_sha256']
assert freeze['historical_admission'] is False
for name, sha in freeze['files'].items():
    assert hashlib.sha256((study/name).read_bytes()).hexdigest() == sha
assert hashlib.sha256((study/'results.csv').read_bytes()).hexdigest() == ev['results_sha256']
rank_path = Path(freeze['config']['rank_dir'])/'ranks.csv'
assert hashlib.sha256(rank_path.read_bytes()).hexdigest() == ev['ranks_sha256']
ranks = {(r['issue'],r['sleeve_id']):r for r in csv.DictReader(rank_path.open())}
funded = defaultdict(list)
for r in csv.DictReader((study/'funded.csv').open()):
    assert not {'actual_rank','actual_gross_cny','hit','net'} & set(r)
    funded[r['issue'],r['arm'],r['seed']].append(r)
seen=set()
for r in csv.DictReader((study/'results.csv').open()):
    key=r['issue'],r['arm'],r['seed']
    assert key not in seen
    seen.add(key)
    selected=funded[key]
    assert len({x['sleeve_id'] for x in selected})==len(selected)
    stake=gross=hits=0
    for x in selected:
        depth=int(x['depth']);copies=int(x['copies'])
        assert 1<=copies<=freeze['config']['max_copies']
        assert 1<=depth<=2187 and float(x['stake'])==2*depth*copies
        assert float(x['coverage'])+1e-12>=float(r['target'])
        if r['mode']=='BREADTH': assert float(x['stake'])<=freeze['config']['cap_cny']
        rank=ranks[key[0],x['sleeve_id']]
        hit=int(rank['actual_rank'])<=depth
        hits+=hit;stake+=2*depth*copies;gross+=hit*copies*float(rank['actual_gross_cny'])
    assert stake==float(r['stake'])<=float(r['budget_cny'])
    assert float(r['cash'])==float(r['budget_cny'])-stake
    assert hits==int(r['hits']) and len(selected)==int(r['groups'])
    assert math.isclose(gross,float(r['gross']),rel_tol=1e-10,abs_tol=1e-6)
    assert math.isclose(gross-stake,float(r['net']),rel_tol=1e-10,abs_tol=1e-6)
assert len(seen)==ev['plans']
cfg=freeze['config']
for name in ('policies','budgets','targets','modes','seeds'):
    if name in cfg and not isinstance(cfg[name],list):cfg[name]=[cfg[name]]
assert 'original_config' not in cfg
arms=[f'T{round(1000*t)}_{m}_B{b}' for t,m,b in product(cfg['targets'],[p['id'] for p in cfg['policies']],cfg['budgets'])]
assert seen==set(product(freeze['metadata'],arms,map(str,cfg['seeds'])))
assert set(funded)<=seen
output.write_text(json.dumps(dict(status='PASS',plans=len(seen),
    freeze_sha256=ev['freeze_sha256'],results_sha256=ev['results_sha256'],
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
print(f'PASS: {len(seen)} plans')
