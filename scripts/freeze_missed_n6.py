"""Freeze all 48 N6 plans before settlement; historical diagnostic only."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_compression_breadth import breadth_candidates
from src.fundamentals_n6_diagnostic import n6_diagnostic_plan

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('New immutable output required')
 path=Path('data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json');data=json.loads(path.read_text())
 verify_clean_file_bindings(data['source_hashes'],repository_root=Path.cwd())
 frame=pd.DataFrame(data['rows']);issues=sorted(frame.issue.unique());assert len(issues)==48
 receipt=dict(scope='EXPOSED_FIXED_RULE_NO_FIT',issues=issues,parameters=dict(seed=41900,pool_size=512,
  depths=[1,2],max_uses=6,max_pair_overlap=5,budget_cny=1024,unit_cny=2,payout_factor=.65),
  sources={str(path):hashlib.sha256(path.read_bytes()).hexdigest()},
  implementation=implementation_closure(Path.cwd(),['scripts.freeze_missed_n6'],distributions=['numpy','pandas','scipy']))
 (out/'plans').mkdir(parents=True);(out/'contract.json').write_text(json.dumps(receipt,indent=2));hashes={}
 for issue in issues:
  f=frame[frame.issue==issue];cuts={str(s):Cutoff.decision_epoch(issue,data['cutoffs'][issue][str(s)]) for s in f.slot}
  pool=breadth_candidates(f,cutoffs=cuts,seed=41900,pool_size=512)
  plans={f'N6_C{d}':n6_diagnostic_plan(f,pool,cutoffs=cuts,depth=d,budget_cny=1024,unit_cny=2,payout_factor=.65,
   max_uses=6,max_pair_overlap=5) for d in [1,2]}
  dest=out/'plans'/f'{issue}.json.gz';dest.write_bytes(gzip.compress(json.dumps(plans).encode(),mtime=0));hashes[str(dest)]=hashlib.sha256(dest.read_bytes()).hexdigest()
  print('FROZEN',issue,{k:(v['groups'],v['stake']) for k,v in plans.items()},flush=True)
 receipt['plan_hashes']=hashes
 (out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
