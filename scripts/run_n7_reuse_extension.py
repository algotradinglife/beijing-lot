"""Freeze fixed-cap and outcome-diversified C3 plans before archived settlement."""
import argparse,gzip,hashlib,json,math,sys
from collections import Counter
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_n7_single import n7_single_plan,settle_n7_single
from src.fundamentals_n7_diversity import diversify_n7_outcomes
from src.fundamentals_n7_reuse_extension import extend_n7_reuse_plan
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parent',required=True);p.add_argument('--output',required=True);a=p.parse_args();parent=Path(a.parent);out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable study directory required')
 old=json.loads((parent/'plans-frozen.json').read_text());assert stable_json_hash(old['receipt'])==old['seal']
 sources=dict(old['receipt']['source_hashes']);input_path=next(k for k in sources if k.endswith('/inputs.json'))
 for path,h in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(input_path).read_text());frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 caps=[3,4,6];rule='PROBABILITY_OVER_ONE_PLUS_PRIOR_COVERAGE'
 contract=dict(caps=caps,single_count=3,group_cost_cny=32,unit_cny=2,payout_factor=.65,max_pair_overlap=2,
  budget='ORIGINAL_PER_ISSUE_CURRENT_STAKE',selection='MAX_SINGLE',grouping='POSTHOC_PRESERVE_CAP2_THEN_APPEND_CAP3_4_6',
  diversity_rule=rule,probabilities='UNCHANGED_FIXED_P_AND_MARKET_Q',diversity_score='RANKING_ONLY_NOT_RECALIBRATED_PROBABILITY',
  draw_version='1.1.0',draw_weight=.5,high_weight=.5,learning='NONE',historical_admission=False)
 closure=implementation_closure(Path.cwd(),['src.fundamentals_n7_single','src.fundamentals_n7_diversity','src.fundamentals_n7_reuse_extension','scripts.run_n7_reuse_extension'],distributions=['numpy','pandas','scipy','scikit-learn'])
 out.mkdir(parents=True);(out/'plans').mkdir();hashes={}
 for issue,f in frame.groupby('issue',sort=True):
  cuts={str(s):Cutoff.decision_epoch(issue,inputs['cutoffs'][issue][str(s)]) for s in f.slot};bundle={}
  path=parent/'plans'/f'{issue}.json.gz';raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest();assert old['receipt']['plan_hashes'][str(path)]==h;sources[str(path)]=h
  prior=json.loads(gzip.decompress(raw));fixed=prior['CAP2_FIXED'];budget=fixed['budget_cny']
  for cap in caps:
   fixed=extend_n7_reuse_plan(fixed,f,cutoffs=cuts,max_uses=cap)
   bundle[f'NESTED_CAP{cap}_FIXED']=fixed
   bundle[f'NESTED_CAP{cap}_DIVERSE']=diversify_n7_outcomes(fixed,cutoffs=cuts,rule=rule)
  path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,flush=True)
 receipt=dict(contract=contract,cutoffs=inputs['cutoffs'],source_hashes=sources,plan_hashes=hashes,implementation=closure,parent_freeze_seal=old['seal'])
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 # Full identity/outcome choices are frozen before opening labels or final SP.
 previous=json.loads((parent/'results.json').read_text());audit_hashes=previous['audit_hashes'];audits=[]
 for path,h in audit_hashes.items():
  raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==h;audits.extend(json.loads(raw))
 audit=pd.DataFrame(audits);results=[]
 for issue in sorted(frame.issue.unique()):
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));observed=audit[audit.issue==issue]
  labels=observed.set_index(['slot','provider_id']);partition='TEST8' if issue in inputs['contract']['test_issues'] else 'VALIDATION8' if issue in inputs['contract']['validation_issues'] else 'TRAINING24'
  for policy,plan in bundle.items():
   r=(settle_n7_baseline if policy=='CURRENT' else settle_n7_single)(plan,observed);assert r['status'] in ['COMPLETE','NO_BET']
   uses=Counter(z['slot'] for z in plan['legs']);pairs={(z['slot'],code) for z in plan['legs'] for code in z['support']};covered=0;expected=0.
   for group in range(1,plan['groups']+1):
    masses=[]
    for leg in [z for z in plan['legs'] if z['group']==group]:
     ds=[d for d,c in zip('WDL','310') if c in leg['support']];masses.append(sum(leg['p_'+d] for d in ds))
     covered+=dict(W='3',D='1',L='0')[labels.loc[(leg['slot'],leg['provider_id']),'actual_direction']] in leg['support']
    expected+=math.prod(masses)
   budget=plan['budget_cny'];r.update(policy=policy,partition=partition,budget_cny=budget,cash_cny=budget-r['stake'],
    budget_return=r['net']/budget if budget else None,disjoint_groups=plan.get('disjoint_groups',plan['groups']),overlap_groups=plan.get('overlap_groups',0),
    unique_fixtures=len(uses),fixture_exposures=len(plan['legs']),max_actual_uses=max(uses.values(),default=0),
    unique_fixture_direction_pairs=len(pairs),covered_legs=covered,expected_winning_groups=expected,
    changed_support_legs=sum(z['changed'] for z in plan.get('diversity_ledger',[])))
   results.append(r)
 verify_implementation_closure(Path.cwd(),closure)
 for path,h in {**sources,**hashes,**audit_hashes}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 (out/'results.json').write_text(json.dumps(dict(rows=results,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(receipt)),indent=2));print('COMPLETE',len(results),flush=True)
