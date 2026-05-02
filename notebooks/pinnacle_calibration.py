"""Calibration check: do Pinnacle 1X2 odds (after de-margining) match
realized outcome frequencies on the Big Five last 5 seasons?

If YES — approach A (market-implied P_real) has a solid foundation.
If NO — we need a different probability source.
"""
from __future__ import annotations

import glob
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
        d["_file"] = f.name
        dfs.append(d)
    df = pd.concat(dfs, ignore_index=True)
    return df


def remove_margin_proportional(h, d, a):
    """Multiplicative / proportional margin removal."""
    inv = np.array([1 / h, 1 / d, 1 / a])
    return inv / inv.sum()


def remove_margin_power(h, d, a, tol=1e-9, max_iter=200):
    """Shin / power method for margin removal — better for biased markets,
    but heavier. Use proportional as default and power as comparison."""
    p = np.array([1 / h, 1 / d, 1 / a])
    s = p.sum()
    n = 1.0
    for _ in range(max_iter):
        q = p ** (1 / n)
        q = q / q.sum()
        # Equate to original margin ratio
        s_q = (q ** n).sum()
        err = s_q - s
        if abs(err) < tol:
            break
        n -= err * 0.1
    return q


def main():
    df = load_all()
    print(f"Loaded {len(df)} match rows")
    # Pinnacle columns: PSH, PSD, PSA (1X2)
    cols = ["PSH", "PSD", "PSA", "FTR", "Date", "Div"]
    df = df.dropna(subset=cols)
    print(f"With Pinnacle 1X2 + result: {len(df)} matches")

    # De-margined probabilities
    inv = 1 / df[["PSH", "PSD", "PSA"]].values
    margin = inv.sum(axis=1)
    p = inv / margin[:, None]
    df["pH"], df["pD"], df["pA"] = p[:, 0], p[:, 1], p[:, 2]

    # Outcome encoding
    df["yH"] = (df["FTR"] == "H").astype(int)
    df["yD"] = (df["FTR"] == "D").astype(int)
    df["yA"] = (df["FTR"] == "A").astype(int)

    # Calibration buckets — group by predicted prob, check realized rate
    print("\n=== Calibration: Home win ===")
    df["pH_bin"] = pd.cut(df["pH"], bins=np.arange(0, 1.05, 0.1))
    cal = df.groupby("pH_bin", observed=True).agg(
        n=("yH", "size"),
        mean_pred=("pH", "mean"),
        rate=("yH", "mean"),
    )
    print(cal)

    print("\n=== Calibration: Draw ===")
    df["pD_bin"] = pd.cut(df["pD"], bins=np.arange(0.10, 0.45, 0.05))
    cal = df.groupby("pD_bin", observed=True).agg(
        n=("yD", "size"),
        mean_pred=("pD", "mean"),
        rate=("yD", "mean"),
    )
    print(cal)

    print("\n=== Calibration: Away win ===")
    df["pA_bin"] = pd.cut(df["pA"], bins=np.arange(0, 1.05, 0.1))
    cal = df.groupby("pA_bin", observed=True).agg(
        n=("yA", "size"),
        mean_pred=("pA", "mean"),
        rate=("yA", "mean"),
    )
    print(cal)

    # Summary stats
    print(f"\nMean Pinnacle margin: {(margin - 1).mean():.4f} ({(margin - 1).mean()*100:.2f}%)")
    print(f"Margin p25/p75: {np.quantile(margin - 1, [0.25, 0.75])}")

    # Brier score and log-loss
    brier = ((df["yH"] - df["pH"]) ** 2 + (df["yD"] - df["pD"]) ** 2 + (df["yA"] - df["pA"]) ** 2).mean()
    eps = 1e-9
    ll = -(
        df["yH"] * np.log(df["pH"].clip(eps, 1 - eps))
        + df["yD"] * np.log(df["pD"].clip(eps, 1 - eps))
        + df["yA"] * np.log(df["pA"].clip(eps, 1 - eps))
    ).mean()
    print(f"\nBrier score (lower better; baseline=2/3): {brier:.4f}")
    print(f"Log-loss   (lower better; uniform=ln 3 = 1.0986): {ll:.4f}")

    # If we BET on the favourite at Pinnacle prices: what's our edge? (sanity check
    # — should be near 0 if Pinnacle is efficient)
    df["fav_pred"] = df[["pH", "pD", "pA"]].values.argmax(axis=1)  # 0=H 1=D 2=A
    df["fav_odds"] = df[["PSH", "PSD", "PSA"]].values.min(axis=1)
    df["actual"] = df["FTR"].map({"H": 0, "D": 1, "A": 2}).astype(int)
    df["fav_win"] = (df["fav_pred"] == df["actual"]).astype(int)
    fav_roi = (df["fav_win"] * df["fav_odds"] - 1).mean()
    print(f"\nFavourite ROI at Pinnacle prices (should be near 0%): {fav_roi*100:.3f}%")

    # By favourite-strength bucket
    df["fav_p"] = df[["pH", "pD", "pA"]].values.max(axis=1)
    df["fav_p_bin"] = pd.cut(df["fav_p"], bins=[0, 0.4, 0.5, 0.6, 0.7, 1.0])
    print("\nFav ROI by predicted-prob bucket:")
    print(df.groupby("fav_p_bin", observed=True).apply(
        lambda x: pd.Series({
            "n": len(x),
            "mean_p": x["fav_p"].mean(),
            "hit_rate": x["fav_win"].mean(),
            "roi_pct": ((x["fav_win"] * x["fav_odds"] - 1).mean()) * 100,
        }), include_groups=False
    ))

    # Save a clean cleaned dataset for reuse
    out_path = "/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/big5_pinnacle.csv"
    df[["Date", "Div", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR",
        "PSH", "PSD", "PSA", "PAHH", "PAHA", "AHh",
        "P>2.5", "P<2.5",
        "pH", "pD", "pA"]].to_csv(out_path, index=False)
    print(f"\nSaved cleaned dataset to {out_path}")


if __name__ == "__main__":
    main()
