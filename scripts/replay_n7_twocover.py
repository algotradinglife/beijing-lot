"""Independent stdlib cash/exposure replay of sealed N7 two-cover plans."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('study');args=cli.parse_args();root=Path(args.study)
    plans=json.loads((root/'plans.json').read_text());settlement=json.loads((root/'settlement.json').read_text())
    audit={(r['issue'],r['slot'],r['provider_id']):r for r in settlement['audit']}
    assert len(audit)==len(settlement['audit'])
    rows={(r['issue'],r['strategy'],r['funding']):r for r in settlement['results']}
    assert len(rows)==len(plans)==len(settlement['results'])
    verified=pending=0
    by_issue={}
    for p in plans:
        assert p['funding']=='UNIT'
        by_issue.setdefault(p['issue'],{})[p['strategy']]=p
    for issue,arms in by_issue.items():
        assert set(arms)=={'BASE','DOUBLE_STAKE','TWO_COVER'}
        base=arms['BASE'];double=arms['DOUBLE_STAKE'];two=arms['TWO_COVER']
        assert len(base['components'])==len(double['components'])==1
        b=base['components'][0];d=double['components'][0];count=b['groups']
        assert b['legs']==d['legs']==two['components'][0]['legs']
        assert b['tickets']==two['components'][0]['tickets']
        assert all(t['units']==1 for t in b['tickets'])
        multiple=2 if count>=2 else 1
        assert double['stake']==two['stake']==base['stake']*multiple
        assert all(p['budget']==p['stake'] for p in arms.values())
        assert d['tickets']==[dict(t,units=multiple) for t in b['tickets']]
        assert len(two['components'])==multiple
        if count>=2:
            groups=[sorted([r for r in b['legs'] if r['group']==g],key=lambda r:(-r['coverage'],r['slot'],r['provider_id'])) for g in range(1,count+1)]
            for i in range(count-1):groups[i][-1],groups[i+1][0]=groups[i+1][0],groups[i][-1]
            expected=[dict(r,group=g) for g,legs in enumerate(groups,1) for r in sorted(legs,key=lambda r:r['slot'])]
            assert two['components'][1]['legs']==expected
            assert all(t['units']==1 for t in two['components'][1]['tickets'])
    for plan in plans:
        row=rows[(plan['issue'],plan['strategy'],plan['funding'])]
        events=[frozenset(r['slot'] for r in c['legs'] if r['group']==g) for c in plan['components'] for g in range(1,c['groups']+1)]
        assert len(set(events))==len(events)
        assert all(sum(slot in e for e in events)<=2 for slot in set().union(*events))
        assert plan['stake']==sum(t['units']*2 for c in plan['components'] for t in c['tickets'])==row['stake']
        assert row['cash']==plan['budget']-row['stake']
        gross=base=0.;hits=0;unknown=False
        for c in plan['components']:
            assert c['n']==7 and c['groups']<=6
            assert len(c['legs'])==len({r['slot'] for r in c['legs']})==c['n']*c['groups']
            for g in range(1,c['groups']+1):
                legs=sorted([r for r in c['legs'] if r['group']==g],key=lambda r:r['slot'])
                tickets={t['code']:t['units'] for t in c['tickets'] if t['group']==g}
                assert len(legs)==c['n'] and len(tickets)==2**c['n']
                assert set(tickets)=={''.join(v) for v in itertools.product(*(r['support'] for r in legs))}
                assert all(isinstance(u,int) and u>0 for u in tickets.values())
                a=[audit.get((r['issue'],r['slot'],r['provider_id'])) for r in legs]
                if any(z is None or z['actual_direction'] not in ['W','D','L'] or z['status'] is None or 'spf:IDENTITY' in z['status'] or z['handicap']!=r['handicap'] for z,r in zip(a,legs)):
                    unknown=True;continue
                code=''.join(dict(W='3',D='1',L='0')[z['actual_direction']] for z in a)
                if code in tickets:
                    if any(z['spf_sp'] is None or not math.isfinite(z['spf_sp']) or z['spf_sp']<=0 for z in a):unknown=True;continue
                    cash=2*.65*math.prod(z['spf_sp'] for z in a);gross+=cash*tickets[code];base+=cash;hits+=1
        if unknown:
            assert row['status']=='PENDING_AUDIT_OR_WINNING_SP' and row['gross'] is None and row['net'] is None
            pending+=1;continue
        assert row['status']==('COMPLETE' if row['groups'] else 'NO_BET')
        assert row['hits']==hits and math.isclose(row['gross'],gross,abs_tol=1e-7)
        assert math.isclose(row['net'],gross-row['stake'],abs_tol=1e-7)
        ideal=gross
        assert math.isclose(row['ideal_gross'],ideal,abs_tol=1e-7)
        verified+=1
    result=dict(status='PASS',verified=verified,pending_verified=pending,plans=len(plans),
        checks=['per-layer uniqueness and max two groups per fixture','distinct groups','full Cartesian support','positive integer units',
                'same comparison budgets and supports; exact doubling and boundary swaps','independent payout and ideal equal allocation','pending and NO_BET'],
        source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['plans.json','settlement.json']})
    (root/'independent-replay.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
