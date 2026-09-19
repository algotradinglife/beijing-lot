"""Independent audit of frozen fresh-Top2 plans and official-label settlement.

Usage: python scripts/check_top2_fresh_replay.py REPORT_DIR
Read-only, prints JSON. No fitting, new source admission or temporal helpers.
The QMD owns the run; this thin audit checks already-bound evidence only.
"""
import csv
import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

root = Path(sys.argv[1])
receipt = json.loads((root / 'receipt.json').read_text())
for name, sha in receipt['files'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha
freeze = json.loads((root / 'freeze.json').read_text())
source = Path(receipt['config']['input'])
raw_receipt = (source / 'receipt.json').read_bytes()
assert hashlib.sha256(raw_receipt).hexdigest() == freeze['source_receipt']
src = json.loads(raw_receipt)
assert hashlib.sha256((source / 'fixture-audit.csv').read_bytes()).hexdigest() == src['files']['fixture-audit.csv']
labels = {(r['issue'], int(r['slot']), r['provider_id']): r for r in csv.DictReader((source / 'fixture-audit.csv').open())}
reported = {(r['issue'], r['policy'], int(r['group'])): r for r in csv.DictReader((root / 'groups.csv').open())}
checked = 0
for path, sha in freeze['plans'].items():
    raw = Path(path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha
    z = json.loads(raw)
    f = z['fixtures']
    masses = []
    factors = []
    opts = []
    for i, row in enumerate(f):
        p = [row['p_' + d] for d in 'WDL']
        q = [row['q_' + d] for d in 'WDL']
        order = sorted(range(3), key=lambda d: (-p[d], d))[:2]
        assert [d + 1 for d in order] == z['options'][i]
        opts.append(order)
        masses.append(sum(p[d] for d in order))
        factors.append(sum(p[d] / q[d] for d in order))
    gs = [set(i - 1 for i in g) for g in z['groups']]
    assert all(len(g) == 7 for g in gs)
    assert len({tuple(sorted(g)) for g in gs}) == len(gs)
    probs = [math.prod(masses[i] for i in g) for g in gs]
    evs = [2 * .65 * math.prod(factors[i] for i in g) for g in gs]
    for policy, ids in z['selected'].items():
        if isinstance(ids, int):
            ids = [ids]
        assert len(ids) == min(4, len(gs)) and len(ids) == len(set(ids))
        union_probability = z['union_probability'][policy]
        if isinstance(union_probability, (int, float)):
            union_probability = [union_probability]
        assert len(union_probability) == len(ids)
        chosen = []
        cumulative = 0.
        for step, one_based in enumerate(ids):
            increments = probs.copy()
            for k in range(1, len(chosen) + 1):
                for subset in itertools.combinations(chosen, k):
                    union = set().union(*(gs[j] for j in subset))
                    for j, g in enumerate(gs):
                        increments[j] += (-1)**k * math.prod(masses[i] for i in union | g)
            scores = probs if policy == 'TOP2_PROB' else increments
            best = sorted((j for j in range(len(gs)) if j not in chosen), key=lambda j: (-scores[j], -evs[j], j))[0]
            j = one_based - 1
            # Stable arithmetic can differ at machine epsilon ties; enforce objective.
            assert math.isclose(scores[j], scores[best], rel_tol=0, abs_tol=1e-12)
            cumulative += increments[j]
            assert math.isclose(cumulative, union_probability[step], abs_tol=1e-12)
            chosen.append(j)
            got = reported[(z['issue'], policy, one_based)]
            actual = []
            sp = []
            for i in sorted(gs[j]):
                row = f[i]
                lab = labels[(row['issue'], row['slot'], row['provider_id'])]
                assert float(lab['handicap']) == row['handicap']
                actual.append('WDL'.index(lab['actual_direction']))
                sp.append(float(lab['spf_sp']))
            states = list(itertools.product(*(opts[i] for i in sorted(gs[j]))))
            assert len(states) == len(set(states)) == 128
            hits = sum(tuple(actual) == state for state in states)
            gross = hits * 2 * .65 * math.prod(sp)
            assert math.isclose(float(got['gross']), gross, rel_tol=1e-12, abs_tol=1e-8)
            assert float(got['stake']) == 256
            checked += 1
assert checked == len(reported)
print(json.dumps({'status': 'PASS', 'issues': len(freeze['plans']), 'settled_groups': checked,
                  'checks': ['plan hashes', 'Top2 ranking', 'exact incremental union',
                             'selection objective', '128 distinct tickets', 'official payout once .65']}))
