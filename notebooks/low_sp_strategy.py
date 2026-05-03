"""Low-SP × short-combo strategy as a complement to high-SP archetype A.

Uses Archetype B niches (SP 3-4.5, q ≈ 1.07-1.20) with N=3 combos.
Tests with/without commission. Goal: figure out if this can serve as
a "high hit rate, low DD, deploy idle capital" overlay strategy.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from src.dual_sweep.archetype_b_niches import discover_archetype_b
from src.niche_analysis.sp_native import load_full_3sp, to_long
from equity_curve_default import simulate_with_stake, INITIAL
from diversity_strict_backtest import metrics


def build_archetype_b_qual():
    """Same as build_archetype_a_qual but for low-SP niches."""
    df = load_full_3sp()
    long = to_long(df)
    result = discover_archetype_b()
    # discover_archetype_b returns a tuple, the surv frame is one element
    if isinstance(result, tuple):
        surv = next(x for x in result if hasattr(x, "columns") and "stratum_str" in x.columns)
    else:
        surv = result

    # Apply niche labels: a leg qualifies if it matches any surviving niche stratum
    # surv has stratum_str like "option=0, sp_bucket=3.5-4.5, league_tier=Asian"
    # We need to label each leg row in `long` by whether it matches.

    # Add helper columns to long
    long["sp_bucket"] = long["sp"].apply(_sp_bucket)
    long["handicap_class"] = long["handicap"].abs().apply(_handicap_class)
    long["league_tier"] = long["league"].apply(_league_tier)

    # For each surviving niche, compute its q_train (for later Kelly)
    qual_rows = []
    for _, niche in surv.iterrows():
        stratum = niche["stratum_str"]
        constraints = _parse_stratum(stratum)
        mask = np.ones(len(long), dtype=bool)
        for col, val in constraints.items():
            mask &= (long[col].astype(str) == str(val))
        sub = long[mask].copy()
        sub["q_train"] = niche["train_mean_q"]
        sub["niche_id"] = stratum
        qual_rows.append(sub)

    if not qual_rows:
        return None
    import pandas as pd
    qual = pd.concat(qual_rows, ignore_index=True)
    # Dedup: same (match_id, option) might match multiple niches — keep highest q
    qual = qual.sort_values("q_train", ascending=False).drop_duplicates(
        subset=["match_id", "option"], keep="first"
    ).reset_index(drop=True)
    qual["leg_ev"] = qual["q_train"] * 0.65 - 1
    qual["p_train"] = qual["q_train"] / qual["sp"]
    qual["kickoff_ts"] = pd.to_datetime(qual["kickoff_ts"], errors="coerce")
    iso = qual["kickoff_ts"].dt.isocalendar()
    qual["iso_year"] = iso.year
    qual["iso_week"] = iso.week
    qual["week_key"] = qual["iso_year"].astype(str) + "-W" + qual["iso_week"].astype(str).str.zfill(2)
    qual["expect"] = qual["expect"].astype(int)
    return qual


def _sp_bucket(sp):
    if sp < 1.5: return "0-1.5"
    if sp < 2: return "1.5-2"
    if sp < 2.5: return "2-2.5"
    if sp < 3: return "2.5-3"
    if sp < 3.5: return "3-3.5"
    if sp < 4.5: return "3.5-4.5"
    if sp < 6: return "4.5-6"
    if sp < 8: return "6-8"
    return "8+"


def _handicap_class(h):
    if h == 0: return "h_unknown"
    if h == 1: return "h1"
    return "h2plus"


def _league_tier(league):
    top5 = {"英超", "德甲", "意甲", "西甲", "法甲"}
    asian = {"日职联", "日职乙", "韩K联", "中超", "中甲", "澳超", "K联赛", "K2联赛"}
    if league in top5: return "Top5EU"
    if league in asian: return "Asian"
    if league in {"英冠", "英甲", "英乙", "意乙", "西乙", "德乙", "法乙", "荷乙", "葡超", "苏超"}:
        return "LowerEU"
    if league in {"墨西联", "巴甲", "阿甲", "美职业", "巴拉甲"}: return "Americas"
    return "Other"


def _parse_stratum(s):
    """Parse 'option=0, sp_bucket=3.5-4.5, league_tier=Asian' → dict."""
    out = {}
    for part in s.split(","):
        k, v = part.strip().split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main():
    print("Building Archetype B (low-SP) qualifying picks...")
    qual_b = build_archetype_b_qual()
    if qual_b is None:
        print("No surviving niches; abort")
        return
    print(f"qual_b rows: {len(qual_b)}")
    print(f"Niches: {qual_b['niche_id'].nunique()}")
    print(f"Mean q: {qual_b['q_train'].mean():.3f}")
    print()

    print(f"{'Config':<40} {'final':>12} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>8} {'hit%':>6}")
    print("-" * 95)
    configs = [
        ("N=3, λ=0.5, K=1/16, no comm",     dict(n_legs=3, kelly_fraction=1/16, diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.0)),
        ("N=3, λ=0.5, K=1/16, +7% comm",   dict(n_legs=3, kelly_fraction=1/16, diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.07)),
        ("N=3, λ=0.5, K=1/8,  no comm",     dict(n_legs=3, kelly_fraction=1/8,  diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.0)),
        ("N=3, λ=0.5, K=1/8,  +7% comm",   dict(n_legs=3, kelly_fraction=1/8,  diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.07)),
        ("N=3, λ=0.5, K=1/4,  no comm",     dict(n_legs=3, kelly_fraction=1/4,  diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.0)),
        ("N=3, λ=0.5, K=1/4,  +7% comm",   dict(n_legs=3, kelly_fraction=1/4,  diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.07)),
        ("N=2, K=1/4,  +7% comm",            dict(n_legs=2, kelly_fraction=1/4,  diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.07)),
        ("N=4, K=1/4,  +7% comm",            dict(n_legs=4, kelly_fraction=1/4,  diversity_lambda=0.5, max_combos_per_week=100, commission_rate=0.07)),
    ]
    for name, cfg in configs:
        df = simulate_with_stake(qual_b, **cfg)
        m = metrics(df["week_pnl"].values)
        if m:
            avg_stake = df[df["week_stake"] > 0]["week_stake"].mean() if (df["week_stake"] > 0).any() else 0
            print(f"{name:<40} {m['final']:>11,.0f}  {m['cagr']*100:>5.1f}%  {m['sharpe']:>5.2f}  "
                  f"{m['max_dd']*100:>6.1f}%  {m['hit_rate']*100:>5.1f}%  avg_stake={avg_stake:>5.0f}")


if __name__ == "__main__":
    main()
