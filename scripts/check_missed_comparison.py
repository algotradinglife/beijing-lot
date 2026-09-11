"""Independent whole-ticket accounting of all fixed N6/N7 portfolios."""
import gzip,json,math,itertools,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.temporal_learning.provenance import verify_implementation_closure

if __name__=='__main__':
 root=Path('data/derived/fundamentals_417/missed-comparison-v1')
 saved=json.loads((root/'frozen.json').read_text());r=saved['receipt'];assert stable_json_hash(r)==saved['seal']
 verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd());verify_implementation_closure(Path.cwd(),r['implementation'])
 result=json.loads((root/'results.json').read_text());assert result['freeze_seal']==saved['seal']
 verify_clean_file_bindings(result['audit_hash'],repository_root=Path.cwd())
 audit=json.loads(Path(next(iter(result['audit_hash']))).read_text())['rows'];lookup={(a['issue'],a['slot'],a['provider_id']):a for a in audit};assert len(lookup)==len(audit)
 rows={(x['issue'],x['policy']):x for x in result['rows']};assert len(rows)==288
 old=json.loads(Path('data/derived/fundamentals_417/cap-depth-grid-v1/results.json').read_text())['rows'];main={x['issue']:x for x in old if x['policy']=='D2_U6_P5_BASE'}
 for issue in r['issues']:
  bundle=json.loads(gzip.decompress((root/'plans'/f'{issue}.json.gz').read_bytes()))
  for policy,p in bundle.items():
   assert p['seal']==stable_json_hash({k:v for k,v in p.items() if k!='seal'})
   stake=gross=hits=0;wallet={k:0 for k in p['wallets']};seen=set()
   for c in p['components']:
    part=c['plan'];assert part['seal']==stable_json_hash({k:v for k,v in part.items() if k!='seal'})
    legs=sorted(part['legs'],key=lambda x:x['slot']);assert len(legs)==c['n'] and len({x['slot'] for x in legs})==c['n']
    codes={''.join(x) for x in itertools.product(*(l['support'] for l in legs))}
    assert len(codes)==len(part['tickets']) and codes=={t['code'] for t in part['tickets']} and all(t['units']==1 for t in part['tickets'])
    key=tuple((l['slot'],l['provider_id'],l['support']) for l in legs);assert key not in seen;seen.add(key)
    cost=2*len(codes);assert cost==part['stake'];stake+=cost;wallet[c['source']]+=cost
    labels=[lookup[issue,l['slot'],l['provider_id']] for l in legs]
    assert all(a['status']=='READY' and a['handicap']==l['handicap'] for a,l in zip(labels,legs))
    code=''.join(dict(W='3',D='1',L='0')[a['actual_direction']] for a in labels)
    if code in codes:gross+=2*.65*math.prod(a['spf_sp'] for a in labels);hits+=1
   assert all(wallet[k]<=p['wallets'][k] for k in wallet) and stake<=1024
   row=rows[issue,policy]
   assert row['stake']==stake and row['cash_cny']==1024-stake and row['hits']==hits
   assert math.isclose(row['net'],gross-stake,abs_tol=1e-7)
   if policy=='N7':assert math.isclose(row['net'],main[issue]['net'],abs_tol=1e-7) and row['hits']==main[issue]['hits']
 print('PASS288 independently settled complete-ticket portfolios;48 original N7 results preserved')
