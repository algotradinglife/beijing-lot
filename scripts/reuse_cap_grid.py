"""Fixed cap grid on the exposed pure-baseline cohort, frozen before settlement."""
import argparse,gzip,hashlib,itertools,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios,settle_breadth_bundle
from src.fundamentals_decision_chain import limit_decision_chain_plan

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True)
 p.add_argument('--source',default='data/derived/fundamentals_417/new48-pure-baseline-v1');a=p.parse_args()
 out=Path(a.study);source=Path(a.source);root=Path.cwd()
 if a.phase=='freeze':
  if out.exists():raise FileExistsError('New immutable study required')
  original=json.loads((source/'plans-frozen.json').read_text());r=original['receipt'];assert original['seal']==stable_json_hash(r)
  verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  factors=json.loads((source/'factors.json').read_text());f=pd.DataFrame(factors['rows'])
  assert factors['scope']=='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC'
  caps=[(1,0)]+list(itertools.product([2,3,4,6,8,16],range(1,7)))
  params=dict(caps=caps,n=7,single_count=2,budget_cny=1024,unit_cny=2,payout_factor=.65,
   candidate_seed=41900,pool_size=512,design_seed=41901,design_draws=1024)
  closure=implementation_closure(root,['scripts.reuse_cap_grid'],distributions=['numpy','pandas','scipy'])
  (out/'plans').mkdir(parents=True);files={}
  for issue in sorted(f.issue.unique()):
   frame=f[f.issue==issue];cuts={str(s):Cutoff.decision_epoch(issue,factors['cutoffs'][issue][str(s)]) for s in frame.slot}
   refs={d:n7_single_plan(frame,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in [1,2]}
   pool=breadth_candidates(frame,cutoffs=cuts,seed=41900,pool_size=512)
   surface=bridge_surface(frame,pool,refs,cutoffs=cuts,depth=2)
   design=breadth_scenarios(frame,surface,cutoffs=cuts,seed=41901,draws=1024)
   kw=dict(cutoffs=cuts,preserve_prefix=True,quality='TOP2',cash_policy='HOLD',budget_cny=1024,unit_cny=2,payout_factor=.65)
   free=bridge_plan(frame,surface,design,refs[2],overlap='FREE',**kw)
   old=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))
   assert free==old['D2_TOP2_FREE_BASE']['plan']
   bundle={}
   for uses,pair in caps:
    key=f'U{uses}_P{pair}';plan=bridge_plan(frame,surface,design,refs[2],overlap='CAPPED',max_uses=uses,max_pair_overlap=pair,**kw)
    if (uses,pair)==(2,2):
     for k in ['legs','tickets','stake','cash_cny']:assert plan[k]==old['D2_TOP2_STRICT_BASE']['plan'][k]
    if (uses,pair)==(16,6):
     for k in ['legs','tickets','stake','cash_cny']:assert plan[k]==free[k]
    matched=limit_decision_chain_plan(free,groups=plan['groups'],cutoffs=cuts)
    # Reconcile descriptive metadata after the authoritative ticket limiter.
    matched.pop('seal');k=matched['groups'];matched['cash_cny']=1024-matched['stake']
    for field in ['group_units','group_probability','selected_candidates']:matched[field]=matched[field][:k]
    matched['contraction_ledger']=[z for z in matched['contraction_ledger'] if z['group']<=k]
    matched.update(unique_tickets=len(matched['tickets']),paid_ticket_units=sum(t['units'] for t in matched['tickets']),
     repeat_units=0,overlap_groups=k-matched['disjoint_groups'],max_uses=16,max_pair_overlap=6)
    matched.pop('model_proxy_gross',None);matched['seal']=stable_json_hash(matched)
    for kind,chosen in [('CAPPED',plan),('MATCHED_STAKE',matched)]:
     bundle[key+'_'+kind]=dict(plan=chosen,max_uses=uses,max_pair_overlap=pair,kind=kind)
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0))
   files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,74,flush=True)
  verify_implementation_closure(root,closure)
  receipt=dict(scope='EXPOSED_FIXED_CAP_GRID_NO_RULE_PROMOTION',parameters=params,issues=sorted(f.issue.unique()),
   source_hashes={str(source/'factors.json'):hashlib.sha256((source/'factors.json').read_bytes()).hexdigest(),
    str(source/'plans-frozen.json'):hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest(),**r['plan_hashes']},
   plan_hashes=files,implementation=closure,legacy_source_model=r['model'])
  (out/'freeze-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable results required')
  frozen=json.loads((out/'freeze-receipt.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
  accepted=json.loads((source/'results.json').read_text());verify_clean_file_bindings(accepted['source_hashes'],repository_root=root)
  audit_path=Path(json.loads((source/'plans-frozen.json').read_text())['receipt']['expert_source'])/'settlement-audit.json'
  assert str(audit_path) in accepted['source_hashes'];audit=pd.DataFrame(json.loads(audit_path.read_text())['rows'])
  assert audit.status.eq('READY').all() and not audit.duplicated(['issue','slot','provider_id']).any()
  rows=[]
  for issue in r['issues']:
   bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
   for policy,row in settle_breadth_bundle(bundle,audit[audit.issue==issue]).items():
    assert row['status']=='COMPLETE';e=bundle[policy];plan=e['plan']
    rows.append(dict(row,policy=policy,max_uses=e['max_uses'],max_pair_overlap=e['max_pair_overlap'],kind=e['kind'],
     budget_cny=1024,cash_cny=1024-row['stake']))
   print('SETTLED',issue,flush=True)
  assert len(rows)==3552
  result=dict(rows=rows,upstream_freeze_seal=frozen['seal'],scope=r['scope'])
  (out/'results.json').write_text(json.dumps(result,indent=2))
  report_files=['quarto/80_reuse_cap_grid.qmd','r/fundamentals_reuse_caps.R','r/fundamentals_equity_curves.R','r/fundamentals_pure_report.R']
  receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],parameters=r['parameters'],
   result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest(),implementation=r['implementation'],
   source_hashes={**r['source_hashes'],**r['plan_hashes'],str(audit_path):hashlib.sha256(audit_path.read_bytes()).hexdigest()},
   report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in report_files})
  canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'))
  (out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest()),indent=2))
