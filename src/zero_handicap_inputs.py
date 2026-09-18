"""Read frozen score projections for a descriptive zero-handicap comparison.

No fitting, quote selection, network, writes or settlement changes. Every parsed
file is checked on the same bytes; the manifest pins the explicit batch list.
"""
import hashlib
import json
import math
from pathlib import Path


def verified_zero_json(path, expected):
    """Read JSON bytes bound by SHA256; missing/changed files raise."""
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError(f"Changed input: {path}")
    return json.loads(raw)


def read_zero_handicap_inputs(manifest_path, manifest_sha256, repository_root):
    """Return JSON with zero-line rows, OU inputs, coverage and source hashes.

    Each row is one issue/slot/provider_id; strings preserve identifier zeros.
    q is raw score mapping, p is the previously frozen draw-corrected market.
    The consumer validates numerical/tabular contracts and joins labels in R.
    Current projection implementation must match the frozen implementation.
    Grid aggregation is independently replayed for every admitted zero-line row.
    Empty zero-line batches are allowed; repeated fixture identities are not.
    """
    manifest = verified_zero_json(manifest_path, manifest_sha256)
    root = Path(repository_root)
    study = Path(manifest['study'])
    sources = {str(manifest_path): manifest_sha256}
    rows, totals, coverage, seen = [], [], [], set()
    batch_ids = [b['batch'] for b in manifest['batches']]
    if not batch_ids or len(set(batch_ids)) != len(batch_ids):
        raise ValueError('Unique explicit batches required')
    for batch in manifest['batches']:
        directory = study / batch['batch']
        receipt_path = directory / 'batch-receipt.json'
        receipt = verified_zero_json(receipt_path, batch['receipt_sha256'])
        sources[str(receipt_path)] = batch['receipt_sha256']
        packets = []
        for name in ('projected.json', 'projection-inputs.json', 'probabilities/predictions.json'):
            path = directory / name
            packets.append(verified_zero_json(path, receipt['files'][name]))
            sources[str(path)] = receipt['files'][name]
        projection, inputs, predictions = packets
        if (projection['historical_admission'] is not False or
                projection['parameters']['method'] != 'EXISTING_OU_FIXED_MEAN_LEAST_SQUARES_1X2' or
                projection['issue_order'] != receipt['issues']):
            raise ValueError('Unexpected projection contract')
        for name, expected in projection['implementation_hashes'].items():
            path = root / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('Current projection implementation differs: ' + name)
            sources[str(path)] = expected
        indexed = []
        for values in (projection['fixtures'], inputs['fixtures'], predictions['rows']):
            by_key = {(r['issue'], r['slot'], r['provider_id']): r for r in values}
            if len(by_key) != len(values):
                raise ValueError('Duplicate fixture identity')
            indexed.append(by_key)
        if not (indexed[0].keys() == indexed[1].keys() == indexed[2].keys()):
            raise ValueError('Projection/input/prediction scope mismatch')
        selected = set()
        for key, row in indexed[0].items():
            if key in seen:
                raise ValueError('Repeated fixture across batches')
            seen.add(key)
            if row['handicap'] != 0:
                continue
            selected.add(key)
            original, corrected = indexed[1][key], indexed[2][key]
            for field in ('handicap', 'cutoff_utc', 'odds_W', 'odds_D', 'odds_L'):
                if row[field] != original[field]:
                    raise ValueError('Projection source value mismatch')
            if corrected['handicap'] != 0:
                raise ValueError('Corrected handicap mismatch')
            grid = projection['grids'][f'{key[0]}/{key[1]}']
            masses = dict(W=0., D=0., L=0.)
            cells = set()
            for cell in grid:
                h, a, p = cell['home_goals'], cell['away_goals'], cell['probability']
                if ((h, a) in cells or h < 0 or a < 0 or h != int(h) or a != int(a)
                        or not math.isfinite(p) or p < 0):
                    raise ValueError('Invalid score grid')
                cells.add((h, a))
                masses['W' if h > a else 'D' if h == a else 'L'] += p
            if abs(sum(masses.values()) - 1) > 1e-8:
                raise ValueError('Grid mass mismatch')
            for direction in 'WDL':
                if (abs(masses[direction] - row['q_' + direction]) > 1e-10 or
                        abs(corrected['q_' + direction] - row['q_' + direction]) > 1e-10):
                    raise ValueError('Grid/prediction probability mismatch')
            rows.append(dict(row, **{'p_' + d: corrected['new_' + d] for d in 'WDL'},
                             batch=batch['batch'], corrected_version=corrected['version']))
        totals.extend(r for r in inputs['total_quotes']
                      if (r['issue'], r['slot'], r['provider_id']) in selected)
        coverage.append(dict(batch=batch['batch'], issues=len(receipt['issues']),
                             first=receipt['issues'][0], last=receipt['issues'][-1],
                             projected=len(indexed[0]), zero_line=len(selected),
                             upstream_exclusions=len(projection['exclusions'])))
    return json.dumps(dict(rows=rows, total_quotes=totals, coverage=coverage,
                           source_hashes=sources, historical_learning='NONE'), allow_nan=False)
