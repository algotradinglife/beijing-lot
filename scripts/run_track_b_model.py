"""Track B P2 — walk-forward: can external factors beat the closing line?

Train p_hat on FEATURE_COLUMNS (strictly pre-kickoff) season-by-season
(train on seasons < t, predict season t, t=2016..2025) and compare OOS against
the bookmaker closing-consensus benchmark. If the model can't beat the close OOS,
there is no per-leg edge and the high-N moonshot stays a pure lottery.

Models: benchmark (p_close, untrained) | logistic (impute+scale) | HistGBM (native NaN).
Deterministic (random_state=0). This is the gated execution step.
Run:  PYTHONPATH=".:src" .venv/bin/python scripts/run_track_b_model.py
"""
from __future__ import annotations

import sqlite3
import numpy as np
import pandas as pd

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from src.track_b.etl import FEATURE_COLUMNS, LABEL_COLUMN
from src.track_b.metrics import (
    multiclass_log_loss, multiclass_brier, accuracy, divergence_lift, CODES,
)

DB = "data/beidan_features.db"
TEST_SEASONS = list(range(2016, 2026))
DIV_EDGES = [-1.0, -0.10, -0.03, 0.03, 0.10, 1.0]
BREAKEVEN_LEG = 0.064   # Track A: N=7 break-even per-leg edge vs closing pool


def load():
    con = sqlite3.connect(DB)
    df = pd.read_sql_query(
        f"SELECT season, {LABEL_COLUMN}, {', '.join(FEATURE_COLUMNS)} "
        f"FROM matches WHERE {LABEL_COLUMN} IS NOT NULL "
        f"AND p_close_3 IS NOT NULL AND season IS NOT NULL", con)
    con.close()
    return df


def _proba_in_code_order(clf, X):
    """Reorder predict_proba columns to (p3,p1,p0)."""
    cols = {str(c): i for i, c in enumerate(clf.classes_)}
    P = clf.predict_proba(X)
    return np.column_stack([P[:, cols[c]] for c in CODES])


def main():
    df = load()
    print(f"rows={len(df)}  seasons {df.season.min()}..{df.season.max()}  "
          f"features={len(FEATURE_COLUMNS)}\n")
    X = df[FEATURE_COLUMNS].to_numpy(dtype=float)
    y = df[LABEL_COLUMN].astype(str).to_numpy()
    season = df.season.to_numpy()
    pclose = df[["p_close_3", "p_close_1", "p_close_0"]].to_numpy(dtype=float)

    logit = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          LogisticRegression(max_iter=1000, C=1.0))
    gbm = HistGradientBoostingClassifier(random_state=0, max_iter=300,
                                         learning_rate=0.05, early_stopping=True)

    acc = {k: {"p": [], "pc": [], "y": []} for k in ("logit", "gbm")}
    print(f"{'season':>6} {'n':>6} | {'bench_ll':>9} {'logit_ll':>9} {'gbm_ll':>9} "
          f"{'gbm−bench':>9}")
    for t in TEST_SEASONS:
        tr, te = season < t, season == t
        if te.sum() == 0 or tr.sum() < 1000:
            continue
        row = [f"{t:>6} {te.sum():>6} |"]
        bench_ll = multiclass_log_loss(pclose[te], y[te])
        row.append(f"{bench_ll:>9.4f}")
        for name, clf in (("logit", logit), ("gbm", gbm)):
            clf.fit(X[tr], y[tr])
            P = _proba_in_code_order(clf, X[te])
            acc[name]["p"].append(P); acc[name]["pc"].append(pclose[te]); acc[name]["y"].append(y[te])
            ll = multiclass_log_loss(P, y[te])
            row.append(f"{ll:>9.4f}")
            if name == "gbm":
                row.append(f"{ll - bench_ll:>+9.4f}")
        print(" ".join(row))

    # pooled OOS
    print("\n== 汇总 OOS（2016-2025 合并）==")
    pc = np.vstack([np.vstack(acc["gbm"]["pc"])])
    yy = np.concatenate(acc["gbm"]["y"])
    bench = [tuple(r) for r in pc]
    print(f"{'model':>10} {'logloss':>9} {'brier':>9} {'acc':>7}  {'Δlogloss vs bench':>18}")
    bll = multiclass_log_loss(bench, yy)
    print(f"{'benchmark':>10} {bll:>9.4f} {multiclass_brier(bench, yy):>9.4f} "
          f"{accuracy(bench, yy):>7.4f}  {'—':>18}")
    gbm_P = None
    for name in ("logit", "gbm"):
        P = [tuple(r) for r in np.vstack(acc[name]["p"])]
        ll = multiclass_log_loss(P, yy)
        print(f"{name:>10} {ll:>9.4f} {multiclass_brier(P, yy):>9.4f} "
              f"{accuracy(P, yy):>7.4f}  {bll - ll:>+18.4f}")
        if name == "gbm":
            gbm_P = P

    # CLV: does the gbm's divergence from close predict realized?
    print("\n== beat-the-close（gbm 对 home 的偏离 vs realized）==")
    print(f"  {'div桶':>14} {'n':>7} {'均偏离':>8} {'p_close':>8} {'realized':>9} {'信号?':>6}")
    tab = divergence_lift(gbm_P, bench, yy, outcome_idx=0, edges=DIV_EDGES)
    for b in tab:
        if b["n"] >= 50:
            sig = "✓" if (b["mean_div"] > 0) == (b["realized"] > b["mean_p_close"]) else "✗"
            print(f"  [{b['lo']:+.2f},{b['hi']:+.2f}) {b['n']:>7} {b['mean_div']:>+8.3f} "
                  f"{b['mean_p_close']:>8.3f} {b['realized']:>9.3f} {sig:>6}")

    print("\n== 裁决（预注册）==")
    improved = bll - multiclass_log_loss(gbm_P, yy)
    print(f"  gbm OOS log-loss 改进 = {improved:+.4f}（>0 才有信号）")
    print(f"  盈亏平衡参照：高N(N=7)需每腿 p_hat/p_池 ≥ +{BREAKEVEN_LEG:.1%} edge。")
    print("  结论看上表：若改进≈0 且 CLV 无单调信号 → 赢不过收盘线、无 leg-edge（登月仍是彩票）。")


if __name__ == "__main__":
    main()
