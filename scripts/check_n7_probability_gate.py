"""Independent candidate ranking and settlement replay; no planner/settler calls."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning import verify_implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--study',required=True);args=cli.parse_args()
    root=Path(args.study);frozen=json.loads((root/'plans-frozen.json').read_text())
    assert stable_json_hash(frozen['receipt'])==frozen['seal'];r=frozen['receipt']
    verify_implementation_closure(Path.cwd(),r['implementation'])
    for path,digest in {**r['source_hashes'],**r['pool_hashes'],**r['plan_hashes']}.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    er=json.loads((root/'evaluation-receipt.json').read_text())
    for path,digest in [(root/'plans-frozen.json',er['freeze_sha256']),(root/'results.json',er['result_sha256']),
            (Path(er['audit_path']),er['audit_sha256']),(Path(er['controls_path']),er['controls_sha256'])]:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    result=json.loads((root/'results.json').read_text());assert result['freeze_seal']==frozen['seal']
    audit=json.loads(Path(er['audit_path']).read_text())['rows']
    lookup={(str(z['issue']),int(z['slot']),str(z['provider_id'])):z for z in audit}
    assert len(lookup)==len(audit)
    pools={};expectations={};composition=[]
    for row in result['rows']:
        issue=row['issue'];depth=row['depth'];count=row['count'];policy=row['policy']
        if issue not in pools:
            pool=json.loads(gzip.decompress((root/'pools'/f'{issue}.json.gz').read_bytes()))
            assert pool['seal']==stable_json_hash({k:v for k,v in pool.items() if k!='seal'})
            pools[issue]=pool
        pool=pools[issue]
        plan=json.loads(gzip.decompress((root/'plans'/f'{issue}_{depth}_{count}_{policy}.json.gz').read_bytes()))
        assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
        assert plan['pool_seal']==pool['seal'] and plan['fixtures']==pool['fixtures'] and plan['cutoffs']==pool['cutoffs']
        f=pool['fixtures'];p=np.array([[z[f'p_{d}'] for d in 'WDL'] for z in f]);q=np.array([[z[f'q_{d}'] for d in 'WDL'] for z in f])
        tickets=np.array(pool['encoded_tickets'],dtype=int).reshape(-1,7)
        tickets=tickets[np.asarray(pool['minimum_scalar_rank'])<=depth]
        masses=np.prod(p[tickets//3,tickets%3],axis=1)
        roi=.65*np.prod(p[tickets//3,tickets%3]/q[tickets//3,tickets%3],axis=1)-1
        allowed=[j for j in range(len(tickets)) if masses[j]>=count/10000 and (policy=='PROB' or roi[j]>0)]
        ordered=sorted(allowed,key=lambda j:(-roi[j],-masses[j],j) if policy=='EV' else (-masses[j],-roi[j],j))[:512]
        actual=3*np.array(plan['fixture_indices'],dtype=int).reshape(-1,7)+np.array(plan['outcomes'],dtype=int).reshape(-1,7)
        assert np.array_equal(actual,tickets[ordered])
        assert len({tuple(t) for t in actual})==len(actual) and np.all(np.diff(actual//3,axis=1)>0)
        assert row['stake']==plan['stake']==2*len(actual)<=1024 and plan['cash_cny']==1024-row['stake']
        composition.append(dict(issue=issue,count=count,depth=depth,policy=policy,
            positions=int(actual.size),draw_positions=int(np.sum(actual%3==1))))
        expected=2*math.fsum(roi[ordered]);assert math.isclose(expected,row['expected_net'],abs_tol=1e-6)
        expectations[issue,count,policy,depth]=expected
        payouts=[]
        for ticket in actual:
            matches=[lookup[(str(f[c//3]['issue']),int(f[c//3]['slot']),str(f[c//3]['provider_id']))] for c in ticket]
            assert all(z['handicap']==f[c//3]['handicap'] and 'spf:IDENTITY' not in z['status'] for c,z in zip(ticket,matches))
            if all('WDL'[c%3]==z['actual_direction'] for c,z in zip(ticket,matches)):
                assert all(math.isfinite(z['spf_sp']) and z['spf_sp']>0 for z in matches)
                payouts.append(1.3*math.prod(z['spf_sp'] for z in matches))
        assert len(payouts)==row['hits'] and math.isclose(math.fsum(payouts),row['gross'],abs_tol=1e-6)
        assert math.isclose(row['gross']-row['stake'],row['net'],abs_tol=1e-6)
    for issue in r['issues']:
        for count in r['counts']:
            assert expectations[issue,count,'EV',2048]+1e-6>=expectations[issue,count,'EV',512]
    assert len(result['rows'])==4800
    receipt=dict(checked=4800,freeze=frozen['seal'],result_sha256=er['result_sha256'],
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),composition=composition)
    (root/'independent-replay.json').write_text(json.dumps(receipt))
    print('PASS: 4800 independent allocations and settlements; expanded-search EV monotonicity')
