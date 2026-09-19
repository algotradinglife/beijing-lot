"""Independent frozen C1/C2 ticket support, source probabilities and cap checks.

No production selection/settlement import and no label reads. Verifies complete
Cartesian tickets and highest-probability singles for every saved selected group;
this does not independently prove the greedy MILP group's optimality.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import itertools
import json
from pathlib import Path
from src.temporal_learning.core import utc, stable_json_hash

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();s=Path(a.study);raw=(s/'plans-frozen.json').read_bytes();f=json.loads(raw);r=f['receipt']
    assert stable_json_hash(r)==f['seal']
    catraw=Path(r['catalog']).read_bytes();assert hashlib.sha256(catraw).hexdigest()==r['catalog_sha256']
    cat=json.loads(catraw);entries={e['issue']:e for e in cat['issues']}
    expected={f'{src}_C{n}_U{u}' for src in ['RAW','CAL'] for n in [1,2] for u in [3,6]}
    checked=0;tickets=0
    for issue in r['issues']:
        e=entries[issue];data=Path(e['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==e['sha256']==r['source_hashes'][e['path']]
        source=json.loads(gzip.decompress(data));fixtures={x['slot']:x for x in source['expanded_pool']['fixtures']}
        path=s/'plans'/(issue+'.json.gz');data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==r['plan_hashes'][str(path)]
        plans=json.loads(gzip.decompress(data));assert set(plans)==expected
        for name,plan in plans.items():
            assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
            assert set(plan['cutoffs'])=={str(s) for s in fixtures}
            assert all(utc(plan['cutoffs'][str(s)])==utc(source['cutoffs'][str(s)]) for s in fixtures)
            src,count,uses=name.split('_');count=int(count[1:]);uses=int(uses[1:]);cost=2*2**(7-count)
            assert plan['issue']==issue and plan['stake']==plan['groups']*cost<=1024
            assert plan['cash_cny']==1024-plan['stake'] and plan['single_count']==count
            groups=[]
            for group in range(1,plan['groups']+1):
                legs=[x for x in plan['legs'] if x['group']==group];slots={x['slot'] for x in legs}
                assert len(legs)==len(slots)==7 and slots<=fixtures.keys()
                candidates=[]
                for leg in legs:
                    original=fixtures[leg['slot']];assert leg['provider_id']==original['provider_id'] and leg['handicap']==original['handicap']
                    probs={d:original[('q_' if src=='RAW' else 'p_')+d] for d in 'WDL'}
                    assert all(abs(leg['p_'+d]-probs[d])<1e-12 and abs(leg['q_'+d]-probs[d])<1e-12 for d in 'WDL')
                    order=sorted('WDL',key=lambda d:(-probs[d],'WDL'.index(d)))
                    candidates.append((leg,max(probs.values()),order))
                singles={x[0]['slot'] for x in sorted(candidates,key=lambda x:(-x[1],x[0]['slot'],x[0]['provider_id']))[:count]}
                for leg,_,order in candidates:
                    dirs=order[:1 if leg['slot'] in singles else 2]
                    support=''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in dirs)
                    assert leg['support']==support
                actual=[x for x in plan['tickets'] if x['group']==group]
                expected_codes={''.join(x) for x in itertools.product(*(z['support'] for z in legs))}
                assert len(actual)==len(expected_codes) and {x['code'] for x in actual}==expected_codes
                assert all(x['units']==1 for x in actual)
                tickets+=len(actual);groups.append(slots)
            assert len(plan['legs'])==7*len(groups) and len(plan['tickets'])==len(groups)*cost//2
            assert max(Counter(slot for group in groups for slot in group).values(),default=0)<=uses
            assert all(len(x&y)<=5 for x,y in itertools.combinations(groups,2))
            checked+=1
    Path(a.output).write_text(json.dumps(dict(status='PASS',issues=len(r['issues']),plans=checked,tickets=tickets,
        frozen_sha256=hashlib.sha256(raw).hexdigest(),scope='Source-bound cutoffs, supports, top singles, Cartesian tickets and exposure caps; no label reads; not MILP optimality proof'),indent=2))
