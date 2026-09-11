"""Independent source-paired occurrence rules and physical payout arithmetic."""
import argparse,gzip,hashlib,json,math,random
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    frozen=json.loads((out/'frozen.json').read_text());v=json.loads((out/'results.json').read_text())
    w=json.loads(json.loads((out/'plans-frozen.json').read_text())['canonical_json'])
    paths=[s for s in w['source_hashes'] if s.endswith('settlement-audit.json')];assert len(paths)==1
    labels={(r['issue'],r['slot'],r['provider_id']):r for r in json.loads(Path(paths[0]).read_text())['rows']}
    results={(r['issue'],r['source_policy'],r['seed']):r for r in v['rows']};n=v['group_size'];assert len(results)==len(v['issue_order'])*(4 if n==7 else 2)*100
    groups=0;swaps=0
    for issue in v['issue_order']:
        f=out/'plans'/f'{issue}.json.gz';assert hashlib.sha256(f.read_bytes()).hexdigest()==frozen['receipt']['plan_hashes'][str(f)]
        plans=json.loads(gzip.decompress(f.read_bytes()));source='double-source-v1' if n==7 else 'consensus-n6-n7-v2';base=json.loads(gzip.decompress(Path(f'data/derived/fundamentals_417/{source}/plans/{issue}.json.gz').read_bytes()))
        if n==6:base={k+'_BASELINE':v for k,v in base.items() if k.startswith('N6_')}
        for policy,variants in plans.items():
            assert set(variants)==set(map(str,range(100)))
            for seed,plan in variants.items():
                seen=set();gross=0;hits=0;index=0
                assert plan['stake']==base[policy]['stake'] and plan['cash_cny']==base[policy]['cash_cny']
                for group,(part,old) in enumerate(zip(plan['components'],base[policy]['components'],strict=True),1):
                    groups+=1;assert len(part['tickets'])==2**(n-2) and all(t['units']==1 for t in part['tickets'])
                    actual=[]
                    for l,b in zip(part['legs'],old['legs'],strict=True):
                        assert (l['slot'],l['role'],l['provider_id'])==(b['slot'],b['role'],b['provider_id'])
                        eligible=l['slot'] in seen;seen.add(l['slot']);single=l['role']=='A'
                        draw=random.Random(int.from_bytes(hashlib.sha256(f'{seed}|{issue}|{group}|{l["slot"]}'.encode()).digest(),'big')).random()
                        changed=eligible and draw<.3;prefix='q' if single or policy.endswith('MARKET') else 'p'
                        order=sorted('WDL',key=lambda d:(-l[f'{prefix}_{d}'],'WDL'.index(d)))
                        expected=order[1:2] if changed and single else [order[0],order[2]] if changed else order[:1] if single else order[:2]
                        codes={dict(W='3',D='1',L='0')[d] for d in expected};assert set(l['support'])==codes
                        ledger=plan['swap_ledger'][index];index+=1
                        assert ledger['swapped']==changed and ledger['eligible']==eligible and ledger['draw']==draw
                        if not eligible:assert l['support']==b['support']
                        swaps+=changed;actual.append(labels[(issue,l['slot'],l['provider_id'])])
                    code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in actual)
                    win=all(c in l['support'] for c,l in zip(code,part['legs'],strict=True))
                    assert sum(t['code']==code for t in part['tickets'])==int(win)
                    hits+=win
                    if win:gross+=2*.65*math.prod(r['spf_sp'] for r in actual)
                row=results[(issue,policy,int(seed))];assert hits==row['hits'] and math.isclose(gross,row['gross'],abs_tol=1e-7)
                assert math.isclose(row['net'],gross-row['stake'],abs_tol=1e-7)
        print('CHECKED',issue,flush=True)
    print('PASS',groups,'groups;',swaps,'swaps; exact100seed ledger replay and physical settlement')
