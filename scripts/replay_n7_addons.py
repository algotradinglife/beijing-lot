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
    inputs=json.loads((root/'inputs.json').read_text())
    for issue,arms in by_issue.items():
        assert set(arms)=={'BASE','ADD1','ADD2'}
        base=arms['BASE'];one=arms['ADD1'];two=arms['ADD2']
        assert len(base['components'])==1
        assert base['components']==one['components'][:1]==two['components'][:1]
        assert one['components']==two['components'][:len(one['components'])]
        assert one['actual_additions']==min(1,two['actual_additions'])
        b=base['components'][0]
        for name,p in arms.items():
            assert p['requested_additions']=={'BASE':0,'ADD1':1,'ADD2':2}[name]
            assert p['actual_additions']==len(p['components'])-1<=p['requested_additions']
            assert p['stake']==p['budget']==base['stake']+256*p['actual_additions']
        events=[{r['slot'] for r in b['legs'] if r['group']==g} for g in range(1,b['groups']+1)]
        candidates=[r for r in inputs['rows'] if r['issue']==issue]
        coverage={r['slot']:sum(sorted([r['p_W'],r['p_D'],r['p_L']],reverse=True)[:2]) for r in candidates}
        ranked=sorted(candidates,key=lambda r:(-coverage[r['slot']],r['slot'],r['provider_id']))
        # Original groups are disjoint. At the second step, original+ADD1
        # fixtures are exhausted; the remaining ADD1-only subset is disjoint
        # from original groups. Thus capacity constraints form a partition
        # matroid and rank-greedy independently certifies each MILP objective.
        for step in range(2 if b['groups'] else 0):
            picked=set()
            for r in ranked:
                slot=r['slot']
                if sum(slot in e for e in events)>=2:continue
                proposed=picked|{slot}
                if all(len(proposed&e)<=3 for e in events):picked=proposed
                if len(picked)==7:break
            if step>=two['actual_additions']:
                assert len(picked)<7, 'Omitted feasible addition'
                break
            part=two['components'][step+1]
            assert part['groups']==1
            event={r['slot'] for r in part['legs']}
            assert all(len(event&e)<=3 for e in events)
            assert len(picked)==7
            assert math.isclose(math.prod(coverage[s] for s in picked),math.prod(coverage[s] for s in event),rel_tol=1e-8)
            receipt=two['solver_steps'][step]
            assert receipt['status']=='OPTIMAL' and receipt['mip_gap']==0
            events.append(event)
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
                'nested additions, unchanged baseline, <=3 overlap, independent probability optimum','independent payout and ideal equal allocation','pending and NO_BET'],
        source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['plans.json','settlement.json']})
    (root/'independent-replay.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
