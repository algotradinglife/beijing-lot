"""Paper forward-test harness for SP-drift mitigation (reuses replay_policy).

Pre-registered (do not change mid-test):
- FORWARD_START: only matches kicking off after this are scored (out-of-sample).
- HAIRCUT_MAP: per-SP-band drift_bias frozen at the GATE 1 estimates.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from src.sp_drift.replay import Policy, replay_policy

FORWARD_START = "2026-06-13"  # naive Beijing date; kickoffs after this are OOS

# Frozen GATE 1 per-band drift_bias (signed). Do NOT re-estimate during the test.
HAIRCUT_MAP = {"<3.5": 0.33, "3.5-4.5": -0.09, "4.5-5": -0.21, "5-8": -0.36, ">8": -0.81}

WINDOW_MTK = 180.0  # 3h, mirrors the live kickoff_window_hours=3 (MTK proxy)


def forward_panel(panel: pd.DataFrame, min_kickoff: str) -> pd.DataFrame:
    """Keep only rows whose kickoff_ts is after min_kickoff (out-of-sample slice).
    kickoff_ts is a naive Beijing ISO string, so lexicographic compare is correct."""
    return panel[panel["kickoff_ts"] > min_kickoff].copy()


def build_arms(baseline_mtk: float, haircut_map: dict) -> List[Tuple[str, Policy]]:
    """Arms:
    - SP-drift arms (drive GATE-FT): C0 control (decide ~18h-out, no haircut),
      C1 window-only, C2 window + frozen haircut. C0 is the N=4 reference.
    - N-sweep arms (descriptive, do not affect GATE-FT): N3 / N5 differ from C0
      only in n_legs, isolating the leg-count effect on ROI / drift-compounding
      (PnL attribution showed drift compounds with N). Same decision timing and
      kelly as C0, no haircut.
    """
    return [
        ("C0", Policy(mtk_target=baseline_mtk)),
        ("C1", Policy(mtk_target=WINDOW_MTK)),
        ("C2", Policy(mtk_target=WINDOW_MTK, haircut=haircut_map)),
        ("N3", Policy(mtk_target=baseline_mtk, n_legs=3)),
        ("N5", Policy(mtk_target=baseline_mtk, n_legs=5)),
    ]


LEDGER_COLS = ["run_date", "arm", "forward_start", "n_combos", "n_hits",
               "total_stake", "total_pnl", "roi", "max_dd", "final_bankroll",
               "weekly_sigma"]


def _weekly_sigma(equity: list) -> float:
    """Population std of weekly PnL from the equity path (consecutive diffs).
    Deterministic 0.0 when there are fewer than 2 weeks of observations."""
    import statistics
    if not equity or len(equity) < 2:
        return 0.0
    weekly_pnl = [equity[i + 1] - equity[i] for i in range(len(equity) - 1)]
    if len(weekly_pnl) < 2:
        return 0.0
    return float(statistics.pstdev(weekly_pnl))


def render_arm_table(latest: dict, arm_names: list) -> list:
    """Markdown table lines for the per-arm summary. Columns include 命中率
    (n_hits/n_combos, guarded for zero combos) and 周σ (weekly PnL std)."""
    lines = [
        "| arm | 组合 | 命中 | 命中率 | 总投注 | ROI | MaxDD | 周σ |",
        "|-----|------|------|--------|--------|-----|-------|-----|",
    ]
    for a in arm_names:
        r = latest[a]
        nc = r["n_combos"]
        hit_rate = (100.0 * r["n_hits"] / nc) if nc else 0.0
        lines.append(
            f"| {a} | {nc} | {r['n_hits']} | {hit_rate:.1f}% | "
            f"{r['total_stake']:,.0f} | **{r['roi'] * 100:+.1f}%** | "
            f"{r['max_dd'] * 100:.0f}% | {r.get('weekly_sigma', 0.0):,.1f} |"
        )
    return lines


def append_ledger(rows: List[dict], ledger_path: str | Path) -> pd.DataFrame:
    """Append rows to the append-only ledger CSV. Idempotent per run_date:
    re-writing an existing run_date replaces those rows (so re-runs don't dup)."""
    ledger_path = Path(ledger_path)
    new = pd.DataFrame(rows, columns=LEDGER_COLS)
    if ledger_path.exists():
        old = pd.read_csv(ledger_path)
        old = old[~old["run_date"].isin(set(new["run_date"]))]
        out = pd.concat([old, new], ignore_index=True)
    else:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        out = new
    out.to_csv(ledger_path, index=False)
    return out


# GATE-FT thresholds (pre-registered, frozen).
MIN_COMBOS = 200
MAX_WEEKS = 12.0
MAXDD_STOP = 0.50
MARGIN = 0.05  # C2-C0 and C1-C0 ROI margin required for a "go"


def check_stopping_rule(ledger_df: pd.DataFrame, forward_start: str, today: str) -> dict:
    """Evaluate the pre-registered stopping rule and GATE-FT verdict on the
    latest run_date's arm rows. See spec §3/§7."""
    latest = ledger_df[ledger_df["run_date"] == ledger_df["run_date"].max()]
    by_arm = {r["arm"]: r for _, r in latest.iterrows()}

    def roi(arm: str) -> float:
        r = by_arm.get(arm)
        return float(r["roi"]) if r is not None else float("nan")

    c2 = by_arm.get("C2")
    c2_n = int(c2["n_combos"]) if c2 is not None else 0
    c2_dd = float(c2["max_dd"]) if c2 is not None else 0.0
    weeks = (date.fromisoformat(today) - date.fromisoformat(forward_start)).days / 7.0

    stop, reason, verdict = False, "running", "pending"
    if c2_dd > MAXDD_STOP:
        stop, reason, verdict = True, "maxdd_stop", "no_go"
    elif c2_n >= MIN_COMBOS:
        stop, reason = True, "n_combos>=200"
    elif weeks >= MAX_WEEKS:
        stop, reason = True, "weeks>=12"

    if stop and verdict == "pending":
        if roi("C2") > 0 and (roi("C2") - roi("C0")) >= MARGIN and (roi("C1") - roi("C0")) >= MARGIN:
            verdict = "go"
        elif roi("C2") <= 0:
            verdict = "no_go"
        else:
            verdict = "uncertain"

    return dict(stop=stop, reason=reason, verdict=verdict,
                c0_roi=roi("C0"), c1_roi=roi("C1"), c2_roi=roi("C2"),
                c2_n_combos=c2_n, weeks_elapsed=weeks, c2_max_dd=c2_dd)


def run_forward(panel: pd.DataFrame, live_db_path, niche_config,
                arms: List[Tuple[str, Policy]], run_date: str,
                forward_start: str = FORWARD_START) -> List[dict]:
    """Replay each arm on the OOS (forward) slice and return one ledger row per
    arm. Reuses replay_policy (qualify on decision SP, settle on real SP)."""
    fp = forward_panel(panel, forward_start)
    rows: List[dict] = []
    for name, pol in arms:
        res = replay_policy(fp, live_db_path, niche_config, pol)
        rows.append({
            "run_date": run_date, "arm": name, "forward_start": forward_start,
            "n_combos": res["n_tickets"], "n_hits": res["n_hits"],
            "total_stake": res["total_stake"], "total_pnl": res["total_pnl"],
            "roi": res["roi"], "max_dd": res["max_dd"],
            "final_bankroll": res["final_bankroll"],
            "weekly_sigma": _weekly_sigma(res.get("equity", [])),
        })
    return rows
