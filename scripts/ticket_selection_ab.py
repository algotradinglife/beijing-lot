#!/usr/bin/env python3
'''A/B: does choosing the bought tickets by expected payout beat choosing them by probability?

Reads the frozen sleeve enumerations (probability, estimated_payout, states) and compares,
at IDENTICAL ticket count and stake:

  baseline  top-N tuples by model probability      (what the frozen portfolio does)
  treatment top-N tuples by expected payout       (model probability x settled payout)

Both are scored on the same observable: whether the settled 7-tuple is among the bought
tickets.  estimated_payout is a per-fixture odds proxy (DIAGNOSTIC_MARKET_INVERSE_Q_NOT_OFFICIAL_SP),
so the treatment arm is a MODEL-EXPECTATION experiment; it is not a cash ROI estimate.
'''
from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

BUNDLE_GLOB = 'runtime/state/issue425-input-v1/bundles/*.json.gz'
TOP_N_RE = re.compile(r'^TOP(\d+)_PROB$')


def iter_sleeves(files: list[Path]):
    for path in files:
        with gzip.open(path, 'rt') as handle:
            bundle = json.load(handle)
        for sleeve in bundle['sleeves']:
            yield bundle['issue'], sleeve


def bought_set(prob: np.ndarray, pay: np.ndarray, n: int, arm: str) -> np.ndarray:
    score = prob if arm == 'PROB' else prob * pay
    return np.argsort(-score)[:n]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', default='/run/media/drwho1985/Sandisk/data/beijing-lot', type=Path)
    parser.add_argument('--output', default='.tmpwork/ticket_selection_ab.csv', type=Path)
    args = parser.parse_args(argv)

    files = sorted(args.data_root.glob(BUNDLE_GLOB))
    if not files:
        raise SystemExit(f'no sleeve bundles under {args.data_root}')

    rows = []
    for issue, sleeve in iter_sleeves(files):
        enum = sleeve['enumeration']
        params = sleeve['options']['PROB']['parameters']
        match = TOP_N_RE.match(params['kind'])
        if match is None:
            raise SystemExit(f'unexpected PROB kind {params["kind"]!r}')
        n = int(match.group(1))
        prob = np.asarray(enum['probability'], dtype=float)
        pay = np.asarray(enum['estimated_payout'], dtype=float)
        states = np.asarray(enum['states'], dtype=int)
        settled = np.asarray(enum['states'][int(sleeve['settled_index'])], dtype=int) \
            if 'settled_index' in sleeve else None

        arm_sets = {arm: bought_set(prob, pay, n, arm) for arm in ('PROB', 'EV')}
        record = {'issue': issue, 'sleeve': sleeve['id'], 'n_tickets': n, 'stake_cny': n * enum['unit_cny']}
        for arm, idx in arm_sets.items():
            record[f'coverage_{arm}'] = float(prob[idx].sum())
            record[f'expected_gross_{arm}'] = float((prob[idx] * pay[idx]).sum())
            record[f'expected_roi_{arm}'] = (record[f'expected_gross_{arm}'] - record['stake_cny']) / record['stake_cny']
        record['expected_roi_delta'] = record['expected_roi_EV'] - record['expected_roi_PROB']
        rows.append(record)

    frame = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)

    print(frame[['coverage_PROB', 'coverage_EV', 'expected_roi_PROB', 'expected_roi_EV']].mean().round(6).to_string())
    print('sleeves', len(frame), 'cells', len(files))
    print('EV lifts model ROI on', int((frame.expected_roi_delta > 0).sum()), 'of', len(frame), 'sleeves')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())