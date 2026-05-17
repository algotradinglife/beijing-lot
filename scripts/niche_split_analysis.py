"""Step 1 & 2 — investigate cup vs league split + draw niches.

Step 1: Classify every match into competition_type ∈ {cup, league, intl}.
Re-evaluate the existing 11 surviving Archetype-B niches by re-computing
their train/test q on each competition_type subset. If a niche's
test_mean_q diverges materially across types (e.g. one subset stays >1.07
while another collapses to <1.0), the niche should be split — replaced
with comp-type-specific rules in `niches_default.json`.

Step 2: Re-run niche mining with a 4-dim grid that includes
`comp_type`, looking specifically for surviving option=1 (draw) niches.
Surviving = train_q_ci_lo > 1.064 AND test_q > 1.064 AND k_test >= 30.

Outputs (printed + CSVs):
  data/raw/niche_split_step1.csv  — per-niche train/test q by comp_type
  data/raw/niche_split_step2.csv  — surviving draw niches with comp_type
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.niche_analysis.sp_native import (  # noqa: E402
    enumerate_niches,
    load_full_3sp,
    split_train_test,
    survival_test,
    RETURN_RATE,
    _bootstrap_q_ci,
)
# Existing surviving niches were mined with alt SP buckets — must reuse
# the same bucket scheme to reproduce them.
from src.dual_sweep.archetype_b_niches import to_long_b as to_long  # noqa: E402


# ---------------------------------------------------------------------------
# Competition-type classifier
# ---------------------------------------------------------------------------
INTL_KEYWORDS = ("友谊", "预选", "锦标")  # 国际友谊, 欧洲预选, 亚洲预选, 南美预选, 亚预选, 北美预选, 球会友谊, 友谊赛, U23亚锦赛 …


def classify_comp_type(league: str | None) -> str:
    if league is None or (isinstance(league, float) and not np.isfinite(league)):
        return "league"
    s = str(league)
    if "杯" in s:
        return "cup"
    for kw in INTL_KEYWORDS:
        if kw in s:
            return "intl"
    return "league"


# ---------------------------------------------------------------------------
# Step 1 — split existing niches by comp_type
# ---------------------------------------------------------------------------
EXISTING_NICHES_CSV = ROOT / "data" / "raw" / "archetype_B_niches.csv"


def _norm_val(v) -> str:
    """Normalise a stratum value for string comparison. Pandas may have
    parsed `d_option` "0" as float 0.0 — strip the trailing ".0"."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def filter_long(long: pd.DataFrame, stratum: dict) -> pd.DataFrame:
    mask = np.ones(len(long), dtype=bool)
    for k, v in stratum.items():
        if pd.isna(v):
            continue
        col_vals = long[k].astype(str).values
        mask &= (col_vals == _norm_val(v))
    return long[mask]


