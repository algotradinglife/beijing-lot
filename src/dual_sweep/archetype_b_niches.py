"""Track 1 — discover Archetype B (low-SP, low-q-but-survives) niches.

Re-runs the OOS niche analysis using sp_native, but with SP buckets
constrained to [1.5, 4.5]. Stratifies by
(option × handicap_class × league_tier × sp_bucket) and applies a
train/test survival test on per-leg q.

Output: surviving low-SP niches saved to
``data/raw/archetype_B_niches.csv``.
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np
import pandas as pd

from src.niche_analysis.sp_native import (
    enumerate_niches,
    load_full_3sp,
    split_train_test,
    survival_test,
    to_long,
)


SP_BUCKETS_B = [
    ("1.5-2", 1.5, 2.0),
    ("2-2.5", 2.0, 2.5),
    ("2.5-3", 2.5, 3.0),
    ("3-3.5", 3.0, 3.5),
    ("3.5-4.5", 3.5, 4.5),
]


def _bucket_sp_b(sp: float) -> str:
    if sp is None or not np.isfinite(sp) or sp < 1.5:
        return "na"
    for name, lo, hi in SP_BUCKETS_B:
        if lo <= sp < hi:
            return name
    return "na"


def to_long_b(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot wide → long with low-SP-only buckets."""
    long = to_long(df)  # primary buckets, but we'll override
    long["sp_bucket"] = long["sp"].map(_bucket_sp_b)
    return long[long["sp_bucket"] != "na"].reset_index(drop=True)


def discover_archetype_b(
    csv_path: Optional[str] = None,
    *,
    min_n: int = 200,
    min_k: int = 30,
    q_ci_lo_min: float = 1.064,
    oos_q_min: float = 1.064,
    permissive_q_min: float = 1.040,
    max_combo_size: int = 3,
    seed: int = 42,
) -> tuple[pd.DataFrame, str]:
    """Returns (surviving_df, threshold_used)."""
    df = load_full_3sp(csv_path) if csv_path else load_full_3sp()
    long = to_long_b(df)
    train, test = split_train_test(long)
    train_niches = enumerate_niches(
        train,
        min_n=min_n, min_k=min_k,
        max_combo_size=max_combo_size, n_boot=200, seed=seed,
    )

    def _try(thr_train: float, thr_test: float) -> pd.DataFrame:
        s = survival_test(
            train_niches, test,
            is_q_ci_lo_min=thr_train, is_n_min=min_n, is_k_min=min_k,
            oos_q_min=thr_test, oos_k_min=min_k,
        )
        s = s[s["survived"]].copy().reset_index(drop=True)
        keep = [c for c in train_niches.columns if c.startswith("d_")]
        s = s.merge(train_niches[["stratum_str"] + keep],
                    on="stratum_str", how="left")
        return s

    surv = _try(q_ci_lo_min, oos_q_min)
    threshold = f"q_ci_lo>{q_ci_lo_min}, oos_q>{oos_q_min}"
    if surv.empty:
        surv = _try(permissive_q_min, permissive_q_min)
        threshold = (f"PERMISSIVE: q_ci_lo>{permissive_q_min}, "
                     f"oos_q>{permissive_q_min}")
    return surv, threshold


def save_archetype_b(out_csv: str, surv: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    surv.to_csv(out_csv, index=False)


if __name__ == "__main__":
    surv, thr = discover_archetype_b()
    print(f"Threshold used: {thr}")
    print(f"# surviving Archetype B niches: {len(surv)}")
    print(surv.head(20))
    save_archetype_b(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "raw", "archetype_B_niches.csv",
        ),
        surv,
    )
