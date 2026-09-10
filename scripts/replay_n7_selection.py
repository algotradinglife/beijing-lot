"""Independent stdlib-only replay of a completed four-arm study; no production imports."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('study');args=cli.parse_args();root=Path(args.study)
    plans=json.loads((root/'plans.json').read_text());settlement=json.loads((root/'settlement.json').read_text())
    frozen=json.loads((root/'expectations.json').read_text())
    audit={(r['issue'],r['slot'],r['provider_id']):r for r in settlement['audit']}
    results={(r['issue'],r['selector'],r['grouping']):r for r in settlement['results']}
    expected={(r['issue'],r['selector'],r['grouping']):r for r in frozen}
    assert len(results)==len(plans)==len(expected)
    pools={};budgets={};codes=dict(zip('310','WDL'))
    for plan in plans:
        key=tuple(plan[k] for k in ['issue','selector','grouping']);row=results[key]
        assert row['status'] in ['COMPLETE','NO_BET'],'Replay requires completed settlement'
        assert (plan['groups']==0)==(row['status']=='NO_BET')
        if row['status']=='NO_BET':
            assert not plan['legs'] and not plan['tickets']
            assert row['stake']==row['gross']==row['net']==0
        assert len({r['slot'] for r in plan['legs']})==plan['groups']*7
        assert sum(t['units']*2 for t in plan['tickets'])==row['stake']
        assert row['stake']==256*plan['groups']
        budgets.setdefault(plan['issue'],set()).add(row['stake'])
        pool={r['slot']:r['support'] for r in plan['legs']};pair=key[:2]
        if pair in pools:assert pools[pair]==pool
        pools[pair]=pool;gross=prediction=0.;hits=0
        for g in range(1,plan['groups']+1):
            legs=sorted([r for r in plan['legs'] if r['group']==g],key=lambda r:r['slot'])
            tickets={t['code']:t['units'] for t in plan['tickets'] if t['group']==g}
            assert len(legs)==7 and len(tickets)==128 and set(tickets.values())=={1}
            assert set(tickets)=={''.join(c) for c in itertools.product(*(r['support'] for r in legs))}
            for code in tickets:
                prediction+=2*.65*math.prod(r['p_'+codes[c]]/r['q_'+codes[c]] for r,c in zip(legs,code))
            observed=[audit[(r['issue'],r['slot'],r['provider_id'])] for r in legs]
            win=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in observed)
            if win in tickets:gross+=2*.65*math.prod(r['spf_sp'] for r in observed);hits+=1
        assert math.isclose(gross,row['gross'],abs_tol=1e-7) and row['hits']==hits
        assert math.isclose(prediction,row['expected_gross'],rel_tol=1e-10)
        assert math.isclose(prediction,expected[key]['expected_gross'],rel_tol=1e-10)
    assert all(len(v)==1 for v in budgets.values())
    receipt=dict(plans=len(plans),issues=len(budgets),status='PASS',
        checks=['disjoint fixtures','same pool/support across grouping','same issue budget','128 one-unit Cartesian tickets',
                'independent actual payout','enumerated expected payout matches frozen expectation'],
        source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['plans.json','settlement.json','expectations.json']})
    (root/'independent-replay.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