def step1_split_existing_niches(long_train: pd.DataFrame,
                                  long_test: pd.DataFrame) -> pd.DataFrame:
    df = pd.read_csv(EXISTING_NICHES_CSV)
    rows = []
    for _, r in df.iterrows():
        # Reconstruct the stratum dict from d_* columns
        stratum = {}
        for col in ("d_option", "d_sp_bucket", "d_handicap_class", "d_league_tier"):
            v = r.get(col)
            if pd.notna(v):
                stratum[col[2:]] = v  # strip 'd_'

        for ct in ("cup", "league", "intl"):
            substratum = dict(stratum)
            sub_train_all = filter_long(long_train, stratum)
            sub_test_all = filter_long(long_test, stratum)
            sub_train = sub_train_all[sub_train_all["comp_type"] == ct]
            sub_test = sub_test_all[sub_test_all["comp_type"] == ct]
            if len(sub_train) == 0:
                continue
            n_tr = len(sub_train)
            k_tr = int(sub_train["did_win"].sum())
            q_tr = float(sub_train["q_obs"].mean()) if n_tr else float("nan")
            ci_lo_tr, _ = _bootstrap_q_ci(sub_train["q_obs"].values, n_boot=300)
            n_te = len(sub_test)
            k_te = int(sub_test["did_win"].sum()) if n_te else 0
            q_te = float(sub_test["q_obs"].mean()) if n_te else float("nan")
            ci_lo_te, _ = _bootstrap_q_ci(sub_test["q_obs"].values, n_boot=300) if n_te else (float("nan"), float("nan"))

            # Original whole-niche q (across all comp_types)
            q_full_train = float(sub_train_all["q_obs"].mean())
            q_full_test = float(sub_test_all["q_obs"].mean())

            rows.append(dict(
                niche=r["stratum_str"],
                comp_type=ct,
                full_train_q=q_full_train,
                full_test_q=q_full_test,
                comp_train_n=n_tr, comp_train_k=k_tr,
                comp_train_q=q_tr, comp_train_q_ci_lo=ci_lo_tr,
                comp_test_n=n_te, comp_test_k=k_te,
                comp_test_q=q_te, comp_test_q_ci_lo=ci_lo_te,
                comp_share_of_train=n_tr / max(1, len(sub_train_all)),
            ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 2 — discover draw niches with comp_type added
# ---------------------------------------------------------------------------
def step2_draw_niche_mining(long: pd.DataFrame) -> pd.DataFrame:
    """Mine niches restricted to option=1 (draw), with comp_type in the grid."""
    long_d = long[long["option"] == "1"].copy()
    train, test = split_train_test(long_d)
    # Add comp_type as a 5th dim
    dims = ["sp_bucket", "handicap_class", "league_tier", "comp_type"]

    train_niches = enumerate_niches(
        train, dims=dims,
        min_n=150, min_k=30,
        max_combo_size=3, n_boot=200,
    )
    if train_niches.empty:
        print("Step 2: no train niches met min_n/min_k.")
        return pd.DataFrame()
    print(f"Step 2: {len(train_niches)} train niches enumerated. "
          f"top train_mean_q heads:")
    print(train_niches.sort_values("train_mean_q" if "train_mean_q" in train_niches.columns else "mean_q",
                                    ascending=False).head(8).to_string())
    surv = survival_test(
        train_niches, test,
        is_q_ci_lo_min=1.05,  # slightly relaxed for draws (sparser sample)
        is_n_min=150, is_k_min=30,
        oos_q_min=1.05, oos_k_min=20,
    )
    surv = surv[surv["survived"]].copy().reset_index(drop=True)
    keep = [c for c in train_niches.columns if c.startswith("d_")]
    if not surv.empty and keep:
        surv = surv.merge(train_niches[["stratum_str"] + keep],
                          on="stratum_str", how="left")
    return surv


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main() -> int:
    print("Loading 3SP dataset…")
    df = load_full_3sp()
    df["comp_type"] = df["league"].map(classify_comp_type)
    print(f"rows: {len(df):,}  matches: {df['match_id'].nunique():,}")
    ct_counts = df["comp_type"].value_counts()
    print("comp_type counts:")
    print(ct_counts.to_string())
    print()

    long = to_long(df)
    # Re-attach comp_type to long (since to_long drops it)
    long = long.merge(df[["match_id", "comp_type"]], on="match_id", how="left")
    train, test = split_train_test(long)
    print(f"train rows {len(train):,}  test rows {len(test):,}")

    # ---- Step 1 ----
    print("\n=== STEP 1: existing 11 niches split by comp_type ===")
    step1 = step1_split_existing_niches(train, test)
    out1 = ROOT / "data" / "raw" / "niche_split_step1.csv"
    step1.to_csv(out1, index=False)
    print(f"wrote {out1}")
    # Print a digest
    print()
    digest = []
    for niche, g in step1.groupby("niche"):
        # Compare per-comp test_q vs full test_q
        full_te = g["full_test_q"].iloc[0]
        diverged = []
        for _, r in g.iterrows():
            if r["comp_test_n"] >= 50:
                delta = r["comp_test_q"] - full_te
                if abs(delta) > 0.05:
                    diverged.append(f"{r['comp_type']}: q={r['comp_test_q']:.3f} ({r['comp_test_n']} legs, Δ{delta:+.3f})")
        digest.append((niche, full_te, diverged))
    print(f"{'niche':<60} full_test_q  divergent comp_types")
    for niche, full_te, dv in digest:
        print(f"  {niche[:58]:<58}  {full_te:.3f}        {' | '.join(dv) if dv else '(no notable split)'}")

    # ---- Step 2 ----
    print("\n=== STEP 2: mine draw (option=1) niches with comp_type ===")
    step2 = step2_draw_niche_mining(long)
    out2 = ROOT / "data" / "raw" / "niche_split_step2.csv"
    step2.to_csv(out2, index=False)
    print(f"wrote {out2}")
    if step2.empty:
        print("→ NO surviving draw niches found at relaxed thresholds.")
    else:
        print(f"→ {len(step2)} surviving draw niche(s):")
        print(step2.to_string())

    return 0


if __name__ == "__main__":
    sys.exit(main())
