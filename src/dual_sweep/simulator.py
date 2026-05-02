"""Bankroll simulator wrapper for the dual-archetype sweep.

Re-uses ``src.sweep.simulator.simulate`` but exposes a ``time_window``
filter (期号 range) so we can run sub-period sims without compounding
across periods.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from src.sweep.simulator import SimulationResult, simulate


def simulate_window(
    qual: pd.DataFrame,
    n_legs: int,
    *,
    initial_bankroll: float = 100_000.0,
    expect_lo: Optional[int] = None,
    expect_hi: Optional[int] = None,
    test_only: bool = False,
    kelly_fraction: float = 0.25,
    per_combo_cap_frac: float = 0.005,
    weekly_stake_cap_frac: float = 0.25,
    max_combos_per_week: int = 300,
    seed: int = 7,
) -> SimulationResult:
    """Simulate over a 期号 window (inclusive lo, exclusive hi)."""
    if qual.empty:
        return simulate(qual, n_legs, initial_bankroll=initial_bankroll,
                        test_only=False, seed=seed)
    sub = qual
    if expect_lo is not None:
        sub = sub[sub["expect"] >= expect_lo]
    if expect_hi is not None:
        sub = sub[sub["expect"] < expect_hi]
    sub = sub.reset_index(drop=True)
    return simulate(
        sub, n_legs,
        initial_bankroll=initial_bankroll,
        kelly_fraction=kelly_fraction,
        per_combo_cap_frac=per_combo_cap_frac,
        weekly_stake_cap_frac=weekly_stake_cap_frac,
        max_combos_per_week=max_combos_per_week,
        seed=seed,
        test_only=test_only,
    )
