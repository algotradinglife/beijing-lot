"""Independent probability, single-role and complete-ticket settlement replay."""
import gzip,json,hashlib,itertools,math,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 root=Path('data/derived/fundamentals_417/n7-hit-improvement-v1')
 frozen=json.loads((root/'frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 data=json.loads((root/'results.json').read_text());assert data['freeze_seal']==frozen['seal'];verify_clean_file_bindings(data['audit_hash'],repository_root=Path.cwd())
 factors=json.loads(Path('data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json').read_text())['rows'];original={(x['issue'],x['slot']):x for x in factors}
 labels={(x['issue'],x['slot'],x['provider_id']):x for x in data['audit']};assert len(labels)==len(data['audit'])
 output={(x['issue'],x['policy']):x for x in data['rows']};assert len(output)==1440
 old=json.loads(Path('data/derived/fundamentals_417/cap-depth-grid-v1/results.json').read_text())['rows'];control={x['issue']:x for x in old if x['policy']=='D2_U6_P5_BASE'}
 for issue in r['issues']:
  z=json.loads(gzip.decompress((root/'plans'/f'{issue}.json.gz').read_bytes()))
  for policy,entry in z['bundles'].items():
   p=entry['plan'];assert p['seal']==stable_json_hash({k:v for k,v in p.items() if k!='seal'})
   unguarded=z['bundles'][f"W{int(entry['weight']*100):03}_P0_C0"]['plan']
   decision_values={l['slot']:[l['p_'+d] for d in 'WDL'] for l in unguarded['legs']}
   counts=Counter();funded=0;gross=hits=0
   for source_group in sorted({l['source_group'] for l in p['guard_ledger']}):
    ledger=[l for l in p['guard_ledger'] if l['source_group']==source_group];eligible=[];probs={};orders={}
    for item in ledger:
     s=item['slot'];f=original[issue,s];w=entry['weight'] if abs(f['handicap'])>=2 else 0
     projected=[(1-w)*f['p_'+d]+w*f['q_'+d] for d in 'WDL']
     # Validate mathematical mass independently, then respect the sealed
     # decision representation for ties below floating summation precision.
     ps=decision_values[s];assert all(math.isclose(a,b,rel_tol=0,abs_tol=1e-12) for a,b in zip(ps,projected))
     qs=[f['q_'+d] for d in 'WDL'];order=sorted(range(3),key=lambda i:(-ps[i],i));top=order[0]
     conflict=top!=max(range(3),key=lambda i:qs[i]) and sum(abs(a-b) for a,b in zip(ps,qs))/2>=.15
     capped=entry['cap'] is not None and counts[s,top]>=entry['cap'];assert conflict==item['conflict'] and capped==item['capped']
     if not (entry['protect'] and conflict) and not capped:eligible.append(s)
     probs[s]=ps;orders[s]=order
    chosen=set(sorted(eligible,key=lambda s:(-probs[s][orders[s][0]],s))[:2]);buy=len(chosen)==2
    assert all(l['funded']==buy and l['single']==(buy and l['slot'] in chosen) for l in ledger), (issue,policy,source_group,chosen,[l for l in ledger if l['single']],{s:probs[s][orders[s][0]] for s in eligible})
    if not buy:continue
    funded+=1;ls=sorted([l for l in p['legs'] if l['group']==funded],key=lambda l:l['slot']);assert len(ls)==7
    for l in ls:
     s=l['slot'];selected=orders[s][:1] if s in chosen else orders[s][:2]
     assert l['support']==''.join('310'[i] for i in range(3) if i in selected)
     assert all(math.isclose(l['p_'+d],probs[s][i],abs_tol=1e-12) for i,d in enumerate('WDL'))
     if s in chosen:counts[s,orders[s][0]]+=1
    ts=[t for t in p['tickets'] if t['group']==funded];codes={''.join(c) for c in itertools.product(*(l['support'] for l in ls))}
    assert len(ts)==len(codes)==32 and all(t['units']==1 for t in ts) and {t['code'] for t in ts}==codes
    truth=[labels[issue,l['slot'],l['provider_id']] for l in ls];code=''.join(dict(W='3',D='1',L='0')[a['actual_direction']] for a in truth)
    assert all(a['status']=='READY' and a['handicap']==l['handicap'] for a,l in zip(truth,ls))
    if code in codes:hits+=1;gross+=2*.65*math.prod(a['spf_sp'] for a in truth)
   row=output[issue,policy];assert funded==p['groups'] and row['stake']==funded*64 and row['cash']==1024-funded*64
   assert row['hits']==hits and math.isclose(row['net'],gross-funded*64,abs_tol=1e-7)
   if policy=='W000_P0_C0':assert hits==control[issue]['hits'] and math.isclose(row['net'],control[issue]['net'],abs_tol=1e-7)
 print('PASS1440 plans: probability projection, conflict/cap/skip decisions, complete tickets, single .65 settlement,48 original controls')
