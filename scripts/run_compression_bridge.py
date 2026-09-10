"""Freeze a fixed factorial bridge before reading the existing settlement audit."""
import argparse,gzip,hashlib,itertools,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan,bind_bridge_reference
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios,breadth_metrics,settle_breadth_bundle
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--old',required=True);p.add_argument('--recent',required=True);p.add_argument('--output',required=True);a=p.parse_args();old=Path(a.old);recent=Path(a.recent);out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable new study directory required')
 prior=json.loads((old/'plans-frozen.json').read_text());new=json.loads((recent/'plans-frozen.json').read_text())
 assert stable_json_hash(prior['receipt'])==prior['seal'] and stable_json_hash(new['receipt'])==new['seal']
 sources=dict(prior['receipt']['source_hashes']);input_path=next(k for k in sources if k.endswith('/inputs.json'))
 for path,h in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(input_path).read_text());frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 contract=dict(scope='EXPOSED_40_ISSUE_FACTORIAL_BRIDGE_NOT_CAUSAL_ACCEPTANCE',depths=[1,2],prefix=[True,False],quality=['TOP2','COMPRESSED'],overlap=['STRICT','FREE'],cash=['HOLD','REPEAT_BEST'],pool='PRIOR512_UNION_OLD_DEPTH1_AND2_GROUPS',candidate_seed=41900,design_seed=41901,evaluation_seed=41902,design_draws=1024,evaluation_draws=8192,budget='SAME_55040_ALLOCATION_CASH_EXPLICIT',unit_cny=2,payout_factor=.65,initial_capital_cny=100000,learning='NONE',draw_version='1.1.0',draw_weight=.5,high_weight=.5)
 closure=implementation_closure(Path.cwd(),['src.fundamentals_compression_bridge','scripts.run_compression_bridge'],distributions=['numpy','pandas','scipy','scikit-learn'])
 out.mkdir(parents=True);(out/'plans').mkdir();(out/'surfaces').mkdir();plan_hashes={};surface_hashes={}
 for issue,f in frame.groupby('issue',sort=True):
  cuts={str(s):Cutoff.decision_epoch(issue,inputs['cutoffs'][issue][str(s)]) for s in f.slot};refs={}
  for depth in (1,2):
   path=old/'plans'/f'{issue}-SINGLE_{depth}.json';raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==prior['receipt']['plan_hashes'][str(path)];sources[str(path)]=hashlib.sha256(raw).hexdigest();refs[depth]=json.loads(raw)
  path=recent/'plans'/f'{issue}.json.gz';raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==new['receipt']['plan_hashes'][str(path)];sources[str(path)]=hashlib.sha256(raw).hexdigest();recent_plans=json.loads(gzip.decompress(raw))
  pool=breadth_candidates(f,cutoffs=cuts,seed=41900,pool_size=512);bundle={};surfaces={}
  for depth in (1,2):
   surface=bridge_surface(f,pool,refs,cutoffs=cuts,depth=depth);design=breadth_scenarios(f,surface,cutoffs=cuts,seed=41901,draws=1024);evaluation=breadth_scenarios(f,surface,cutoffs=cuts,seed=41902,draws=8192)
   surfaces[str(depth)]=dict(surface=surface,design={k:v for k,v in design.items() if k!='hits'},evaluation={k:v for k,v in evaluation.items() if k!='hits'})
   original=bind_bridge_reference(refs[depth],surface,design,cutoffs=cuts);bundle[f'D{depth}_OLD']=dict(plan=original,metrics=breadth_metrics(original,evaluation,cutoffs=cuts),kind='OLD',depth=depth)
   previous=recent_plans[f'D{depth}_TOP1_QUALITY_C0_B0'];bundle[f'D{depth}_RECENT']=dict(plan=previous['plan'],metrics=previous['metrics'],kind='RECENT',depth=depth)
   for prefix,quality,cap,cash in itertools.product([True,False],['TOP2','COMPRESSED'],['STRICT','FREE'],['HOLD','REPEAT_BEST']):
    policy=f'D{depth}_P{int(prefix)}_{quality}_{cap}_{cash}'
    plan=bridge_plan(f,surface,design,refs[depth],cutoffs=cuts,preserve_prefix=prefix,quality=quality,overlap=cap,cash_policy=cash,budget_cny=refs[depth]['budget_cny'],unit_cny=2,payout_factor=.65)
    bundle[policy]=dict(plan=plan,metrics=breadth_metrics(plan,evaluation,cutoffs=cuts),kind='FACTORIAL',depth=depth)
  assert len(bundle)==36
  for folder,obj,hashes in [('plans',bundle,plan_hashes),('surfaces',surfaces,surface_hashes)]:
   path=out/folder/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(obj,separators=(',',':')).encode(),mtime=0));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  print('FROZEN',issue,flush=True)
 receipt=dict(contract=contract,cutoffs=inputs['cutoffs'],source_hashes=sources,plan_hashes=plan_hashes,surface_hashes=surface_hashes,implementation=closure,old_seal=prior['seal'],recent_seal=new['seal'])
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 # All choices and model diagnostics frozen above; labels are opened only here.
 old_results=json.loads((old/'results.json').read_text());recent_results=json.loads((recent/'results.json').read_text());audit_hashes=old_results['audit_hashes'];assert audit_hashes==recent_results['audit_hashes'];audits=[]
 for path,h in audit_hashes.items():
  raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==h;audits.extend(json.loads(raw))
 old_rows={(r['issue'],r['policy']):r for r in old_results['rows']};recent_rows={(r['issue'],r['policy']):r for r in recent_results['rows']};audit=pd.DataFrame(audits);results=[]
 for issue in sorted(frame.issue.unique()):
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));settled=settle_breadth_bundle(bundle,audit[audit.issue==issue]);partition='TEST8' if issue in inputs['contract']['test_issues'] else 'VALIDATION8' if issue in inputs['contract']['validation_issues'] else 'TRAINING24'
  for policy,entry in bundle.items():
   plan=entry['plan'];r=settled[policy];assert r['status']=='COMPLETE';depth=entry['depth']
   if entry['kind'] in ('OLD','RECENT'):
    original=old_rows[issue,f'SINGLE_{depth}'] if entry['kind']=='OLD' else recent_rows[issue,f'D{depth}_TOP1_QUALITY_C0_B0']
    assert all(abs(r[k]-original[k])<1e-7 for k in ['stake','gross','net','hits'])
   r.update(policy=policy,partition=partition,depth=depth,kind=entry['kind'],budget_cny=plan['budget_cny'],cash_cny=plan['cash_cny'],budget_return=r['net']/plan['budget_cny'],unique_tickets=plan['unique_tickets'],paid_ticket_units=plan['paid_ticket_units'],repeat_units=plan['repeat_units'],**entry['metrics'],**plan.get('factors',dict(preserve_prefix=None,quality=None,overlap=None,cash_policy=None)))
   results.append(r)
  print('SETTLED',issue,flush=True)
 verify_implementation_closure(Path.cwd(),closure)
 for path,h in {**sources,**plan_hashes,**surface_hashes,**audit_hashes}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 (out/'results.json').write_text(json.dumps(dict(rows=results,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(receipt)),indent=2));print('COMPLETE',len(results),flush=True)
