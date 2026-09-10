"""Post-hoc attribution control: same retained groups, all money on main tickets."""
import argparse,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_conflict_portfolios import fund_complete_plan
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--output',required=True);a=p.parse_args();study=Path(a.study);out=Path(a.output)
 if out.exists():raise FileExistsError('Attribution already frozen')
 c=json.loads((study/'contract.json').read_text());parent=Path(c['parent_study']);source=study/'protect'
 freeze=json.loads((source/'plans-frozen.json').read_text());assert stable_json_hash(freeze['receipt'])==freeze['seal']
 out.mkdir();(out/'plans').mkdir();plans={};bindings={str(source/'plans-frozen.json'):hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest()}
 for path in sorted((source/'plans').glob('*-CONFLICT_SCORE_FIXED.json')):
  assert hashlib.sha256(path.read_bytes()).hexdigest()==freeze['receipt']['plan_hashes'][str(path)]
  fixed=json.loads(path.read_text());main=fixed['main'];issue=main['issue'];bindings[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  cuts={s:Cutoff.decision_epoch(issue,t) for s,t in main['cutoffs'].items()}
  control=fund_complete_plan(main,cutoffs=cuts,budget_cny=fixed['base_stake'],allocation_seed=c['allocation_seed']) if main['groups'] else main
  plans[issue]=control;(out/'plans'/f'{issue}.json').write_text(json.dumps(control,indent=2))
 receipt=dict(interpretation='POSTHOC_ATTRIBUTION_NOT_NEW_SELECTED_STRATEGY',source_hashes=bindings,
  plan_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'plans').glob('*.json')},
  implementation=implementation_closure(Path.cwd(),['scripts.attribute_conflict_score_funding'],distributions=['numpy','pandas']),
  cutoff_maps={i:p['cutoffs'] for i,p in plans.items()},historical_admission=False)
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 # Outcomes are already exposed in the main study: this is labelled attribution.
 original=json.loads((source/'results.json').read_text());rows=[];audit_hashes={}
 for part,name in [('TRAINING24','training'),('VALIDATION8','validation'),('TEST8','test')]:
  path=parent/f'{name}-audit.json';raw=path.read_bytes();audit_hashes[str(path)]=hashlib.sha256(raw).hexdigest()
  assert audit_hashes[str(path)]==original['audit_hashes'][str(path)]
  audit=pd.DataFrame(json.loads(raw))
  for r in [r for r in original['rows'] if r['partition']==part and r['policy']=='CURRENT']:
   issue=r['issue'];plan=plans[issue];settled=settle_n7_baseline(plan,audit[audit.issue==issue]);assert settled['status'] in ['COMPLETE','NO_BET']
   result=dict(r,**{k:v for k,v in settled.items() if k not in ['issue']});result.update(stage='ATTRIBUTION',policy='SAME_GROUPS_NO_SCORE',main_stake=settled['stake'],main_gross=settled['gross'],
    retained_matches=len(plan['legs']),removed_matches=r['retained_matches']-len(plan['legs']),added_matches=0,
    distinct_tickets=len(plan['tickets']),betting_units=sum(t['units'] for t in plan['tickets']),interpretation=receipt['interpretation'])
   rows.append(result)
 for r in original['rows']:
  if r['policy'] in ['CURRENT','CONFLICT_SCORE_FIXED']:rows.append(dict(r,stage='ATTRIBUTION',interpretation=receipt['interpretation']))
 (out/'results.json').write_text(json.dumps(dict(rows=rows,prediction_metrics=[],audit_hashes=audit_hashes,contract=c,freeze_seal=freeze['seal'],attribution_freeze_seal=stable_json_hash(receipt),historical_admission=False),indent=2))
 print('ATTRIBUTION',len(plans),'plans',len(rows),'rows')
