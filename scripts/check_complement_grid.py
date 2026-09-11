"""Independent physical-ticket, wallet, source-order and settlement replay."""
import argparse,gzip,hashlib,itertools,json,math,sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 frozen=json.loads((out/'freeze-receipt.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 report=json.loads((out/'plans-frozen.json').read_text());assert hashlib.sha256(report['canonical_json'].encode()).hexdigest()==report['seal']
 receipt=json.loads(report['canonical_json']);assert hashlib.sha256((out/'results.json').read_bytes()).hexdigest()==receipt['result_sha256']
 verify_clean_file_bindings(receipt['source_hashes'],repository_root=Path.cwd())
 paths=[k for k in receipt['source_hashes'] if k.endswith('settlement-audit.json')];assert len(paths)==1
 audit=json.loads(Path(paths[0]).read_text())['rows'];labels={(z['issue'],z['slot'],z['provider_id']):z for z in audit};assert len(labels)==len(audit)
 results=json.loads((out/'results.json').read_text())['rows'];seen={(z['issue'],z['policy']):z for z in results};assert len(seen)==len(results)==22368
 original_results=json.loads((Path(r['source'])/'results.json').read_text())['rows'];old={(z['issue'],z['policy']):z for z in original_results};checked=0
 for issue in r['issues']:
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));c=bundle['catalog'];recipes=bundle['recipes']
  assert c['seal']==stable_json_hash({k:v for k,v in c.items() if k!='seal'})
  original=json.loads(gzip.decompress((Path(r['source'])/'plans'/f'{issue}.json.gz').read_bytes()))
  for name,z in original.items():
   assert c['source_seals'][name]==z['plan']['seal']
   expected=[]
   for g in range(1,z['plan']['groups']+1):
    legs=sorted([l for l in z['plan']['legs'] if l['group']==g],key=lambda l:l['slot'])
    expected.append(stable_json_hash([(l['slot'],l['provider_id'],l['support']) for l in legs]))
   assert c['source_order'][name]==expected
  pay={};wins={};tickets={}
  for key,v in c['components'].items():
   part=v['plan'];legs=sorted(part['legs'],key=lambda z:z['slot'])
   assert part['seal']==stable_json_hash({k:v for k,v in part.items() if k!='seal'})
   assert key==stable_json_hash([(z['slot'],z['provider_id'],z['support']) for z in legs])
   assert len(legs)==7 and len({z['slot'] for z in legs})==7
   codes={''.join(z) for z in itertools.product(*(l['support'] for l in legs))}
   assert codes=={t['code'] for t in part['tickets']} and len(codes)==len(part['tickets'])
   assert all(t['units']==1 for t in part['tickets']) and part['stake']==len(codes)*2
   truth=[labels[issue,l['slot'],l['provider_id']] for l in legs]
   assert all(z['status']=='READY' and z['handicap']==l['handicap'] for z,l in zip(truth,legs))
   code=''.join(dict(W='3',D='1',L='0')[z['actual_direction']] for z in truth);wins[key]=int(code in codes)
   pay[key]=2*.65*math.prod(z['spf_sp'] for z in truth) if wins[key] else 0.
   tickets[key]=[stable_json_hash([(l['slot'],l['provider_id'],v) for l,v in zip(legs,code)]) for code in sorted(codes)]
   assert set(tickets[key])==set(v['ticket_ids'])
  for policy,recipe in recipes.items():
   assert recipe['seal']==stable_json_hash({k:v for k,v in recipe.items() if k!='seal'}) and recipe['catalog_seal']==c['seal']
   chosen=[];allocation=[]
   for role,source,wallet in [('MAIN',recipe['main'],recipe['main_budget_cny']),('ALTERNATIVE',recipe['alternative'],1024-recipe['main_budget_cny'])]:
    paid=0
    for key in c['source_order'][source]:
     cost=c['components'][key]['plan']['stake']
     if key not in chosen and paid+cost<=wallet:
      chosen.append(key);paid+=cost;allocation.append(dict(component=key,role=role,source=source,stake=cost))
   assert allocation==recipe['allocations'];stake=sum(a['stake'] for a in allocation)
   assert recipe['stake']==stake and recipe['cash_cny']==1024-stake and recipe['groups']==len(chosen)
   physical=[t for key in chosen for t in tickets[key]];assert len(physical)*2==stake
   assert recipe['duplicate_ticket_units']==len(physical)-len(set(physical))
   fixture=Counter(l['slot'] for key in chosen for l in c['components'][key]['plan']['legs'])
   assert recipe['max_fixture_uses']==max(fixture.values(),default=0)
   sets=[{l['slot'] for l in c['components'][key]['plan']['legs']} for key in chosen]
   assert recipe['max_pair_overlap']==max((len(x&y) for x,y in itertools.combinations(sets,2)),default=0)
   assert recipe['unique_fixtures']==len(fixture)
   total=sum(fixture.values());hhi=sum((v/total)**2 for v in fixture.values()) if total else 0.
   assert math.isclose(recipe['fixture_hhi'],hhi,abs_tol=1e-12)
   row=seen[issue,policy];gross=sum(pay[k] for k in chosen)
   assert math.isclose(row['gross'],gross,abs_tol=1e-7) and math.isclose(row['net'],gross-stake,abs_tol=1e-7)
   assert row['hits']==sum(wins[k] for k in chosen) and row['budget_cny']==1024
   if policy=='MAIN':assert math.isclose(row['net'],old[issue,'D2_U6_P5_BASE']['net'],abs_tol=1e-7)
   if policy.startswith('ONLY__') and recipe['alternative'] in original:
    assert math.isclose(row['net'],old[issue,recipe['alternative']]['net'],abs_tol=1e-7)
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==22368
 print('PASS22368 physical portfolios; source orders, wallets, duplicates, single .65 payouts; original148 standalones preserved')
