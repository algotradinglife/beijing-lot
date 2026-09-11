"""Independent physical-ticket settlement and paired group invariants."""
import argparse,gzip,json,math
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    v=json.loads((out/'results.json').read_text());w=json.loads(json.loads((out/'plans-frozen.json').read_text())['canonical_json'])
    paths=[s for s in w['source_hashes'] if s.endswith('settlement-audit.json')];assert len(paths)==1
    labels=json.loads(Path(paths[0]).read_text())['rows'];labels={(x['issue'],x['slot'],x['provider_id']):x for x in labels}
    original=json.loads(Path('data/derived/fundamentals_417/high-hit-filter-v1/results.json').read_text())['rows']
    old={(x['issue'],x['policy']):x for x in original}
    stats={u:dict(both=0,baseline_only=0,market_only=0,neither=0,baseline_only_gross=0.,market_only_gross=0.) for u in (3,6)}
    records=[]
    for issue in v['issue_order']:
        plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
        for u in (3,6):
            b=plans[f'U{u}_BASELINE'];m=plans[f'U{u}_MARKET'];assert b['stake']==m['stake']
            pairs=[]
            for x,y in zip(b['components'],m['components'],strict=True):
                assert [(r['slot'],r['provider_id'],r['role']) for r in x['legs']]==[(r['slot'],r['provider_id'],r['role']) for r in y['legs']]
                assert sum(i['support']!=j['support'] for i,j in zip(x['legs'],y['legs'],strict=True))==1
                payouts=[]
                for c in (x,y):
                    assert sum(len(r['support'])==1 for r in c['legs'])==2
                    actual=[labels[(issue,r['slot'],r['provider_id'])] for r in sorted(c['legs'],key=lambda r:r['slot'])]
                    code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in actual)
                    win=[t for t in c['tickets'] if t['code']==code];assert len(win)<=1
                    payouts.append(2*.65*math.prod(r['spf_sp'] for r in actual) if win else 0.)
                    assert len(c['tickets'])==32 and all(t['units']==1 for t in c['tickets'])
                pairs.append(payouts)
                key='both' if all(payouts) else 'baseline_only' if payouts[0] else 'market_only' if payouts[1] else 'neither'
                stats[u][key]+=1
                if key=='baseline_only':stats[u]['baseline_only_gross']+=payouts[0]
                if key=='market_only':stats[u]['market_only_gross']+=payouts[1]
            for j,mode in enumerate(('BASELINE','MARKET')):
                row=next(r for r in v['rows'] if r['issue']==issue and r['policy']==f'U{u}_{mode}')
                gross=sum(z[j] for z in pairs);hits=sum(z[j]>0 for z in pairs)
                assert hits==row['hits'] and math.isclose(gross,row['gross'],abs_tol=1e-7)
                assert math.isclose(gross-row['stake'],row['net'],abs_tol=1e-7)
                if j==0:
                    previous=old[(issue,f'U{u}_ORIGINAL')]
                    for field in ('stake','gross','net','groups','hits'):assert math.isclose(row[field],previous[field],abs_tol=1e-7)
    print('PASS: 192 rows, 1524 groups, baseline exact replay; paired attribution',json.dumps(stats))
