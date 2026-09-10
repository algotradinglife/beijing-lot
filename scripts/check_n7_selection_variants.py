"""Independent enumeration of frozen random/precompression tickets and payouts."""
import argparse,gzip,hashlib,itertools,json,math,random,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 frozen=json.loads((out/'plans-frozen.json').read_text());f=frozen['receipt'];assert stable_json_hash(f)==frozen['seal'];verify_implementation_closure(Path.cwd(),f['implementation'])
 results=json.loads((out/'results.json').read_text());assert results['freeze_seal']==frozen['seal']
 for path,h in {**f['source_hashes'],**f['plan_hashes'],**results['audit_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 source=json.loads(Path(next(k for k in f['source_hashes'] if k.endswith('/inputs.json'))).read_text());rows=[r for r in source['rows'] if r['weight']==.5]
 labels={}
 for path in results['audit_hashes']:
  for r in json.loads(Path(path).read_text()):
   key=(r['issue'],r['slot'],r['provider_id']);assert key not in labels;labels[key]=r
 observed={(r['issue'],r['policy']):r for r in results['rows']};checked=0
 for path in f['plan_hashes']:
  bundle=json.loads(gzip.decompress(Path(path).read_bytes()));issue=bundle['CURRENT']['issue'];pool=[r for r in rows if r['issue']==issue]
  ranked=sorted(pool,key=lambda r:(-max(r['p_'+d] for d in 'WDL'),r['slot'],r['provider_id']))
  for policy,plan in bundle.items():
   assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal'];o=observed[issue,policy];gross=0;hits=0;sets=[]
   if policy.startswith('GLOBAL'):
    v=plan['precompress_value'];singles={r['slot'] for r in (ranked[:v] if plan['precompress_mode']=='FIXED' else [r for r in ranked if max(r['p_'+d] for d in 'WDL')>=v])};assert singles==set(plan['single_slots'])
   for group in range(1,plan['groups']+1):
    legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot']);slots={r['slot'] for r in legs};assert len(legs)==len(slots)==7;sets.append(slots)
    if policy.startswith('GLOBAL'):assert len(slots&singles)==2
    if policy.startswith('RANDOM'):
     base=[r for r in bundle['SINGLE_2']['legs'] if r['group']==group];assert slots=={r['slot'] for r in base}
     order=sorted(base,key=lambda r:(-max(r['p_'+d] for d in 'WDL'),r['slot'],r['provider_id']));anchor=order[0]['slot'];others=sorted(order[1:],key=lambda r:(r['slot'],r['provider_id']))
     rng=random.Random(int.from_bytes(hashlib.sha256(f"{plan['seed']}|{issue}|{group}".encode()).digest(),'big'));second=others[rng.randrange(6)]['slot']
     singles={anchor,second}
    if policy.startswith(('GLOBAL','RANDOM')):
     for r in legs:
      ds=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)))[:1 if r['slot'] in singles else 2]
      assert r['support']==''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in ds)
    tickets=[t for t in plan['tickets'] if t['group']==group];cartesian=[''.join(z) for z in itertools.product(*(r['support'] for r in legs))]
    assert sorted(t['code'] for t in tickets)==sorted(cartesian) and all(t['units']==1 for t in tickets)
    assert len(cartesian)==(128 if policy=='CURRENT' else 64 if policy=='SINGLE_1' else 32)
    obs=[labels[issue,r['slot'],r['provider_id']] for r in legs];assert all(l['handicap']==r['handicap'] for l,r in zip(obs,legs))
    code=''.join(dict(W='3',D='1',L='0')[l['actual_direction']] for l in obs)
    if code in cartesian:gross+=2*.65*math.prod(l['spf_sp'] for l in obs);hits+=1
   assert max(Counter(s for g in sets for s in g).values(),default=0)<=(1 if policy=='CURRENT' else 2)
   assert all(len(a&b)<=(0 if policy=='CURRENT' else 2) for a,b in itertools.combinations(sets,2))
   assert o['stake']==len(plan['tickets'])*2 and o['cash_cny']==o['budget_cny']-o['stake']>=0
   assert abs(o['gross']-gross)<1e-7 and abs(o['net']-gross+o['stake'])<1e-7 and o['hits']==hits
   checked+=1
 print('PASS',checked,'plans, random draws, global roles, supports, budgets, reuse caps and payouts')
