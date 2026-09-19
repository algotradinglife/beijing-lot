"""Independent audit end-to-end on 50 tiny canonical hard-support fixtures."""
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('policy',['HARD0','WITHIN0','ANCHOR0'])
def test_frozen_hard_supports_and_corrupt_paid_distribution(tmp_path,policy):
    source=tmp_path/'input';source.mkdir()
    labels=[];rows=[];plans={};states=list(itertools.product((0,1),repeat=7))
    first=None
    for issue in (f'{i:03d}' for i in range(50)):
        f=[dict(issue=issue,slot=i+1,provider_id=str(i),handicap=0,p_W=.5,p_D=.3,p_L=.2,q_W=.5,q_D=.3,q_L=.2) for i in range(7)]
        ts=[]
        for state in states:
            p=math.prod((.5,.3)[d] for d in state)
            ts.append(dict(policy=policy,group_id=0,state_id=1+sum(d*3**(6-k) for k,d in enumerate(state)),probability=p,estimated_payout=1.3/p,outside_support=False))
        if policy!='HARD0':ts=sorted(ts,key=lambda t:(-t['probability'],t['state_id']))[:64]
        stake=2*len(ts)
        z=dict(issue=issue,fixtures=f,groups=[dict(group_id=0,fixture_index=i+1) for i in range(7)],tickets=ts,policies=[policy],settings=dict(temperature=.5,marginal_tv_cap=.25,outside_mix=.05,outside_ticket_fraction=.05))
        path=tmp_path/f'{issue}.json';path.write_text(json.dumps(z));plans[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        if first is None:first=path
        labels.extend(dict(issue=issue,slot=i+1,provider_id=str(i),handicap=0,actual_direction='W',spf_sp=2) for i in range(7))
        rows.append(dict(issue=issue,policy='EXPANDED/'+policy,stake=stake,gross=1.3*2**7,hits=1,bought_groups=1,net=1.3*2**7-stake))
    for path,data in [(source/'fixture-audit.csv',labels),(tmp_path/'rows.csv',rows)]:
        with path.open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    (source/'receipt.json').write_text(json.dumps(dict(files={'fixture-audit.csv':hashlib.sha256((source/'fixture-audit.csv').read_bytes()).hexdigest()})))
    frozen=dict(plans=plans,source_receipt=hashlib.sha256((source/'receipt.json').read_bytes()).hexdigest())
    (tmp_path/'freeze.json').write_text(json.dumps(frozen))
    rec=dict(config=dict(input=str(source)),files={n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in ('rows.csv','freeze.json')})
    (tmp_path/'receipt.json').write_text(json.dumps(rec))
    script=Path(__file__).resolve().parents[1]/'scripts/check_joint_candidate_replay.py'
    run=subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    assert json.loads(run.stdout)['groups']==50
    original=first.read_text()
    z=json.loads(original)
    if policy=='HARD0':
        replacement=(0,0,0,0,0,0,2)
    else:
        purchased={t['state_id'] for t in z['tickets']}
        alternatives=sorted(states,key=lambda st:(-math.prod((.5,.3)[d] for d in st),sum(d*3**(6-k) for k,d in enumerate(st))))
        replacement=next(st for st in alternatives if 1+sum(d*3**(6-k) for k,d in enumerate(st)) not in purchased)
    mass=math.prod((.5,.3,.2)[d] for d in replacement)
    z['tickets'][-1]=dict(policy=policy,group_id=0,state_id=1+sum(d*3**(6-k) for k,d in enumerate(replacement)),probability=mass,estimated_payout=1.3/mass,outside_support=2 in replacement)
    first.write_text(json.dumps(z))
    frozen['plans'][str(first)]=hashlib.sha256(first.read_bytes()).hexdigest();(tmp_path/'freeze.json').write_text(json.dumps(frozen))
    rec['files']['freeze.json']=hashlib.sha256((tmp_path/'freeze.json').read_bytes()).hexdigest();(tmp_path/'receipt.json').write_text(json.dumps(rec))
    rejected=subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True)
    assert rejected.returncode!=0
    assert ('set(ids)' if policy=='HARD0' else 'rank[len(ids)-1]') in rejected.stderr
    z=json.loads(original);z['tickets'][0]['outside_support']=True;first.write_text(json.dumps(z))
    frozen['plans'][str(first)]=hashlib.sha256(first.read_bytes()).hexdigest();(tmp_path/'freeze.json').write_text(json.dumps(frozen))
    rec['files']['freeze.json']=hashlib.sha256((tmp_path/'freeze.json').read_bytes()).hexdigest();(tmp_path/'receipt.json').write_text(json.dumps(rec))
    run=subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True)
    assert run.returncode!=0 and 'array_equal' in run.stderr
