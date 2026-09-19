"""Read-only independent support, ticket-price and settlement audit.

Usage: python scripts/check_joint_candidate_replay.py REPORT_DIR
Validates already frozen prediction plans against receipt-bound official labels;
no new learning, ranking decisions, source admission, or chronology helpers.
"""
import csv
import hashlib
import itertools
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

root=Path(sys.argv[1])
receipt=json.loads((root/'receipt.json').read_text())
for name,sha in receipt['files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha
freeze=json.loads((root/'freeze.json').read_text())
source=Path(receipt['config']['input'])
src_raw=(source/'receipt.json').read_bytes()
assert hashlib.sha256(src_raw).hexdigest()==freeze['source_receipt']
src=json.loads(src_raw)
assert hashlib.sha256((source/'fixture-audit.csv').read_bytes()).hexdigest()==src['files']['fixture-audit.csv']
labels={}
for row in csv.DictReader((source/'fixture-audit.csv').open()):
    key=(row['issue'],int(row['slot']),row['provider_id'])
    assert key not in labels
    labels[key]=row
rows={}
for row in csv.DictReader((root/'rows.csv').open()):
    key=(row['issue'],row['policy']);assert key not in rows;rows[key]=row
states=np.asarray(list(itertools.product(range(3),repeat=7)))
checked=0
seen_issues=set()
for path,sha in freeze['plans'].items():
    raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==sha
    z=json.loads(raw);f=z['fixtures'];s=z['settings']
    assert z['issue'] not in seen_issues;seen_issues.add(z['issue'])
    groups=defaultdict(list)
    for g in z['groups']:
        groups[g['group_id']].append(g['fixture_index']-1)
    assert all(len(g)==len(set(g))==7 for g in groups.values())
    tickets=defaultdict(list);seen=set()
    for t in z['tickets']:
        key=(t['policy'],t['group_id'],t['state_id']);assert key not in seen;seen.add(key)
        tickets[(t['policy'],t['group_id'])].append(t)
    totals={pol:[0.,0.,0,0] for pol in z['policies']}
    for (pol,gid),ts in tickets.items():
        ix=groups[gid]
        p=np.asarray([[f[i]['p_'+d] for d in 'WDL'] for i in ix])
        q=np.asarray([[f[i]['q_'+d] for d in 'WDL'] for i in ix])
        mass=np.prod(p[np.arange(7),states],axis=1)
        pay=2*.65/np.prod(q[np.arange(7),states],axis=1)
        ids=np.asarray([t['state_id']-1 for t in ts],dtype=int)
        assert np.all((ids>=0)&(ids<2187))
        assert np.allclose([t['probability'] for t in ts],mass[ids],rtol=1e-12,atol=1e-15)
        assert np.allclose([t['estimated_payout'] for t in ts],pay[ids],rtol=1e-12,atol=1e-8)
        if pol!='JOINT_NATIVE':
            compressed=int(pol[-1]);single=sorted(range(7),key=lambda k:(-max(p[k]),f[ix[k]]['slot']))[:compressed]
            order=np.argsort(-p,axis=1,kind='stable');mask=np.ones(2187,dtype=bool);target=np.zeros((7,3))
            for k in range(7):
                allowed=order[k,:1 if k in single else 2]
                mask &= np.isin(states[:,k],allowed);target[k,allowed]=1/len(allowed)
            if pol.startswith('HARD'):
                assert set(ids)==set(np.flatnonzero(mask))
            else:
                assert len(ids) in (2**(7-compressed),2**(6-compressed),2**(5-compressed))
            outside=~mask[ids]
            assert np.array_equal([t['outside_support'] for t in ts],outside)
            if pol.startswith(('HARD','WITHIN')):assert not outside.any()
            else:assert outside.mean()<=s['outside_ticket_fraction']+1e-12
            tv=max(np.abs(np.bincount(states[ids,k],minlength=3)/len(ids)-target[k]).sum()/2 for k in range(7))
            assert tv<=s['marginal_tv_cap']+1e-12
            # Full hard option is retained as an explicit alternative/fallback.
            if set(ids)!=set(np.flatnonzero(mask)):
                score=mass**s['temperature']*mask;score/=score.sum()
                if pol.startswith('ANCHOR'):score=(1-s['outside_mix'])*score+s['outside_mix']*mass
                rank=np.lexsort((np.arange(2187),-mass*pay,-score))
                assert score[ids].min()+1e-12>=score[rank[len(ids)-1]]
        official=[];sp=[]
        for i in ix:
            ff=f[i];lab=labels[(ff['issue'],ff['slot'],ff['provider_id'])]
            assert float(lab['handicap'])==ff['handicap']
            official.append('WDL'.index(lab['actual_direction']));sp.append(float(lab['spf_sp']))
        actual=sum(d*3**(6-k) for k,d in enumerate(official))
        hit=int(actual in ids);gross=hit*2*.65*math.prod(sp)
        totals[pol][0]+=len(ids)*2;totals[pol][1]+=gross;totals[pol][2]+=hit;totals[pol][3]+=1
        checked+=1
    for pol,(stake,gross,hits,bought) in totals.items():
        r=rows[(z['issue'],'EXPANDED/'+pol)]
        assert stake<=1024 and math.isclose(stake,float(r['stake']),abs_tol=1e-8)
        assert math.isclose(gross,float(r['gross']),rel_tol=1e-12,abs_tol=1e-7)
        assert hits==int(r['hits']) and bought==int(r['bought_groups'])
        assert math.isclose(gross-stake,float(r['net']),abs_tol=1e-7)
assert len(freeze['plans'])==50
print(json.dumps(dict(status='PASS',issues=50,groups=checked,checks=['frozen hashes','unique states','original p/q pricing','hard support','anchored marginal and outside caps','ranking prefixes','official settlement once .65'])))
