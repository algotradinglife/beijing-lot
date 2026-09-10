"""Frozen local routing, shared N7 planning/settlement, prior-only penalty choice."""
import argparse,json,hashlib,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_integration_weight import select_integration_weights,select_integration_penalty
from src.fundamentals_n7_baseline import n7_baseline_plan,settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import utc
from src.temporal_learning.diagnostic_labels import diagnostic_label_clock
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 if (out/'results.json').exists():raise FileExistsError('Results already frozen')
 c=json.loads((out/'contract.json').read_text());source=json.loads((out/'candidates.json').read_text());frame=pd.DataFrame(source['rows']);cuts=source['cutoffs']
 metadata={}
 for name,digest in source['implementation_hashes'].items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Projection implementation changed: '+name)
 for study in ['train-eight-test-eight-v2','cv-sixteen-test-sixteen-v1','cv-thirtytwo-test-sixteen-v1']:
  old=json.loads(Path(f'data/derived/fundamentals_417/{study}/predictions.json').read_text())
  for r in old['features']:metadata[(r['issue'],r['slot'],r['provider_id'])]=r['handicap']
 policies=[(f'FIXED_{w:g}','FIXED',0,w) for w in c['weights']]+[(f'EV_{v:g}','EXPECTED_RETURN',v,None) for v in c['penalties']]
 routing_cuts={i:{s:Cutoff.decision_epoch(i,t) for s,t in slots.items()} for i,slots in cuts.items()}
 plans={};routings={};weights=[];issues=sorted(frame.issue.unique())
 plan_dir=out/'plans';plan_dir.mkdir(exist_ok=False)
 for issue in issues:
  f=frame[frame.issue==issue]
  for name,mode,penalty,w in policies:
   route=select_integration_weights(f,cutoffs=routing_cuts,mode=mode,penalty=penalty,fixed_weight=w)
   chosen=pd.DataFrame(route['rows']);chosen['handicap']=[metadata[(r.issue,r.slot,r.provider_id)] for r in chosen.itertuples()]
   selected_cuts={str(r.slot):Cutoff.decision_epoch(issue,cuts[issue][str(r.slot)]) for r in chosen.itertuples()}
   plan=n7_baseline_plan(chosen,cutoffs=selected_cuts,selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=0)
   key=f'{issue}/{name}';plans[key]=plan;routings[key]=route
   weights.extend(dict(issue=issue,policy=name,slot=r['slot'],provider_id=r['provider_id'],weight=r['weight']) for r in plan['legs'])
   (plan_dir/f'{issue}-{name}.json').write_text(json.dumps(dict(plan=plan,routing=route),indent=2))
  print('PLANNED',issue,flush=True)
 # All potential supports/tickets frozen before settlement reads. No labels in routing.
 validation_bytes=(out/'validation-audit.json').read_bytes()
 audit_hashes={str(out/'validation-audit.json'):hashlib.sha256(validation_bytes).hexdigest()}
 val=pd.DataFrame(json.loads(validation_bytes));validation=[]
 for issue in c['validation_issues']:
  for name,mode,penalty,w in policies:
   result=settle_n7_baseline(plans[f'{issue}/{name}'],val[val.issue==issue]);result.update(policy=name,partition='VALIDATION8');validation.append(result)
 target=c['test_issues'][0];cutoff=Cutoff.decision_epoch(target,min(cuts[target].values()));history=[]
 for issue in c['validation_issues']:
  last=max(cuts[issue].values(),key=utc)
  row=dict(issue_code=issue,issue_year=utc(last).year,data_available_ts=last,label_available_ts=diagnostic_label_clock(last,cutoff=cutoff,delay_hours=6))
  for i,v in enumerate(c['penalties']):
   r=next(r for r in validation if r['issue']==issue and r['policy']==f'EV_{v:g}')
   if r['status'] not in ['COMPLETE','NO_BET']:raise ValueError('Validation settlement incomplete')
   row[f'net_{i}']=r['net']
  history.append(row)
 selection=select_integration_penalty(pd.DataFrame(history),cutoff,penalties=c['penalties'],minimum_issues=8,repository_root=Path.cwd(),source_hashes={**source['input_hashes'],**source['implementation_hashes'],**{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [out/'contract.json',out/'candidates.json',out/'endpoints.json',out/'validation-audit.json',Path('scripts/prepare_integration_weight_endpoints.py')]}})
 (out/'penalty-selection.json').write_text(json.dumps(selection,indent=2))
 # Selection receipt is frozen before opening the final test labels.
 rows=list(validation)
 for part,path in [('TRAINING24','training-audit.json'),('TEST8','test-audit.json')]:
  audit_bytes=(out/path).read_bytes();audit_hashes[str(out/path)]=hashlib.sha256(audit_bytes).hexdigest()
  audit=pd.DataFrame(json.loads(audit_bytes))
  group=c['test_issues'] if part=='TEST8' else [i for i in issues if i not in c['test_issues']+c['validation_issues']]
  for issue in group:
   for name,mode,penalty,w in policies:
    result=settle_n7_baseline(plans[f'{issue}/{name}'],audit[audit.issue==issue]);result.update(policy=name,partition=part);rows.append(result)
 for row in list(rows):
  if row['policy']==f"EV_{selection['penalty']:g}":rows.append(dict(row,policy='SELECTED_PENALTY',selection_scope='VALIDATION_REVIEW' if row['partition']!='TEST8' else 'FROZEN_BEFORE_TEST'))
 for name,digest in audit_hashes.items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Audit changed during evaluation')
 (out/'results.json').write_text(json.dumps(dict(rows=rows,weights=weights,selection=selection,contract=c,audit_hashes=audit_hashes,historical_admission=False),indent=2))
 print('COMPLETE',len(rows),selection['penalty'],flush=True)
