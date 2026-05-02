"""Track 3 — split 8 years into 4 sub-periods. Each is a fresh 10万 sim.

We define sub-periods by 期号 prefix (期号 starts with 'YYMM##').
Buckets:
  P1: 2018-2020  → expect in [180000, 200000)
  P2: 2020-2022  → expect in [200000, 220000)
  P3: 2022-2024  → expect in [220000, 240000)
  P4: 2024-2026  → expect in [240000, 260000)
"""
from __future__ import annotations

import pandas as pd

from src.dual_sweep.metrics import full_metrics
from src.dual_sweep.simulator import simulate_window


SUB_PERIODS = [
    ("2018-2020", 180000, 200000),
    ("2020-2022", 200000, 220000),
    ("2022-2024", 220000, 240000),
    ("2024-2026", 240000, 260000),
]


def run_sub_periods(qual: pd.DataFrame, n_legs: int, label: str) -> pd.DataFrame:
    rows = []
    for name, lo, hi in SUB_PERIODS:
        sim = simulate_window(
            qual, n_legs,
            initial_bankroll=100_000.0,
            expect_lo=lo, expect_hi=hi,
            test_only=False,
        )
        m = full_metrics(sim, f"{label}__{name}")
        m["period"] = name
        m["n_legs"] = n_legs
        rows.append(m)
    return pd.DataFrame(rows)
