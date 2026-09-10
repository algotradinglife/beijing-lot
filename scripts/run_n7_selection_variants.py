"""Freeze random-seed and precompression experiments before opening labels."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_n7_random_single import random_second_single_plan
from src.fundamentals_n7_precompress import precompress_n7_plan
from src.fundamentals_n7_single import settle_n7_single
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parent',required=True);p.add_argument('--output',required=True);a=p.parse_args();parent=Path(a.parent);out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable output required')
 frozen=json.loads((parent/'plans-frozen.json').read_text());assert stable_json_hash(frozen['receipt'])==frozen['seal']
 sources=dict(frozen['receipt']['source_hashes']);input_path=next(k for k in sources if k.endswith('/inputs.json'))
 for name,h in sources.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 inputs=json.loads(Path(input_path).read_text());frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 seeds=list(range(100));global_rules=[('FIXED',8),('FIXED',12),('FIXED',16),('THRESHOLD',.5),('THRESHOLD',.6),('THRESHOLD',.7)]
 contract=dict(seeds=seeds,random_outcome_mode='TOP1',global_rules=global_rules,budget='ORIGINAL_PER_ISSUE_CURRENT_STAKE',
  max_uses=2,max_pair_overlap=2,unit_cny=2,payout_factor=.65,draw_version='1.1.0',draw_weight=.5,high_weight=.5,
  seed_selection='NONE_ALL_100_REPORTED',learning='NONE',historical_admission=False)
 closure=implementation_closure(Path.cwd(),['src.fundamentals_n7_random_single','src.fundamentals_n7_precompress','scripts.run_n7_selection_variants'],distributions=['numpy','pandas','scipy','scikit-learn'])
 out.mkdir(parents=True);(out/'plans').mkdir();plan_hashes={}
 for issue,f in frame.groupby('issue',sort=True):
  cuts={str(s):Cutoff.decision_epoch(issue,inputs['cutoffs'][issue][str(s)]) for s in f.slot};bundle={}
  for policy in ['CURRENT','SINGLE_1','SINGLE_2']:
   path=parent/'plans'/f'{issue}-{policy}.json';raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest();assert frozen['receipt']['plan_hashes'][str(path)]==h;sources[str(path)]=h;bundle[policy]=json.loads(raw)
  budget=bundle['CURRENT']['stake']
  for mode,value in global_rules:
   policy=f'GLOBAL_{mode}_{value}';bundle[policy]=precompress_n7_plan(f,cutoffs=cuts,budget_cny=budget,mode=mode,value=value,unit_cny=2,payout_factor=.65,allocation_seed=0)
  for seed in seeds:bundle[f'RANDOM_{seed:03d}']=random_second_single_plan(bundle['SINGLE_2'],cutoffs=cuts,seed=seed,outcome_mode='TOP1')
  path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0));plan_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,flush=True)
 receipt=dict(contract=contract,cutoffs=inputs['cutoffs'],source_hashes=sources,plan_hashes=plan_hashes,implementation=closure,parent_freeze_seal=frozen['seal'])
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 # Every random draw/global-role/group/ticket is frozen before labels or final SP.
 old_results=json.loads((parent/'results.json').read_text());audit_hashes=old_results['audit_hashes'];audits=[]
 for name,h in audit_hashes.items():
  raw=Path(name).read_bytes();assert hashlib.sha256(raw).hexdigest()==h;audits.extend(json.loads(raw))
 audit=pd.DataFrame(audits);results=[]
 for issue in sorted(frame.issue.unique()):
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));observed=audit[audit.issue==issue]
  partition='TEST8' if issue in inputs['contract']['test_issues'] else 'VALIDATION8' if issue in inputs['contract']['validation_issues'] else 'TRAINING24'
  for policy,plan in bundle.items():
   r=(settle_n7_baseline if policy=='CURRENT' else settle_n7_single)(plan,observed);assert r['status'] in ['COMPLETE','NO_BET']
   budget=bundle['CURRENT']['stake'];r.update(policy=policy,partition=partition,budget_cny=budget,cash_cny=budget-r['stake'],
    budget_return=r['net']/budget if budget else None,seed=plan.get('seed'),
    single_pool_size=len(plan.get('single_slots',[])) if policy.startswith('GLOBAL') else None,
    disjoint_groups=plan.get('disjoint_groups',plan['groups']),overlap_groups=plan.get('overlap_groups',0))
   results.append(r)
  print('SETTLED',issue,flush=True)
 verify_implementation_closure(Path.cwd(),closure)
 for name,h in {**sources,**plan_hashes,**audit_hashes}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 (out/'results.json').write_text(json.dumps(dict(rows=results,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(receipt)),indent=2));print('COMPLETE',len(results),flush=True)
