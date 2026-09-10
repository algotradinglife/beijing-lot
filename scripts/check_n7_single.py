"""Independently enumerate single-leg ticket supports, reuse caps and settlement."""
import argparse,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 frozen=json.loads((out/'plans-frozen.json').read_text());f=frozen['receipt'];assert stable_json_hash(f)==frozen['seal'];verify_implementation_closure(Path.cwd(),f['implementation'])
 results=json.loads((out/'results.json').read_text());assert results['freeze_seal']==frozen['seal']
 for path,h in {**f['source_hashes'],**f['plan_hashes'],**results['audit_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(next(k for k in f['source_hashes'] if k.endswith('/inputs.json'))).read_text());rows=[r for r in inputs['rows'] if r['weight']==.5]
 labels={}
 for path in results['audit_hashes']:
  for r in json.loads(Path(path).read_text()):
   key=(r['issue'],r['slot'],r['provider_id']);assert key not in labels;labels[key]=r
 lookup={(r['issue'],r['policy']):r for r in results['rows']};overlap=0
 for path in f['plan_hashes']:
  plan=json.loads(Path(path).read_text());assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
  issue=plan['issue'];policy='CURRENT' if 'single_count' not in plan else f"SINGLE_{plan['single_count']}";k=plan.get('single_count',0);o=lookup[issue,policy];sets=[];gross=0;hits=0
  ranked=sorted([r for r in rows if r['issue']==issue],key=lambda r:(-sum(sorted([r['p_'+d] for d in 'WDL'],reverse=True)[:2]),r['slot'],r['provider_id']))
  disjoint=plan.get('disjoint_groups',plan['groups'])
  assert plan['groups']==o['groups']
  for group in range(1,plan['groups']+1):
   legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot']);slots={r['slot'] for r in legs};sets.append(slots)
   assert len(legs)==7 and len(slots)==7
   if group<=disjoint:assert slots=={r['slot'] for r in ranked[(group-1)*7:group*7]}
   if policy!='CURRENT':
    candidates=[]
    for r in legs:
     ds=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)));v=r['p_'+ds[0]];mass=v+r['p_'+ds[1]]
     candidates.append((-(v if plan['single_rule']=='MAX_SINGLE' else v/mass),r['slot'],r['provider_id'],ds))
    chosen={t[1] for t in sorted(candidates)[:k]}
   for r in legs:
    ds=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)))[:1 if policy!='CURRENT' and r['slot'] in chosen else 2]
    assert r['support']==''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in ds)
   tickets=[t for t in plan['tickets'] if t['group']==group];cartesian=[''.join(c) for c in itertools.product(*(r['support'] for r in legs))]
   assert len(cartesian)==2**(7-k) and sorted(t['code'] for t in tickets)==sorted(cartesian) and all(t['units']==1 for t in tickets)
   obs=[labels[issue,r['slot'],r['provider_id']] for r in legs]
   assert all(l['handicap']==r['handicap'] for l,r in zip(obs,legs))
   code=''.join(dict(W='3',D='1',L='0')[l['actual_direction']] for l in obs)
   if code in cartesian:gross+=2*.65*math.prod(l['spf_sp'] for l in obs);hits+=1
  counts=Counter(s for slots in sets for s in slots)
  assert max(counts.values(),default=0)<=(1 if policy=='CURRENT' else 2)
  assert all(len(a&b)<=(0 if policy=='CURRENT' else 2) for a,b in itertools.combinations(sets,2))
  assert o['stake']==len(plan['tickets'])*2 and abs(o['gross']-gross)<1e-7 and o['hits']==hits
  assert o['cash_cny']==o['budget_cny']-o['stake']>=0 and abs(o['net']-gross+o['stake'])<1e-7
  assert abs(o['ending_funds_cny']-o['budget_cny']-o['net'])<1e-7
  if policy!='CURRENT':
   overlap+=plan['overlap_groups']
   if plan['cash_cny']>=plan['group_cost_cny']:assert plan['overlap_ledger'][-1]['status']=='PROVEN_INFEASIBLE'
 print('PASS',len(f['plan_hashes']),'plans;',overlap,'overlap groups; complete supports, caps and payouts')
