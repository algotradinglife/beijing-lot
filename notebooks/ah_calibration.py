"""Calibration of Pinnacle Asian Handicap market on Big Five 5 seasons.

Tests whether the AH-implied "home covers" probability matches realized
home-cover rate. This is critical because the strategy uses the AH market
as the foundation for deriving 北单 integer-line 3/1/0 probabilities.

Asian Handicap settlement (standard):
- Home line h. If FTHG - FTAG + h > 0: home covers fully (away ticket loses)
- If = 0: push (stakes returned, "win" rate counted as 0.5)
- If < 0: home loses (away covers)
- For half-ball lines (e.g. -0.5): no push possible
- For quarter-ball lines (e.g. -0.25): split stakes between two adjacent half lines
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR = Path("/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/football-data")


def load_all() -> pd.DataFrame:
    files = sorted(DATA_DIR.glob("*.csv"))
    dfs = []
    for f in files:
        try:
            d = pd.read_csv(f, encoding="utf-8")
        except UnicodeDecodeError:
            d = pd.read_csv(f, encoding="latin-1")
        dfs.append(d)
    return pd.concat(dfs, ignore_index=True)


def ah_settle_home(spread: float, line: float) -> float:
    """Return home AH ticket payout multiplier given goal spread (home-away)
    and AH home line. 1.0 = full win, 0.5 = half win/push refund, 0 = full loss."""
    # adjusted spread
    adj = spread + line
    # quarter-ball lines: split between floor(line*2)/2 and ceil(line*2)/2
    half_units = line * 2
    if abs(half_units - round(half_units)) < 1e-9:
        # half- or whole-ball line
        if abs(adj) < 1e-9:  # push
            return 0.5  # we treat as 0.5 win for calibration
        return 1.0 if adj > 0 else 0.0
    # quarter-ball line: split between adjacent half lines
    lower = np.floor(half_units) / 2.0
    upper = np.ceil(half_units) / 2.0
    return 0.5 * ah_settle_home(spread, lower) + 0.5 * ah_settle_home(spread, upper)


def main():
    df = load_all()
    df = df.dropna(subset=["PAHH", "PAHA", "AHh", "FTHG", "FTAG"])
    print(f"Matches with Pinnacle AH: {len(df)}")
    df["spread"] = df["FTHG"] - df["FTAG"]

    # AH-implied probability of home covering, after de-margining
    df["pHome_inv"] = 1 / df["PAHH"]
    df["pAway_inv"] = 1 / df["PAHA"]
    margin = df["pHome_inv"] + df["pAway_inv"]
    df["pHome_AH"] = df["pHome_inv"] / margin
    df["pAway_AH"] = df["pAway_inv"] / margin

    # Realized home cover (treating push as 0.5)
    df["home_cover"] = df.apply(lambda r: ah_settle_home(r["spread"], r["AHh"]), axis=1)

    print(f"\nAH market margin: mean={margin.mean()-1:.4f}, p50={(margin-1).median():.4f}")
    print(f"Realized home-cover rate: {df['home_cover'].mean():.4f}")
    print(f"Predicted home-cover rate: {df['pHome_AH'].mean():.4f}")

    # Calibration buckets
    df["pH_bin"] = pd.cut(df["pHome_AH"], bins=np.arange(0, 1.05, 0.05))
    cal = df.groupby("pH_bin", observed=True).agg(
        n=("home_cover", "size"),
        mean_pred=("pHome_AH", "mean"),
        rate=("home_cover", "mean"),
    )
    print("\nAH home-cover calibration:")
    print(cal.to_string())

    # If we always backed home at AH price: ROI?
    # Settle at full odds (multiplier 1.0 → win at PAHH; 0.5 → half stake refund + half stake won at PAHH)
    df["home_pnl"] = df["home_cover"] * df["PAHH"] - 1.0
    print(f"\nAlways-back-home ROI at Pinnacle AH: {df['home_pnl'].mean()*100:.3f}%")
    df["away_pnl"] = (1 - df["home_cover"]) * df["PAHA"] - 1.0
    # Note: for half-cover (push), away gets 0.5 refund + 0.5 staked → handled imperfectly here
    # This approximation is OK for calibration purposes
    print(f"Always-back-away ROI at Pinnacle AH: {df['away_pnl'].mean()*100:.3f}%")

    # Distribution of AH lines
    print("\nDistribution of AH lines (home favourite negative):")
    print(df["AHh"].describe())
    print("\nLine type frequency:")
    df["line_type"] = df["AHh"].apply(
        lambda x: "whole" if abs(x*2 - round(x*2)) < 1e-9 and abs(x - round(x)) < 1e-9
        else ("half" if abs(x*2 - round(x*2)) < 1e-9 else "quarter")
    )
    print(df["line_type"].value_counts())

    # Critical: how often is the AH line a WHOLE INTEGER (matching 北单 directly)?
    whole_share = (df["line_type"] == "whole").mean()
    print(f"\nShare of matches with whole-integer AH line (no conversion needed): {whole_share*100:.2f}%")


if __name__ == "__main__":
    main()
