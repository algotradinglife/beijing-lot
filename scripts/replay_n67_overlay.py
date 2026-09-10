"""Independent stdlib cash/exposure replay of sealed N6/N7 overlays."""
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
    pools={};matched={};verified=pending=0
    for plan in plans:
        row=rows[(plan['issue'],plan['strategy'],plan['funding'])]
        assert len({c['n'] for c in plan['components']})==len(plan['components'])
        assert plan['stake']==sum(t['units']*2 for c in plan['components'] for t in c['tickets'])==row['stake']
        assert row['cash']==plan['budget']-row['stake']
        if plan['funding']=='MATCHED':matched.setdefault(plan['issue'],set()).add(plan['budget'])
        gross=base=0.;hits=0;unknown=False
        for c in plan['components']:
            assert c['n'] in [6,7] and c['groups']<=plan['max_n'+str(c['n'])]
            assert len(c['legs'])==len({r['slot'] for r in c['legs']})==c['n']*c['groups']
            if plan['strategy'] in ['DIRECT','CROSS']:
                key=(plan['issue'],plan['funding'],c['n']);pool={r['slot']:r['support'] for r in c['legs']}
                if key in pools:assert pools[key]==pool
                pools[key]=pool
            for g in range(1,c['groups']+1):
                legs=sorted([r for r in c['legs'] if r['group']==g],key=lambda r:r['slot'])
                tickets={t['code']:t['units'] for t in c['tickets'] if t['group']==g}
                assert len(legs)==c['n'] and len(tickets)==2**c['n']
                assert set(tickets)=={''.join(v) for v in itertools.product(*(r['support'] for r in legs))}
                assert all(isinstance(u,int) and u>0 for u in tickets.values())
                a=[audit.get((r['issue'],r['slot'],r['provider_id'])) for r in legs]
                if any(z is None or z['actual_direction'] not in ['W','D','L'] or 'spf:IDENTITY' in z['status'] or z['handicap']!=r['handicap'] for z,r in zip(a,legs)):
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
        ideal=base*row['stake']/plan['minimum_stake'] if plan['minimum_stake'] else 0
        assert math.isclose(row['ideal_gross'],ideal,abs_tol=1e-7)
        verified+=1
    assert all(len(b)==1 for b in matched.values())
    result=dict(status='PASS',verified=verified,pending_verified=pending,plans=len(plans),
        checks=['per-N fixture uniqueness','same overlay pools','full Cartesian support','positive integer units',
                'same matched budget','independent payout and ideal equal allocation','pending and NO_BET'],
        source_hashes={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['plans.json','settlement.json']})
    (root/'independent-replay.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
