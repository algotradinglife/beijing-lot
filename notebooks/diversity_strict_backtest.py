"""Strict diversity-vs-no-diversity backtest.

Wraps the production sweep simulator components but replaces the
combo selection step with greedy diversity-aware ranking.
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dual_sweep.variants import build_archetype_a_qual
from src.sweep.combo_builder import _choose_one_per_match, build_combos_for_week, materialize_combos
from src.sweep.simulator import (
    MIN_STAKE_PER_TICKET,
    TAX_FREE_PRIZE_CAP,
    _floor_even,
    kelly_fraction_full,
)

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
                hit_rate=float((weekly_pnl > 0).mean()),
                n_weeks=n)


def select_diverse(combos_idx, materialized, max_combos, diversity_lambda):
    """Greedy diversity-aware selection.

    combos_idx: list of N-tuples of leg indices (into week_picks)
    materialized: DataFrame with columns joint_p, joint_sp, payout_per_yuan, all_hit
    Returns: list of (combo_idx, materialized_row) tuples in selection order.
    """
    if len(combos_idx) == 0:
        return [], []

    # Compute combo "edge" = expected return per yuan = p × payout - 1
    edges = materialized["joint_p"].to_numpy() * materialized["payout_per_yuan"].to_numpy() - 1.0

    if diversity_lambda <= 0:
        # Pure EV ranking
        order = np.argsort(-edges)[:max_combos]
        return [combos_idx[i] for i in order], [materialized.iloc[i] for i in order]

    leg_count: Counter = Counter()
    selected = []
    selected_rows = []
    available = list(range(len(combos_idx)))

    while available and len(selected) < max_combos:
        best_idx = -1
        best_score = -np.inf
        for i in available:
            penalty = sum(leg_count[l] for l in combos_idx[i])
            score = edges[i] - diversity_lambda * penalty
            if score > best_score:
                best_score = score
                best_idx = i
        if best_idx < 0:
            break
        selected.append(combos_idx[best_idx])
        selected_rows.append(materialized.iloc[best_idx])
        for l in combos_idx[best_idx]:
            leg_count[l] += 1
        available.remove(best_idx)

    return selected, selected_rows


def simulate_strict(
    qual,
    n_legs=4,
    *,
    initial=INITIAL,
    kelly_fraction=1/16,
    per_combo_cap_frac=0.005,
    weekly_stake_cap_frac=0.25,
    max_combos_per_week=300,
    enumerate_threshold=5000,
    diversity_lambda=0.0,
    test_only=True,
    seed=7,
):
    """Strict simulator matching production behavior + diversity_lambda."""
    if test_only and len(qual):
        median_expect = qual["expect"].median()
        qual = qual[qual["expect"] >= median_expect].reset_index(drop=True)

    bankroll = initial
    weekly_pnl = []
    rng = np.random.default_rng(seed)

    for wk, sub in qual.groupby("week_key", sort=True):
        ded = _choose_one_per_match(sub, rng)
        if len(ded) < n_legs:
            weekly_pnl.append(0.0)
            continue
        combos = build_combos_for_week(
            ded, n_legs,
            max_combos_per_week=max_combos_per_week,
            enumerate_threshold=enumerate_threshold,
            rng=rng,
        )
        if not combos:
            weekly_pnl.append(0.0)
            continue
        mat = materialize_combos(ded, combos)

        # Diversity-aware selection
        kept_idx, kept_rows = select_diverse(combos, mat, max_combos_per_week, diversity_lambda)
        if not kept_rows:
            weekly_pnl.append(0.0)
            continue

        # Stake each kept combo (matches production logic)
        per_cap = per_combo_cap_frac * bankroll
        plans = []
        for combo_legs, row in zip(kept_idx, kept_rows):
            payout = float(row["payout_per_yuan"])
            p = float(row["joint_p"])
            f = kelly_fraction_full(p, payout)
            raw_stake = bankroll * kelly_fraction * f
            if raw_stake <= 0 or payout <= 0:
                continue
            raw_stake = min(raw_stake, per_cap)
            cap_per_ticket = _floor_even(TAX_FREE_PRIZE_CAP / payout)
            if cap_per_ticket < MIN_STAKE_PER_TICKET:
                continue
            if raw_stake <= cap_per_ticket:
                stake = _floor_even(raw_stake)
                if stake < MIN_STAKE_PER_TICKET:
                    continue
                n_tickets = 1
                stake_per_ticket = stake
            else:
                n_tickets = max(1, math.ceil(raw_stake / cap_per_ticket))
                stake_per_ticket = cap_per_ticket
            plans.append(dict(
                stake_per_ticket=stake_per_ticket,
                n_tickets=n_tickets,
                total_stake=stake_per_ticket * n_tickets,
                payout_per_yuan=payout,
                all_hit=bool(row["all_hit"]),
            ))

        if not plans:
            weekly_pnl.append(0.0)
            continue

        # Weekly cap
        weekly_cap = weekly_stake_cap_frac * bankroll
        total = sum(p["total_stake"] for p in plans)
        if total > weekly_cap and total > 0:
            scale = weekly_cap / total
            for p in plans:
                new_st = _floor_even(p["stake_per_ticket"] * scale)
                if new_st < MIN_STAKE_PER_TICKET:
                    p["stake_per_ticket"] = 0
                    p["total_stake"] = 0
                else:
                    p["stake_per_ticket"] = new_st
                    p["total_stake"] = new_st * p["n_tickets"]
            plans = [p for p in plans if p["total_stake"] > 0]
            if not plans:
                weekly_pnl.append(0.0)
                continue

        # Settle
        week_stake = sum(p["total_stake"] for p in plans)
        week_payout = sum(
            p["total_stake"] * p["payout_per_yuan"] for p in plans if p["all_hit"]
        )
        wk_pnl = week_payout - week_stake
        weekly_pnl.append(wk_pnl)
        bankroll += wk_pnl
        if bankroll <= 0:
            break

    return np.array(weekly_pnl)


def main():
    print("Loading qualifying picks...")
    qual_a, _ = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}")

    max_combos_grid = [10, 25, 50, 100, 200, 500, 1001]
    lambda_grid = [0.0, 0.3, 1.0, 2.0]

    # Collect into a DataFrame for clear table output
    rows = []
    for mc in max_combos_grid:
        for lam in lambda_grid:
            pnl = simulate_strict(
                qual_a, n_legs=4, kelly_fraction=1/16,
                diversity_lambda=lam, test_only=True,
                max_combos_per_week=mc,
            )
            m = metrics(pnl)
            if m is None:
                continue
            rows.append({
                "max_combos": mc, "lambda": lam,
                "CAGR%": round(m["cagr"] * 100, 1),
                "Sharpe": round(m["sharpe"], 2),
                "MaxDD%": round(m["max_dd"] * 100, 1),
                "Calmar": round(m["calmar"], 2),
                "hit%": round(m["hit_rate"] * 100, 1),
                "final": m["final"],
            })
    df = pd.DataFrame(rows)
    out = "/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/diversity_strict_grid.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved to {out}\n")

    # Pivots for human reading
    pd.set_option("display.float_format", lambda x: f"{x:.2f}")
    pd.set_option("display.width", 200)
    for metric in ["CAGR%", "Sharpe", "MaxDD%", "Calmar"]:
        print(f"\n=== {metric} (rows = max_combos, cols = λ) ===")
        piv = df.pivot(index="max_combos", columns="lambda", values=metric)
        print(piv)

    # Best per-row
    print("\n=== Best λ per max_combos (by Sharpe) ===")
    for mc in max_combos_grid:
        sub = df[df["max_combos"] == mc].sort_values("Sharpe", ascending=False)
        if not len(sub):
            continue
        best = sub.iloc[0]
        print(f"  max_combos={mc:>4}: λ={best['lambda']:.1f}  "
              f"CAGR={best['CAGR%']:>5.1f}%  Sharpe={best['Sharpe']:.2f}  "
              f"MaxDD={best['MaxDD%']:>6.1f}%  Calmar={best['Calmar']:.2f}  "
              f"final={best['final']:>12,.0f}")


if __name__ == "__main__":
    main()
