"""Compare leg-level hit rate / ROI for three pick policies on the 8-year dataset:

  STRAT  — our niche-qualified pick (whichever of 3/1/0 passes the rule)
  INVERSE — among the *other* two options not picked by STRAT, pick the
            highest-SP one (i.e., the "least likely by pool money")
  FAVORITE — always pick the lowest-SP option (most-bet by the pool)

For each policy we compute:
  - n legs evaluated (matches where the policy emits a pick)
  - hit rate (fraction of legs that won)
  - implied probability from SP: 1 / sp / 0.65 (fair prob)
  - q ratio = hit_rate / implied_prob (>1 means our edge is real, <1 means biased)
  - ROI per yuan staked = mean(0.65 * sp if hit else 0) − 1

Reads `data/raw/beidan_full_3sp.csv`.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.niche_analysis.data_loader import classify_handicap, classify_league
from src.phase5a.filter import NicheConfig

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "raw" / "beidan_full_3sp.csv"
RETURN_RATE = 0.65


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=["sp_3", "sp_1", "sp_0", "result_code"])
    df = df[df["result_code"].astype(str).isin(["0", "1", "3"])]
    print(f"Loaded {len(df):,} matches")

    cfg = NicheConfig.load()

    rows = []
    for r in df.itertuples(index=False):
        sp_by_opt = {"3": float(r.sp_3), "1": float(r.sp_1), "0": float(r.sp_0)}
        # Skip degenerate SPs
        if min(sp_by_opt.values()) <= 1.0:
            continue
        league_tier = classify_league(r.league)
        handicap_class = classify_handicap(r.handicap)
        outcome = str(r.result_code)

        # STRAT: first niche rule that matches any option
        strat_pick = None
        strat_p_hat = None
        for opt, sp in sp_by_opt.items():
            for rule in cfg.rules:
                if rule.option is not None and rule.option != opt: continue
                if rule.sp_lo is not None and sp < rule.sp_lo: continue
                if rule.sp_hi is not None and sp >= rule.sp_hi: continue
                if rule.league_tier is not None and rule.league_tier != league_tier: continue
                if rule.handicap_class is not None and rule.handicap_class != handicap_class: continue
                # Match. Take the first STRAT pick that fires (mirror builder).
                if strat_pick is None or sp < sp_by_opt[strat_pick]:
                    # prefer lower SP if multiple? No: mirror build_weekly_plan which
                    # emits all and dedupes by highest edge. For policy comparison
                    # we just need a deterministic choice. Use first match.
                    if strat_pick is None:
                        strat_pick = opt
                        strat_p_hat = rule.p_hat_train
                break

        # FAVORITE: lowest SP
        favorite = min(sp_by_opt, key=lambda o: sp_by_opt[o])

        # INVERSE: pick the highest-SP option among those NOT picked by STRAT
        # If STRAT did not fire, inverse skips too (no pick to invert).
        inverse = None
        if strat_pick is not None:
            others = [o for o in sp_by_opt if o != strat_pick]
            inverse = max(others, key=lambda o: sp_by_opt[o])

        for policy, pick in [("STRAT", strat_pick), ("INVERSE", inverse), ("FAVORITE", favorite)]:
            if pick is None:
                continue
            sp = sp_by_opt[pick]
            hit = (pick == outcome)
            implied_p = 1.0 / sp / RETURN_RATE  # fair p (no rake)
            ret_per_yuan = (RETURN_RATE * sp - 1.0) if hit else -1.0
            rows.append({
                "policy": policy, "pick": pick, "sp": sp,
                "hit": int(hit), "implied_p": implied_p,
                "ret": ret_per_yuan,
                "p_hat_train": strat_p_hat if policy == "STRAT" else None,
            })

    out = pd.DataFrame(rows)
    print()
    print("=" * 72)
    print(f"{'Policy':<10} {'N legs':>8} {'Hit %':>8} {'Implied %':>10} "
          f"{'q (hit/imp)':>13} {'Avg SP':>8} {'ROI %':>8}")
    print("-" * 72)
    for policy in ["STRAT", "INVERSE", "FAVORITE"]:
        sub = out[out["policy"] == policy]
        n = len(sub)
        hit_rate = sub["hit"].mean()
        implied = sub["implied_p"].mean()
        q = hit_rate / implied if implied > 0 else 0
        avg_sp = sub["sp"].mean()
        roi = sub["ret"].mean() * 100
        print(f"{policy:<10} {n:>8,d} {hit_rate*100:>7.2f}% {implied*100:>9.2f}% "
              f"{q:>13.3f} {avg_sp:>8.2f} {roi:>+7.2f}%")
    print("=" * 72)

    # Break STRAT down by SP bucket — does q drop in any range?
    print("\nSTRAT q by SP bucket:")
    sub = out[out["policy"] == "STRAT"]
    sub = sub.assign(bucket=pd.cut(sub["sp"], bins=[1, 2, 3, 5, 8, 15, 100],
                                    labels=["1-2", "2-3", "3-5", "5-8", "8-15", "15+"]))
    for b, g in sub.groupby("bucket", observed=True):
        if len(g) == 0: continue
        hr = g["hit"].mean()
        imp = g["implied_p"].mean()
        q = hr / imp if imp > 0 else 0
        roi = g["ret"].mean() * 100
        print(f"  SP {str(b):<7} N={len(g):>6,d}  hit={hr*100:>5.1f}%  imp={imp*100:>5.1f}%  "
              f"q={q:>5.2f}  ROI={roi:>+6.2f}%")

    # By rule (which niche is actually adding edge?)
    print("\nSTRAT q by p_hat_train bucket (= rule strength):")
    sub2 = out[(out["policy"] == "STRAT") & (out["p_hat_train"].notna())]
    sub2 = sub2.assign(rb=pd.cut(sub2["p_hat_train"], bins=[0, 0.20, 0.30, 0.40, 0.50, 1.0]))
    for b, g in sub2.groupby("rb", observed=True):
        hr = g["hit"].mean()
        imp = g["implied_p"].mean()
        q = hr / imp if imp > 0 else 0
        roi = g["ret"].mean() * 100
        avg_p = g["p_hat_train"].mean()
        print(f"  p_hat {str(b):<14} N={len(g):>6,d}  hit={hr*100:>5.1f}%  "
              f"p_hat≈{avg_p:.2f}  imp={imp*100:>5.1f}%  q={q:>5.2f}  ROI={roi:>+6.2f}%")


if __name__ == "__main__":
    main()
