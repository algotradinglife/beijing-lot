"""Paper forward-test harness for SP-drift mitigation (reuses replay_policy).

Pre-registered (do not change mid-test):
- FORWARD_START: only matches kicking off after this are scored (out-of-sample).
- HAIRCUT_MAP: per-SP-band drift_bias frozen at the GATE 1 estimates.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from src.sp_drift.replay import Policy

FORWARD_START = "2026-06-13"  # naive Beijing date; kickoffs after this are OOS

# Frozen GATE 1 per-band drift_bias (signed). Do NOT re-estimate during the test.
HAIRCUT_MAP = {"<3.5": 0.33, "3.5-4.5": -0.09, "4.5-5": -0.21, "5-8": -0.36, ">8": -0.81}

WINDOW_MTK = 180.0  # 3h, mirrors the live kickoff_window_hours=3 (MTK proxy)


def forward_panel(panel: pd.DataFrame, min_kickoff: str) -> pd.DataFrame:
    """Keep only rows whose kickoff_ts is after min_kickoff (out-of-sample slice).
    kickoff_ts is a naive Beijing ISO string, so lexicographic compare is correct."""
    return panel[panel["kickoff_ts"] > min_kickoff].copy()


def build_arms(baseline_mtk: float, haircut_map: dict) -> List[Tuple[str, Policy]]:
    """Three arms: C0 control (decide ~18h-out, no haircut), C1 window-only,
    C2 window + frozen haircut."""
    return [
        ("C0", Policy(mtk_target=baseline_mtk)),
        ("C1", Policy(mtk_target=WINDOW_MTK)),
        ("C2", Policy(mtk_target=WINDOW_MTK, haircut=haircut_map)),
    ]
