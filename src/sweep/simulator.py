"""Weekly bankroll simulator with fractional-Kelly stake + tax-cap split.

Per week:
  1. From qualifying picks, build per-week combos (combo_builder).
  2. For each combo, raw_stake = bankroll × 0.25 × kelly_full(p, payout).
  3. Cap raw_stake at ``per_combo_cap_frac × bankroll`` (default 0.5%).
  4. Round down to even yuan, ensure >= 2 yuan; else drop.
  5. Tax-cap split into multiple tickets if prize_per_ticket > 9999.
  6. After listing all combos, scale all stakes proportionally if total
     weekly stake > ``weekly_stake_cap_frac × bankroll``.
  7. Settle: each combo wins if ``all_hit`` -> payout = stake × payout_per_yuan.
  8. Update bankroll.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src.combo_optimizer.combo_math import kelly_fraction_full
from src.combo_optimizer.types import (
    MIN_STAKE_PER_TICKET,
    TAX_FREE_PRIZE_CAP,
)
from src.sweep.combo_builder import iter_weekly_combos, materialize_combos


def _floor_even(x: float) -> int:
    n = int(math.floor(max(0.0, x)))
    return n - (n % 2)


@dataclass
class SimulationResult:
    weekly: pd.DataFrame  # per-week metrics
    combos: pd.DataFrame  # all individual combos placed
    final_bankroll: float
    initial_bankroll: float


def simulate(
    qual: pd.DataFrame,
    n_legs: int,
    *,
    initial_bankroll: float = 100_000.0,
    kelly_fraction: float = 0.25,
    per_combo_cap_frac: float = 0.005,
    weekly_stake_cap_frac: float = 0.25,
    max_combos_per_week: int = 300,
    enumerate_threshold: int = 5000,
    seed: int = 7,
    test_only: bool = True,
) -> SimulationResult:
    """Run weekly simulation. If ``test_only=True``, only weeks in the
    test half of the dataset (期号 ≥ median) drive bankroll PnL — train
    weeks are skipped (they were used for niche selection)."""
    if test_only and len(qual):
        median_expect = qual["expect"].median()
        qual = qual[qual["expect"] >= median_expect].reset_index(drop=True)

    bankroll = initial_bankroll
    weekly_rows: list[dict] = []
    combo_rows: list[dict] = []

    for wk, ded, combos_idx in iter_weekly_combos(
        qual, n_legs,
        max_combos_per_week=max_combos_per_week,
        enumerate_threshold=enumerate_threshold,
        seed=seed,
    ):
        mat = materialize_combos(ded, combos_idx)
        if mat.empty:
            continue

        # Sizing — raw fractional-Kelly then per-combo cap.
        per_cap = per_combo_cap_frac * bankroll
        plans: list[dict] = []
        for i, row in mat.iterrows():
            payout = float(row["payout_per_yuan"])
            p = float(row["joint_p"])
            f = kelly_fraction_full(p, payout)
            raw_stake = bankroll * kelly_fraction * f
            if raw_stake <= 0:
                continue
            raw_stake = min(raw_stake, per_cap)

            # Tax-cap per ticket
            if payout <= 0:
                continue
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
            total_stake = stake_per_ticket * n_tickets
            plans.append(dict(
                week_key=wk,
                combo_idx=i,
                joint_p=p,
                joint_sp=float(row["joint_sp"]),
                payout_per_yuan=payout,
                all_hit=bool(row["all_hit"]),
                stake_per_ticket=stake_per_ticket,
                n_tickets=n_tickets,
                total_stake=total_stake,
                prize_per_ticket=stake_per_ticket * payout,
                kelly_f=f,
            ))

        if not plans:
            continue

        # Weekly cap: scale proportionally if total stake exceeds limit.
        weekly_cap = weekly_stake_cap_frac * bankroll
        total = sum(p["total_stake"] for p in plans)
        scale = 1.0
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
                    p["prize_per_ticket"] = new_st * p["payout_per_yuan"]
            plans = [p for p in plans if p["total_stake"] > 0]
            if not plans:
                continue

        # Settle
        week_stake = sum(p["total_stake"] for p in plans)
        week_payout = 0.0
        n_hits = 0
        for p in plans:
            if p["all_hit"]:
                week_payout += p["total_stake"] * p["payout_per_yuan"]
                n_hits += 1
            combo_rows.append(p)
        week_pnl = week_payout - week_stake
        bankroll += week_pnl

        weekly_rows.append(dict(
            week_key=wk,
            n_combos=len(plans),
            n_hits=n_hits,
            week_stake=week_stake,
            week_payout=week_payout,
            week_pnl=week_pnl,
            bankroll_end=bankroll,
            week_roi=week_pnl / week_stake if week_stake > 0 else 0.0,
        ))

        if bankroll <= 0:
            break

    weekly_df = pd.DataFrame(weekly_rows)
    combos_df = pd.DataFrame(combo_rows)
    return SimulationResult(
        weekly=weekly_df, combos=combos_df,
        final_bankroll=bankroll, initial_bankroll=initial_bankroll,
    )
