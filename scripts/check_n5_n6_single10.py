"""Independent physical-ticket audit of paired N5/N6 10% single swaps."""
import argparse,gzip,hashlib,itertools,json,math,random
from pathlib import Path
import numpy as np
import pandas as pd

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study);root=out.parent
    v=json.loads((out/'results.json').read_text());w=json.loads(json.loads((out/'plans-frozen.json').read_text())['canonical_json'])
    paths=[s for s in w['source_hashes'] if s.endswith('settlement-audit.json')];assert len(paths)==1
    labels={(x['issue'],x['slot'],x['provider_id']):x for x in json.loads(Path(paths[0]).read_text())['rows']}
    rows={(x['issue'],x['policy']):x for x in v['rows']};total=0;swaps={5:0,6:0};eligible_count={5:0,6:0}
    for issue in v['issue_order']:
        plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
        old5=json.loads(gzip.decompress((root/'n5-single-swaps-v1/plans'/f'{issue}.json.gz').read_bytes()))
        old6=json.loads(gzip.decompress((root/'n6-uncapped-v1/plans'/f'{issue}.json.gz').read_bytes()))
        assert set(plans)=={f'N{n}_NO_SWAP' for n in (5,6)}|{f'N{n}_S{s:03}' for n in (5,6) for s in range(100)}
        for n in (5,6):
            base=plans[f'N{n}_NO_SWAP'];original_base=old5['N5_NO_SWAP'] if n==5 else old6
            for k in ('components','stake','cash_cny','cutoffs','decision_ledger'):assert base[k]==original_base[k]
            assert len(base['components'])<=1024//(2*2**(n-2))
            for policy,plan in plans.items():
                if not policy.startswith(f'N{n}_'):continue
                seen=set();payouts=[];expected_eligible=0;expected_swaps=0;is_control=policy.endswith('NO_SWAP')
                assert len(plan['components'])==len(base['components'])
                if not is_control:assert len(plan['swap_ledger'])==n*len(base['components'])
                for g,(c,b) in enumerate(zip(plan['components'],base['components'],strict=True),1):
                    assert len(c['legs'])==n and sum(len(r['support'])==1 for r in c['legs'])==2
                    assert len(c['tickets'])==2**(n-2) and c['stake']==2*2**(n-2) and all(t['units']==1 for t in c['tickets'])
                    for i,(r,original) in enumerate(zip(c['legs'],b['legs'],strict=True)):
                        assert {k:x for k,x in r.items() if k!='support'}=={k:x for k,x in original.items() if k!='support'}
                        eligible=r['slot'] in seen;seen.add(r['slot']);single=r['role']=='A';expected=original['support']
                        if not is_control:
                            seed=int(policy[-3:]);draw=random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{issue}|{g}|{r["slot"]}'.encode()).digest(),'big')).random()
                            swap=eligible and single and draw<.1
                            if swap:expected=dict(W='3',D='1',L='0')[sorted('WDL',key=lambda d:-r['q_'+d])[1]]
                            l=plan['swap_ledger'][(g-1)*n+i]
                            assert (l['group'],l['slot'],l['eligible'],l['single'],l['draw'],l['swapped'],l['original'],l['support'])==(g,r['slot'],eligible,single,draw,swap,original['support'],expected)
                            if n==5:
                                prior=old5[f'N5_SWAP_S{seed:03}']['swap_ledger'][(g-1)*n+i]
                                assert prior['draw']==draw and (not swap or prior['swapped'])
                            expected_eligible+=eligible and single;expected_swaps+=swap
                        assert r['support']==expected
                    assert {t['code'] for t in c['tickets']}=={''.join(x) for x in itertools.product(*(r['support'] for r in c['legs']))}
                    actual=[labels[(issue,r['slot'],r['provider_id'])] for r in c['legs']]
                    code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in actual)
                    payouts.append(2*.65*math.prod(r['spf_sp'] for r in actual) if code in {t['code'] for t in c['tickets']} else 0.)
                row=rows[issue,policy];total+=len(payouts);swaps[n]+=expected_swaps;eligible_count[n]+=expected_eligible
                assert row['groups']==len(payouts) and row['stake']==2*2**(n-2)*len(payouts) and row['cash_cny']==1024-row['stake']
                assert row['hits']==sum(x>0 for x in payouts) and row['swapped_double']==0
                assert row['eligible_single']==expected_eligible and row['swapped_single']==expected_swaps
                assert math.isclose(sum(payouts),row['gross'],abs_tol=1e-7) and math.isclose(sum(payouts)-row['stake'],row['net'],abs_tol=1e-7)
        print('CHECKED',issue,flush=True)
    metrics=pd.concat([pd.read_csv(out/'controls.csv'),pd.read_csv(out/'seed_metrics.csv')]).set_index('policy');frame=pd.DataFrame(v['rows'])
    for policy,group in frame.groupby('policy'):
        group=group.set_index('issue').loc[v['issue_order']];r=metrics.loc[policy];equity=np.r_[100000,100000+np.cumsum(group.net)]
        for field,value in dict(net=group.net.sum(),stake=group.stake.sum(),gross=group.gross.sum(),ROI_percent=100*group.net.sum()/group.stake.sum(),
            groups=group.groups.sum(),winning_groups=group.hits.sum(),hit_issues=(group.hits>0).sum(),max_drawdown=np.max(np.maximum.accumulate(equity)-equity)).items():
            assert math.isclose(r[field],value,abs_tol=1e-7),(policy,field)
    print('PASS',total,'groups;',swaps,'swaps;',eligible_count,'eligible singles; all rows, N5 nested draws and R metrics reconciled')
