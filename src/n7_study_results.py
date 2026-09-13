"""Join already evaluated frozen batches without changing financial outcomes."""
from src.temporal_learning.core import stable_json_hash


def combine_n7_study_results(parts, *, issue_order, seeds, arms):
    """Combine result/freeze pairs into one exact issue x seed x arm grid.

    Each part contains `result` and `freeze` dictionaries. This pure data-boundary
    check verifies seals and grid identity, not independent settlement acceptance;
    callers must verify source files and replay evidence before supplying parts.
    Rows are preserved, including explicit NOT_EVALUABLE rows. No missing cells
    are invented, zero-filled, or discarded; duplicate cells raise ValueError.
    Returns ordered rows, issue_order and source freeze seals. No I/O or learning.
    """
    for values in (issue_order, seeds, arms):
        if not isinstance(values, list) or not values or len(set(values)) != len(values):
            raise ValueError('Explicit unique full scope, seeds and arms required')
    if any(not isinstance(i, str) or not i for i in issue_order):
        raise ValueError('Native string issue identities required')
    rows = {}
    seals = []
    for part in parts:
        result, frozen = part['result'], part['freeze']
        receipt = frozen['receipt']
        if (frozen['seal'] != stable_json_hash(receipt) or
                result['freeze_seal'] != frozen['seal'] or
                result['historical_admission'] is not False or
                receipt['historical_admission'] is not False or
                result['issue_order'] != receipt['issues']):
            raise ValueError('Result/freeze identity mismatch')
        cfg = receipt['parameters']
        expected = {(i,s,a) for i in receipt['issues'] for s in cfg['seeds'] for a in cfg['arms']}
        seen = set()
        for row in result['rows']:
            key = (row['issue'],row['seed'],row['arm'])
            if key not in expected or key in seen or key in rows:
                raise ValueError('Duplicate or unexpected batch result')
            if row['status'] == 'NOT_EVALUABLE' and (
                    not row.get('reason') or any(row.get(k) is not None for k in ('stake','gross','net','roi','hits'))):
                raise ValueError('Unavailable period must retain reason and null financial results')
            seen.add(key)
            rows[key] = dict(row)
        if seen != expected:
            raise ValueError('Incomplete batch result grid')
        seals.append(frozen['seal'])
    ordered = [(i,s,a) for i in issue_order for s in seeds for a in arms]
    if set(rows) != set(ordered):
        raise ValueError('Combined results do not cover exact requested study grid')
    return dict(rows=[rows[key] for key in ordered],issue_order=list(issue_order),
                source_freeze_seals=seals,historical_admission=False)
