#!/usr/bin/env python3
"""Independent retrospective accounting replay; no fitting or selection.

Usage: project-python scripts/check_n7_exchange_attribution.py SOURCE OUTPUT.
Reads explicit immutable CSVs and receipts, validates hashes and all group/plan
contributions and trim definitions. Prints a PASS receipt; never writes data.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

p = argparse.ArgumentParser()
p.add_argument('source', type=Path)
p.add_argument('output', type=Path)
a = p.parse_args()
receipt = json.loads((a.output / 'receipt.json').read_text())
for name, identity in receipt['source_files'].items():
    assert hashlib.sha256((a.source / name).read_bytes()).hexdigest() == identity
for name, identity in receipt['outputs'].items():
    assert hashlib.sha256((a.output / name).read_bytes()).hexdigest() == identity
for name, identity in receipt['implementation'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == identity
g = pd.read_csv(a.source / 'settled-groups.csv', dtype={'issue': str, 'sleeve_id': str})
rank_path = Path(receipt['ranks_path'])
assert hashlib.sha256(rank_path.read_bytes()).hexdigest() == receipt['ranks_sha256']
rank = pd.read_csv(rank_path, dtype={'issue': str, 'sleeve_id': str})
funded = pd.read_csv(a.source / 'funded.csv', dtype={'issue': str, 'sleeve_id': str})
rebuilt = funded.merge(rank[['issue','sleeve_id','actual_rank','actual_gross_cny']],
                       on=['issue','sleeve_id'], how='left', validate='many_to_one')
assert not rebuilt.isna().any().any()
rebuilt['hit'] = rebuilt.actual_rank <= rebuilt.depth
rebuilt['gross'] = np.where(rebuilt.hit, rebuilt.actual_gross_cny, 0)
rebuilt['net'] = rebuilt.gross - rebuilt.stake
group_keys = ['issue','arm','seed','sleeve_id']
gp = rebuilt.merge(g, on=group_keys, suffixes=('_expected',''), validate='one_to_one')
assert len(gp) == len(g) == len(rebuilt)
for field in set(rebuilt.columns) - set(group_keys):
    assert np.allclose(gp[field], gp[field+'_expected'], atol=1e-7, rtol=1e-12)
r = pd.read_csv(a.source / 'results.csv', dtype={'issue': str})
l = pd.read_csv(a.output / 'ledger.csv', dtype={'issue': str, 'sleeve_id': str})
trims = pd.read_csv(a.output / 'trims.csv')
adverse = pd.read_csv(a.output / 'adverse.csv')
totals = pd.read_csv(a.output / 'totals.csv')
actions = pd.read_csv(a.source / 'actions.csv', dtype={'issue': str, 'removed_id': str, 'added_ids': str})
freeze = json.loads((a.source / 'plans-frozen.json').read_text())
source = Path(freeze['config']['source_dir'])
prior = json.loads((source / 'plans-frozen.json').read_text())
assert hashlib.sha256((source / 'plans-frozen.json').read_bytes()).hexdigest() == freeze['source_freeze_sha256']
members = {}
for issue in r.issue.unique():
    name = f'replay-{issue}-42501.json.gz'
    assert hashlib.sha256((source / name).read_bytes()).hexdigest() == prior['files'][name]
    with gzip.open(source / name, 'rt') as stream:
        snapshot = json.load(stream)
    for option in snapshot['options']:
        members[issue, str(option['sleeve_id'])] = set(option['fixtures'])
keys = ['issue', 'arm', 'seed']
g = g.merge(r[keys + ['variant', 'budget_cny']], on=keys, validate='many_to_one')
verified = 0
for (budget, seed), plans in r.groupby(['budget_cny', 'seed']):
    b = g[(g.budget_cny == budget) & (g.seed == seed) & (g.variant == 'JOINT')]
    bp = plans[plans.variant == 'JOINT']
    for variant in ['EXCHANGE11', 'EXCHANGE12']:
        new = g[(g.budget_cny == budget) & (g.seed == seed) & (g.variant == variant)]
        paired = b.merge(new, on=['issue', 'sleeve_id'], how='outer', suffixes=('_base', '_new'), validate='one_to_one')
        expected = paired[['issue', 'sleeve_id']].copy()
        expected['role'] = np.where(paired.stake_base.isna(), 'added', np.where(paired.stake_new.isna(), 'removed', 'retained'))
        for field in ['stake', 'gross', 'net']:
            expected['delta_' + field] = paired[field + '_new'].fillna(0) - paired[field + '_base'].fillna(0)
        actual = l[(l.budget_cny == budget) & (l.seed == seed) & (l.variant == variant)]
        merged = expected.merge(actual, on=['issue', 'sleeve_id'], suffixes=('_expected', ''), validate='one_to_one')
        assert len(merged) == len(expected) == len(actual)
        assert (merged.role == merged.role_expected).all()
        for field in ['stake', 'gross', 'net']:
            assert np.allclose(merged['delta_' + field], merged['delta_' + field + '_expected'], atol=1e-7, rtol=1e-12)
        delta = plans.loc[plans.variant == variant, 'net'].sum() - bp.net.sum()
        assert np.isclose(expected.delta_net.sum(), delta, atol=1e-7, rtol=1e-12)
        reported = totals[(totals.budget_cny == budget) & (totals.seed == seed) & (totals.variant == variant)].iloc[0]
        assert np.isclose(reported.delta_net, delta, atol=1e-7, rtol=1e-12)
        for row in actual.itertuples():
            others = b[(b.issue == row.issue) & (b.sleeve_id != row.sleeve_id)]
            overlaps = [len(members[row.issue, row.sleeve_id] & members[row.issue, sid]) for sid in others.sleeve_id]
            if overlaps:
                assert np.isclose(row.mean_overlap, np.mean(overlaps))
            else:
                assert pd.isna(row.mean_overlap)
        for k in [1, 3, 5]:
            bt = bp.net.sum() - b.loc[b.net > 0, 'net'].nlargest(k).sum()
            nt = plans.loc[plans.variant == variant, 'net'].sum() - new.loc[new.net > 0, 'net'].nlargest(k).sum()
            row = trims[(trims.budget_cny == budget) & (trims.seed == seed) & (trims.variant == variant) & (trims.k == k)].iloc[0]
            assert np.isclose(nt - bt, row.delta_trimmed_net, atol=1e-7, rtol=1e-12)
            removed = paired.loc[expected.role == 'added', 'gross_new'].nlargest(k).sum()
            row = adverse[(adverse.budget_cny == budget) & (adverse.seed == seed) & (adverse.variant == variant) & (adverse.k == k)].iloc[0]
            assert np.isclose(delta - removed, row.stressed_delta_net, atol=1e-7, rtol=1e-12)
        # Apply actual logged set operations to original selections; captures
        # groups that enter and leave in intermediate steps without funding them.
        arm = plans.loc[plans.variant == variant, 'arm'].iloc[0]
        for issue in bp.issue:
            selected = set(b.loc[b.issue == issue, 'sleeve_id'])
            steps = actions[(actions.issue == issue) & (actions.seed == seed) & (actions.arm == arm)].sort_values('step')
            for step in steps.itertuples():
                if pd.notna(step.removed_id):
                    removed_id = str(int(float(step.removed_id)))
                    assert removed_id in selected
                    selected.remove(removed_id)
                added_ids = set(str(int(float(x))) for x in str(step.added_ids).split(','))
                assert not selected.intersection(added_ids)
                selected.update(added_ids)
            assert selected == set(new.loc[new.issue == issue, 'sleeve_id'])
            verified += 1
assert verified == 3600
print(json.dumps({'status': 'PASS', 'paired_plans': verified, 'group_rows': len(l),
                  'source_freeze_sha256': receipt['source_freeze_sha256'],
                  'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))
