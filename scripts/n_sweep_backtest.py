"""N-leg sweep backtest: compare N=3..8 using actual CSV parimutuel SP + niche rules.

Methodology:
  - Candidates: qualify_candidates() with niches_default.json (p_hat from training)
  - SP: actual sp_3/sp_1/sp_0 from CSV (same data production uses)
  - Settlement: actual winning_sp from CSV
  - Bankroll: fixed 100k per issue (no compounding) → clean ROI comparison
  - Parallelised across issues via ProcessPoolExecutor
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest_combo.settler import settle_plan
from src.combo_optimizer import build_plan
from src.phase5a.data_loader import LiveSnapshot
from src.phase5a.filter import NicheConfig, qualify_candidates

BANKROLL = 100_000.0
WEEKLY_STAKE_CAP_FRAC = 0.25
TOP_K = 14
RETURN_RATE = 0.65
COMBO_EV_THRESHOLD = 0.05
EDGE_FLOOR = -1.0  # niche legs pass edge at combo level, not single-leg level


# ---------------------------------------------------------------------------
# Per-issue helpers
# ---------------------------------------------------------------------------

def _rows_to_snapshots(issue_df: pd.DataFrame, issue: str) -> List[LiveSnapshot]:
    snaps = []
    for row in issue_df.itertuples(index=False):
        snaps.append(LiveSnapshot(
            match_id=f"{issue}-{int(row.match_no):03d}",
            issue=issue,
            match_idx=int(row.match_no),
            league=str(row.league) if pd.notna(row.league) else None,
            kickoff_ts=str(row.kickoff_ts) if pd.notna(row.kickoff_ts) else None,
            home=None, away=None,
            handicap_line=float(row.handicap) if pd.notna(row.handicap) else None,
            sp_3=float(row.sp_3) if pd.notna(row.sp_3) else None,
            sp_1=float(row.sp_1) if pd.notna(row.sp_1) else None,
            sp_0=float(row.sp_0) if pd.notna(row.sp_0) else None,
            snapshot_ts=None,
        ))
    return snaps


def _actuals(issue_df: pd.DataFrame, issue: str) -> dict:
    out = {}
    for row in issue_df.itertuples(index=False):
        mid = f"{issue}-{int(row.match_no):03d}"
        out[mid] = dict(
            result_code=str(int(row.result_code)) if pd.notna(row.result_code) else None,
            winning_sp=float(row.winning_sp) if pd.notna(row.winning_sp) else 0.0,
        )
    return out


def simulate_issue_n(
    issue: str,
    issue_df: pd.DataFrame,
    config: NicheConfig,
    n: int,
    kelly: float,
    max_combos: int,
    diversity_lambda: float,
) -> Optional[dict]:
    snaps = _rows_to_snapshots(issue_df, issue)
    qualified = qualify_candidates(snaps, config)
    if len(qualified) < n:
        return None

    plans = build_plan(
        [q.candidate for q in qualified],
        bankroll=BANKROLL,
        n_legs=n,
        top_k=TOP_K,
        single_leg_edge_floor=EDGE_FLOOR,
        combo_ev_threshold=COMBO_EV_THRESHOLD,
        kelly_fraction=kelly,
        weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC,
        max_combos=max_combos,
        diversity_lambda=diversity_lambda,
    )
    if not plans:
        return None

    actuals = _actuals(issue_df, issue)
    settlements = [settle_plan(p, actuals) for p in plans]

    total_stake = sum(s.total_stake for s in settlements)
    total_profit = sum(s.total_profit for s in settlements)
    n_hit = sum(1 for s in settlements if s.all_hit)

    return dict(
        issue=issue,
        n_combos=len(plans),
        n_qualified=len(qualified),
        n_hit=n_hit,
        total_stake=total_stake,
        total_profit=total_profit,
        roi=total_profit / total_stake if total_stake > 0 else float("nan"),
    )


def _worker(args):
    issue, issue_df_dict, n, kelly, max_combos, diversity_lambda = args
    issue_df = pd.DataFrame(issue_df_dict)
    config = NicheConfig.load()
    return simulate_issue_n(issue, issue_df, config, n, kelly, max_combos, diversity_lambda)


# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------

def compute_stats(rows: List[dict]) -> dict:
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    total_stake = df["total_stake"].sum()
    total_profit = df["total_profit"].sum()
    roi = total_profit / total_stake if total_stake > 0 else float("nan")

    # Weekly win rate (sessions with profit > 0)
    win_rate = (df["total_profit"] > 0).mean()

    # Simulated compound growth (start 100k, add/sub each week's pnl)
    bankroll = BANKROLL
    peak = bankroll
    drawdowns = []
    weekly_returns = []
    for r in df["total_profit"]:
        bankroll += r
        peak = max(peak, bankroll)
        drawdowns.append((bankroll - peak) / peak)
        weekly_returns.append(r / BANKROLL)

    max_dd = min(drawdowns) if drawdowns else 0.0
    n_weeks = len(df)
    # Annualised from compound
    end_bankroll = BANKROLL + total_profit  # fixed bankroll → linear
    cagr_approx = (end_bankroll / BANKROLL) ** (52 / n_weeks) - 1 if n_weeks >= 4 else float("nan")

    wr = np.array(weekly_returns)
    sharpe = (wr.mean() / wr.std() * np.sqrt(52)) if wr.std() > 0 else float("nan")
    calmar = cagr_approx / abs(max_dd) if max_dd < 0 else float("nan")

    return dict(
        n_issues=n_weeks,
        total_stake=total_stake,
        total_profit=total_profit,
        roi_pct=roi * 100,
        win_rate_pct=win_rate * 100,
        max_dd_pct=max_dd * 100,
        cagr_pct=cagr_approx * 100,
        sharpe=sharpe,
        calmar=calmar,
        avg_combos=df["n_combos"].mean(),
        avg_qualified=df["n_qualified"].mean(),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_sweep(
    csv_path: str = "data/raw/beidan_full_3sp.csv",
    n_values: tuple = (3, 4, 5, 6, 7, 8),
    kelly_values: tuple = (0.125,),
    max_combos: int = 200,
    diversity_lambda: float = 1.0,
    workers: int = 8,
):
    print(f"Loading CSV…")
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["result_code", "winning_sp", "sp_3", "sp_1", "sp_0"])
    df["result_code"] = df["result_code"].astype(int)

    issues = sorted(df["expect"].unique())
    print(f"{len(issues)} issues, {len(df)} rows after filter")

    header = f"{'N':>3} {'Kelly':>6} {'期数':>5} {'总下注':>10} {'总盈亏':>10} {'ROI%':>7} {'CAGR%':>7} {'MaxDD%':>7} {'Sharpe':>7} {'Calmar':>7} {'周胜率%':>8} {'均合格腿':>8}"
    print()
    print(header)
    print("-" * len(header))

    for kelly in kelly_values:
        for n in n_values:
            args_list = []
            for issue in issues:
                idf = df[df["expect"] == issue]
                args_list.append((str(issue), idf.to_dict("list"), n, kelly, max_combos, diversity_lambda))

            results = []
            with ProcessPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_worker, a): a for a in args_list}
                for fut in as_completed(futs):
                    r = fut.result()
                    if r:
                        results.append(r)

            stats = compute_stats(results)
            if not stats:
                print(f"  N={n} kelly={kelly}: no results")
                continue

            print(
                f"{n:>3} {kelly:>6.4f} "
                f"{stats['n_issues']:>5} "
                f"{stats['total_stake']:>10,.0f} "
                f"{stats['total_profit']:>+10,.0f} "
                f"{stats['roi_pct']:>7.1f} "
                f"{stats['cagr_pct']:>7.1f} "
                f"{stats['max_dd_pct']:>7.1f} "
                f"{stats['sharpe']:>7.2f} "
                f"{stats['calmar']:>7.2f} "
                f"{stats['win_rate_pct']:>8.1f} "
                f"{stats['avg_qualified']:>8.1f}"
            )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="n_sweep", choices=["n_sweep", "kelly_sweep"])
    args = ap.parse_args()

    t0 = time.time()
    if args.mode == "kelly_sweep":
        # High-Kelly test for N=6,7,8 — forces stakes above 2-yuan minimum
        run_sweep(
            n_values=(6, 7, 8),
            kelly_values=(0.125, 0.25, 0.5, 1.0),
            max_combos=200,
            diversity_lambda=1.0,
            workers=8,
        )
    else:
        run_sweep(
            n_values=(3, 4, 5, 6, 7, 8),
            kelly_values=(0.125,),
            max_combos=200,
            diversity_lambda=1.0,
            workers=8,
        )
    print(f"\n完成，耗时 {time.time()-t0:.1f}s")
