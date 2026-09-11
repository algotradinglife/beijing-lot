"""Fixed C1/C2 single75 comparison from inventoried frozen historical plans."""
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
 p.add_argument('--source',default='data/derived/fundamentals_417/new48-pure-baseline-v1')
 p.add_argument('--positive-control',default='data/derived/fundamentals_417/repeated-support-v2');a=p.parse_args()
 out=Path(a.study);source=Path(a.source);control=Path(a.positive_control);root=Path.cwd()
 if a.phase=='freeze':
  if out.exists():raise FileExistsError('New immutable study required')
  old=json.loads((source/'plans-frozen.json').read_text());r=old['receipt'];assert stable_json_hash(r)==old['seal']
  verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  positive=json.loads((control/'freeze-receipt.json').read_text());pr=positive['receipt'];assert stable_json_hash(pr)==positive['seal']
  verify_clean_file_bindings(pr['plan_hashes'],repository_root=root)
  params=dict(depths=[1,2],overlaps=['FREE','STRICT'],single_ceiling=.75,change_singles=True,double_rule='NONE',max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
  closure=implementation_closure(root,['scripts.single75_depth'],distributions=['pandas'])
  (out/'plans').mkdir(parents=True);files={}
  for issue in r['issues']:
   saved=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()));bundle={}
   prior=json.loads(gzip.decompress((control/'plans'/f'{issue}.json.gz').read_bytes()))
   for depth in params['depths']:
    for overlap in params['overlaps']:
     case=f'D{depth}_TOP2_{overlap}';base=saved[case+'_BASE']['plan']
     cuts={str(s):Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
     transformed=replace_repeated_support(base,cutoffs=cuts,**{k:v for k,v in params.items() if k not in ['depths','overlaps']})
     for key in ['groups','stake','cash_cny','budget_cny','cutoffs','group_units','single_count']:assert base[key]==transformed[key]
     if depth==2 and overlap=='FREE':assert transformed==prior['D2_TOP2_FREE_SINGLE']['plan']
     for rule,plan in [('BASE',base),('SINGLE75',transformed)]:
      bundle[case+'_'+rule]=dict(case=case,rule=rule,depth=depth,quality='TOP2',overlap=overlap,plan=plan,evaluation=dict(metrics={}))
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0))
   files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,8,flush=True)
  verify_implementation_closure(root,closure)
  receipt=dict(scope='EXPOSED_FIXED_C1_C2_SINGLE75_NO_REFIT',issues=r['issues'],parameters=params,source=str(source),
   positive_control=str(control),plan_hashes=files,implementation=closure,
   source_hashes={**r['plan_hashes'],**pr['plan_hashes'],str(source/'plans-frozen.json'):hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest(),
    str(control/'freeze-receipt.json'):hashlib.sha256((control/'freeze-receipt.json').read_bytes()).hexdigest()},
   legacy_evidence='Pre-rule exposed frozen plans; original implementation commits required for original full replay; no causal availability promotion')
  (out/'freeze-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable results required')
  saved=json.loads((out/'freeze-receipt.json').read_text());r=saved['receipt'];assert stable_json_hash(r)==saved['seal']
  assert str(source)==r['source'] and str(control)==r['positive_control']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  accepted=json.loads((source/'results.json').read_text());verify_clean_file_bindings(accepted['source_hashes'],repository_root=root)
  audit_path=Path(json.loads((source/'plans-frozen.json').read_text())['receipt']['expert_source'])/'settlement-audit.json'
  assert str(audit_path) in accepted['source_hashes'];audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);rows=[]
  for issue in r['issues']:
   bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
   rows.extend(settle_compression_variants(bundle,audit[audit.issue==issue]));print('SETTLED',issue,flush=True)
  assert len(rows)==384
  result=dict(rows=rows,upstream_freeze_seal=saved['seal'],scope=r['scope']);(out/'results.json').write_text(json.dumps(result,indent=2))
  reports=['quarto/84_single75_depth.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R','r/fundamentals_drawdown_plot.R',
   'r/fundamentals_integration_weight.R','r/fundamentals_compression_bridge.R','r/fundamentals_repeated_double.R']
  receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=saved['seal'],parameters=r['parameters'],
   result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest(),implementation=r['implementation'],
   source_hashes={**r['source_hashes'],**r['plan_hashes'],str(audit_path):hashlib.sha256(audit_path.read_bytes()).hexdigest()},
   report_files={q:hashlib.sha256(Path(q).read_bytes()).hexdigest() for q in reports})
  canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'))
  (out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest()),indent=2))
