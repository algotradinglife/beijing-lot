"""Independent checks of fixed-market routing, group assignment and R-audited payoffs."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 result=json.loads((out/'results.json').read_text());source=json.loads((out/'candidates.json').read_text());end=json.loads((out/'endpoints.json').read_text());c=result['contract']
 assert end['version']==c['draw_version']=='1.1.0'
 assert hashlib.sha256(Path(c['high_model']).read_bytes()).hexdigest()==c['high_model_sha256']
 assert hashlib.sha256((out/'endpoints.json').read_bytes()).hexdigest()==source['endpoints_sha256']
 for bindings in [source['input_hashes'],end['input_hashes'],source['implementation_hashes'],result['audit_hashes']]:
  for name,h in bindings.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 candidates={}
 for r in source['rows']:candidates.setdefault((r['issue'],r['slot'],r['provider_id']),[]).append(r)
 audit={}
 for name in ['training','validation','test']:
  for r in json.loads((out/f'{name}-audit.json').read_text()):
   key=(r['issue'],r['slot'],r['provider_id']);assert key not in audit;audit[key]=r
 expected={(r['issue'],r['policy']):r for r in result['rows']};checked=0
 for path in sorted((out/'plans').glob('*.json')):
  bundle=json.loads(path.read_text());plan=bundle['plan'];route=bundle['routing'];mode=route['receipt']['mode'];penalty=route['receipt']['penalty'];fixed=route['receipt']['fixed_weight'];issue=plan['issue'];policy=path.stem[len(issue)+1:]
  for row in route['rows']:
   key=(issue,row['slot'],row['provider_id']);options=candidates[key];first=options[0]
   scores=[]
   for option in options:
    for d in 'WDL':assert abs(option['q_'+d]-first['q_'+d])<1e-12
    ps=[option['p_'+d] for d in 'WDL'];qs=[option['q_'+d] for d in 'WDL'];ix=sorted(range(3),key=lambda i:(-ps[i],i))[:2]
    objective=sum(ps[i]/qs[i] for i in ix)/2-penalty*option['weight']**2
    if mode!='FIXED' or option['weight']==fixed:scores.append((objective,-option['weight'],option['weight']))
   assert row['weight']==max(scores)[2]
  ordered=sorted(route['rows'],key=lambda r:(-sum(sorted([r['p_'+d] for d in 'WDL'],reverse=True)[:2]),r['slot'],r['provider_id']))
  groups=min(6,len(ordered)//7);wanted={(r['slot'],r['provider_id']):i//7+1 for i,r in enumerate(ordered[:groups*7])}
  assert {(r['slot'],r['provider_id']):r['group'] for r in plan['legs']}==wanted
  gross=0;hits=0
  for group in range(1,groups+1):
   legs=[r for r in plan['legs'] if r['group']==group];assert len(legs)==7
   hit=True
   for leg in legs:
    ps=[leg['p_'+d] for d in 'WDL'];ix=sorted(range(3),key=lambda i:(-ps[i],i))[:2];dirs={'WDL'[i] for i in ix}
    observed=audit[(issue,leg['slot'],leg['provider_id'])]
    hit &= observed['actual_direction'] in dirs
   if hit:
    hits+=1;gross+=2*.65*math.prod(audit[(issue,r['slot'],r['provider_id'])]['spf_sp'] for r in legs)
  e=expected[(issue,policy)];assert e['status'] in ['COMPLETE','NO_BET'];assert e['stake']==groups*256 and e['hits']==hits and abs(e['gross']-gross)<1e-7
  checked+=1
 # The chosen penalty uses validation outcomes only, with larger-penalty tie break.
 scores=[]
 for penalty in c['penalties']:
  net=sum(r['net'] for r in result['rows'] if r['partition']=='VALIDATION8' and r['policy']==f'EV_{penalty:g}');scores.append((net,penalty))
 assert max(scores)[1]==result['selection']['penalty']
 for r in result['rows']:
  if r['policy']=='SELECTED_PENALTY':
   original=expected[(r['issue'],f"EV_{result['selection']['penalty']:g}")]
   assert (r['stake'],r['gross'],r['net'])==(original['stake'],original['gross'],original['net'])
 paths=[out/'results.json',out/'candidates.json',out/'endpoints.json',out/'penalty-selection.json']
 (out/'independent-check.json').write_text(json.dumps(dict(status='PASS',plans_checked=checked,rows_checked=len(result['rows']),source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}),indent=2));print('PASS',checked,len(result['rows']))
