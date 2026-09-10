"""Independent new-period source, support, scenario and payout replay."""
import argparse,gzip,hashlib,itertools,json,math,sys
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_clean_receipts import verify_clean_validation_receipts
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash,utc
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();root=Path(a.study)
 verify_clean_validation_receipts(root,repository_root=Path.cwd())
 frozen=json.loads((root/'plans-frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
 verify_implementation_closure(Path.cwd(),r['implementation'])
 for name,h in {**r['source_hashes'],**r['plan_hashes']}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 prepared=json.loads((root/'prepared.json').read_text());assert stable_json_hash(prepared['receipt'])==prepared['seal']
 verify_implementation_closure(Path.cwd(),prepared['receipt']['implementation'])
 for name,h in {**prepared['receipt']['source_hashes'],**prepared['receipt']['files']}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 for stage in ['projected','signals']:
  receipt=json.loads((root/stage/'receipt.json').read_text())
  for name,h in {**receipt['files'],**(receipt.get('implementation',{}))}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 f=pd.DataFrame(json.loads((root/'factors.json').read_text())['rows'])
 result=json.loads((root/'results.json').read_text());assert result['freeze_seal']==frozen['seal']
 assert result['audit_sha256']==hashlib.sha256((root/'settlement-audit.json').read_bytes()).hexdigest()
 audit=json.loads((root/'settlement-audit.json').read_text());labels={(x['issue'],x['slot'],x['provider_id']):x for x in audit['rows']}
 assert len(labels)==len(audit['rows'])
 observed={(x['issue'],x['policy']):x for x in result['rows']};assert len(observed)==len(result['rows'])==1920
 checked=0
 for issue in r['contract']['issues']:
  frame=f[f.issue==issue].sort_values('slot')
  if issue in r['no_bet']:
   assert len(frame)<7
   rs=[x for x in result['rows'] if x['issue']==issue]
   assert len(rs)==40 and all(x['status']=='NO_BET' and x['stake']==x['gross']==x['net']==0 and x['cash_cny']==1024 for x in rs)
   checked+=40;continue
  cuts={str(s):Cutoff.decision_epoch(issue,r['cutoffs'][issue][str(s)]) for s in frame.slot}
  refs={d:n7_single_plan(frame,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in (1,2)}
  pool=breadth_candidates(frame,cutoffs=cuts,seed=41900,pool_size=512)
  bundle=json.loads(gzip.decompress((root/'plans'/f'{issue}.json.gz').read_bytes()));assert len(bundle)==40
  for depth in (1,2):
   surface=bridge_surface(frame,pool,refs,cutoffs=cuts,depth=depth);design=breadth_scenarios(frame,surface,cutoffs=cuts,seed=41901,draws=1024)
   for quality,overlap in itertools.product(['TOP2','COMPRESSED'],['STRICT','FREE']):
    case=f'D{depth}_{quality}_{overlap}'
    replay=bridge_plan(frame,surface,design,refs[depth],cutoffs=cuts,preserve_prefix=True,quality=quality,overlap=overlap,cash_policy='HOLD',budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert replay==bundle[case+'_BASE']['plan']
  slots=list(frame.slot);prob=frame[['p_W','p_D','p_L']].to_numpy();u=np.random.default_rng(41902).random((len(frame),8192));directions=(u>=prob[:,0,None]).astype(int)+(u>=(prob[:,0]+prob[:,1])[:,None]).astype(int);codes=np.array(list('310'))[directions]
  for policy,e in bundle.items():
   plan=e['plan'];o=observed[issue,policy];base=bundle[e['case']+'_BASE']['plan'];assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
   for k in ['stake','cash_cny','budget_cny','groups','cutoffs']:assert plan[k]==base[k]
   assert plan['budget_cny']==1024 and plan['stake']+plan['cash_cny']==1024
   seen=Counter();scenarios=[];gross=0.;hits=0;pending=False
   for g in range(1,plan['groups']+1):
    before=sorted([x for x in base['legs'] if x['group']==g],key=lambda x:x['slot']);legs=sorted([x for x in plan['legs'] if x['group']==g],key=lambda x:x['slot'])
    assert len(legs)==7 and len({x['slot'] for x in legs})==7
    for b,z in zip(before,legs):
     order=sorted('WDL',key=lambda d:(-b['p_'+d],'WDL'.index(d)));support=b['support']
     if e['max_gap'] is not None and seen[b['slot']] and len(support)==2 and b['p_'+order[1]]-b['p_'+order[2]]<=e['max_gap']+1e-12:
      support=''.join(c for d,c in zip('WDL','310') if d in [order[0],order[2]])
     assert z==dict(b,support=support);seen[b['slot']]+=1
    ts=[x for x in plan['tickets'] if x['group']==g];physical={''.join(c) for c in itertools.product(*(z['support'] for z in legs))}
    assert len(ts)==len(physical)==2**(7-e['depth']) and {t['code'] for t in ts}==physical and all(t['units']==1 for t in ts)
    scenarios.append(np.all([np.isin(codes[slots.index(z['slot'])],list(z['support'])) for z in legs],axis=0))
    obs=[labels[issue,z['slot'],z['provider_id']] for z in legs]
    if any(q['actual_direction'] not in 'WDL' if isinstance(q['actual_direction'],str) else True for q in obs) or any(q['status'].startswith('spf:IDENTITY') or q['handicap']!=z['handicap'] for q,z in zip(obs,legs)):
     pending=True;continue
    winner=''.join(dict(W='3',D='1',L='0')[q['actual_direction']] for q in obs) in physical
    if winner:
     if any(q['spf_sp'] is None or not math.isfinite(q['spf_sp']) or q['spf_sp']<=0 for q in obs):pending=True;continue
     hits+=1;gross+=2*.65*math.prod(q['spf_sp'] for q in obs)
   assert sum(t['units']*2 for t in plan['tickets'])==o['stake']
   matrix=np.asarray(scenarios);assert matrix.any(axis=0).mean()==o['model_union']
   assert e['evaluation']['receipt']['evaluation']['sha256']==hashlib.sha256(matrix.tobytes()).hexdigest()
   if pending:assert o['status']=='PENDING_AUDIT_OR_WINNING_SP' and o['net'] is None
   else:assert o['status']=='COMPLETE' and abs(o['gross']-gross)<1e-7 and abs(o['net']-(gross-plan['stake']))<1e-7 and o['hits']==hits
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==1920
 print('PASS',checked,'results; original selections replayed, replacement rules/money/shared scenarios and payouts independently checked',flush=True)
