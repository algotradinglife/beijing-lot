#!/usr/bin/env python3
"""Strategy attribution: where the single-leg edge disappears in the 7x1 baskets.

Reads only sealed audits plus the DC-rebased fixture probabilities produced by
scripts/rebase_handicap_line_gap_dc.py. Needs no pre-match SP of any kind.

Data contracts consumed:
  audits/joint-basket-oos-v1/{legs,baskets,basket_gross,returns}.csv
  audits/handicap-line-gap-v1/inputs.json.gz   (net-goal grids, handicap-independent)
  .tmpwork/handicap_line_gap_dc.csv            (DC q_W/q_D/q_L per fixture)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PAYOUT_FACTOR = 0.65
UNIT_CNY = 2.0
LEGS_PER_TICKET = 7


def load_dc_fixtures(path: Path) -> pd.DataFrame:
    dc = pd.read_csv(path, dtype={'issue': str, 'provider_id': str})
    dc['key'] = dc['issue'] + '_' + dc['slot'].astype(str)
    return dc


def load_basket_audit(root: Path) -> dict[str, pd.DataFrame]:
    legs = pd.read_csv(root / 'legs.csv', dtype={'issue': str, 'provider_id': str})
    legs['key'] = legs['issue'] + '_' + legs['slot'].astype(str)
    baskets = pd.read_csv(root / 'baskets.csv', dtype={'issue': str}).rename(
        columns={'group': 'basket'}
    )
    gross = pd.read_csv(root / 'basket_gross.csv', dtype={'issue': str})
    returns = pd.read_csv(root / 'returns.csv', dtype={'issue': str})
    return {'legs': legs, 'baskets': baskets, 'gross': gross, 'returns': returns}


def covered_set_rank(leg_q: np.ndarray, settled: np.ndarray) -> int:
    '''Rank of the settled 7-tuple inside the joint 3^7 ordering of leg_q.'''
    import itertools

    probs = np.array(
        [
            np.prod([leg_q[i, t - 1] for i, t in enumerate(tup)])
            for tup in itertools.product((1, 2, 3), repeat=LEGS_PER_TICKET)
        ]
    )
    order = np.argsort(-probs)
    tuples = list(itertools.product((1, 2, 3), repeat=LEGS_PER_TICKET))
    pos = tuples.index(tuple(int(x) for x in settled))
    return int(np.flatnonzero(order == pos)[0]) + 1


def covered_set_top_probability(leg_q: np.ndarray) -> float:
    return float(np.prod(leg_q.max(axis=1)))


def realised_return(frame: pd.DataFrame, mask: pd.Series) -> dict[str, float]:
    sub = frame[mask]
    stake = float((sub['tickets'] * UNIT_CNY).sum())
    gross = float(sub.loc[sub['hit'], 'gross_if_hit'].sum())
    return {
        'baskets': int(len(sub)),
        'stake_cny': stake,
        'gross_cny': gross,
        'roi': (gross - stake) / stake if stake else float('nan'),
        'hit_rate': float(sub['hit'].mean()) if len(sub) else float('nan'),
    }


def leg_edge_table(legs: pd.DataFrame) -> pd.DataFrame:
    '''Gross edge per leg: E[payout] / stake - 1 = q_selected * SP_selected * factor^(1/7).'''
    raise NotImplementedError(
        'Requires pre-match SP; the settlement store holds only the settled winner SP.'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--data-root',
        default='/run/media/drwho1985/Sandisk/data/beijing-lot',
        type=Path,
    )
    parser.add_argument('--dc-fixtures', default='.tmpwork/handicap_line_gap_dc.csv', type=Path)
    parser.add_argument('--output', default='.tmpwork/strategy_attribution.csv', type=Path)
    args = parser.parse_args(argv)

    audit = load_basket_audit(args.data_root / 'audits' / 'joint-basket-oos-v1')
    dc = load_dc_fixtures(args.dc_fixtures)
    qcols = ['q_W', 'q_D', 'q_L']

    legs = audit['legs'].merge(dc[['key', *qcols]], on='key', how='left')
    complete = legs['q_W'].notna()
    legs = legs[complete].copy()
    legs['q_selected'] = np.where(
        legs['outcome'] == 1, legs['q_W'], np.where(legs['outcome'] == 2, legs['q_D'], legs['q_L'])
    )
    legs['q_max'] = legs[qcols].max(axis=1)
    legs['is_argmax'] = (legs[qcols].to_numpy().argmax(axis=1) + 1) == legs['outcome'].to_numpy()

    grouped = legs.groupby(['issue', 'basket'])
    sizes = grouped.size()
    full = sizes[sizes == LEGS_PER_TICKET].index
    legs = legs.set_index(['issue', 'basket']).loc[full].reset_index()

    agg = legs.groupby(['issue', 'basket']).agg(
        p_selected=('q_selected', lambda s: float(np.prod(s))),
        p_argmax=('q_max', lambda s: float(np.prod(s))),
    ).reset_index()

    frame = (
        agg.merge(
            audit['baskets'][['issue', 'basket', 'hit', 'mass', 'tickets']].rename(
                columns={'tickets': 'tickets'}
            ),
            on=['issue', 'basket'],
            how='inner',
        )
        .merge(
            audit['gross'].rename(columns={'tickets': 'tickets_gross'}),
            on=['issue', 'basket'],
            how='left',
            validate='one_to_one',
        )
    )
    if not (frame['tickets'] == frame['tickets_gross']).all():
        raise ValueError('basket tickets disagree between baskets.csv and basket_gross.csv')

    gap = float(frame['p_selected'].sum())
    hits = int(frame['hit'].sum())
    overall = realised_return(frame, pd.Series(True, index=frame.index))

    report = {
        'baskets_analysed': int(len(frame)),
        'actual_hits': hits,
        'expected_hits_independent': gap,
        'hit_rate_over_independent': hits / gap if gap else float('nan'),
        'overall_roi': overall['roi'],
        'mean_leg_q_selected': float(legs['q_selected'].mean()),
        'mean_leg_q_max': float(legs['q_max'].mean()),
        'argmax_leg_share': float(legs['is_argmax'].mean()),
    }

    frame.to_csv(args.output, index=False)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())