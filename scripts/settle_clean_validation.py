"""Open roster results and query R/SQLite only after all new-period plans freeze."""
import argparse,gzip,hashlib,itertools,json,subprocess,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_home_away import roster_observed_results
from src.fundamentals_compression_breadth import settle_breadth_bundle

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--db',required=True);a=p.parse_args();out=Path(a.study)
 if (out/'results.json').exists() or (out/'labels.json').exists():raise FileExistsError('Immutable new settlement required')
 frozen=json.loads((out/'plans-frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
 verify_implementation_closure(Path.cwd(),r['implementation'])
 for path,h in {**r['source_hashes'],**r['plan_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 factors=json.loads((out/'factors.json').read_text());frame=pd.DataFrame(factors['rows']);labels=[]
 for issue in r['contract']['issues']:
  f=frame[frame.issue==issue]
  if f.empty:continue
  data=json.loads(gzip.decompress((out/'inputs'/f'{issue}.json.gz').read_bytes()))
  observed=roster_observed_results(data['roster_path'],issue=issue,slots=list(map(int,f.slot)))
  by={z['slot']:z for z in observed}
  for z in f.to_dict('records'):
   o=by[z['slot']];assert o['provider_id']==z['provider_id']
   labels.append(dict(**{k:z[k] for k in ['issue','slot','provider_id','handicap','home','away']},**{k:o[k] for k in ['actual_home','actual_away','result_state']}))
 (out/'labels.json').write_text(json.dumps(labels))
 subprocess.run(['Rscript','--vanilla','scripts/query_clean_validation.R',str(out),a.db],check=True)
 saved=json.loads((out/'settlement-audit.json').read_text());audit=pd.DataFrame(saved['rows']);results=[]
 for issue in r['contract']['issues']:
  if issue in r['no_bet']:
   for depth,quality,overlap,rule in itertools.product([1,2],['TOP2','COMPRESSED'],['STRICT','FREE'],['BASE','GAP02','GAP05','GAP10','ALL']):
    case=f'D{depth}_{quality}_{overlap}'
    results.append(dict(issue=issue,policy=case+'_'+rule,case=case,rule=rule,depth=depth,quality=quality,overlap=overlap,status='NO_BET',
     stake=0,cash_cny=1024,budget_cny=1024,gross=0,net=0,roi=None,hits=0,groups=0,model_union=0,fixture_hhi=0,repeat_units=0,
     changed_legs=0,gained_groups=0,lost_groups=0,mean_group_probability=0,partition='NEW48',budget_return=0))
   continue
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));observed=audit[audit.issue==issue];settled=settle_breadth_bundle(bundle,observed);lookup=observed.set_index(['slot','provider_id']);won={}
  for policy,entry in bundle.items():
   plan=entry['plan'];hits=[]
   for g in range(1,plan['groups']+1):
    legs=[l for l in plan['legs'] if l['group']==g];rows=[lookup.loc[l['slot'],l['provider_id']] for l in legs]
    hits.append(None if any(z.status.startswith('spf:IDENTITY') or z.actual_direction not in ['W','D','L'] for z in rows) else all(dict(W='3',D='1',L='0')[z.actual_direction] in l['support'] for l,z in zip(legs,rows)))
   won[policy]=hits
  for policy,entry in bundle.items():
   plan=entry['plan'];row=settled[policy];control=won[entry['case']+'_BASE'];actual=won[policy];known=all(x is not None for x in actual+control)
   row.update(policy=policy,case=entry['case'],rule=entry['rule'],depth=entry['depth'],quality=entry['quality'],overlap=entry['overlap'],partition='NEW48',
    budget_cny=1024,cash_cny=plan['cash_cny'],budget_return=row['net']/1024 if row['net'] is not None else None,repeat_units=plan['repeat_units'],
    changed_legs=sum(x['changed'] for x in plan.get('diversity_ledger',[])),
    gained_groups=sum(a and not b for a,b in zip(actual,control)) if known else None,
    lost_groups=sum(b and not a for a,b in zip(actual,control)) if known else None,
    mean_group_probability=sum(plan['group_probability'])/plan['groups'],**entry['evaluation']['metrics'])
   results.append(row)
  print('SETTLED',issue,flush=True)
 assert len(results)==48*40
 (out/'results.json').write_text(json.dumps(dict(rows=results,freeze_seal=frozen['seal'],audit_sha256=hashlib.sha256((out/'settlement-audit.json').read_bytes()).hexdigest(),implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
