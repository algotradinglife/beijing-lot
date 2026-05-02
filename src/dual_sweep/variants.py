"""Define the 14 strategy variants and assemble qualifying picks for each.

Archetype A: SP ∈ [5, 8] niches surviving on the primary bucket scheme
             (re-uses sweep.qualifying_picks with default config; we then
             FILTER picks to mean_sp ≥ 5 niches only).
Archetype B: low-SP niches surviving on the [1.5, 4.5] scheme
             (Track 1, archetype_b_niches.discover_archetype_b).

A "variant" = (n_legs, archetype). 7 N values × 2 archetypes = 14 variants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from src.dual_sweep.archetype_b_niches import (
    SP_BUCKETS_B,
    discover_archetype_b,
    to_long_b,
)
from src.niche_analysis.sp_native import (
    NICHE_DIMS,
    load_full_3sp,
    to_long,
)
from src.sweep.qualifying_picks import (
    label_qualifying,
    select_surviving_niches,
)


N_LEG_VALUES: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8)


@dataclass
class VariantData:
    archetype: str  # "A" or "B"
    n_legs: int
    qual: pd.DataFrame  # qualifying picks (long form, has did_win, p_train, sp)
    surv_niches: pd.DataFrame
    notes: str = ""

    @property
    def name(self) -> str:
        return f"N={self.n_legs}_{self.archetype}"


# ---------------------------------------------------------------------------
# Archetype A: high-SP qualifying picks (SP ∈ [5, 8])

def build_archetype_a_qual(csv_path: Optional[str] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (qual, surv) for Archetype A — mean_sp ∈ [5, 8] surviving niches."""
    df = load_full_3sp(csv_path) if csv_path else load_full_3sp()
    long = to_long(df)
    surv = select_surviving_niches(long)
    # restrict niches by their mean sp bucket — keep ones that map to SP ~ [5, 8]
    # The "5-8" sp bucket name is exact in the primary scheme.
    if "d_sp_bucket" in surv.columns:
        mask = surv["d_sp_bucket"].isin(["5-8"]) | surv["d_sp_bucket"].isna()
        # niches without sp_bucket dim are general buckets; filter by stratum_str
        # to require either explicit "5-8" or no sp_bucket dim. Then we still
        # restrict picks themselves to sp ∈ [5, 8] downstream.
        surv = surv[mask].reset_index(drop=True)
    qual = label_qualifying(long, surv)
    # Final restriction: rows with sp ∈ [5, 8]
    qual = qual[(qual["sp"] >= 5.0) & (qual["sp"] < 8.0)].reset_index(drop=True)
    qual = _attach_week_keys(qual)
    return qual, surv


def build_archetype_b_qual(csv_path: Optional[str] = None) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Return (qual, surv, threshold_used) for Archetype B."""
    df = load_full_3sp(csv_path) if csv_path else load_full_3sp()
    long = to_long_b(df)
    # We need survival niches: we can call discover_archetype_b which loads/long
    # again. To avoid a duplicate load, re-compute here off of `long`.
    surv, thr = discover_archetype_b(csv_path=csv_path)
    qual = label_qualifying(long, surv)
    # Restrict picks to SP ∈ [1.5, 4.5]
    qual = qual[(qual["sp"] >= 1.5) & (qual["sp"] < 4.5)].reset_index(drop=True)
    qual = _attach_week_keys(qual)
    return qual, surv, thr


def _attach_week_keys(qual: pd.DataFrame) -> pd.DataFrame:
    qual = qual.copy()
    qual["kickoff_ts"] = pd.to_datetime(qual["kickoff_ts"], errors="coerce")
    qual = qual.dropna(subset=["kickoff_ts"]).reset_index(drop=True)
    iso = qual["kickoff_ts"].dt.isocalendar()
    qual["iso_year"] = iso["year"].astype(int)
    qual["iso_week"] = iso["week"].astype(int)
    qual["week_key"] = qual["iso_year"] * 100 + qual["iso_week"]
    return qual


def build_all_variants(
    csv_path: Optional[str] = None,
) -> tuple[list[VariantData], dict]:
    """Build all 14 variants. Returns (variants, info_dict)."""
    qa, surv_a = build_archetype_a_qual(csv_path)
    qb, surv_b, thr_b = build_archetype_b_qual(csv_path)
    variants: list[VariantData] = []
    for n in N_LEG_VALUES:
        variants.append(VariantData(
            archetype="A", n_legs=n, qual=qa, surv_niches=surv_a,
            notes="SP[5-8]",
        ))
        variants.append(VariantData(
            archetype="B", n_legs=n, qual=qb, surv_niches=surv_b,
            notes=f"SP[1.5-4.5] · {thr_b}",
        ))
    info = dict(
        n_a_picks=int(len(qa)),
        n_b_picks=int(len(qb)),
        n_a_niches=int(len(surv_a)),
        n_b_niches=int(len(surv_b)),
        archetype_b_threshold=thr_b,
    )
    return variants, info
