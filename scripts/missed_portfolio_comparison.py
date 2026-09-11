"""Freeze fixed six-arm comparison before audited historical settlement."""
import argparse,gzip,json,hashlib,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_missed_portfolio import drop_weak_leg,fixed_n67_wallets,settle_missed_portfolio

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 n6=Path('data/derived/fundamentals_417/missed-n6-v1');n7=Path('data/derived/fundamentals_417/cap-depth-grid-v1')
 if a.phase=='freeze':
  if out.exists():raise FileExistsError('New immutable directory required')
  f=json.loads((n6/'frozen.json').read_text());r=f['receipt'];assert stable_json_hash(r)==f['seal']
  verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['sources'],**r['plan_hashes']},repository_root=Path.cwd())
  prior=json.loads((n7/'freeze-receipt.json').read_text());pr=prior['receipt'];assert stable_json_hash(pr)==prior['seal']
  verify_clean_file_bindings(pr['plan_hashes'],repository_root=Path.cwd())
  receipt=dict(scope='EXPOSED_NO_FIT_FIXED_BUDGET',issues=r['issues'],source_hashes={**r['plan_hashes'],**pr['plan_hashes']},
   implementation=implementation_closure(Path.cwd(),['scripts.missed_portfolio_comparison'],distributions=['numpy','pandas','scipy']))
  (out/'plans').mkdir(parents=True);hashes={}
  for issue in r['issues']:
   plans=json.loads(gzip.decompress((n6/'plans'/f'{issue}.json.gz').read_bytes()))
   plans['N7']=json.loads(gzip.decompress((n7/'plans'/f'{issue}.json.gz').read_bytes()))['D2_U6_P5_BASE']['plan']
   cuts={s:Cutoff.decision_epoch(issue,t) for s,t in plans['N7']['cutoffs'].items()}
   plans['DROP']=drop_weak_leg(plans['N7'],cutoffs=cuts)
   bundles={k:fixed_n67_wallets({k:v},cutoffs=cuts,wallets={k:1024},budget_cny=1024,unit_cny=2,payout_factor=.65) for k,v in plans.items()}
   for d in [1,2]:
    bundles[f'MIX_C{d}']=fixed_n67_wallets({'N7':plans['N7'],'N6':plans[f'N6_C{d}']},cutoffs=cuts,wallets={'N7':512,'N6':512},budget_cny=1024,unit_cny=2,payout_factor=.65)
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundles).encode(),mtime=0));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  receipt['plan_hashes']=hashes;(out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
  print('FROZEN288 portfolios before settlement')
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable results')
  f=json.loads((out/'frozen.json').read_text());r=f['receipt'];assert stable_json_hash(r)==f['seal']
  verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
  old=json.loads((n7/'plans-frozen.json').read_text());assert hashlib.sha256(old['canonical_json'].encode()).hexdigest()==old['seal'];pr=json.loads(old['canonical_json'])
  paths=[k for k in pr['source_hashes'] if k.endswith('settlement-audit.json')];assert len(paths)==1
  verify_clean_file_bindings({paths[0]:pr['source_hashes'][paths[0]]},repository_root=Path.cwd());audit=pd.DataFrame(json.loads(Path(paths[0]).read_text())['rows']);rows=[]
  for issue in r['issues']:
   plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
   for policy,plan in plans.items():rows.append(dict(policy=policy,**settle_missed_portfolio(plan,audit[audit.issue==issue])))
  (out/'results.json').write_text(json.dumps(dict(rows=rows,freeze_seal=f['seal'],audit_hash={paths[0]:pr['source_hashes'][paths[0]]}),indent=2))
  print('SETTLED288 portfolios')
