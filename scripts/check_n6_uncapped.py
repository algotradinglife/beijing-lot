"""Independent ticket, support, settlement and correlation audit of QMD113."""
import argparse,gzip,itertools,json,math
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    v=json.loads((out/'results.json').read_text());w=json.loads(json.loads((out/'plans-frozen.json').read_text())['canonical_json'])
    paths=[s for s in w['source_hashes'] if s.endswith('settlement-audit.json')];assert len(paths)==1
    labels={(x['issue'],x['slot'],x['provider_id']):x for x in json.loads(Path(paths[0]).read_text())['rows']}
    originals=json.loads(Path('data/derived/fundamentals_417/double-source-v1/results.json').read_text())['rows']
    assert [x for x in v['rows'] if x['policy']!='N6_UNCAPPED']==[x for x in originals if x['policy'] in ('U3_BASELINE','U6_BASELINE')]
    total=0;max_reuse=0
    for issue in v['issue_order']:
        plan=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));sets=[];uses=Counter();payouts=[]
        assert len(plan['components'])<=32
        for c in plan['components']:
            legs=sorted(c['legs'],key=lambda r:r['slot']);slots={r['slot'] for r in legs}
            assert len(slots)==6 and Counter(r['role'] for r in legs)==dict(A=2,D=3,C=1)
            assert all(len(slots & previous)<=5 for previous in sets)
            sets.append(slots);uses.update(slots)
            for r in legs:
                ranks={s:sorted('WDL',key=lambda d:-r[f'{s}_{d}']) for s in ('p','q')}
                if r['role']=='A':
                    assert ranks['p'][0]==ranks['q'][0] and r['q_'+ranks['q'][0]]>=.5
                    support=ranks['q'][:1]
                else:
                    assert (set(ranks['p'][:2])==set(ranks['q'][:2]))==(r['role']=='D')
                    support=ranks['p'][:2]
                assert set(r['support'])=={dict(W='3',D='1',L='0')[d] for d in support}
                assert r['handicap']!=0 or set(ranks['p'][:2])==set(ranks['q'][:2])
            assert len(c['tickets'])==16 and all(t['units']==1 for t in c['tickets'])
            assert {t['code'] for t in c['tickets']}=={''.join(x) for x in itertools.product(*(r['support'] for r in legs))}
            actual=[labels[(issue,r['slot'],r['provider_id'])] for r in legs]
            code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in actual)
            payouts.append(2*.65*math.prod(r['spf_sp'] for r in actual) if code in {t['code'] for t in c['tickets']} else 0.)
        total+=len(sets);max_reuse=max(max_reuse,max(uses.values(),default=0))
        row=next(r for r in v['rows'] if r['issue']==issue and r['policy']=='N6_UNCAPPED')
        assert row['groups']==len(sets) and row['stake']==32*len(sets) and row['cash_cny']==1024-row['stake']
        assert row['hits']==sum(x>0 for x in payouts)
        assert math.isclose(sum(payouts),row['gross'],abs_tol=1e-7)
        assert math.isclose(sum(payouts)-row['stake'],row['net'],abs_tol=1e-7)
    frame=pd.DataFrame(v['rows']);wide=frame.pivot(index='issue',columns='policy',values='net').loc[v['issue_order']]
    hits=frame.pivot(index='issue',columns='policy',values='hits').loc[v['issue_order']].gt(0)
    for r in pd.read_csv(out/'correlations.csv').to_dict('records'):
        x=wide.N6_UNCAPPED;y=wide[r['reference']]
        assert math.isclose(np.corrcoef(x,y)[0,1],r['pearson'],abs_tol=1e-12)
        assert math.isclose(spearmanr(x,y).statistic,r['spearman'],abs_tol=1e-12)
        assert math.isclose(np.corrcoef(hits.N6_UNCAPPED,hits[r['reference']])[0,1],r['hit_phi'],abs_tol=1e-12)
    for r in pd.read_csv(out/'summary.csv').to_dict('records'):
        series=wide[r['policy']].to_numpy();equity=np.r_[100000,100000+np.cumsum(series)]
        assert math.isclose(float(np.max(np.maximum.accumulate(equity)-equity)),r['max_drawdown_cny'],abs_tol=1e-7)
    print('PASS',total,'groups; max reuse',max_reuse,'; all 144 rows and correlations/drawdowns reconciled')
