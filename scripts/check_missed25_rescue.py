"""Independent fixed-support, budget, complete-ticket and payout replay."""
import gzip,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 root=Path('data/derived/fundamentals_417/missed25-rescue-v1');fr=json.loads((root/'frozen.json').read_text());r=fr['receipt'];assert stable_json_hash(r)==fr['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 result=json.loads((root/'results.json').read_text());assert result['freeze_seal']==fr['seal'];verify_clean_file_bindings(result['audit_hash'],repository_root=Path.cwd())
 audit={(a['issue'],a['slot'],a['provider_id']):a for a in result['audit']};assert len(audit)==len(result['audit'])
 output={(a['issue'],a['policy']):a for a in result['rows']};assert len(output)==2160
 oldroot=Path('data/derived/fundamentals_417/n7-hit-improvement-v1');oldrows={(a['issue'],a['policy']):a for a in json.loads((oldroot/'results.json').read_text())['rows']}
 for issue in r['issues']:
  bundles=json.loads(gzip.decompress((root/'plans'/f'{issue}.json.gz').read_bytes()));old=json.loads(gzip.decompress((oldroot/'plans'/f'{issue}.json.gz').read_bytes()))['bundles']
  assert len(bundles)==45
  for policy,e in bundles.items():
   p=e['plan'];shape=e['shape_plan'];assert p['seal']==stable_json_hash({k:v for k,v in p.items() if k!='seal'});assert shape['seal']==stable_json_hash({k:v for k,v in shape.items() if k!='seal'})
   if e['mode']!='EXISTING':
    source=old[f"W{int(e['source_weight']*100):03}_P0_C0"]['plan'];mode=e['mode'];w=e['support_weight'];counts=Counter();seen=set();expected=[];spent=0
    for source_g in range(1,source['groups']+1):
     ls=sorted([a for a in source['legs'] if a['group']==source_g],key=lambda a:a['slot'])
     masses={a['slot']:[(1-w)*a['p_'+d]+w*a['q_'+d] for d in 'WDL'] for a in ls}
     orders={s:sorted(range(3),key=lambda j:(-v[j],j)) for s,v in masses.items()}
     if mode=='N6_C1_RETENTION':
      weak=min(ls,key=lambda a:(sum(masses[a['slot']][j] for j in orders[a['slot']][:2]),a['slot']))['slot'];ls=[a for a in ls if a['slot']!=weak]
     depth=0 if mode=='N7_C0' else 1 if mode in ['N7_C1_RETENTION','N6_C1_RETENTION'] else 2
     eligible=[a['slot'] for a in ls if mode!='N7_C2_RETENTION_CAP2' or counts[a['slot'],orders[a['slot']][0]]<2]
     merit={s:masses[s][orders[s][0]]/(1 if mode in ['N7_C2_TOP1','N6_DROP_SUPPORT'] else sum(masses[s][j] for j in orders[s][:2])) for s in eligible}
     singles=set(sorted(eligible,key=lambda s:(-merit[s],s))[:depth]);cost=2*2**(len(ls)-depth)
     holding=tuple((a['slot'],a['provider_id'],''.join('310'[j] for j in range(3) if j in orders[a['slot']][:1 if a['slot'] in singles else 2])) for a in ls)
     if len(singles)!=depth or holding in seen or spent+cost>1024:continue
     spent+=cost;seen.add(holding);counts.update((s,orders[s][0]) for s in singles)
     if mode=='N6_DROP_SUPPORT':
      weakest=min(holding,key=lambda a:(sum(masses[a[0]]['310'.index(c)] for c in a[2]),a[0]));holding=tuple(a for a in holding if a[0]!=weakest[0])
     if holding not in expected:expected.append(holding)
    actual=[tuple((a['slot'],a['provider_id'],a['support']) for a in c['plan']['legs']) for c in p['components']]
    assert actual==expected,(issue,policy)
   stake=gross=hits=0;seen=set()
   for c in p['components']:
    z=c['plan'];assert z['seal']==stable_json_hash({k:v for k,v in z.items() if k!='seal'})
    ls=sorted(z['legs'],key=lambda a:a['slot']);assert len(ls)==c['n'] and len(set(a['slot'] for a in ls))==c['n']
    key=tuple((a['slot'],a['provider_id'],a['support']) for a in ls);assert key not in seen;seen.add(key)
    codes={''.join(v) for v in itertools.product(*(a['support'] for a in ls))};ts=z['tickets']
    assert len(codes)==len(ts) and codes=={t['code'] for t in ts} and all(t['units']==1 for t in ts)
    cost=len(codes)*2;assert cost==z['stake'];stake+=cost
    labels=[audit[issue,a['slot'],a['provider_id']] for a in ls];assert all(a['status']=='READY' and a['handicap']==l['handicap'] for a,l in zip(labels,ls))
    truth=''.join(dict(W='3',D='1',L='0')[a['actual_direction']] for a in labels)
    if truth in codes:hits+=1;gross+=2*.65*math.prod(a['spf_sp'] for a in labels)
   row=output[issue,policy];assert stake==p['stake']==row['stake'] and 0<=stake<=1024 and row['cash_cny']==1024-stake
   assert row['hits']==hits and math.isclose(row['net'],gross-stake,abs_tol=1e-7)
   oldkey='W000_P0_C0' if policy=='H0_R000_N7_C2_TOP1' else policy if e['mode']=='EXISTING' else None
   if oldkey:assert hits==oldrows[issue,oldkey]['hits'] and math.isclose(row['net'],oldrows[issue,oldkey]['net'],abs_tol=1e-7)
 print('PASS2160: fixed support/depth/caps/drop/order/budget, complete tickets, independent payout,192 existing-control rows')
 import pandas as pd
 summary=pd.read_csv(root/'summary.csv').set_index('policy');df=pd.DataFrame(result['rows']);main=df[df.policy=='H0_R000_N7_C2_TOP1'].set_index('issue').sort_index()
 for policy,g in df.groupby('policy'):
  g=g.set_index('issue').sort_index();assert list(g.index)==list(main.index);miss=main.hits==0;delta=g.net-main.net
  equity=peak=100000.;drawdown=0.
  for n in g.net:equity+=n;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
  values=dict(net_cny=g.net.sum(),stake_cny=g.stake.sum(),hit_issues=(g.hits>0).sum(),max_drawdown_cny=drawdown,
   rescued_issues=((g.hits>0)&miss).sum(),lost_issues=((g.hits==0)&~miss).sum(),profitable_old_misses=((g.net>0)&miss).sum(),
   net_old_misses=g.net[miss].sum(),ex_best_miss_net=g.net[miss].sum()-g.net[miss].max(),ex_best_lift=delta.sum()-delta.max())
  for key,v in values.items():assert math.isclose(v,summary.loc[policy,key],abs_tol=1e-7),(policy,key)
 print('PASS45 independent financial/rescue/profit/drawdown/tail summaries')
