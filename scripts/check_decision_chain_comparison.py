"""Independent reconstruction of conflict decisions, groups, tickets and payoff."""
import argparse,hashlib,itertools,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--reference',required=True);a=p.parse_args();out=Path(a.study)
 pack=json.loads((out/'inputs.json').read_text());result=json.loads((out/'results.json').read_text());freeze=json.loads((out/'plans-frozen.json').read_text())
 assert stable_json_hash({k:v for k,v in pack.items() if k!='seal'})==pack['seal']
 assert stable_json_hash(freeze['receipt'])==freeze['seal']==result['freeze_seal']
 assert pack['contract']==result['contract']==freeze['receipt']['contract']
 verify_implementation_closure(Path.cwd(),freeze['receipt']['implementation'])
 for name,digest in {**freeze['receipt']['input_hashes'],**freeze['receipt']['plan_hashes'],**result['audit_hashes']}.items():
  assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
 c=pack['contract'];options={}
 for r in pack['rows']:options.setdefault((r['issue'],r['slot'],r['provider_id']),{})[r['weight']]=r
 audits={}
 for part in ['training','validation','test']:
  local=out/f'{part}-audit.json'
  original_digest=[digest for name,digest in result['audit_hashes'].items() if Path(name).name==local.name]
  assert original_digest==[hashlib.sha256(local.read_bytes()).hexdigest()]
  for r in json.loads((out/f'{part}-audit.json').read_text()):
   key=(r['issue'],r['slot'],r['provider_id']);assert key not in audits;audits[key]=r
 expected={(r['issue'],r['policy']):r for r in result['rows']};assert len(expected)==len(result['rows'])
 issues=sorted(set(k[0] for k in options));checked=0;leg_checks=0
 for issue in issues:
  computed={};ledgers={}
  for policy,parameters in c['policies'].items():
   chosen=[];ledger=[]
   for key,weights in sorted(options.items()):
    if key[0]!=issue:continue
    current=weights[.5];rank=sorted('WDL',key=lambda d:(-current['p_'+d],'WDL'.index(d)))[:2]
    top=sorted('WDL',key=lambda d:(-current['q_'+d],'WDL'.index(d)))[0];conflict=top not in rank
    action='SKIP' if conflict and parameters['policy']=='SKIP' else 'REDUCE' if conflict and parameters['policy']=='REDUCE' else 'KEEP'
    routed=weights[parameters['fallback_weight']] if action=='REDUCE' else current
    ledger.append((key,conflict,action,routed))
    for w in weights.values():
     assert all(abs(w['q_'+d]-current['q_'+d])<1e-12 for d in 'WDL')
    if action!='SKIP':chosen.append(routed)
   chosen.sort(key=lambda r:(-sum(sorted([r['p_'+d] for d in 'WDL'],reverse=True)[:2]),r['slot'],r['provider_id']))
   count=min(6,len(chosen)//7);computed[policy]=[chosen[i*7:(i+1)*7] for i in range(count)];ledgers[policy]=ledger
  computed['SKIP_MATCHED_CURRENT']=computed['CURRENT'][:len(computed['CONFLICT_SKIP'])]
  for policy,groups in computed.items():
   bundle=json.loads((out/'plans'/f'{issue}-{policy}.json').read_text());plan=bundle['plan']
   assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
   assert plan['groups']==len(groups) and plan['stake']==256*len(groups)
   if 'routing' in bundle:
    route=bundle['routing'];assert stable_json_hash({k:v for k,v in route.items() if k!='seal'})==route['seal']
    for row,(key,conflict,action,routed) in zip(route['ledger'],ledgers[policy],strict=True):
     assert (row['issue'],row['slot'],row['provider_id'])==key and row['conflict']==conflict and row['action']==action
     assert row['draw_weight']==(None if action=='SKIP' else routed['weight'])
    assert len(route['rows'])==sum(z[2]!='SKIP' for z in ledgers[policy])
   gross=0.;hits=0
   for index,group in enumerate(groups,1):
    group=sorted(group,key=lambda r:r['slot']);legs=sorted([r for r in plan['legs'] if r['group']==index],key=lambda r:r['slot'])
    assert [(r['slot'],r['provider_id']) for r in legs]==[(r['slot'],r['provider_id']) for r in group]
    supports=[];actual=[];sp=[]
    for leg,r in zip(legs,group,strict=True):
     assert all(leg['p_'+d]==r['p_'+d] and leg['q_'+d]==r['q_'+d] for d in 'WDL')
     ix=sorted(range(3),key=lambda i:(-r['p_'+'WDL'[i]],i))[:2];support=''.join('310'[i] for i in sorted(ix));supports.append(support)
     assert leg['support']==support
     observed=audits[(issue,r['slot'],r['provider_id'])];assert observed['handicap']==r['handicap']
     actual.append(dict(W='3',D='1',L='0')[observed['actual_direction']]);sp.append(observed['spf_sp'])
    tickets=[t for t in plan['tickets'] if t['group']==index]
    wanted={''.join(parts) for parts in itertools.product(*supports)}
    assert len(tickets)==128 and {t['code'] for t in tickets}==wanted and all(t['units']==1 for t in tickets)
    if ''.join(actual) in wanted:hits+=1;gross+=2*.65*math.prod(sp)
   r=expected[(issue,policy)];assert r['hits']==hits and r['stake']==256*len(groups) and abs(r['gross']-gross)<1e-7 and abs(r['net']-(gross-r['stake']))<1e-7
   assert r['groups']==len(groups) and r['selected_matches']==7*len(groups)
   checked+=1
  assert expected[(issue,'CONFLICT_SKIP')]['stake']==expected[(issue,'SKIP_MATCHED_CURRENT')]['stake']
  for row in [r for r in result['legs'] if r['issue']==issue]:
   key=(issue,row['slot'],row['provider_id']);observed=audits[key]['actual_direction']
   current=options[key][.5];rank=sorted('WDL',key=lambda d:(-current['p_'+d],'WDL'.index(d)))[:2]
   assert set(row['current_top2'])==set(rank)
   policy=row['policy'];parameters=c['policies']['CURRENT' if policy=='SKIP_MATCHED_CURRENT' else policy]
   top=max('WDL',key=lambda d:current['q_'+d]);conflict=top not in rank
   action='SKIP' if conflict and parameters['policy']=='SKIP' else 'REDUCE' if conflict and parameters['policy']=='REDUCE' else 'KEEP'
   routed=options[key][parameters['fallback_weight']] if action=='REDUCE' else current
   rank2=sorted('WDL',key=lambda d:(-routed['p_'+d],'WDL'.index(d)))[:2]
   assert row['conflict']==conflict and row['action']==action
   assert row['routed_top2']==(None if action=='SKIP' else ''.join(d for d in 'WDL' if d in rank2))
   selected={(r['slot'],r['provider_id']) for group in computed[policy] for r in group}
   assert row['selected']==((row['slot'],row['provider_id']) in selected)
   assert row['selected_hit']==(None if not row['selected'] else observed in rank2)
   assert row['actual_direction']==observed and row['current_hit']==(observed in row['current_top2'])
   assert row['routed_hit']==(None if row['routed_top2'] is None else observed in row['routed_top2'])
   leg_checks+=1
 # Exact reproduction of prior .5 control, not merely approximately similar ROI.
 prior=Path(a.reference)
 original={(r['issue']):r for r in json.loads(prior.read_text())['rows'] if r['policy']=='FIXED_0.5'}
 for issue in issues:
  assert all(expected[(issue,'CURRENT')][k]==original[issue][k] for k in ['stake','gross','net','hits'])
 paths=[out/n for n in ['inputs.json','contract.json','scope-exclusions.json','plans-frozen.json','results.json','training-audit.json','validation-audit.json','test-audit.json']]
 paths.append(prior)
 report=dict(status='PASS',plans_checked=checked,leg_rows_checked=leg_checks,control_parity_issues=len(issues),
  source_hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},historical_admission=False)
 (out/'independent-check.json').write_text(json.dumps(report,indent=2));print('PASS',checked,'plans',leg_checks,'ledger rows')
