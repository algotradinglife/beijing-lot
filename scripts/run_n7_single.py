"""Freeze a declared single-count sweep before archived settlement access."""
import argparse,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_n7_single import n7_single_plan,settle_n7_single
from src.fundamentals_n7_baseline import n7_baseline_plan,settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parent',required=True);p.add_argument('--output',required=True);p.add_argument('--single-counts',nargs='+',type=int,required=True);p.add_argument('--single-rule',choices=['MAX_SINGLE','MIN_RELATIVE_LOSS'],required=True);a=p.parse_args();parent=Path(a.parent);out=Path(a.output)
 if out.exists():raise FileExistsError('New immutable output required')
 if len(set(a.single_counts))!=len(a.single_counts) or any(k<0 or k>7 for k in a.single_counts):raise ValueError('Unique counts 0..7 required')
 policies=['CURRENT']+[f'SINGLE_{k}' for k in a.single_counts]
 inputs=json.loads((parent/'inputs.json').read_text());receipt=json.loads((parent/'study-receipt.json').read_text())
 assert stable_json_hash(receipt['receipt'])==receipt['seal']
 assert stable_json_hash({k:v for k,v in inputs.items() if k!='seal'})==inputs['seal']
 sources=dict(inputs['source_hashes']);sources[str(parent/'inputs.json')]=hashlib.sha256((parent/'inputs.json').read_bytes()).hexdigest()
 assert sources[str(parent/'inputs.json')]==receipt['receipt']['file_hashes'][str(parent/'inputs.json')]
 for name,h in sources.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 closure=implementation_closure(Path.cwd(),['src.fundamentals_n7_single','scripts.run_n7_single'],distributions=['numpy','pandas','scipy','scikit-learn'])
 plans={};hashes={};out.mkdir(parents=True);(out/'plans').mkdir()
 for issue,f in frame.groupby('issue',sort=True):
  cuts={str(s):Cutoff.decision_epoch(issue,inputs['cutoffs'][issue][str(s)]) for s in f.slot}
  path=parent/'plans'/f'{issue}-CURRENT.json';raw=path.read_bytes();assert receipt['receipt']['file_hashes'][str(path)]==hashlib.sha256(raw).hexdigest();sources[str(path)]=hashlib.sha256(raw).hexdigest()
  base=json.loads(raw)['plan'];assert n7_baseline_plan(f,cutoffs=cuts,selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=0)==base
  for policy in policies:
   plan=base if policy=='CURRENT' else n7_single_plan(f,max_uses=2,single_count=int(policy.split('_')[-1]),cutoffs=cuts,budget_cny=base['stake'],single_rule=a.single_rule,unit_cny=2,payout_factor=.65,allocation_seed=0)
   plans[issue,policy]=plan;path=out/'plans'/f'{issue}-{policy}.json';path.write_text(json.dumps(plan,indent=2));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 freeze=dict(source_hashes=sources,plan_hashes=hashes,implementation=closure,cutoffs=inputs['cutoffs'],
  contract=dict(budget='PER_ISSUE_CURRENT_STAKE',group_cost='2*2**(7-k)',single_counts=a.single_counts,single_rule=a.single_rule,unit_cny=2,payout_factor=.65,
    max_groups='BUDGET_AND_REUSE_CAPS',max_uses=2,max_pair_overlap=2,overlap_selector='SEQUENTIAL_MAX_DOUBLE_COVERAGE_LOG_MILP',cash='HOLD_NO_REINVESTMENT',draw_version='1.1.0',draw_weight=.5,high_weight=.5,
    policies=policies,learning='NONE',historical_admission=False))
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=freeze,seal=stable_json_hash(freeze)),indent=2))
 # Only now open target labels/final SP.
 results=[];audit_hashes={}
 for partition,name in [('TRAINING24','training'),('VALIDATION8','validation'),('TEST8','test')]:
  path=parent/f'{name}-audit.json';raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest();assert receipt['receipt']['file_hashes'][str(path)]==h;audit_hashes[str(path)]=h;audit=pd.DataFrame(json.loads(raw))
  members=inputs['contract']['test_issues'] if partition=='TEST8' else inputs['contract']['validation_issues'] if partition=='VALIDATION8' else sorted(set(frame.issue)-set(inputs['contract']['test_issues']+inputs['contract']['validation_issues']))
  for issue in members:
   for policy in freeze['contract']['policies']:
    plan=plans[issue,policy];r=(settle_n7_baseline if policy=='CURRENT' else settle_n7_single)(plan,audit[audit.issue==issue]);assert r['status'] in ['COMPLETE','NO_BET']
    budget=plans[issue,'CURRENT']['stake'];r.update(partition=partition,policy=policy,budget_cny=budget,
      cash_cny=budget-r['stake'],ending_funds_cny=budget-r['stake']+r['gross'],budget_return=r['net']/budget if budget else None,
      selected_matches=len({r['slot'] for r in plan['legs']}),eligible_matches=int((frame.issue==issue).sum()),
      disjoint_groups=plan.get('disjoint_groups',plan['groups']),overlap_groups=plan.get('overlap_groups',0),single_count=plan.get('single_count',0))
    results.append(r)
 verify_implementation_closure(Path.cwd(),closure)
 for name,h in {**sources,**hashes,**audit_hashes}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 (out/'results.json').write_text(json.dumps(dict(rows=results,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(freeze)),indent=2));print('COMPLETE',len(results),'rows')
