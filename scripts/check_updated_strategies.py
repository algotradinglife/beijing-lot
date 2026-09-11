"""Independent physical-group settlement and reported-curve audit."""
import argparse,gzip,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from src.temporal_learning.core import stable_json_hash

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 result=json.loads((out/'results.json').read_text())
 audit={(r['issue'],r['slot'],r['provider_id']):r for r in json.loads((out/'settlement-audit.json').read_text())['rows']}
 reports={(r['issue'],r['policy']):r for r in result['rows']};checked=0
 for issue in result['issue_order']:
  plans=json.loads(gzip.decompress((out/'plans'/(issue+'.json.gz')).read_bytes()))['plans']
  for policy,plan in plans.items():
   assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
   parts=[c['plan'] if policy.startswith('MIX') else c for c in plan['components']]
   gross=stake=hits=0
   if policy.startswith('MIX'):
    seed=policy[-3:]
    original=plans['N5_S'+seed]['components'][:32]+plans['U3_BASELINE']['components'][:8]
    assert [[(l['slot'],l['support']) for l in z['legs']] for z in parts]==[[(l['slot'],l['support']) for l in z['legs']] for z in original]
   for part in parts:
    assert part['seal']==stable_json_hash({k:v for k,v in part.items() if k!='seal'})
    legs=part['legs'];cost=2*math.prod(len(l['support']) for l in legs)
    assert cost==part['stake']==2*len(part['tickets'])
    assert len({t['code'] for t in part['tickets']})==len(part['tickets']) and all(t['units']==1 for t in part['tickets'])
    obs=[audit[issue,l['slot'],l['provider_id']] for l in legs]
    assert all(o['actual_direction'] in ('W','D','L') and not o['status'].startswith('spf:IDENTITY') for o in obs)
    actual=''.join(dict(W='3',D='1',L='0')[o['actual_direction']] for o in obs)
    won=all(code in l['support'] for code,l in zip(actual,legs))
    if won:assert all(o['status']=='READY' and o['spf_sp']>0 for o in obs)
    assert sum(t['code']==actual for t in part['tickets'])==int(won)
    gross+=2*.65*math.prod(o['spf_sp'] for o in obs) if won else 0
    hits+=int(won);stake+=cost;checked+=1
   r=reports[issue,policy]
   assert r['groups']==len(parts) and r['hits']==hits and r['stake']==stake
   assert math.isclose(r['gross'],gross,abs_tol=1e-6) and math.isclose(r['net'],gross-stake,abs_tol=1e-6)
  print('CHECKED',issue,flush=True)
 data=pd.DataFrame(result['prior_rows']+result['rows']);order=result['prior_issue_order']+result['issue_order']
 metrics=pd.read_csv(out/'metrics.csv');curves=pd.read_csv(out/'curves.csv',dtype={'issue':str})
 for cohort,issues in [('原48期',result['prior_issue_order']),('新增100期',result['issue_order']),('合计148期',order)]:
  for policy,frame in data[data.issue.isin(issues)].groupby('policy'):
   frame=frame.set_index('issue').loc[issues];equity=np.r_[100000,100000+frame.net.cumsum().to_numpy()];dd=np.maximum.accumulate(equity)-equity
   r=metrics[(metrics.cohort==cohort)&(metrics.policy==policy)].iloc[0]
   assert np.isclose(r.net,frame.net.sum()) and np.isclose(r.stake,frame.stake.sum())
   assert np.isclose(r.ROI_percent,100*frame.net.sum()/frame.stake.sum()) and np.isclose(r.max_drawdown,max(dd))
   if cohort=='合计148期':
    c=curves[curves.policy==policy].sort_values('period')
    assert np.allclose(c.equity_cny,equity) and np.allclose(c.drawdown_cny,dd)
 print('PASS',checked,'physical groups; all 1212 cohort-policy metrics and 404 continuous equity/DD curves')
