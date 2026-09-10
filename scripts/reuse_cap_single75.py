"""Apply the existing fixed 75% single gate to six frozen cap plans, then settle."""
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
 p.add_argument('--source',default='data/derived/fundamentals_417/reuse-cap-grid-v1');a=p.parse_args()
 out=Path(a.study);source=Path(a.source);root=Path.cwd()
 if a.phase=='freeze':
  if out.exists():raise FileExistsError('New immutable study required')
  prior=json.loads((source/'freeze-receipt.json').read_text());r=prior['receipt'];assert stable_json_hash(r)==prior['seal']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  caps=[(16,6),(2,2),(1,0),(2,4),(6,4),(6,5)]
  params=dict(caps=caps,single_ceiling=.75,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05,change_singles=True,double_rule='NONE')
  closure=implementation_closure(root,['scripts.reuse_cap_single75'],distributions=['pandas'])
  (out/'plans').mkdir(parents=True);files={}
  for issue in r['issues']:
   old=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()));bundle={}
   for uses,pair in caps:
    case=f'U{uses}_P{pair}';base=old[case+'_CAPPED']['plan']
    cuts={str(s):Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
    changed=replace_repeated_support(base,cutoffs=cuts,**{k:v for k,v in params.items() if k!='caps'})
    for key in ['groups','stake','cash_cny','budget_cny','cutoffs','group_units','max_uses','max_pair_overlap']:
     assert base[key]==changed[key]
    if uses==1:assert changed['legs']==base['legs'] and changed['tickets']==base['tickets']
    for rule,plan in [('BASE',base),('SINGLE75',changed)]:
     bundle[case+'_'+rule]=dict(case=case,rule=rule,depth=2,quality='TOP2',overlap='CAPPED',plan=plan,evaluation=dict(metrics={}))
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0))
   files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,12,flush=True)
  verify_implementation_closure(root,closure)
  receipt=dict(scope='FIXED_CAP_SINGLE75_EXPOSED_DIAGNOSTIC_NO_REFIT',parameters=params,issues=r['issues'],
   source=str(source),source_hashes={str(source/'freeze-receipt.json'):hashlib.sha256((source/'freeze-receipt.json').read_bytes()).hexdigest(),
    str(source/'plans-frozen.json'):hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest(),**r['plan_hashes']},
   plan_hashes=files,implementation=closure)
  (out/'freeze-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable result required')
  frozen=json.loads((out/'freeze-receipt.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
  assert str(source)==r['source']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  old=json.loads((source/'plans-frozen.json').read_text());assert hashlib.sha256(old['canonical_json'].encode()).hexdigest()==old['seal']
  accepted=json.loads(old['canonical_json']);verify_clean_file_bindings(accepted['source_hashes'],repository_root=root)
  assert hashlib.sha256((source/'results.json').read_bytes()).hexdigest()==accepted['result_sha256']
  originals={(z['issue'],z['policy']):z for z in json.loads((source/'results.json').read_text())['rows']}
  audit_paths=[k for k in accepted['source_hashes'] if k.endswith('settlement-audit.json')];assert len(audit_paths)==1
  audit_path=Path(audit_paths[0]);audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);rows=[]
  for issue in r['issues']:
   bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
   observed=settle_compression_variants(bundle,audit[audit.issue==issue])
   for z in observed:
    plan=bundle[z['policy']]['plan'];z.update(max_uses=plan['max_uses'],max_pair_overlap=plan['max_pair_overlap'])
    if z['rule']=='BASE':
     expected=originals[issue,z['case']+'_CAPPED']
     for key in ['stake','net','gross','hits','groups']:assert z[key]==expected[key]
   rows.extend(observed);print('SETTLED',issue,flush=True)
  assert len(rows)==576
  result=dict(rows=rows,upstream_freeze_seal=frozen['seal'],scope=r['scope'])
  (out/'results.json').write_text(json.dumps(result,indent=2))
  report_files=['quarto/82_reuse_cap_single75.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R',
   'r/fundamentals_integration_weight.R','r/fundamentals_compression_bridge.R','r/fundamentals_repeated_double.R']
  receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],parameters=r['parameters'],
   result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest(),implementation=r['implementation'],
   source_hashes={**r['source_hashes'],**r['plan_hashes'],str(audit_path):hashlib.sha256(audit_path.read_bytes()).hexdigest(),str(source/'results.json'):accepted['result_sha256']},
   report_files={q:hashlib.sha256(Path(q).read_bytes()).hexdigest() for q in report_files})
  canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'))
  (out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest()),indent=2))
