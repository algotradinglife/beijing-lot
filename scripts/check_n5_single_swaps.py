"""Independent N5 physical supports, fixed random draws, payouts and R metrics."""
import argparse,gzip,hashlib,itertools,json,math,random
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    v=json.loads((out/'results.json').read_text());w=json.loads(json.loads((out/'plans-frozen.json').read_text())['canonical_json'])
    paths=[s for s in w['source_hashes'] if s.endswith('settlement-audit.json')];assert len(paths)==1
    labels={(x['issue'],x['slot'],x['provider_id']):x for x in json.loads(Path(paths[0]).read_text())['rows']}
    old=json.loads(Path('data/derived/fundamentals_417/n6-uncapped-v1/results.json').read_text());assert v['controls']==old['rows']
    rows={(x['issue'],x['policy']):x for x in v['rows']};total=0;swaps=0;maximum=0
    for issue in v['issue_order']:
        plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));base=plans['N5_NO_SWAP'];sets=[];uses=Counter()
        assert set(plans)=={'N5_NO_SWAP'}|{f'N5_SWAP_S{s:03}' for s in range(100)}
        for c in base['components']:
            slots={r['slot'] for r in c['legs']};uses.update(slots)
            assert len(slots)==5 and all(len(slots&s)<=4 for s in sets);sets.append(slots)
            assert Counter(r['role'] for r in c['legs'])==dict(A=2,D=2,C=1)
            for r in c['legs']:
                ranks={s:sorted('WDL',key=lambda d:-r[f'{s}_{d}']) for s in ('p','q')}
                if r['role']=='A':
                    assert ranks['p'][0]==ranks['q'][0] and r['q_'+ranks['q'][0]]>=.5
                    support=ranks['q'][:1]
                else:
                    assert (set(ranks['p'][:2])==set(ranks['q'][:2]))==(r['role']=='D');support=ranks['p'][:2]
                assert set(r['support'])=={dict(W='3',D='1',L='0')[d] for d in support}
                assert r['handicap']!=0 or set(ranks['p'][:2])==set(ranks['q'][:2])
        maximum=max(maximum,max(uses.values(),default=0));assert len(sets)<=64
        for policy,plan in plans.items():
            seen=set();payouts=[];expected_eligible=0;expected_swaps=0
            assert len(plan['components'])==len(base['components'])
            if policy!='N5_NO_SWAP':assert len(plan['swap_ledger'])==5*len(sets)
            for g,(c,b) in enumerate(zip(plan['components'],base['components'],strict=True),1):
                assert len(c['tickets'])==8 and c['stake']==16 and all(t['units']==1 for t in c['tickets'])
                for i,(r,original) in enumerate(zip(c['legs'],b['legs'],strict=True)):
                    assert {k:x for k,x in r.items() if k!='support'}=={k:x for k,x in original.items() if k!='support'}
                    eligible=r['slot'] in seen;seen.add(r['slot']);single=r['role']=='A';expected=original['support']
                    if policy!='N5_NO_SWAP':
                        seed=int(policy[-3:]);draw=random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{issue}|{g}|{r["slot"]}'.encode()).digest(),'big')).random()
                        swap=eligible and single and draw<.25
                        if swap:expected=dict(W='3',D='1',L='0')[sorted('WDL',key=lambda d:-r['q_'+d])[1]]
                        l=plan['swap_ledger'][(g-1)*5+i]
                        assert (l['group'],l['slot'],l['eligible'],l['single'],l['draw'],l['swapped'],l['original'],l['support'])==(g,r['slot'],eligible,single,draw,swap,original['support'],expected)
                        expected_eligible+=eligible and single;expected_swaps+=swap
                    assert r['support']==expected
                assert {t['code'] for t in c['tickets']}=={''.join(x) for x in itertools.product(*(r['support'] for r in c['legs']))}
                actual=[labels[(issue,r['slot'],r['provider_id'])] for r in c['legs']]
                code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in actual)
                payouts.append(2*.65*math.prod(r['spf_sp'] for r in actual) if code in {t['code'] for t in c['tickets']} else 0.)
            row=rows[issue,policy];total+=len(payouts);swaps+=expected_swaps
            assert row['groups']==len(payouts) and row['stake']==16*len(payouts) and row['cash_cny']==1024-row['stake']
            assert row['hits']==sum(x>0 for x in payouts) and row['swapped_double']==0
            assert row['eligible_single']==expected_eligible and row['swapped_single']==expected_swaps
            assert math.isclose(sum(payouts),row['gross'],abs_tol=1e-7) and math.isclose(sum(payouts)-row['stake'],row['net'],abs_tol=1e-7)
        print('CHECKED',issue,flush=True)
    metrics=pd.concat([pd.read_csv(out/'controls.csv'),pd.read_csv(out/'seed_metrics.csv')]).set_index('policy')
    frame=pd.DataFrame(v['rows']+v['controls'])
    for policy,group in frame.groupby('policy'):
        group=group.set_index('issue').loc[v['issue_order']];r=metrics.loc[policy];equity=np.r_[100000,100000+np.cumsum(group.net)]
        for field,value in dict(net=group.net.sum(),stake=group.stake.sum(),gross=group.gross.sum(),ROI_percent=100*group.net.sum()/group.stake.sum(),
            groups=group.groups.sum(),winning_groups=group.hits.sum(),hit_issues=(group.hits>0).sum(),max_drawdown=np.max(np.maximum.accumulate(equity)-equity)).items():
            assert math.isclose(r[field],value,abs_tol=1e-7),(policy,field)
    print('PASS',total,'physical groups,',swaps,'single swaps; max reuse',maximum,'; all rows and R policy metrics reconciled')
