"""Freeze all fixed-policy plans before reading archived R/SQLite settlement."""
import argparse,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_decision_chain import route_decision_chain,limit_decision_chain_plan
from src.fundamentals_n7_baseline import n7_baseline_plan,settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--audit-source',required=True);a=p.parse_args()
 out=Path(a.study);audit_source=Path(a.audit_source);root=Path.cwd()
 if (out/'plans').exists() or (out/'results.json').exists():raise FileExistsError('Plans/results already frozen')
 raw=(out/'inputs.json').read_bytes();pack=json.loads(raw)
 if stable_json_hash({k:v for k,v in pack.items() if k!='seal'})!=pack['seal']:raise ValueError('Input seal mismatch')
 if json.loads((out/'contract.json').read_text())!=pack['contract']:raise ValueError('Contract mismatch')
 for name,digest in pack['source_hashes'].items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Input source changed: '+name)
 c=pack['contract'];frame=pd.DataFrame(pack['rows']);issues=sorted(frame.issue.unique())
 bindings={**pack['source_hashes'],str(out/'inputs.json'):hashlib.sha256(raw).hexdigest()}
 implementation=implementation_closure(root,['src.fundamentals_decision_chain','scripts.run_decision_chain_comparison'],distributions=['numpy','pandas'])
 (out/'plans').mkdir();plans={};routes={};hashes={}
 business=dict(selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=c['max_groups'],unit_cny=c['unit_cny'],group_budget_cny=432,payout_factor=c['payout_factor'],allocation_seed=0)
 for issue in issues:
  f=frame[frame.issue==issue];slots=sorted(set(f.slot));cuts={str(s):Cutoff.decision_epoch(issue,pack['cutoffs'][issue][str(s)]) for s in slots}
  for policy,parameters in c['policies'].items():
   route=route_decision_chain(f,cutoffs=cuts,repository_root=root,source_hashes=bindings,**parameters)
   chosen=pd.DataFrame(route['rows'])
   if chosen.empty:
    plan=limit_decision_chain_plan(plans[(issue,'CURRENT')],groups=0,cutoffs=cuts)
   else:
    plan=n7_baseline_plan(chosen,cutoffs={str(s):cuts[str(s)] for s in chosen.slot},**business)
   plans[(issue,policy)]=plan;routes[(issue,policy)]=route
   path=out/'plans'/f'{issue}-{policy}.json';path.write_text(json.dumps(dict(plan=plan,routing=route),indent=2))
   hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  plan=limit_decision_chain_plan(plans[(issue,'CURRENT')],groups=plans[(issue,'CONFLICT_SKIP')]['groups'],cutoffs=cuts)
  policy='SKIP_MATCHED_CURRENT';plans[(issue,policy)]=plan
  path=out/'plans'/f'{issue}-{policy}.json';path.write_text(json.dumps(dict(plan=plan,matching='FIRST_K_CURRENT_GROUPS; K_FROM_LABEL_FREE_SKIP_PLAN'),indent=2));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  print('FROZEN',issue,flush=True)
 freeze=dict(plan_hashes=hashes,input_hashes=bindings,implementation=implementation,contract=c,historical_admission=False)
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=freeze,seal=stable_json_hash(freeze)),indent=2))
 # First opening of settlement in this run is strictly after ALL plans above.
 rows=[];leg_rows=[];audit_hashes={}
 for part,name in [('TRAINING24','training'),('VALIDATION8','validation'),('TEST8','test')]:
  path=audit_source/f'{name}-audit.json';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest();audit_hashes[str(path)]=digest
  (out/f'{name}-audit.json').write_bytes(raw);audit=pd.DataFrame(json.loads(raw))
  partition=c['test_issues'] if part=='TEST8' else c['validation_issues'] if part=='VALIDATION8' else [i for i in issues if i not in c['test_issues']+c['validation_issues']]
  for issue in partition:
   observed=audit[audit.issue==issue];base=plans[(issue,'CURRENT')];baseline_slots={r['slot'] for r in base['legs']}
   for policy in list(c['policies'])+['SKIP_MATCHED_CURRENT']:
    plan=plans[(issue,policy)];r=settle_n7_baseline(plan,observed)
    if r['status'] not in ['COMPLETE','NO_BET']:raise ValueError('Incomplete audit: '+str((issue,policy,r['status'])))
    route=routes[(issue,'CURRENT' if policy=='SKIP_MATCHED_CURRENT' else policy)]
    selected={leg['slot'] for leg in plan['legs']}
    r.update(partition=part,policy=policy,candidates=len(route['baseline']),conflict_candidates=sum(z['conflict'] for z in route['ledger']),skipped_candidates=sum(z['action']=='SKIP' for z in route['ledger']),
     selected_matches=len(selected),selected_conflicts=sum(z['conflict'] and z['slot'] in selected for z in route['ledger']),
     removed_current_matches=len(baseline_slots-selected),added_matches=len(selected-baseline_slots),
     unspent_vs_current_cny=base['stake']-plan['stake'])
    rows.append(r)
    labels=observed.set_index('slot').to_dict('index');selected_legs={leg['slot']:leg for leg in plan['legs']}
    for z in route['ledger']:
     label=labels[z['slot']]
     if label['provider_id']!=z['provider_id']:raise ValueError('Ledger identity mismatch')
     leg=selected_legs.get(z['slot']);native={'W':'3','D':'1','L':'0'}[label['actual_direction']]
     leg_rows.append(dict(z,partition=part,policy=policy,selected=leg is not None,actual_direction=label['actual_direction'],
      current_hit=label['actual_direction'] in z['current_top2'],routed_hit=None if z['routed_top2'] is None else label['actual_direction'] in z['routed_top2'],
      selected_hit=None if leg is None else native in leg['support']))
 verify_implementation_closure(root,implementation)
 for name,digest in {**bindings,**hashes,**audit_hashes}.items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('File changed during run: '+name)
 result=dict(rows=rows,legs=leg_rows,contract=c,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(freeze),historical_admission=False)
 (out/'results.json').write_text(json.dumps(result,indent=2));print('COMPLETE',len(rows),flush=True)
