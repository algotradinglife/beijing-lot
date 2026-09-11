"""Two independent shards; seal the entire exposed cohort before settlement."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_complement import complementary_sources,complement_catalog,allocate_complement,settle_complements

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['init','freeze','seal','settle','report']);p.add_argument('--study',required=True)
 p.add_argument('--source',default='data/derived/fundamentals_417/cap-depth-grid-v1');p.add_argument('--shard',type=int,choices=[0,1]);a=p.parse_args()
 out=Path(a.study);source=Path(a.source);root=Path.cwd()
 if a.phase=='init':
  if out.exists():raise FileExistsError('New immutable directory required')
  prior=json.loads((source/'freeze-receipt.json').read_text());r=prior['receipt'];assert stable_json_hash(r)==prior['seal']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings(r['plan_hashes'],repository_root=root)
  factors=Path(r['source'])/'factors.json';verify_clean_file_bindings({str(factors):r['source_hashes'][str(factors)]},repository_root=root)
  params=dict(main='D2_U6_P5_BASE',main_wallets=[0,512,768],budget_cny=1024,unit_cny=2,payout_factor=.65,
   candidate_seeds=[41910,41911,41912],random_seeds=[41910,41911,41912],quality_pool_size=64,
   base_candidate_seed=41900,pool_size=512,design_seed=41901,design_draws=1024,shards=2)
  closure=implementation_closure(root,['scripts.complement_grid'],distributions=['numpy','pandas','scipy'])
  receipt=dict(scope='EXPOSED_FIXED_COMPLEMENT_GRID_NO_FIT_OR_PROMOTION',parameters=params,issues=r['issues'],source=str(source),factors=str(factors),
   source_hashes={**r['plan_hashes'],str(factors):r['source_hashes'][str(factors)],str(source/'freeze-receipt.json'):hashlib.sha256((source/'freeze-receipt.json').read_bytes()).hexdigest(),
    str(source/'plans-frozen.json'):hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest()},implementation=closure)
  (out/'plans').mkdir(parents=True);(out/'contract.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
  print('INITIALIZED',len(r['issues']),'issues; fixed155sources/466portfolios each')
 else:
  saved=json.loads((out/'contract.json').read_text());r=saved['receipt'];assert stable_json_hash(r)==saved['seal'] and str(source)==r['source'];params=r['parameters']
  verify_implementation_closure(root,r['implementation']);verify_clean_file_bindings(r['source_hashes'],repository_root=root)
  if a.phase=='freeze':
   assert a.shard is not None
   marker=out/f'freeze-shard-{a.shard}.json'
   if marker.exists():raise FileExistsError('Frozen shard exists')
   data=json.loads(Path(r['factors']).read_text());f=pd.DataFrame(data['rows']);hashes={}
   for issue in r['issues'][a.shard::2]:
    path=out/'plans'/f'{issue}.json.gz'
    if path.exists():raise FileExistsError(path)
    frame=f[f.issue==issue];cuts={str(s):Cutoff.decision_epoch(issue,data['cutoffs'][issue][str(s)]) for s in frame.slot}
    original=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()));sources={k:v['plan'] for k,v in original.items()}
    sources.update(complementary_sources(frame,cutoffs=cuts,**{k:v for k,v in params.items() if k not in ['main','main_wallets','shards']}))
    assert len(sources)==155
    catalog=complement_catalog(sources,cutoffs=cuts,unit_cny=2,payout_factor=.65);recipes={}
    for alternative in sources:
     for wallet in params['main_wallets']:
      name=('ONLY' if wallet==0 else f'M{wallet}')+'__'+alternative
      recipes[name]=allocate_complement(catalog,cutoffs=cuts,main=params['main'],alternative=alternative,main_budget_cny=wallet,budget_cny=1024)
    recipes['MAIN']=allocate_complement(catalog,cutoffs=cuts,main=params['main'],alternative=params['main'],main_budget_cny=1024,budget_cny=1024)
    assert len(recipes)==466
    path.write_bytes(gzip.compress(json.dumps(dict(catalog=catalog,recipes=recipes),separators=(',',':')).encode(),mtime=0))
    hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,len(catalog['components']),flush=True)
   verify_implementation_closure(root,r['implementation']);marker.write_text(json.dumps(dict(hashes=hashes,contract_seal=saved['seal'])))
  elif a.phase=='seal':
   if (out/'freeze-receipt.json').exists():raise FileExistsError('Cohort already frozen')
   hashes={}
   for shard in range(2):
    cell=json.loads((out/f'freeze-shard-{shard}.json').read_text());assert cell['contract_seal']==saved['seal']
    assert {Path(k).name for k in cell['hashes']}=={f'{issue}.json.gz' for issue in r['issues'][shard::2]}
    assert not (hashes.keys() & cell['hashes'].keys());hashes.update(cell['hashes'])
   verify_clean_file_bindings(hashes,repository_root=root)
   receipt=dict(**r,plan_hashes=hashes,contract_seal=saved['seal']);(out/'freeze-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
   print('SEALED ALL48 BEFORE SETTLEMENT')
  elif a.phase=='settle':
   assert a.shard is not None
   target=out/f'rows-shard-{a.shard}.json'
   if target.exists():raise FileExistsError('Settled shard exists')
   frozen=json.loads((out/'freeze-receipt.json').read_text());fr=frozen['receipt'];assert stable_json_hash(fr)==frozen['seal']
   verify_clean_file_bindings(fr['plan_hashes'],repository_root=root)
   prior=json.loads((source/'plans-frozen.json').read_text());pr=json.loads(prior['canonical_json'])
   assert hashlib.sha256(prior['canonical_json'].encode()).hexdigest()==prior['seal']
   paths=[x for x in pr['source_hashes'] if x.endswith('settlement-audit.json')];assert len(paths)==1;audit_path=paths[0]
   verify_clean_file_bindings({audit_path:pr['source_hashes'][audit_path]},repository_root=root)
   audit=pd.DataFrame(json.loads(Path(audit_path).read_text())['rows']);rows=[]
   for issue in r['issues'][a.shard::2]:
    bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
    rows.extend(settle_complements(bundle['catalog'],bundle['recipes'],audit[audit.issue==issue]));print('SETTLED',issue,flush=True)
   target.write_text(json.dumps(dict(rows=rows,freeze_seal=frozen['seal'],audit_hashes={audit_path:pr['source_hashes'][audit_path]}),indent=2))
  else:
   if (out/'results.json').exists():raise FileExistsError('Immutable report required')
   frozen=json.loads((out/'freeze-receipt.json').read_text());fr=frozen['receipt'];assert stable_json_hash(fr)==frozen['seal']
   verify_clean_file_bindings(fr['plan_hashes'],repository_root=root);rows=[];audit_hashes=None
   for shard in range(2):
    cell=json.loads((out/f'rows-shard-{shard}.json').read_text());assert cell['freeze_seal']==frozen['seal']
    assert {z['issue'] for z in cell['rows']}==set(r['issues'][shard::2])
    if audit_hashes is None:audit_hashes=cell['audit_hashes']
    assert audit_hashes==cell['audit_hashes'];rows.extend(cell['rows'])
   assert len(rows)==22368 and len({(z['issue'],z['policy']) for z in rows})==22368
   verify_clean_file_bindings(audit_hashes,repository_root=root)
   result=dict(rows=rows,scope=r['scope'],upstream_freeze_seal=frozen['seal']);(out/'results.json').write_text(json.dumps(result,indent=2))
   reports=['quarto/87_complement_portfolios.qmd','r/fundamentals_complement.R','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R','r/fundamentals_drawdown_plot.R']
   receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',parameters=params,plan_freeze_seal=frozen['seal'],implementation=r['implementation'],
    result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest(),source_hashes={**r['source_hashes'],**fr['plan_hashes'],**audit_hashes},
    report_files={q:hashlib.sha256(Path(q).read_bytes()).hexdigest() for q in reports})
   canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest()),indent=2))
   print('REPORT22368 ROWS')
