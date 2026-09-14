"""Independent NumPy selection, prefix, shared-world and budget replay.

CLI: project-python scripts/check_n7_expanded_allocations.py ALLOCATION_DIR
Reads only prediction artifacts; never target settlement. Writes one receipt.
"""
import csv
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import shutil
from itertools import product

import numpy as np
from src.n7_core_check import core_replay_surface
from src.n7_expanded_replay import replay_open_first
from src.n7_exchange_replay import replay_group_exchange
from src.n7_quality_replay import validate_quality_funded
from src.n7_expanded_pool_check import verify_expanded_pool

study=Path(sys.argv[1]);out=study/'prediction-replay.json'
if out.exists():raise ValueError('Replay exists')
raw=(study/'plans-frozen.json').read_bytes();f=json.loads(raw);cfg=f['config']
assert f['historical_admission'] is False
canonical=json.loads((Path(cfg['repository_root'])/'config/n7_expanded_459.json').read_text())
assert all(cfg[k]==v for k,v in canonical.items()),'Fixed research configuration differs'
for path,sha in f['source_hashes'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha
for name,sha in f['files'].items():assert hashlib.sha256((study/name).read_bytes()).hexdigest()==sha
for name,sha in f['implementation'].items():assert hashlib.sha256((Path(cfg['repository_root'])/name).read_bytes()).hexdigest()==sha
assert hashlib.sha256(Path(cfg['catalog']).read_bytes()).hexdigest()==cfg['catalog_sha256']
catalog=json.loads(Path(cfg['catalog']).read_text())
bundles={r['issue']:r for r in catalog['issues']}
rows=list(csv.DictReader((study/'predictions.csv').open()))
records=defaultdict(list)
for r in csv.DictReader((study/'funded.csv').open()):
    for k in ['sleeve_id','depth','copies','stake','coverage','expected_gross']:r[k]=float(r[k])
    records[r['issue'],r['arm'],r['seed']].append(r)
assert len(rows)==len(catalog['requested_issues'])*len(cfg['policies'])*len(cfg['seeds'])*len(cfg['budgets'])
seen=set();last_issue=None;last_snapshot=None
for r in rows:
    key=r['issue'],r['arm'],r['seed'];assert key not in seen;seen.add(key)
    policy=next(p for p in cfg['policies'] if p['variant']==r['variant'])
    budget=int(r['budget_cny'])
    assert r['arm']==f"T250_{policy['id']}_B{budget}" and budget in cfg['budgets'] and int(r['seed']) in cfg['seeds']
    if r['issue'] not in bundles:
        assert r['issue'] in catalog['unavailable'] and not records[key]
        assert float(r['stake'])==0 and float(r['cash'])==budget
        continue
    if last_issue!=r['issue']:
        item=bundles[r['issue']];braw=Path(item['path']).read_bytes()
        assert hashlib.sha256(braw).hexdigest()==item['sha256']
        bundle=json.loads(gzip.decompress(braw));cuts=bundle['cutoffs']
        surface=core_replay_surface(bundle,dict(core_open_coverage=.25),cutoffs=cuts)
        request={k:cfg[k] for k in ['seeds','allocation_worlds','evaluation_worlds','evaluation_seed_offset']}
        request.update(bundle=item['path'],cutoffs=cuts)
        rng=subprocess.run([shutil.which('Rscript'),str(Path(cfg['repository_root'])/'scripts/replay_n7_expanded_worlds.R'),cfg['repository_root']],
            input=json.dumps(request),text=True,capture_output=True,check=True)
        seed_worlds=json.loads(rng.stdout)
        last_issue=r['issue']
    name=f"replay-{r['issue']}-{r['seed']}-{r['variant']}.json.gz"
    if name!=last_snapshot:
        snapshot=json.loads(gzip.decompress((study/name).read_bytes()))
        assert snapshot['cutoffs']==cuts==f['cutoffs'][r['issue']]
        verify_expanded_pool(snapshot,bundle,surface,cuts,cfg,policy)
        opts=snapshot['options']
        for o in opts:
            z=surface[o['sleeve_id']];d=int(o['depth'])
            assert o['state_ids']==(z['rank'][:d]+1).tolist()
            assert np.allclose(o['state_probability'],z['p'],rtol=1e-10,atol=1e-14)
            assert np.allclose(o['state_payout'],z['payout'],rtol=1e-10)
            assert np.isclose(o['coverage'],z['mass'][d]) and np.isclose(o['expected_gross'],z['value'][d])
            assert o['stake']==2*d and o['unit_copies']==1
            assert o['fixtures']==(z['f']+1).tolist()
        for kind,world_key in [('train','train_worlds'),('evaluation','evaluation_worlds')]:
            w=np.asarray(snapshot[world_key]);sc=snapshot[kind]
            count=cfg['allocation_worlds'] if kind=='train' else cfg['evaluation_worlds']
            assert sc['cutoffs']==cuts and w.shape==(count,len(bundle['expanded_pool']['fixtures'])) and np.isin(w,[0,1,2]).all()
            assert np.array_equal(w,np.asarray(seed_worlds[r['seed']][kind])),'Seed-derived simulation worlds differ'
            hits=np.asarray(sc['hits']);gross=np.asarray(sc['gross'])
            assert hits.shape==gross.shape==(len(w),len(opts))
            for j,o in enumerate(opts):
                states=w[:,np.array(o['fixtures'])-1]@(3**np.arange(6,-1,-1))
                won=np.isin(states,np.array(o['state_ids'])-1)
                assert np.array_equal(hits[:,j],won)
                assert np.allclose(gross[:,j],won*np.array(o['state_payout'])[states],rtol=1e-10,atol=1e-8)
        last_snapshot=name
    selected=replay_open_first(snapshot,cuts,budget,policy['objective'])
    if policy['max_add']:selected=replay_group_exchange(snapshot,cuts,selected,budget,policy['max_add'])
    validate_quality_funded(snapshot,selected,records[key])
    cost=sum(o['stake'] for o in records[key]);assert cost==float(r['stake'])<=budget
    assert budget-cost==float(r['cash']) and len(selected)==int(r['groups'])
    for kind,column in [('train','train_union'),('evaluation','eval_union')]:
        h=np.asarray(snapshot[kind]['hits'])[:,np.array(selected,dtype=int)-1]
        assert np.isclose((h.sum(axis=1)>0).mean(),float(r[column]),atol=1e-12)
expected={(issue,f"T250_{p['id']}_B{budget}",str(seed)) for issue,p,budget,seed in
          product(catalog['requested_issues'],cfg['policies'],cfg['budgets'],cfg['seeds'])}
assert set(records)<=seen and seen==expected
out.write_text(json.dumps(dict(status='PASS',plans=len(rows),freeze_sha256=hashlib.sha256(raw).hexdigest(),
    implementation={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in
      ['scripts/check_n7_expanded_allocations.py','src/n7_expanded_replay.py','src/n7_core_check.py',
       'src/n7_exchange_replay.py','src/n7_quality_replay.py','src/n7_expanded_pool_check.py',
       'scripts/replay_n7_expanded_worlds.R','config/n7_expanded_459.json'] }),indent=2))
print('PASS independently replayed',len(rows),'plans')
