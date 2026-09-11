"""Freeze all fixed45 diagnostic plans before opening this run's settlement."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_rescue_shapes import MODES,rescue_shape_plan
from src.fundamentals_missed_portfolio import fixed_n67_wallets,settle_missed_portfolio

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['freeze','settle']);parser.add_argument('--study',required=True);a=parser.parse_args();out=Path(a.study)
 source=Path('data/derived/fundamentals_417/n7-hit-improvement-v1')
 if a.phase=='freeze':
  if out.exists():raise FileExistsError('New immutable study required')
  old=json.loads((source/'frozen.json').read_text());r=old['receipt'];assert old['seal']==stable_json_hash(r)
  verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
  parameters=dict(source_weights=[0,1],support_weights=[0,.5,1],modes=list(MODES),existing=['W100_P0_C2','W100_P1_C2','W050_P1_C2'],budget_cny=1024,unit_cny=2,payout_factor=.65)
  receipt=dict(scope='EXPOSED_MISSED25_FIXED45_NOT_ROUTING',issues=r['issues'],parameters=parameters,source_hashes={**r['plan_hashes'],str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest()},implementation=implementation_closure(Path.cwd(),['scripts.missed25_rescue'],distributions=['numpy','pandas','scipy']))
  (out/'plans').mkdir(parents=True);(out/'contract.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));hashes={}
  for issue in r['issues']:
   originals=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))['bundles'];bundles={}
   for h in parameters['source_weights']:
    base=originals[f'W{h*100:03}_P0_C0']['plan'];cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
    for w in parameters['support_weights']:
     for mode in MODES:
      shaped=rescue_shape_plan(base,cutoffs=cuts,market_weight=w,mode=mode,budget_cny=1024,unit_cny=2,payout_factor=.65)
      if h==0 and w==0 and mode=='N7_C2_TOP1':assert shaped['tickets']==base['tickets'] and shaped['stake']==base['stake']
      portfolio=fixed_n67_wallets({'only':shaped},cutoffs=cuts,wallets={'only':1024},budget_cny=1024,unit_cny=2,payout_factor=.65)
      bundles[f'H{h}_R{int(w*100):03}_{mode}']=dict(plan=portfolio,shape_plan=shaped,source_weight=h,support_weight=w,mode=mode)
   for name in parameters['existing']:
    base=originals[name]['plan'];cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
    bundles[name]=dict(plan=fixed_n67_wallets({'only':base},cutoffs=cuts,wallets={'only':1024},budget_cny=1024,unit_cny=2,payout_factor=.65),shape_plan=base,source_weight=None,support_weight=None,mode='EXISTING')
   assert len(bundles)==45
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundles).encode(),mtime=0));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,flush=True)
  receipt['plan_hashes']=hashes;(out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));print('SEALED2160 plans')
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable settlement')
  frozen=json.loads((out/'frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
  verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
  prior=json.loads((source/'results.json').read_text());assert prior['freeze_seal']==json.loads((source/'frozen.json').read_text())['seal'];verify_clean_file_bindings(prior['audit_hash'],repository_root=Path.cwd())
  assert len(prior['audit_hash'])==1
  audit=pd.DataFrame(json.loads(Path(next(iter(prior['audit_hash']))).read_text())['rows']);rows=[];base_legs=[]
  for issue in r['issues']:
   plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));base_legs.extend(plans['H0_R000_N7_C2_TOP1']['shape_plan']['legs'])
   for policy,entry in plans.items():
    settled=settle_missed_portfolio(entry['plan'],audit[audit.issue==issue])
    rows.append(dict(policy=policy,**{k:entry[k] for k in ['source_weight','support_weight','mode']},**settled))
  (out/'results.json').write_text(json.dumps(dict(rows=rows,base_legs=base_legs,audit=audit.to_dict('records'),audit_hash=prior['audit_hash'],freeze_seal=frozen['seal'])));print('SETTLED2160 plans')
