"""Independent stdlib replay of #437 frozen budgets, overlap and settlement.

Usage: project-python scripts/check_n7_sweet_region.py STUDY OUTPUT_JSON
Reads sealed CSV evidence and original rank labels; writes a new check receipt.
No fitting, selection, source mutation, network or credential access.
"""
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

study, output = map(Path, sys.argv[1:])
assert not output.exists()
freeze_raw = (study / 'plans-frozen.json').read_bytes()
freeze = json.loads(freeze_raw)
evaluation = json.loads((study / 'evaluation-receipt.json').read_text())
assert hashlib.sha256(freeze_raw).hexdigest() == evaluation['freeze_sha256']
assert freeze['historical_admission'] is False
for name, expected in freeze['files'].items():
    assert hashlib.sha256((study / name).read_bytes()).hexdigest() == expected
assert hashlib.sha256((study / 'results.csv').read_bytes()).hexdigest() == evaluation['results_sha256']
rank_path = Path(freeze['config']['rank_dir']) / 'ranks.csv'
assert hashlib.sha256(rank_path.read_bytes()).hexdigest() == evaluation['ranks_sha256']
ranks = {(r['issue'], r['sleeve_id']): r for r in csv.DictReader(rank_path.open())}
policies = {p['arm']: p for p in freeze['config']['policies']}
points = {}
for p in csv.DictReader((study / 'prediction-points.csv').open()):
    assert not {'actual_rank', 'actual_gross_cny', 'hit', 'net'} & set(p)
    key = (p['issue'], p['sleeve_id'], round(float(p['target']), 8))
    assert key not in points
    points[key] = p
funded = defaultdict(list)
for p in csv.DictReader((study / 'frozen-plan-groups.csv').open()):
    funded[p['issue'], p['arm']].append(p)
seen = set()
for result in csv.DictReader((study / 'results.csv').open()):
    issue, arm = result['issue'], result['arm']
    assert (issue, arm) not in seen
    seen.add((issue, arm))
    policy = policies[arm]
    selected = funded[issue, arm]
    ids = [p['sleeve_id'] for p in selected]
    assert len(ids) == len(set(ids))
    sets = [set(freeze['metadata'][issue]['fixture_sets'][i]) for i in ids]
    assert all(len(s) == 7 for s in sets)
    counts = Counter(f for s in sets for f in s)
    assert max(counts.values(), default=0) <= policy['reuse']
    assert all(len(a & b) <= policy['overlap'] for a, b in combinations(sets, 2))
    cost = gross = hits = 0
    for p in selected:
        original = points[issue, p['sleeve_id'], round(policy['target'], 8)]
        assert int(p['depth']) == int(original['depth'])
        assert float(p['stake']) == 2 * int(p['depth']) <= policy['cap_cny']
        assert float(p['coverage']) + 1e-12 >= policy['target']
        cost += float(p['stake'])
        rank = ranks[issue, p['sleeve_id']]
        hit = int(rank['actual_rank']) <= int(p['depth'])
        hits += hit
        gross += float(rank['actual_gross_cny']) * hit
    assert cost <= 1024 and cost == float(result['stake'])
    assert 1024 - cost == float(result['cash'])
    assert len(ids) == int(result['groups']) and hits == int(result['hits'])
    assert math.isclose(gross, float(result['gross']), rel_tol=1e-10, abs_tol=1e-6)
    assert math.isclose(gross-cost, float(result['net']), rel_tol=1e-10, abs_tol=1e-6)
assert len(seen) == 200 * 27
assert len(points) == 200 * 24 * 17
output.write_text(json.dumps(dict(status='PASS', plans=len(seen), prediction_points=len(points),
    freeze_sha256=evaluation['freeze_sha256'], results_sha256=evaluation['results_sha256'],
    labels_sha256=evaluation['ranks_sha256'],
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    checks=['frozen hashes','prediction-only points','candidate target/depth identity',
            'budget','reuse','pair overlap','groups','hits','gross','net']), indent=2))
print(f'PASS: {len(seen)} plans, {len(points)} prediction points')
