"""Fixed30-cell exposed diagnostic, two freeze shards then cohort settlement."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_market_blend import blend_market_scores
from src.fundamentals_single_guard import guard_single_positions
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios,settle_breadth_bundle
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_n7_single import n7_single_plan

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['init','freeze','seal','settle']);p.add_argument('--study',required=True);p.add_argument('--shard',type=int,choices=[0,1]);a=p.parse_args();out=Path(a.study)
 pure=Path('data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json');old=Path('data/derived/fundamentals_417/cap-depth-grid-v1')
 if a.phase=='init':
  if out.exists():raise FileExistsError('New immutable study required')
  data=json.loads(pure.read_text());verify_clean_file_bindings(data['source_hashes'],repository_root=Path.cwd())
  prior=json.loads((old/'freeze-receipt.json').read_text());r=prior['receipt'];assert stable_json_hash(r)==prior['seal'];verify_clean_file_bindings(r['plan_hashes'],repository_root=Path.cwd())
  receipt=dict(scope='EXPOSED_FIXED30_NO_LEARNING_OR_PROMOTION',issues=r['issues'],projected_source=data['expert_source'],
   parameters=dict(weights=[0,.25,.5,.75,1],protect=[False,True],caps=[None,2,3],minimum_tv=.15,minimum_handicap=2,
    seed=41900,pool_size=512,design_seed=41901,design_draws=1024,max_uses=6,max_pair_overlap=5,budget_cny=1024,unit_cny=2,payout_factor=.65),
   source_hashes={**data['source_hashes'],**r['plan_hashes'],str(pure):hashlib.sha256(pure.read_bytes()).hexdigest()},
   implementation=implementation_closure(Path.cwd(),['scripts.n7_hit_improvement'],distributions=['numpy','pandas','scipy']))
  (out/'plans').mkdir(parents=True);(out/'contract.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));print('INITIALIZED30 fixed rules x48 issues')
 else:
  contract=json.loads((out/'contract.json').read_text());r=contract['receipt'];assert stable_json_hash(r)==contract['seal'];params=r['parameters']
  verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings(r['source_hashes'],repository_root=Path.cwd())
  if a.phase=='freeze':
   assert a.shard is not None
   marker=out/f'freeze-{a.shard}.json'
   if marker.exists():raise FileExistsError('Shard frozen')
   data=json.loads(pure.read_text());original=pd.DataFrame(data['rows']);hashes={}
   for issue in r['issues'][a.shard::2]:
    target=out/'plans'/f'{issue}.json.gz'
    if target.exists():raise FileExistsError(target)
    f=original[original.issue==issue].copy();cuts={str(s):Cutoff.decision_epoch(issue,data['cutoffs'][issue][str(s)]) for s in f.slot}
    x=json.loads((Path(r['projected_source'])/'projected'/f'{issue}.json').read_text())
    prior=json.loads(gzip.decompress((old/'plans'/f'{issue}.json.gz').read_bytes()))['D2_U6_P5_BASE']['plan']
    bundles={};events=[]
    for w in params['weights']:
     blended=blend_market_scores(x['control'],x['market'],cutoffs=cuts,market_weight=w,minimum_handicap=2)
     b=pd.DataFrame(blended['rows']).set_index('slot').loc[f.slot]
     assert np.allclose(b[['q_W','q_D','q_L']],f[['q_W','q_D','q_L']],atol=1e-12,rtol=0)
     current=f.copy()
     if w==0:
      assert np.allclose(b[['p_W','p_D','p_L']],f[['p_W','p_D','p_L']],atol=1e-12,rtol=0);source=prior
     else:
      current[['p_W','p_D','p_L']]=b[['p_W','p_D','p_L']].to_numpy()
      refs={d:n7_single_plan(current,cutoffs=cuts,budget_cny=1024,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in [1,2]}
      pool=breadth_candidates(current,cutoffs=cuts,seed=41900,pool_size=512)
      surface=bridge_surface(current,pool,refs,cutoffs=cuts,depth=2);design=breadth_scenarios(current,surface,cutoffs=cuts,seed=41901,draws=1024)
      source=bridge_plan(current,surface,design,refs[2],cutoffs=cuts,preserve_prefix=True,quality='TOP2',overlap='CAPPED',cash_policy='HOLD',budget_cny=1024,unit_cny=2,payout_factor=.65,max_uses=6,max_pair_overlap=5)
     for protect in params['protect']:
      for cap in params['caps']:
       name=f'W{int(w*100):03}_P{int(protect)}_C{cap or 0}'
       guarded=guard_single_positions(source,cutoffs=cuts,protect_conflict=protect,minimum_tv=.15,single_cap=cap)
       if w==0 and not protect and cap is None:assert guarded['tickets']==prior['tickets'] and guarded['stake']==prior['stake']
       bundles[name]=dict(plan=guarded,weight=w,protect=protect,cap=cap,blend_seal=blended['seal'])
     events.extend(dict(e,weight=w) for e in blended['events'])
    target.write_bytes(gzip.compress(json.dumps(dict(bundles=bundles,events=events)).encode(),mtime=0));hashes[str(target)]=hashlib.sha256(target.read_bytes()).hexdigest();print('FROZEN',issue,flush=True)
   marker.write_text(json.dumps(dict(plan_hashes=hashes,contract_seal=contract['seal'])))
  elif a.phase=='seal':
   if (out/'frozen.json').exists():raise FileExistsError('Cohort already frozen')
   hashes={}
   for shard in [0,1]:
    cell=json.loads((out/f'freeze-{shard}.json').read_text());assert cell['contract_seal']==contract['seal']
    assert {Path(k).name for k in cell['plan_hashes']}=={f'{i}.json.gz' for i in r['issues'][shard::2]};hashes.update(cell['plan_hashes'])
   verify_clean_file_bindings(hashes,repository_root=Path.cwd());receipt=dict(**r,plan_hashes=hashes)
   (out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));print('SEALED1440 plans before settlement')
  else:
   if (out/'results.json').exists():raise FileExistsError('Immutable results')
   fr=json.loads((out/'frozen.json').read_text());assert stable_json_hash(fr['receipt'])==fr['seal'];verify_clean_file_bindings(fr['receipt']['plan_hashes'],repository_root=Path.cwd())
   saved=json.loads((old/'plans-frozen.json').read_text());assert hashlib.sha256(saved['canonical_json'].encode()).hexdigest()==saved['seal'];prior=json.loads(saved['canonical_json'])
   paths=[k for k in prior['source_hashes'] if k.endswith('settlement-audit.json')];assert len(paths)==1
   audit_hash={paths[0]:prior['source_hashes'][paths[0]]};verify_clean_file_bindings(audit_hash,repository_root=Path.cwd());audit=pd.DataFrame(json.loads(Path(paths[0]).read_text())['rows']);rows=[];events=[]
   for issue in r['issues']:
    z=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));settled=settle_breadth_bundle(z['bundles'],audit[audit.issue==issue]);events.extend(z['events'])
    for name,s in settled.items():
     assert s['status'] in ['COMPLETE','NO_BET'];entry=z['bundles'][name]
     rows.append(dict(policy=name,weight=entry['weight'],protect=entry['protect'],cap=entry['cap'],**s))
   (out/'results.json').write_text(json.dumps(dict(rows=rows,events=events,audit=audit.to_dict('records'),audit_hash=audit_hash,freeze_seal=fr['seal'])))
   print('SETTLED1440 plans')
