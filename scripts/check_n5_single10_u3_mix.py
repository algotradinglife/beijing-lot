"""Independent original-group prefix, full-ticket and financial mix audit."""
import argparse,gzip,itertools,json,math
from pathlib import Path
import numpy as np
import pandas as pd

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study);root=out.parent
    v=json.loads((out/'results.json').read_text());w=json.loads(json.loads((out/'plans-frozen.json').read_text())['canonical_json'])
    paths=[s for s in w['source_hashes'] if s.endswith('settlement-audit.json')];assert len(paths)==1
    labels={(x['issue'],x['slot'],x['provider_id']):x for x in json.loads(Path(paths[0]).read_text())['rows']}
    rows={(x['issue'],x['seed']):x for x in v['rows']};total=0
    for issue in v['issue_order']:
        plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
        n5=json.loads(gzip.decompress((root/'n5-n6-single10-v1/plans'/f'{issue}.json.gz').read_bytes()))
        n7=json.loads(gzip.decompress((root/'double-source-v1/plans'/f'{issue}.json.gz').read_bytes()))['U3_BASELINE']
        assert set(plans)=={str(s) for s in range(100)}
        for seed,plan in plans.items():
            expected=[('N5',p) for p in n5[f'N5_S{int(seed):03}']['components'][:32]]+[('U3',p) for p in n7['components'][:8]]
            assert len(plan['components'])==len(expected);payouts=[];stakes={'N5':0,'U3':0}
            for c,(name,original) in zip(plan['components'],expected,strict=True):
                assert c['source']==name and c['n']==(5 if name=='N5' else 7);part=c['plan']
                assert part['legs']==original['legs'] and part['tickets']==original['tickets']
                assert part['stake']==original['stake']==(16 if name=='N5' else 64)
                assert {t['code'] for t in part['tickets']}=={''.join(x) for x in itertools.product(*(r['support'] for r in part['legs']))}
                assert all(t['units']==1 for t in part['tickets'])
                actual=[labels[(issue,r['slot'],r['provider_id'])] for r in part['legs']]
                code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in actual)
                payouts.append(2*.65*math.prod(r['spf_sp'] for r in actual) if code in {t['code'] for t in part['tickets']} else 0.)
                stakes[name]+=part['stake']
            row=rows[issue,int(seed)];total+=len(expected)
            assert all(s<=512 for s in stakes.values()) and row['n5_stake']==stakes['N5'] and row['u3_stake']==stakes['U3']
            assert row['stake']==sum(stakes.values()) and row['cash_cny']==1024-row['stake']
            assert row['groups']==len(expected) and row['hits']==sum(x>0 for x in payouts)
            assert math.isclose(sum(payouts),row['gross'],abs_tol=1e-7) and math.isclose(sum(payouts)-row['stake'],row['net'],abs_tol=1e-7)
        print('CHECKED',issue,flush=True)
    old10=json.loads((root/'n5-n6-single10-v1/results.json').read_text())['rows']
    old25=json.loads((root/'n5-single-swaps-v1/results.json').read_text())
    expected_controls=old10+[dict(x,source_policy='N5_25') for x in old25['rows'] if x['policy'].startswith('N5_SWAP_S')]+[dict(x,source_policy=x['policy']) for x in old25['controls'] if x['policy'] in ('U3_BASELINE','U6_BASELINE')]
    assert v['controls']==expected_controls
    metrics=pd.read_csv(out/'metrics.csv').set_index('policy');curves=pd.read_csv(out/'curves.csv');frame=pd.DataFrame(v['rows']+v['controls'])
    for policy,group in frame.groupby('policy'):
        group=group.set_index('issue').loc[v['issue_order']];r=metrics.loc[policy];equity=np.r_[100000,100000+np.cumsum(group.net)];dd=np.maximum.accumulate(equity)-equity
        c=curves[curves.policy==policy].sort_values('period');np.testing.assert_allclose(c.equity_cny,equity,rtol=0,atol=1e-7);np.testing.assert_allclose(c.drawdown_cny,dd,rtol=0,atol=1e-7)
        for field,value in dict(net=group.net.sum(),stake=group.stake.sum(),ROI_percent=100*group.net.sum()/group.stake.sum(),
            groups=group.groups.sum(),winning_groups=group.hits.sum(),hit_issues=(group.hits>0).sum(),max_drawdown=max(dd)).items():
            assert math.isclose(r[field],value,abs_tol=1e-7),(policy,field)
    print('PASS',total,'physical groups; original prefixes exact; all mixed and control rows and404 policy metrics/equity/DD verified')
