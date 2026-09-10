"""Independent sequential-cap selection, physical tickets and cash/payout replay."""
import argparse,gzip,itertools,json,math,sys
from collections import Counter
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_compression_bridge import bridge_surface
from src.fundamentals_compression_breadth import breadth_candidates
from src.fundamentals_n7_baseline import rank_double_candidates

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 saved=json.loads((out/'freeze-receipt.json').read_text());r=saved['receipt'];assert stable_json_hash(r)==saved['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 factor_path=next(p for p in r['source_hashes'] if p.endswith('/factors.json'));factor=json.loads(Path(factor_path).read_text());f=pd.DataFrame(factor['rows'])
 receipt=json.loads(json.loads((out/'plans-frozen.json').read_text())['canonical_json']);verify_clean_file_bindings(receipt['source_hashes'],repository_root=Path.cwd())
 audit_path=next(p for p in receipt['source_hashes'] if p.endswith('/settlement-audit.json'))
 audit=json.loads(Path(audit_path).read_text())['rows'];labels={(z['issue'],z['slot'],z['provider_id']):z for z in audit};assert len(labels)==len(audit)
 results=json.loads((out/'results.json').read_text())['rows'];observed={(z['issue'],z['policy']):z for z in results};assert len(observed)==3552
 checked=0
 for issue in r['issues']:
  frame=f[f.issue==issue];cuts={str(s):Cutoff.decision_epoch(issue,factor['cutoffs'][issue][str(s)]) for s in frame.slot}
  refs={d:n7_single_plan(frame,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in [1,2]}
  pool=breadth_candidates(frame,cutoffs=cuts,seed=41900,pool_size=512);surface=bridge_surface(frame,pool,refs,cutoffs=cuts,depth=2)
  ranked,_=rank_double_candidates(frame,cutoffs=cuts);ranked=ranked.sort_values(['slot','provider_id']).to_dict('records');candidates=surface['pool']['groups']
  order=sorted(range(len(candidates)),key=lambda i:(-(sum(math.log(ranked[j]['coverage']) for j in candidates[i])-1e-10*sum(candidates[i])),candidates[i]))
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));free=bundle['U16_P6_CAPPED']['plan']
  for policy,entry in bundle.items():
   plan=entry['plan'];uses=entry['max_uses'];pair=entry['max_pair_overlap'];obs=observed[issue,policy]
   assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
   if entry['kind']=='CAPPED':
    selected=list(surface['prefix']);counts=Counter(j for i in selected for j in candidates[i]);sets=[set(candidates[i]) for i in selected]
    for i in order:
     if len(selected)==16:break
     g=set(candidates[i])
     if i in selected or any(counts[j]>=uses for j in g) or any(len(g&s)>pair for s in sets):continue
     selected.append(i);sets.append(g);counts.update(g)
    assert plan['selected_candidates']==selected
    assert max(counts.values())<=uses and all(len(a&b)<=pair for a,b in itertools.combinations(sets,2))
   else:
    assert plan['legs']==[z for z in free['legs'] if z['group']<=plan['groups']]
    assert plan['tickets']==[z for z in free['tickets'] if z['group']<=plan['groups']]
   assert len(plan['group_units'])==len(plan['group_probability'])==len(plan['selected_candidates'])==plan['groups']
   assert plan['stake']==64*plan['groups']==obs['stake'] and plan['stake']+plan['cash_cny']==1024
   gross=0.;hits=0
   for group in range(1,plan['groups']+1):
    legs=sorted([z for z in plan['legs'] if z['group']==group],key=lambda z:z['slot'])
    singles=sorted(legs,key=lambda z:(-max(z['p_'+d] for d in 'WDL'),z['slot'],z['provider_id']))[:2];single_slots={z['slot'] for z in singles}
    assert len(legs)==7 and len({z['slot'] for z in legs})==7
    for z in legs:
     rank=sorted('WDL',key=lambda d:(-z['p_'+d],'WDL'.index(d)));expected=rank[:1 if z['slot'] in single_slots else 2]
     assert set(z['support'])=={dict(W='3',D='1',L='0')[d] for d in expected}
    tickets=[z for z in plan['tickets'] if z['group']==group]
    assert len(tickets)==32 and all(z['units']==1 for z in tickets)
    assert {z['code'] for z in tickets}=={''.join(c) for c in itertools.product(*(z['support'] for z in legs))}
    truth=[labels[issue,z['slot'],z['provider_id']] for z in legs]
    assert all(q['status']=='READY' and q['handicap']==z['handicap'] for q,z in zip(truth,legs))
    if all(dict(W='3',D='1',L='0')[q['actual_direction']] in z['support'] for q,z in zip(truth,legs)):
     hits+=1;gross+=2*.65*math.prod(q['spf_sp'] for q in truth)
   assert abs(obs['gross']-gross)<1e-7 and abs(obs['net']-(gross-plan['stake']))<1e-7 and obs['hits']==hits
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==3552
 print('PASS 3552 plans: independent greedy caps, unchanged top supports, same-stake controls, exact tickets and payouts')
