"""Phase 1 backtest: EU-vs-SP divergence signal (div_raw).

Tests whether filtering niche candidates by EU-vs-SP divergence
improves hit rate, Sharpe, and Calmar on N=4 (and optionally N=5) combos.

Data source: beidan_live.db (9 issues, 2026-05)
Signal: div_raw = eu_p_devigged - 0.65/sp  (positive = sharps back this outcome more than crowd)
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest_combo.settler import settle_plan
from src.combo_optimizer import build_plan
from src.phase5a.data_loader import LiveSnapshot
from src.phase5a.filter import NicheConfig, qualify_candidates

DB_PATH = str(ROOT / "data" / "beidan_live.db")
BANKROLL = 100_000.0
WEEKLY_STAKE_CAP_FRAC = 0.25
TOP_K = 14
COMBO_EV_THRESHOLD = 0.05
EDGE_FLOOR = -1.0
RETURN_RATE = 0.65


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_issue(issue: str, conn: sqlite3.Connection) -> Optional[dict]:
    """Load all data for one issue: snapshots, actuals, and div_raw per (match_id, selection)."""

    # Last snapshot before kickoff with SP data
    rows = conn.execute("""
        WITH last_sp AS (
            SELECT sn.match_id, MAX(sn.snapshot_ts) AS snap_ts
            FROM snapshots sn
            JOIN matches m ON m.match_id = sn.match_id
            WHERE m.issue = ?
              AND sn.snapshot_ts < m.kickoff_ts
              AND sn.sp_3 IS NOT NULL
            GROUP BY sn.match_id
        )
        SELECT
            m.match_id, m.match_idx, m.league, m.kickoff_ts, m.handicap_line,
            sn.sp_3, sn.sp_1, sn.sp_0,
            sn.eu_h, sn.eu_d, sn.eu_a
        FROM matches m
        JOIN last_sp ls ON ls.match_id = m.match_id
        JOIN snapshots sn ON sn.match_id = m.match_id AND sn.snapshot_ts = ls.snap_ts
        WHERE m.issue = ?
    """, (issue, issue)).fetchall()

    if not rows:
        return None

    snapshots: List[LiveSnapshot] = []
    div_dict: Dict[Tuple[str, int], float] = {}  # (match_id, selection) -> div_raw

    for r in rows:
        (match_id, match_idx, league, kickoff_ts, handicap,
         sp_3, sp_1, sp_0, eu_h, eu_d, eu_a) = r

        snap = LiveSnapshot(
            match_id=match_id,
            issue=issue,
            match_idx=int(match_idx),
            league=league,
            kickoff_ts=kickoff_ts,
            home=None,
            away=None,
            handicap_line=float(handicap) if handicap is not None else None,
            sp_3=float(sp_3) if sp_3 is not None else None,
            sp_1=float(sp_1) if sp_1 is not None else None,
            sp_0=float(sp_0) if sp_0 is not None else None,
            snapshot_ts=None,
        )
        snapshots.append(snap)

        # Compute div_raw for each outcome where we have both EU and SP
        if eu_h and eu_d and eu_a:
            raw = [1.0 / eu_h, 1.0 / eu_d, 1.0 / eu_a]
            ovr = sum(raw)
            eu_ps = [r / ovr for r in raw]  # [eu_p3, eu_p1, eu_p0]

            for code, eu_p, sp in [(3, eu_ps[0], sp_3), (1, eu_ps[1], sp_1), (0, eu_ps[2], sp_0)]:
                if sp and sp > 0:
                    pool_p = RETURN_RATE / float(sp)
                    div_dict[(match_id, code)] = eu_p - pool_p

    # Actuals: result_code and winning_sp per match
    settled = conn.execute("""
        SELECT match_id, result_code, winning_sp
        FROM settlements
        WHERE issue = ?
    """, (issue,)).fetchall()

    actuals = {}
    for match_id, result_code, winning_sp in settled:
        actuals[match_id] = {
            "result_code": str(result_code) if result_code is not None else None,
            "winning_sp": float(winning_sp) if winning_sp is not None else 0.0,
        }

    return dict(snapshots=snapshots, actuals=actuals, div_dict=div_dict)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def simulate_issue(
    issue_data: dict,
    n: int,
    kelly: float,
    max_combos: int,
    div_threshold: float,
    config: NicheConfig,
) -> Optional[dict]:
    snapshots = issue_data["snapshots"]
    actuals = issue_data["actuals"]
    div_dict = issue_data["div_dict"]

    qualified = qualify_candidates(snapshots, config)
    if not qualified:
        return None

    # Apply div_threshold filter
    if div_threshold > -99:  # -99 = baseline (no filter)
        qualified = [
            q for q in qualified
            if div_dict.get((q.candidate.match_id, q.candidate.selection), float("nan")) >= div_threshold
        ]

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
        diversity_lambda=1.0,
    )
    if not plans:
        return None

    settlements = [settle_plan(p, actuals) for p in plans]
    total_stake = sum(s.total_stake for s in settlements)
    total_profit = sum(s.total_profit for s in settlements)
    n_hit = sum(1 for s in settlements if s.all_hit)

    return dict(
        n_combos=len(plans),
        n_qualified=len(qualified),
        n_hit=n_hit,
        total_stake=total_stake,
        total_profit=total_profit,
    )


# ---------------------------------------------------------------------------
# Stats aggregation (same as n_sweep_backtest.py)
# ---------------------------------------------------------------------------

def compute_stats(rows: List[dict]) -> dict:
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    total_stake = df["total_stake"].sum()
    total_profit = df["total_profit"].sum()
    roi = total_profit / total_stake if total_stake > 0 else float("nan")
    win_rate = (df["total_profit"] > 0).mean()

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
    end_bankroll = BANKROLL + total_profit
    cagr = (end_bankroll / BANKROLL) ** (52 / n_weeks) - 1 if n_weeks >= 2 else float("nan")

    wr = np.array(weekly_returns)
    sharpe = (wr.mean() / wr.std() * np.sqrt(52)) if wr.std() > 0 else float("nan")
    calmar = cagr / abs(max_dd) if max_dd < 0 else float("nan")

    return dict(
        n_issues=n_weeks,
        total_stake=total_stake,
        total_profit=total_profit,
        roi_pct=roi * 100,
        win_rate_pct=win_rate * 100,
        max_dd_pct=max_dd * 100,
        cagr_pct=cagr * 100,
        sharpe=sharpe,
        calmar=calmar,
        avg_combos=df["n_combos"].mean(),
        avg_qualified=df["n_qualified"].mean(),
    )


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def run_sweep(
    db_path: str = DB_PATH,
    n_values: tuple = (4, 5),
    kelly: float = 0.125,
    max_combos: int = 200,
    div_thresholds: tuple = (-99.0, -0.10, -0.05, 0.0, 0.02, 0.05, 0.10),
):
    conn = sqlite3.connect(db_path)
    config = NicheConfig.load()

    issues = [r[0] for r in conn.execute(
        "SELECT DISTINCT issue FROM settlements ORDER BY issue"
    ).fetchall()]
    print(f"Issues: {issues}  ({len(issues)} total)")

    # Pre-load all issue data
    issue_data = {}
    for iss in issues:
        d = _load_issue(iss, conn)
        if d:
            issue_data[iss] = d
    conn.close()
    print(f"Loaded {len(issue_data)} issues with snapshot data\n")

    # Print signal distribution stats
    all_divs = []
    for d in issue_data.values():
        all_divs.extend(d["div_dict"].values())
    divs = np.array(all_divs)
    print(f"div_raw distribution (N={len(divs)}):")
    print(f"  mean={divs.mean():.3f}  std={divs.std():.3f}")
    print(f"  p10={np.percentile(divs,10):.3f}  p25={np.percentile(divs,25):.3f}  "
          f"median={np.median(divs):.3f}  p75={np.percentile(divs,75):.3f}  p90={np.percentile(divs,90):.3f}")
    print()

    # Header
    col = f"{'Threshold':>10} {'N':>3} {'Issues':>6} {'Combos':>7} {'Qualified':>9} " \
          f"{'ROI%':>7} {'WinRate%':>9} {'CAGR%':>7} {'MaxDD%':>7} {'Sharpe':>7} {'Calmar':>7} {'PnL':>10}"
    print(col)
    print("-" * len(col))

    for n in n_values:
        for thresh in div_thresholds:
            rows = []
            for iss, d in issue_data.items():
                r = simulate_issue(d, n=n, kelly=kelly, max_combos=max_combos,
                                   div_threshold=thresh, config=config)
                if r:
                    rows.append(r)

            stats = compute_stats(rows)
            if not stats:
                lbl = "baseline" if thresh <= -99 else f"{thresh:+.2f}"
                print(f"{lbl:>10} {n:>3} {'—':>6}")
                continue

            lbl = "baseline" if thresh <= -99 else f"{thresh:+.2f}"
            print(
                f"{lbl:>10} {n:>3} "
                f"{stats['n_issues']:>6} "
                f"{stats['avg_combos']:>7.1f} "
                f"{stats['avg_qualified']:>9.1f} "
                f"{stats['roi_pct']:>7.1f} "
                f"{stats['win_rate_pct']:>9.1f} "
                f"{stats['cagr_pct']:>7.1f} "
                f"{stats['max_dd_pct']:>7.1f} "
                f"{stats['sharpe']:>7.2f} "
                f"{stats['calmar']:>7.2f} "
                f"{stats['total_profit']:>+10,.0f}"
            )
        print()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="+", default=[4, 5])
    ap.add_argument("--kelly", type=float, default=0.125)
    ap.add_argument("--max-combos", type=int, default=200)
    ap.add_argument("--thresholds", type=float, nargs="+",
                    default=[-99.0, -0.10, -0.05, 0.0, 0.02, 0.05, 0.10])
    args = ap.parse_args()

    run_sweep(
        n_values=tuple(args.n),
        kelly=args.kelly,
        max_combos=args.max_combos,
        div_thresholds=tuple(args.thresholds),
    )
