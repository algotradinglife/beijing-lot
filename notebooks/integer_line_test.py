"""Test the AH→1X2 converter on real Pinnacle data, mapping each match's
AH line to its NEAREST INTEGER (which is what 北单 would offer).

Goal: verify the converter doesn't blow up on edge-cases, and gather
empirical distributions of p3/p1/p0 the strategy will see at integer lines.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, "/Volumes/Data Drive/workspace/trading/beijing-lot/notebooks")
from ah_to_1x2 import ah_to_1x2

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


def main():
    df = load_all()
    needed = ["PSH", "PSD", "PSA", "PAHH", "PAHA", "AHh",
              "P>2.5", "P<2.5", "FTHG", "FTAG", "FTR"]
    df = df.dropna(subset=needed)
    print(f"Matches with all Pinnacle markets + result: {len(df)}")

    # Map each match's AH line to nearest integer (the line 北单 would set)
    df["int_line"] = df["AHh"].round().astype(int)
    df["int_line"] = df["int_line"].clip(-3, 3)
    print("\nNearest-integer line distribution (北单-like):")
    print(df["int_line"].value_counts().sort_index())

    # For each match, compute model p3/p1/p0 at the integer line
    rows = []
    failures = 0
    for i, (_, r) in enumerate(df.iterrows()):
        if i % 2000 == 0 and i > 0:
            print(f"  processed {i}/{len(df)}, failures={failures}")
        try:
            res = ah_to_1x2(
                ah_line=float(r["AHh"]),
                ah_home_odds=float(r["PAHH"]),
                ah_away_odds=float(r["PAHA"]),
                total_line=2.5,
                over_odds=float(r["P>2.5"]),
                under_odds=float(r["P<2.5"]),
                target_handicap=int(r["int_line"]),
            )
            rows.append({
                "p3_int": res["3"], "p1_int": res["1"], "p0_int": res["0"],
                "AHh": r["AHh"], "int_line": int(r["int_line"]),
                "FTHG": r["FTHG"], "FTAG": r["FTAG"], "FTR": r["FTR"],
                "spread": r["FTHG"] - r["FTAG"],
            })
        except Exception as e:
            failures += 1
            if failures <= 5:
                print(f"  failure {failures}: {e}")
    res_df = pd.DataFrame(rows)
    print(f"  total failures: {failures}")
    print(f"\nSuccessful conversions: {len(res_df)}/{len(df)}")

    # Realized 3/1/0 at integer line: 3 if spread > -line, 1 if spread = -line, 0 else
    res_df["realized"] = np.where(
        res_df["spread"] > -res_df["int_line"], 3,
        np.where(res_df["spread"] == -res_df["int_line"], 1, 0),
    )

    # Empirical hit rate by predicted-probability bucket for each outcome
    print("\n=== p3 (home wins after handicap) calibration ===")
    res_df["p3_bin"] = pd.cut(res_df["p3_int"], bins=np.arange(0, 1.05, 0.1))
    print(res_df.groupby("p3_bin", observed=True).agg(
        n=("p3_int", "size"),
        mean_pred=("p3_int", "mean"),
        rate=("realized", lambda x: (x == 3).mean()),
    ))

    print("\n=== p1 (push) calibration ===")
    res_df["p1_bin"] = pd.cut(res_df["p1_int"], bins=np.arange(0, 0.45, 0.05))
    print(res_df.groupby("p1_bin", observed=True).agg(
        n=("p1_int", "size"),
        mean_pred=("p1_int", "mean"),
        rate=("realized", lambda x: (x == 1).mean()),
    ))

    print("\n=== p0 (away wins after handicap) calibration ===")
    res_df["p0_bin"] = pd.cut(res_df["p0_int"], bins=np.arange(0, 1.05, 0.1))
    print(res_df.groupby("p0_bin", observed=True).agg(
        n=("p0_int", "size"),
        mean_pred=("p0_int", "mean"),
        rate=("realized", lambda x: (x == 0).mean()),
    ))

    # Brier scores
    y3 = (res_df["realized"] == 3).astype(int)
    y1 = (res_df["realized"] == 1).astype(int)
    y0 = (res_df["realized"] == 0).astype(int)
    brier = ((y3 - res_df["p3_int"])**2 + (y1 - res_df["p1_int"])**2 + (y0 - res_df["p0_int"])**2).mean()
    eps = 1e-9
    ll = -(
        y3 * np.log(res_df["p3_int"].clip(eps, 1-eps))
        + y1 * np.log(res_df["p1_int"].clip(eps, 1-eps))
        + y0 * np.log(res_df["p0_int"].clip(eps, 1-eps))
    ).mean()
    print(f"\nIntegrated 3/1/0 Brier: {brier:.4f}")
    print(f"Integrated 3/1/0 Log-loss: {ll:.4f}")
    print(f"P(3/1/0) realized: {y3.mean():.4f} / {y1.mean():.4f} / {y0.mean():.4f}")
    print(f"P(3/1/0) predicted: {res_df['p3_int'].mean():.4f} / {res_df['p1_int'].mean():.4f} / {res_df['p0_int'].mean():.4f}")

    # Save for potential downstream use
    res_df[["AHh", "int_line", "p3_int", "p1_int", "p0_int", "realized", "spread"]].to_csv(
        "/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/big5_int_line_predictions.csv",
        index=False,
    )
    print("\nSaved predictions to big5_int_line_predictions.csv")


if __name__ == "__main__":
    main()
