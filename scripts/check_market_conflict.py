"""Independent support, payout and shared-scenario replay for conflict gates."""
import argparse,gzip,itertools,json,math,sys
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings,verify_clean_validation_receipts

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();root=Path.cwd();out=Path(a.study)
 frozen=json.loads((out/'plans-frozen.json').read_text());receipt=frozen['receipt'];assert stable_json_hash(receipt)==frozen['seal']
 verify_implementation_closure(root,receipt['implementation']);verify_clean_file_bindings({**receipt['source_hashes'],**receipt['plan_hashes']},repository_root=root)
 source=Path(receipt['contract']['source']);verify_clean_validation_receipts(source,repository_root=root)
 result=json.loads((out/'results.json').read_text());assert result['freeze_seal']==frozen['seal'];verify_clean_file_bindings(result['source_hashes'],repository_root=root)
 obs={(r['issue'],r['policy']):r for r in result['rows']};assert len(obs)==len(result['rows'])==2688
 audit={(r['issue'],r['slot'],r['provider_id']):r for r in json.loads((source/'settlement-audit.json').read_text())['rows']}
 frame=pd.DataFrame(json.loads((source/'factors.json').read_text())['rows']);checked=0
 for issue in receipt['contract']['issues']:
  if issue in receipt['contract']['no_bet']:
   rows=[r for r in result['rows'] if r['issue']==issue];assert len(rows)==56 and all(r['status']=='NO_BET' and r['cash_cny']==1024 and r['stake']==r['net']==0 for r in rows);checked+=56;continue
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));old=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))
  f=frame[frame.issue==issue].sort_values('slot');slots=list(f.slot);p=f[['p_W','p_D','p_L']].to_numpy();u=np.random.default_rng(41902).random((len(f),8192));di=(u>=p[:,0,None]).astype(int)+(u>=(p[:,0]+p[:,1])[:,None]).astype(int);codes=np.array(list('310'))[di]
  for policy,e in bundle.items():
   plan=e['plan'];base=old[e['case']+'_BASE']['plan'];row=obs[issue,policy];assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
   for k in ['groups','budget_cny','stake','cash_cny','single_count','cutoffs','input_sha256']:assert plan[k]==base[k]
   assert plan['stake']+plan['cash_cny']==1024
   if e['rule'] not in receipt['contract']['tv_thresholds']:assert e==old[policy]
   seen=Counter();gross=0.;hits=0;changed=0;scenarios=[];proxy=0.;unique=set()
   for g in range(1,plan['groups']+1):
    before=sorted([z for z in base['legs'] if z['group']==g],key=lambda z:z['slot']);legs=sorted([z for z in plan['legs'] if z['group']==g],key=lambda z:z['slot'])
    assert len(legs)==7
    for b,z in zip(before,legs):
     if e['rule'] in receipt['contract']['tv_thresholds']:
      rank=np.argsort(-np.array([b['p_'+d] for d in 'WDL']),kind='stable');d2='WDL'[rank[1]];d3='WDL'[rank[2]]
      tv=sum(abs(b['p_'+d]-b['q_'+d]) for d in 'WDL')/2;lead=b['q_'+d3]-b['q_'+d2]
      replace=bool(seen[b['slot']] and len(b['support'])==2 and tv+1e-12>=receipt['contract']['tv_thresholds'][e['rule']] and lead+1e-12>=.05)
      expected=''.join(c for d,c in zip('WDL','310') if d in ['WDL'[rank[0]],d3]) if replace else b['support']
      assert z==dict(b,support=expected)
     changed+=z['support']!=b['support'];seen[b['slot']]+=1
    ts=[t for t in plan['tickets'] if t['group']==g];units={t['units'] for t in ts};assert len(units)==1 and next(iter(units))>0
    physical={''.join(c) for c in itertools.product(*(z['support'] for z in legs))};assert len(ts)==len(physical)==2**(7-e['depth']) and physical=={t['code'] for t in ts}
    for code in physical:
     key=tuple((z['slot'],c) for z,c in zip(legs,code));assert key not in unique;unique.add(key)
    labels=[audit[issue,z['slot'],z['provider_id']] for z in legs];assert all(v['status']=='READY' and v['handicap']==z['handicap'] for v,z in zip(labels,legs))
    win=''.join(dict(W='3',D='1',L='0')[v['actual_direction']] for v in labels) in physical
    if win:hits+=1;gross+=2*.65*next(iter(units))*math.prod(v['spf_sp'] for v in labels)
    scenarios.append(np.all([np.isin(codes[slots.index(z['slot'])],list(z['support'])) for z in legs],axis=0))
    if e['rule'] in receipt['contract']['tv_thresholds']:
     proxy+=2*.65*next(iter(units))*math.prod(sum(z['p_'+d]/z['q_'+d] for d,c in zip('WDL','310') if c in z['support']) for z in legs)
   assert sum(t['units']*2 for t in plan['tickets'])==row['stake']
   assert row['hits']==hits and abs(row['gross']-gross)<1e-7 and abs(row['net']-(gross-row['stake']))<1e-7
   assert row['changed_legs']==changed and row['model_union']==np.any(scenarios,axis=0).mean()
   if e['rule'] in receipt['contract']['tv_thresholds']:
    assert abs(plan['model_proxy_gross']-proxy)<1e-7 and proxy<=base['model_proxy_gross']+1e-7
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==2688
 print('PASS 2688 results; gates, tickets, unchanged controls, payouts and common scenarios',flush=True)
