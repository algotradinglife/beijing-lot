"""Compare backtest at N=4 Kelly=1/16 across diversity_lambda values.

Tests if greedy diversity-aware selection materially changes the
8-year OOS results vs the old EV-only ranking.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dual_sweep.variants import build_archetype_a_qual
from src.sweep.simulator import simulate
from src.combo_optimizer.builder import (
    enumerate_combos,
    rank_combos,
    select_diverse_combos,
    filter_by_combo_ev,
)

# Patch sweep simulator to support diversity:
# The simulator builds combos via combo_builder.iter_weekly_combos which
# uses sampling/enumeration. Cleaner: patch combo_optimizer.builder.build_combos
# usage path. The src/sweep/ module bypasses this, so we need a different approach.

# Approach: monkey-patch combo selection in combo_optimizer.build_plan and re-run
# the dual_sweep simulator (which uses build_plan via phase5a).
#
# Actually the sweep.simulator does NOT use combo_optimizer.build_plan;
# it samples combos at the simulator level (random_sample / enumerate).
# So diversity_lambda would need plumbing into iter_weekly_combos.
#
# Simpler path: write a minimal Plan-B-aware simulator that:
#   1. Per week: enumerate all C(K, 4) combos from week's qualified picks
#   2. Apply diversity selection with given lambda
#   3. Stake each combo per Kelly + caps
#   4. Settle and compute weekly PnL

INITIAL = 100_000.0


def metrics(weekly_pnl, initial=INITIAL):
    if len(weekly_pnl) == 0:
        return None
    bankroll = initial + np.cumsum(weekly_pnl)
    bankroll = np.maximum(bankroll, 0.01)
    n = len(weekly_pnl)
    cum_roi = (bankroll[-1] - initial) / initial
    yrs = n / 52.0
    cagr = (bankroll[-1] / initial) ** (1.0 / max(yrs, 1e-6)) - 1.0
    pct = weekly_pnl / initial
    sharpe = (np.mean(pct) * 52) / (np.std(pct, ddof=1) * np.sqrt(52)) if len(pct) > 1 and np.std(pct) > 0 else 0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0
    return dict(final=float(bankroll[-1]), cum_roi=float(cum_roi),
                cagr=float(cagr), sharpe=float(sharpe),
                max_dd=float(max_dd), calmar=float(calmar),
                hit_rate=float((weekly_pnl > 0).mean()))


def run_with_diversity(qual, n_legs, kelly_fraction, diversity_lambda,
                        per_combo_cap_frac=0.005, weekly_cap_frac=0.25,
                        max_combos_per_week=300, seed=7, test_only=True):
    """Custom simulator with diversity-aware selection per week."""
    from src.combo_optimizer.types import Candidate, Combo
    import math

    if test_only:
        median_expect = qual["expect"].median()
        qual = qual[qual["expect"] >= median_expect].reset_index(drop=True)

    bankroll = INITIAL
    weekly_pnl = []

    for wk_key, wk_grp in qual.groupby("week_key"):
        # Build candidates per match (same-match dedup: keep highest leg_ev)
        wk_grp = wk_grp.sort_values("leg_ev", ascending=False)
        seen_match = set()
        wk_unique = []
        for _, r in wk_grp.iterrows():
            if r["match_id"] in seen_match:
                continue
            seen_match.add(r["match_id"])
            wk_unique.append(r)

        if len(wk_unique) < n_legs:
            weekly_pnl.append(0.0)
            continue

        # Top-K
        wk_unique = wk_unique[:14]

        # Build Candidate objects
        cands = []
        for r in wk_unique:
            cands.append(Candidate(
                match_id=r["match_id"], selection=int(r["option"]),
                p_hat=r["q_train"] / r["sp"], sp=float(r["sp"]),
            ))

        # Enumerate
        combos = enumerate_combos(cands, n_legs=n_legs)
        # No EV threshold here (diversity sim) — let stake-cap drop bad ones
        # Apply diversity
        if diversity_lambda > 0:
            selected = select_diverse_combos(combos, max_combos=max_combos_per_week,
                                              diversity_lambda=diversity_lambda)
        else:
            selected = rank_combos(combos, max_combos=max_combos_per_week)

        # Size each combo via fractional Kelly
        per_cap = per_combo_cap_frac * bankroll
        weekly_cap = weekly_cap_frac * bankroll
        plans = []
        for c in selected:
            o = c.payout_per_yuan  # = ∏SP × 0.65
            if o <= 1.0:
                continue
            f_kelly = (c.joint_p * o - 1) / (o - 1)
            if f_kelly <= 0:
                continue
            raw_stake = kelly_fraction * f_kelly * bankroll
            stake = min(raw_stake, per_cap)
            stake = math.floor(max(0.0, stake))
            stake = stake - (stake % 2)
            if stake < 2:
                continue
            # Settlement
            all_hit = all(leg.did_win == 1 for leg in [
                # Need did_win — get from wk_unique
            ])
            # Lookup did_win
            did_wins = []
            for leg in c.legs:
                # Find row in wk_unique matching this leg
                row = next((r for r in wk_unique if r["match_id"] == leg.match_id and int(r["option"]) == leg.selection), None)
                if row is None or pd.isna(row["did_win"]):
                    did_wins = None
                    break
                did_wins.append(int(row["did_win"]))
            if did_wins is None:
                continue
            all_hit = all(did_wins) == 1
            payout = stake * o if all(d == 1 for d in did_wins) else 0
            plans.append(dict(stake=stake, payout=payout))

        # Apply weekly cap proportionally
        total_stake = sum(p["stake"] for p in plans)
        if total_stake > weekly_cap:
            scale = weekly_cap / total_stake
            for p in plans:
                p["stake"] = math.floor(p["stake"] * scale)
                p["stake"] = p["stake"] - (p["stake"] % 2)
                # Recompute payout proportionally
                if p["payout"] > 0:
                    p["payout"] = p["payout"] * scale

        week_stake = sum(p["stake"] for p in plans)
        week_payout = sum(p["payout"] for p in plans)
        wk_pnl = week_payout - week_stake
        weekly_pnl.append(wk_pnl)
        bankroll = max(0.01, bankroll + wk_pnl)

    return np.array(weekly_pnl)


import pandas as pd


def main():
    print("Loading qualifying picks...")
    qual_a, _ = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}\n")

    print("Comparing diversity_lambda variants (N=4, Kelly=1/16):")
    print(f"{'λ':>6} {'final':>13} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} {'hit_rate':>8}")
    for lam in [0.0, 0.3, 0.5, 1.0, 2.0]:
        pnl = run_with_diversity(qual_a, n_legs=4, kelly_fraction=1/16,
                                  diversity_lambda=lam)
        m = metrics(pnl)
        if m is None:
            print(f"  λ={lam:.1f}: empty")
            continue
        print(f"  {lam:>4.1f}   {m['final']:>11,.0f}  {m['cagr']*100:>6.1f}%  "
              f"{m['sharpe']:>5.2f}  {m['max_dd']*100:>6.1f}%  {m['calmar']:>5.2f}  "
              f"{m['hit_rate']*100:>6.1f}%")


if __name__ == "__main__":
    main()
