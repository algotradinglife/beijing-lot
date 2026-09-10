"""Run one declared stage; freeze every plan before opening settlement labels."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_conflict_probabilities import conflict_score_projection,conflict_score_offer
from src.fundamentals_conflict_portfolios import expand_conflict_plan,conflict_protection_plan,settle_conflict_protection
from src.fundamentals_reverse_gate import reverse_positive_ceiling
from src.fundamentals_n7_baseline import n7_baseline_plan,settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--study',required=True);parser.add_argument('--stage',required=True,choices=['REESTIMATE','EXPAND','PROTECT']);args=parser.parse_args()
 study=Path(args.study);stage=args.stage;out=study/stage.lower();root=Path.cwd()
 if out.exists():raise FileExistsError('New immutable stage directory required')
 contract=json.loads((study/'contract.json').read_text());parent=Path(contract['parent_study'])
 inputs=json.loads((parent/'inputs.json').read_text());scores=json.loads((study/'scores.json').read_text())
 if hashlib.sha256((parent/'inputs.json').read_bytes()).hexdigest()!=contract['parent_input_sha256']:raise ValueError('Parent inputs changed')
 if stable_json_hash({k:v for k,v in inputs.items() if k!='seal'})!=inputs['seal']:raise ValueError('Parent seal mismatch')
 expected=json.loads((parent/'study-receipt.json').read_text())
 if stable_json_hash(expected['receipt'])!=expected['seal']:raise ValueError('Parent study receipt invalid')
 sources={**inputs['source_hashes'],**scores['source_hashes'],**scores['implementation_hashes']}
 for name,digest in sources.items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Changed source: '+name)
 for path in [study/'contract.json',study/'scores.json',parent/'inputs.json',parent/'study-receipt.json']:
  sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 if scores['cutoffs']!=inputs['cutoffs']:raise ValueError('Score clocks differ')
 frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 current_rows=frame.sort_values(['issue','slot','provider_id']).to_dict('records')
 issues=sorted(frame.issue.unique());cutoffs={i:{str(s):Cutoff.decision_epoch(i,inputs['cutoffs'][i][str(s)]) for s in frame[frame.issue==i].slot} for i in issues}
 if len(scores['grids'])!=len(frame):raise ValueError('Exact score cohort required')
 policies=['CURRENT','MARKET_MIX_050','MARKET_MIX_100'] if stage=='REESTIMATE' else ['CURRENT','FULL_ONE_EXTRA','FULL_ONE_FIXED','FULL_ALL_EXTRA','FULL_ALL_FIXED'] if stage=='EXPAND' else ['CURRENT','REVERSE_POSITIVE_ONLY','CONFLICT_SCORE_EXTRA','CONFLICT_SCORE_FIXED']
 reverse=None
 if stage=='PROTECT':
  path=Path(contract['reverse_source']);raw=path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=contract['reverse_sha256']:raise ValueError('Reverse archive changed')
  sources[str(path)]=contract['reverse_sha256'];reverse=json.loads(raw)
 closure=implementation_closure(root,['src.fundamentals_conflict_probabilities','src.fundamentals_conflict_portfolios','src.fundamentals_reverse_gate','scripts.run_conflict_actions'],distributions=['numpy','pandas','scipy','scikit-learn'])
 out.mkdir();(out/'plans').mkdir();plans={};plan_hashes={};predictions=[];offers=[];gates=[]
 for issue in issues:
  path=parent/'plans'/f'{issue}-CURRENT.json';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  if expected['receipt']['file_hashes'][str(path)]!=digest:raise ValueError('Current plan changed')
  sources[str(path)]=digest;base=json.loads(raw)['plan'];rows=frame[frame.issue==issue].to_dict('records');issue_offers=[];projected={policy:[] for policy in policies}
  for row in rows:
   cutoff=cutoffs[issue][str(row['slot'])];grid=scores['grids'][f"{issue}/{row['slot']}"]
   zero=conflict_score_projection(grid,row,cutoff=cutoff,market_weight=0)
   offer=conflict_score_offer(zero,cutoff=cutoff);issue_offers.append(offer);offers.append(offer)
   if stage=='PROTECT':
    gate=reverse_positive_ceiling(reverse,cutoff=cutoff,expected_seal=contract['reverse_receipt_seal'])
    if gate['status']!='NO_POSITIVE_LEAF':raise ValueError('Exact executable expert inference needed; no synthetic signal substitution')
    gates.append(dict(issue=issue,slot=row['slot'],provider_id=row['provider_id'],**gate))
   if stage=='REESTIMATE':
    for policy,weight in [('CURRENT',0),('MARKET_MIX_050',.5),('MARKET_MIX_100',1)]:
     projection=zero if weight==0 else conflict_score_projection(grid,row,cutoff=cutoff,market_weight=weight)
     projected[policy].append(projection['fixture'])
     predictions.append(dict(projection['fixture'],policy=policy,conflict=projection['receipt']['conflict'],
      applied_market_weight=projection['receipt']['applied_weight'],projection_seal=projection['seal']))
  for policy in policies:
   if policy=='CURRENT':plan=base
   elif stage=='REESTIMATE':
    plan=n7_baseline_plan(pd.DataFrame(projected[policy]),cutoffs=cutoffs[issue],selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=contract['max_groups'],unit_cny=contract['unit_cny'],group_budget_cny=432,payout_factor=contract['payout_factor'],allocation_seed=contract['allocation_seed'])
   elif stage=='EXPAND':
    _,mode,funding=policy.split('_');plan=expand_conflict_plan(base,issue_offers,cutoffs=cutoffs[issue],mode=mode,funding=funding,budget_cny=base['stake'],allocation_seed=contract['allocation_seed'])
   elif policy=='REVERSE_POSITIVE_ONLY':plan=base
   else:
    plan=conflict_protection_plan(base,issue_offers,cutoffs=cutoffs[issue],funding=policy.split('_')[-1],unit_cny=contract['unit_cny'],allocation_seed=contract['allocation_seed'])
   plans[(issue,policy)]=plan;path=out/'plans'/f'{issue}-{policy}.json';path.write_text(json.dumps(plan,indent=2));plan_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  print('FROZEN',stage,issue,flush=True)
 label_free=dict(predictions=predictions,offers=offers,reverse_gates=gates)
 (out/'decisions.json').write_text(json.dumps(label_free,indent=2));sources[str(out/'decisions.json')]=hashlib.sha256((out/'decisions.json').read_bytes()).hexdigest()
 receipt=dict(stage=stage,contract=contract,source_hashes=sources,plan_hashes=plan_hashes,implementation=closure,
  cutoff_map={i:{s:c.cutoff_ts.isoformat() for s,c in cuts.items()} for i,cuts in cutoffs.items()},learning='NONE',historical_admission=False)
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 # No target outcome, final SP, or final score has been opened before this line.
 results=[];prediction_metrics=[];audit_hashes={}
 for partition,name in [('TRAINING24','training'),('VALIDATION8','validation'),('TEST8','test')]:
  path=parent/f'{name}-audit.json';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  if expected['receipt']['file_hashes'][str(path)]!=digest:raise ValueError('Archived R audit changed')
  audit_hashes[str(path)]=digest;audit=pd.DataFrame(json.loads(raw));lookup=audit.set_index(['issue','slot','provider_id'])
  members=inputs['contract']['test_issues'] if partition=='TEST8' else inputs['contract']['validation_issues'] if partition=='VALIDATION8' else [i for i in issues if i not in inputs['contract']['test_issues']+inputs['contract']['validation_issues']]
  for issue in members:
   for policy in policies:
    plan=plans[(issue,policy)];side=stage=='PROTECT' and policy.startswith('CONFLICT_SCORE')
    observed=audit[audit.issue==issue];result=settle_conflict_protection(plan,observed) if side else settle_n7_baseline(plan,observed)
    if result['status'] not in {'COMPLETE','NO_BET'}:raise ValueError('Pending settlement: '+str((issue,policy,result)))
    if not side:result.update(main_stake=result['stake'],main_gross=result['gross'],score_stake=0,score_gross=0.,score_net=0.,score_bets=0,score_hits=0)
    current=plans[(issue,'CURRENT')];main=plan['main'] if side else plan
    slots={r['slot'] for r in main['legs']};baseline_slots={r['slot'] for r in current['legs']}
    result.update(stage=stage,partition=partition,policy=policy,base_stake=current['stake'],extra_stake=result['stake']-current['stake'],
     retained_matches=len(slots),removed_matches=len(baseline_slots-slots),added_matches=len(slots-baseline_slots),
     expanded_matches=sum(len(r['support'])==3 for r in main['legs']),distinct_tickets=len(main['tickets']),
     betting_units=sum(t['units'] for t in main['tickets']),historical_admission=False)
    results.append(result)
  if stage=='REESTIMATE':
   for r in predictions:
    if r['issue'] not in members:continue
    label=lookup.loc[(r['issue'],r['slot'],r['provider_id'])];grid=scores['grids'][f"{r['issue']}/{r['slot']}"]
    actual=[g for g in grid if g['home_goals']==label.actual_home and g['away_goals']==label.actual_away]
    p_actual=(1-r['applied_market_weight'])*actual[0]['p']+r['applied_market_weight']*actual[0]['q'] if actual else 0.
    prediction_metrics.append(dict(r,partition=partition,actual_direction=label.actual_direction,p_actual_score=p_actual,
     score_outside_support=not bool(actual),actual_home=int(label.actual_home),actual_away=int(label.actual_away)))
 verify_implementation_closure(root,closure)
 for name,digest in {**sources,**plan_hashes,**audit_hashes}.items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during run: '+name)
 result=dict(rows=results,prediction_metrics=prediction_metrics,contract=contract,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(receipt),historical_admission=False)
 (out/'results.json').write_text(json.dumps(result,indent=2));print('COMPLETE',stage,len(results),flush=True)
