"""Freeze overlap-double support changes before reopening archived settlement."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_n7_diversity import replace_repeated_double_tail,evaluate_fixed_supports
from src.fundamentals_compression_breadth import settle_breadth_bundle
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parent',required=True);p.add_argument('--output',required=True);p.add_argument('--max-gap',type=float,default=1.0);a=p.parse_args();parent=Path(a.parent);out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable new output required')
 old=json.loads((parent/'plans-frozen.json').read_text());assert stable_json_hash(old['receipt'])==old['seal'];sources=dict(old['receipt']['source_hashes'])
 for path,h in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(next(k for k in sources if k.endswith('/inputs.json'))).read_text());frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 contract=dict(scope='EXPOSED_40_ISSUES_REPEATED_DOUBLE_TOP1_TOP3',max_gap=a.max_gap,threshold_policy='FIXED_DIAGNOSTIC_NOT_FITTED',depths=[1,2],quality=['TOP2','COMPRESSED'],overlap=['STRICT','FREE'],preserve_prefix=True,cash_policy='HOLD',support_rule='FIRST_USE_TOP2_LATER_DOUBLE_TOP1_TOP3_ALL_SINGLES_FIXED',same_fixture_counts_even_if_previous_single=True,third_use='TOP1_TOP3_NOT_ALTERNATING',evaluation_seed=41902,evaluation_draws=8192,unit_cny=2,payout_factor=.65,learning='NONE',draw_version='1.1.0',draw_weight=.5,high_weight=.5)
 closure=implementation_closure(Path.cwd(),['src.fundamentals_n7_diversity','scripts.run_repeated_double'],distributions=['numpy','pandas','scipy','scikit-learn'])
 out.mkdir(parents=True);(out/'plans').mkdir();plan_hashes={}
 for issue,f in frame.groupby('issue',sort=True):
  cuts={str(s):Cutoff.decision_epoch(issue,inputs['cutoffs'][issue][str(s)]) for s in f.slot};path=parent/'plans'/f'{issue}.json.gz';raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest();assert h==old['receipt']['plan_hashes'][str(path)];sources[str(path)]=h;previous=json.loads(gzip.decompress(raw));bundle={}
  for depth in (1,2):
   for quality in ['TOP2','COMPRESSED']:
    for overlap in ['STRICT','FREE']:
     source_policy=f'D{depth}_P1_{quality}_{overlap}_HOLD';base=previous[source_policy]['plan'];case=f'D{depth}_{quality}_{overlap}';adjusted=replace_repeated_double_tail(base,cutoffs=cuts,max_gap=a.max_gap)
     for action,plan in [('BASE',base),('ADJUSTED',adjusted)]:
      evaluation=evaluate_fixed_supports(f,plan,cutoffs=cuts,seed=41902,draws=8192)
      if action=='BASE':assert evaluation['metrics']==previous[source_policy]['metrics']
      bundle[f'{case}_{action}']=dict(plan=plan,evaluation=evaluation,case=case,action=action,depth=depth,quality=quality,overlap=overlap,source_policy=source_policy)
  assert len(bundle)==16
  path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0));plan_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,flush=True)
 receipt=dict(contract=contract,cutoffs=inputs['cutoffs'],source_hashes=sources,plan_hashes=plan_hashes,implementation=closure,parent_seal=old['seal'])
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 # Only after all paired plans and actual-support probabilities are frozen.
 previous_result=json.loads((parent/'results.json').read_text());audit_hashes=previous_result['audit_hashes'];audits=[];original_rows={(r['issue'],r['policy']):r for r in previous_result['rows']}
 for path,h in audit_hashes.items():
  raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==h;audits.extend(json.loads(raw))
 audit=pd.DataFrame(audits);results=[]
 for issue in sorted(frame.issue.unique()):
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));observed=audit[audit.issue==issue];labels=observed.set_index(['slot','provider_id']);settled=settle_breadth_bundle(bundle,observed);partition='TEST8' if issue in inputs['contract']['test_issues'] else 'VALIDATION8' if issue in inputs['contract']['validation_issues'] else 'TRAINING24'
  group_hits={}
  for policy,entry in bundle.items():
   plan=entry['plan'];group_hits[policy]=[all(dict(W='3',D='1',L='0')[labels.loc[(l['slot'],l['provider_id']),'actual_direction']] in l['support'] for l in plan['legs'] if l['group']==g) for g in range(1,plan['groups']+1)]
  for policy,entry in bundle.items():
   plan=entry['plan'];r=settled[policy];assert r['status']=='COMPLETE';control=group_hits[entry['case']+'_BASE'];actual=group_hits[policy]
   if entry['action']=='BASE':assert all(abs(r[k]-original_rows[issue,entry['source_policy']][k])<1e-7 for k in ['stake','gross','net','hits'])
   r.update(policy=policy,partition=partition,case=entry['case'],action=entry['action'],kind='OLD' if entry['action']=='BASE' else 'ADJUSTED',depth=entry['depth'],quality=entry['quality'],overlap=entry['overlap'],
    budget_cny=plan['budget_cny'],cash_cny=plan['cash_cny'],budget_return=r['net']/plan['budget_cny'],repeat_units=plan['repeat_units'],unique_tickets=plan['unique_tickets'],
    changed_legs=sum(l['changed'] for l in plan.get('diversity_ledger',[])),gained_groups=sum(a and not b for a,b in zip(actual,control)),lost_groups=sum(b and not a for a,b in zip(actual,control)),
    mean_group_probability=sum(plan['group_probability'])/plan['groups'],**entry['evaluation']['metrics'])
   results.append(r)
  print('SETTLED',issue,flush=True)
 verify_implementation_closure(Path.cwd(),closure)
 for path,h in {**sources,**plan_hashes,**audit_hashes}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 (out/'results.json').write_text(json.dumps(dict(rows=results,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(receipt)),indent=2));print('COMPLETE',len(results),flush=True)
