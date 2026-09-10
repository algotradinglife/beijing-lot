"""Independent raw-grid, original selection, physical ticket and payout replay."""
import argparse,gzip,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 saved=json.loads((out/'plans-frozen.json').read_text());r=saved['receipt'];assert stable_json_hash(r)==saved['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 factors=json.loads((out/'factors.json').read_text());verify_clean_file_bindings({**factors['source_hashes'],**factors['implementation']},repository_root=Path.cwd())
 result=json.loads((out/'results.json').read_text());assert result['freeze_seal']==saved['seal'];verify_clean_file_bindings(result['source_hashes'],repository_root=Path.cwd())
 source=Path(r['expert_source']);audit=pd.DataFrame(json.loads((source/'settlement-audit.json').read_text())['rows'])
 labels=audit.set_index(['issue','slot','provider_id']);assert len(labels)==2561 and not labels.index.duplicated().any()
 f=pd.DataFrame(factors['rows']);observed={(x['issue'],x['policy']):x for x in result['rows']};assert len(observed)==3456
 expert=pd.DataFrame(json.loads((source/'factors.json').read_text())['rows']).set_index(['issue','slot','provider_id'])
 checked=0;params=r['parameters'];assert params==dict(n=7,budget_cny=1024,unit_cny=2,payout_factor=.65,
  candidate_seed=41900,design_seed=41901,evaluation_seed=41902,pool_size=512,design_draws=1024,evaluation_draws=8192,
  gap_rules=dict(GAP02=.02,GAP05=.05,GAP10=.10,ALL=1.),conflict_rules=dict(TAIL05=0.,TV10=.10,TV15=.15,TV20=.20),minimum_market_tail_lead=.05)
 for issue in r['issues']:
  frame=f[f.issue==issue].sort_values('slot');raw=json.loads((source/'projected'/f'{issue}.json').read_text())
  for row in frame.to_dict('records'):
   grid=[g for g in raw['control']['scores'] if g['slot']==row['slot'] and g['provider_id']==row['provider_id'] and g['scenario']=='baseline']
   assert abs(sum(g['probability'] for g in grid)-1)<1e-8
   for d in 'WDL':
    assert abs(row['p_'+d]-sum(g['probability'] for g in grid if g['outcome']==d))<1e-12
    assert abs(row['q_'+d]-expert.loc[(issue,row['slot'],row['provider_id']),'q_'+d])<1e-12
  cuts={str(s):Cutoff.decision_epoch(issue,r['cutoffs'][issue][str(s)]) for s in frame.slot}
  refs={d:n7_single_plan(frame,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in (1,2)}
  pool=breadth_candidates(frame,cutoffs=cuts,seed=41900,pool_size=512)
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));assert len(bundle)==72
  for depth in (1,2):
   surface=bridge_surface(frame,pool,refs,cutoffs=cuts,depth=depth);design=breadth_scenarios(frame,surface,cutoffs=cuts,seed=41901,draws=1024)
   for quality,overlap in itertools.product(['TOP2','COMPRESSED'],['STRICT','FREE']):
    replay=bridge_plan(frame,surface,design,refs[depth],cutoffs=cuts,preserve_prefix=True,quality=quality,overlap=overlap,cash_policy='HOLD',budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert replay==bundle[f'D{depth}_{quality}_{overlap}_BASE']['plan']
  prob=frame[['p_W','p_D','p_L']].to_numpy();u=np.random.default_rng(41902).random((len(frame),8192));direction=(u>=prob[:,0,None]).astype(int)+(u>=(prob[:,0]+prob[:,1])[:,None]).astype(int)
  codes=np.array(list('310'))[direction];slots=list(frame.slot)
  for policy,entry in bundle.items():
   plan=entry['plan'];base=bundle[entry['case']+'_BASE']['plan'];o=observed[issue,policy]
   assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
   for k in ['groups','stake','cash_cny','budget_cny','cutoffs']:assert plan[k]==base[k]
   assert plan['stake']+plan['cash_cny']==1024
   seen=Counter();gross=0.;hits=0;mat=[]
   for group in range(1,plan['groups']+1):
    before=sorted([z for z in base['legs'] if z['group']==group],key=lambda z:z['slot'])
    legs=sorted([z for z in plan['legs'] if z['group']==group],key=lambda z:z['slot'])
    assert len(legs)==7 and len({z['slot'] for z in legs})==7
    for b,z in zip(before,legs):
     order=sorted('WDL',key=lambda d:(-b['p_'+d],'WDL'.index(d)));support=b['support'];rule=entry['rule'];change=False
     if rule in params['gap_rules']:change=b['p_'+order[1]]-b['p_'+order[2]]<=params['gap_rules'][rule]+1e-12
     if rule in params['conflict_rules']:
      change=.5*sum(abs(b['p_'+d]-b['q_'+d]) for d in 'WDL')+1e-12>=params['conflict_rules'][rule] and b['q_'+order[2]]-b['q_'+order[1]]+1e-12>=.05
     if seen[b['slot']] and len(support)==2 and change:support=''.join(c for d,c in zip('WDL','310') if d in [order[0],order[2]])
     assert z==dict(b,support=support);seen[b['slot']]+=1
    physical={''.join(c) for c in itertools.product(*(z['support'] for z in legs))};tickets=[t for t in plan['tickets'] if t['group']==group]
    assert len(tickets)==len(physical)==2**(7-entry['depth']) and {t['code'] for t in tickets}==physical and all(t['units']==1 for t in tickets)
    obs=[labels.loc[(issue,z['slot'],z['provider_id'])] for z in legs]
    assert all(q.status=='READY' and q.handicap==z['handicap'] for q,z in zip(obs,legs))
    if all(dict(W='3',D='1',L='0')[q.actual_direction] in z['support'] for q,z in zip(obs,legs)):
     hits+=1;gross+=2*.65*math.prod(q.spf_sp for q in obs)
    mat.append(np.all([np.isin(codes[slots.index(z['slot'])],list(z['support'])) for z in legs],axis=0))
   assert sum(t['units']*2 for t in plan['tickets'])==o['stake']
   assert abs(gross-o['gross'])<1e-7 and abs(gross-plan['stake']-o['net'])<1e-7 and hits==o['hits'] and o['status']=='COMPLETE'
   mat=np.asarray(mat);assert mat.any(axis=0).mean()==o['model_union']
   assert hashlib.sha256(mat.tobytes()).hexdigest()==entry['evaluation']['receipt']['evaluation']['sha256']
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==3456
 print('PASS',checked,'results; raw baseline p, unchanged market q, base selections, gates, tickets, scenarios and payouts',flush=True)
