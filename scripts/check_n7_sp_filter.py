"""Independent #445 fixture admission and #443 no-filter equivalence check.

Usage: project-python scripts/check_n7_sp_filter.py STUDY CONTROL NEW_RECEIPT
Reads frozen bundles and results; never selects tickets or mutates inputs.
Admission is reconstructed directly from q and p, separately from the R gate.
"""
import csv
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

study,control,out=map(Path,sys.argv[1:])
assert not out.exists()
frozen=json.loads((study/'plans-frozen.json').read_text())
old=json.loads((control/'plans-frozen.json').read_text())
for directory,receipt in ((study,frozen),(control,old)):
    for name,sha in receipt['files'].items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==sha
    evaluation=json.loads((directory/'evaluation-receipt.json').read_text())
    assert hashlib.sha256((directory/'results.csv').read_bytes()).hexdigest()==evaluation['results_sha256']
    assert hashlib.sha256((directory/'plans-frozen.json').read_bytes()).hexdigest()==evaluation['freeze_sha256']
assert frozen['source_catalog_sha256']==old['source_catalog_sha256']
cat=Path(frozen['config']['catalog'])
assert hashlib.sha256(cat.read_bytes()).hexdigest()==frozen['source_catalog_sha256']
policies=frozen['config']['policies']
thresholds={p['minimum_sp'] for p in policies}
expected_threshold={f'T{round(1000*t)}_{p["id"]}_B{b}':p['minimum_sp']
    for t in frozen['config']['targets'] for p in policies for b in frozen['config']['budgets']}
assert len(expected_threshold)==len(frozen['config']['targets'])*len(policies)*len(frozen['config']['budgets'])
assert thresholds=={1,1.1,1.2,1.3,1.5}
allowed={};diagnostics={};excluded_fixtures=[]
for item in json.loads(cat.read_text())['issues']:
    raw=Path(item['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256']
    bundle=json.loads(gzip.decompress(raw));fixtures=bundle['expanded_pool']['fixtures']
    assert bundle['cutoffs']==frozen['cutoffs'][item['issue']]
    prices=[];probabilities=[];directions=[]
    for fixture in fixtures:
        p=[fixture['p_'+d] for d in ('W','D','L')];q=[fixture['q_'+d] for d in ('W','D','L')]
        assert all(math.isfinite(x) and 0<=x<=1 for x in p)
        assert all(math.isfinite(x) and 0<x<=1 for x in q)
        assert abs(sum(p)-1)<1e-8 and abs(sum(q)-1)<1e-8
        k=max(range(3),key=lambda k:p[k]);prices.append(1/q[k]);probabilities.append(p[k]);directions.append(('W','D','L')[k])
    for threshold in thresholds:
        keep=[x>=threshold for x in prices]
        groups={str(g['id']) for g in bundle['sleeves'] if all(keep[i] for i in g['fixture_indices'])}
        allowed[item['issue'],threshold]=groups
        diagnostics[item['issue'],threshold]=(sum(keep),len(fixtures),len(groups),len(bundle['sleeves']),sum(p for p,k in zip(probabilities,keep) if not k))
        for i,retained in enumerate(keep):
            if not retained:
                fixture=fixtures[i]
                excluded_fixtures.append(dict(issue=item['issue'],minimum_sp=threshold,
                    fixture_index=i+1,slot=fixture['slot'],provider_id=fixture['provider_id'],
                    top1=directions[i],top1_probability=probabilities[i],estimated_sp=prices[i]))
rows=list(csv.DictReader((study/'results.csv').open()))
keys={}
for row in rows:
    threshold=float(row['minimum_sp']);key=row['issue'],row['arm'],row['seed']
    assert threshold==expected_threshold[row['arm']],('threshold-policy mismatch',key)
    assert key not in keys;keys[key]=threshold
    expected=diagnostics[row['issue'],threshold]
    for column,value in zip(('eligible_fixtures','total_fixtures','eligible_groups','total_groups','removed_top1_mass'),expected):
        assert math.isclose(float(row[column]),value,abs_tol=1e-9)
    if not allowed[row['issue'],threshold]:
        assert float(row['stake'])==0 and int(row['groups'])==0
        assert float(row['cash'])==float(row['budget_cny'])
for row in csv.DictReader((study/'funded.csv').open()):
    threshold=keys[row['issue'],row['arm'],row['seed']]
    assert row['sleeve_id'] in allowed[row['issue'],threshold]
# Compare every common column of all control results/funded/actions, preserving
# action order inside each plan. New diagnostic columns do not replace controls.
counts={}
for filename in ('results.csv','funded.csv','actions.csv'):
    old_rows=list(csv.DictReader((control/filename).open()))
    new_rows=[]
    for row in csv.DictReader((study/filename).open()):
        if '_SP100_' in row['arm']:
            row['arm']=row['arm'].replace('_SP100_','_')
            new_rows.append(row)
    assert len(old_rows)==len(new_rows),(filename,len(old_rows),len(new_rows))
    index={}
    for row in new_rows:
        key=(row['issue'],row['arm'],row['seed'])
        if filename=='funded.csv':key+=row['sleeve_id'],
        if filename=='actions.csv':key+=row['step'],
        assert key not in index;index[key]=row
    for row in old_rows:
        key=(row['issue'],row['arm'],row['seed'])
        if filename=='funded.csv':key+=row['sleeve_id'],
        if filename=='actions.csv':key+=row['step'],
        new=index[key]
        for column,value in row.items():
            if value==new[column]:continue
            try:
                a,b=float(value),float(new[column])
            except ValueError:
                raise AssertionError((filename,key,column,value,new[column])) from None
            assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-8),(filename,key,column,value,new[column])
    counts[filename]=len(old_rows)
out.write_text(json.dumps(dict(status='PASS',plans=len(rows),admission_cells=len(diagnostics),excluded_fixtures=excluded_fixtures,
    control_rows=counts,results_sha256=hashlib.sha256((study/'results.csv').read_bytes()).hexdigest(),freeze_sha256=hashlib.sha256((study/'plans-frozen.json').read_bytes()).hexdigest(),
    control_freeze_sha256=hashlib.sha256((control/'plans-frozen.json').read_bytes()).hexdigest(),
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
print(json.loads(out.read_text()))
