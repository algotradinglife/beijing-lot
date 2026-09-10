"""Freeze fixed support variants first; settle only after the complete freeze."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_repeated_support import replace_repeated_support
from src.fundamentals_compression_variants import settle_compression_variants

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True)
 p.add_argument('--source',default='data/derived/fundamentals_417/new48-pure-baseline-v1');a=p.parse_args()
 out=Path(a.study);source=Path(a.source);root=Path.cwd()
 if a.phase=='freeze':
  if out.exists():raise FileExistsError('New immutable study required')
  original=json.loads((source/'plans-frozen.json').read_text());r=original['receipt']
  assert stable_json_hash(r)==original['seal']
  verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  params=dict(single_ceiling=.75,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
  closure=implementation_closure(root,['scripts.repeated_support_variants'],distributions=['pandas'])
  (out/'plans').mkdir(parents=True);files={}
  for issue in r['issues']:
   old=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))
   base=old['D2_TOP2_FREE_BASE']['plan'];assert base['stake']==base['budget_cny']==1024
   cuts={str(s):Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
   modes=dict(BASE=(False,'NONE'),SINGLE=(True,'NONE'),GAP=(False,'GAP'),MARKET=(False,'MARKET'),DOUBLE_OR=(False,'EITHER'),ALL=(True,'EITHER'))
   bundle={}
   for rule,(singles,doubles) in modes.items():
    plan=base if rule=='BASE' else replace_repeated_support(base,cutoffs=cuts,change_singles=singles,double_rule=doubles,**params)
    bundle['D2_TOP2_FREE_'+rule]=dict(case='D2_TOP2_FREE',rule=rule,depth=2,quality='TOP2',overlap='FREE',plan=plan,evaluation=dict(metrics={}))
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0))
   files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,flush=True)
  verify_implementation_closure(root,closure)
  receipt=dict(scope='FIXED_SUPPORT_POST_EXPOSURE_DIAGNOSTIC_NO_REFIT',parameters=params,issues=r['issues'],
   cutoffs=r['cutoffs'],plan_hashes=files,implementation=closure,
   source_hashes={str(source/'plans-frozen.json'):hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest(),**r['plan_hashes']})
  (out/'freeze-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable result required')
  frozen=json.loads((out/'freeze-receipt.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  accepted=json.loads((source/'results.json').read_text());verify_clean_file_bindings(accepted['source_hashes'],repository_root=root)
  audit_path=Path(json.loads((source/'plans-frozen.json').read_text())['receipt']['expert_source'])/'settlement-audit.json'
  assert str(audit_path) in accepted['source_hashes']
  audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);rows=[]
  for issue in r['issues']:
   bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
   rows.extend(settle_compression_variants(bundle,audit[audit.issue==issue]));print('SETTLED',issue,flush=True)
  assert len(rows)==288
  body=dict(rows=rows,upstream_freeze_seal=frozen['seal'],scope='PURE_BASELINE_FIXED_GROUP_SUPPORT_COMPARISON')
  (out/'results.json').write_text(json.dumps(body,indent=2))
  report_files=['quarto/78_repeated_support_variants.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R']
  receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],
   result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest(),implementation=r['implementation'],
   source_hashes={**r['source_hashes'],**r['plan_hashes'],str(audit_path):hashlib.sha256(audit_path.read_bytes()).hexdigest()},
   report_files={q:hashlib.sha256(Path(q).read_bytes()).hexdigest() for q in report_files},parameters=r['parameters'])
  canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'))
  (out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest()),indent=2))
