"""Freeze all fixed-threshold new-period N7 supports before settlement access."""
import argparse,gzip,hashlib,itertools,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios
from src.fundamentals_n7_diversity import replace_repeated_double_tail,evaluate_fixed_supports

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study);folder=out/'plans'
 if folder.exists():raise FileExistsError('Immutable plans already exist')
 factors=json.loads((out/'factors.json').read_text());prepared=json.loads((out/'prepared.json').read_text());f=pd.DataFrame(factors['rows'])
 for k,path in [('prepared',out/'prepared.json'),('projected',out/'projected/receipt.json'),('signals',out/'signals/receipt.json')]:
  assert factors['source_hashes'][k]==hashlib.sha256(path.read_bytes()).hexdigest()
 for path,h in factors['implementation'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 assert factors['contract']==prepared['receipt']['contract'] and factors['cutoffs']==prepared['receipt']['cutoffs']
 contract=dict(factors['contract'],candidate_seed=41900,design_seed=41901,evaluation_seed=41902,pool_size=512,design_draws=1024,evaluation_draws=8192,
               budget_note='CNY1024_EACH_NEW_ISSUE; PRIOR40_USED_VARIABLE_BUDGET_NOT_DIRECT_PNL_COMPARABLE')
 closure=implementation_closure(Path.cwd(),['scripts.plan_clean_validation'],distributions=['numpy','pandas','scipy','scikit-learn'])
 folder.mkdir();hashes={};skipped={}
 for issue in contract['issues']:
  frame=f[f.issue==issue];bundle={}
  if len(frame)<7:skipped[issue]=dict(ready=len(frame),reason='FEWER_THAN_SEVEN_READY_FIXTURES',budget_cny=1024,cash_cny=1024);print('NO_BET',issue,len(frame),flush=True);continue
  cuts={str(s):Cutoff.decision_epoch(issue,factors['cutoffs'][issue][str(s)]) for s in frame.slot}
  refs={d:n7_single_plan(frame,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in (1,2)}
  pool=breadth_candidates(frame,cutoffs=cuts,seed=41900,pool_size=512)
  for depth in (1,2):
   surface=bridge_surface(frame,pool,refs,cutoffs=cuts,depth=depth);design=breadth_scenarios(frame,surface,cutoffs=cuts,seed=41901,draws=1024)
   for quality,overlap in itertools.product(['TOP2','COMPRESSED'],['STRICT','FREE']):
    case=f'D{depth}_{quality}_{overlap}'
    base=bridge_plan(frame,surface,design,refs[depth],cutoffs=cuts,preserve_prefix=True,quality=quality,overlap=overlap,cash_policy='HOLD',budget_cny=1024,unit_cny=2,payout_factor=.65)
    for rule,gap in [('BASE',None),('GAP02',.02),('GAP05',.05),('GAP10',.10),('ALL',1.)]:
     plan=base if gap is None else replace_repeated_double_tail(base,cutoffs=cuts,max_gap=gap)
     evaluation=evaluate_fixed_supports(frame,plan,cutoffs=cuts,seed=41902,draws=8192)
     bundle[case+'_'+rule]=dict(plan=plan,evaluation=evaluation,case=case,rule=rule,max_gap=gap,depth=depth,quality=quality,overlap=overlap)
  assert len(bundle)==40
  path=folder/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  print('FROZEN',issue,40,flush=True)
 verify_implementation_closure(Path.cwd(),closure)
 sources={str(out/n):hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['factors.json','prepared.json','projected/receipt.json','signals/receipt.json']}
 receipt=dict(contract=contract,source_hashes=sources,plan_hashes=hashes,no_bet=skipped,cutoffs=factors['cutoffs'],implementation=closure)
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 print('ALL_PLANS_FROZEN',len(hashes),len(skipped),flush=True)
