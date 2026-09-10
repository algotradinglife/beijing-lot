"""Freeze all pure-baseline variants, then settle against the accepted audit."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_expanded_comparison import read_verified_report_archive
from src.fundamentals_compression_variants import build_compression_variants,settle_compression_variants

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True)
 p.add_argument('--expert-archive',default='tests/fixtures/expanded_comparison_report.json.gz');a=p.parse_args()
 out=Path(a.study);root=Path.cwd();factors=json.loads((out/'factors.json').read_text());f=pd.DataFrame(factors['rows'])
 verify_clean_file_bindings({**factors['source_hashes'],**factors['implementation']},repository_root=root)
 assert factors['scope']=='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC'
 if a.phase=='freeze':
  if (out/'plans').exists():raise FileExistsError('Immutable new plans required')
  params=dict(n=7,budget_cny=1024,unit_cny=2,payout_factor=.65,candidate_seed=41900,design_seed=41901,
   evaluation_seed=41902,pool_size=512,design_draws=1024,evaluation_draws=8192,
   gap_rules=dict(GAP02=.02,GAP05=.05,GAP10=.10,ALL=1.),
   conflict_rules=dict(TAIL05=0.,TV10=.10,TV15=.15,TV20=.20),minimum_market_tail_lead=.05)
  closure=implementation_closure(root,['scripts.pure_baseline_variants'],distributions=['numpy','pandas','scipy','scikit-learn'])
  (out/'plans').mkdir();files={}
  for issue in sorted(f.issue.unique()):
   frame=f[f.issue==issue];cuts={str(s):Cutoff.decision_epoch(issue,factors['cutoffs'][issue][str(s)]) for s in frame.slot}
   bundle=build_compression_variants(frame,cutoffs=cuts,**params)
   assert len(bundle)==72
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0))
   files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,72,flush=True)
  verify_implementation_closure(root,closure)
  receipt=dict(scope=factors['scope'],model='PURE_RAW_SCORE_BASELINE_NO_EXPERTS',parameters=params,
   issues=sorted(f.issue.unique()),cutoffs=factors['cutoffs'],expert_source=factors['expert_source'],
   source_hashes={str(out/'factors.json'):hashlib.sha256((out/'factors.json').read_bytes()).hexdigest()},
   plan_hashes=files,implementation=closure)
  (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
  print('ALL_FROZEN',len(files),flush=True)
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable results required')
  frozen=json.loads((out/'plans-frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  source=Path(r['expert_source']);audit_path=source/'settlement-audit.json'
  source_result=json.loads((source/'results.json').read_text());assert source_result['audit_sha256']==hashlib.sha256(audit_path.read_bytes()).hexdigest()
  expert,expert_frozen=read_verified_report_archive(a.expert_archive)
  verify_clean_file_bindings(expert_frozen['receipt']['source_hashes'],repository_root=root)
  assert expert_frozen['receipt']['expert_versions']==dict(draw='1.1.0',high_margin='0.1.0')
  assert expert_frozen['receipt']['expert_weights']==dict(draw=.5,high_margin=.5)
  audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);rows=[]
  for issue in r['issues']:
   bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
   rows.extend(settle_compression_variants(bundle,audit[audit.issue==issue]));print('SETTLED',issue,flush=True)
  assert len(rows)==3456 and {(x['issue'],x['policy']) for x in rows}=={(x['issue'],x['policy']) for x in expert['rows']}
  paths=[str(audit_path),str(source/'results.json'),a.expert_archive]
  (out/'results.json').write_text(json.dumps(dict(rows=rows,before=expert['rows'],freeze_seal=frozen['seal'],
   comparison='PURE_AFTER_VS_EXPERT_BEFORE_SAME_INPUT_SNAPSHOT',
   source_hashes={q:hashlib.sha256(Path(q).read_bytes()).hexdigest() for q in paths}),indent=2))
