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
STABLE_MTK = 60.0   # 1h, descriptive stable-SP main-strategy arm.
STABLE_BASE_MTK = 600.0

STABLE_STRICT = {
    "max_odds": 4.5,
    "min_multiplier": 0.85,
    "max_abs_log_move": 0.12,
    "min_stability_score": 0.80,
}


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


def training_panel(panel: pd.DataFrame, forward_start: str) -> pd.DataFrame:
    """Pre-forward (in-sample) slice: kickoffs ON or BEFORE forward_start. The
    complement of forward_panel — used to train models WITHOUT leaking the OOS
    forward period. kickoff_ts is naive Beijing ISO, so lexicographic compare."""
    return panel[panel["kickoff_ts"] <= forward_start].copy()


def build_qhc_arm_from_panel(panel: pd.DataFrame, forward_start: str = FORWARD_START,
                             decision_mtk: float = WINDOW_MTK,
                             q: float = 0.25) -> Tuple[str, Policy]:
    """Safe QHC entry point: fit the DriftModel on the PRE-forward slice only
    (no lookahead), then build the arm. Always use this from the runner rather
    than fit_drift_model(full_panel) to avoid leaking the OOS period into sizing."""
    from src.sp_drift.drift_model import fit_drift_model
    model = fit_drift_model(training_panel(panel, forward_start))
    return build_qhc_arm(model, decision_mtk=decision_mtk, q=q)


def build_qhc_arm(model, decision_mtk: float = WINDOW_MTK,
                  q: float = 0.25) -> Tuple[str, Policy]:
    """QHC arm: like C2 (decide at the 180min window) but size on the model's
    CONSERVATIVE-QUANTILE predicted settlement SP instead of the frozen band map.
    Tests whether the (SP-band × MTK) drift model + conservative quantile
    recovers value the frozen-band C2 haircut misses. Descriptive, not GATE-FT."""
    return ("QHC", Policy(mtk_target=decision_mtk,
                          sp_adjust=lambda sp: model.adjusted_sp(sp, decision_mtk, q)))


def _odds_stability_component(odds: float) -> float:
    if odds < 3.5:
        return 1.10
    if odds < 4.5:
        return 1.00
    if odds < 5.0:
        return 0.75
    if odds < 8.0:
        return 0.45
    return 0.20


def _move_stability_component(move_log: float | None) -> float:
    import math
    if move_log is None:
        return 1.0
    return max(0.25, min(1.15, math.exp(-abs(move_log) / 0.16)))


def stable_sp_decision_snapshots(
    panel: pd.DataFrame,
    model,
    *,
    forward_start: str = FORWARD_START,
    decision_mtk: float = STABLE_MTK,
    base_mtk: float = STABLE_BASE_MTK,
    max_odds: float = STABLE_STRICT["max_odds"],
    min_multiplier: float = STABLE_STRICT["min_multiplier"],
    max_abs_log_move: float = STABLE_STRICT["max_abs_log_move"],
    min_stability_score: float = STABLE_STRICT["min_stability_score"],
):
    """Return 1h decision LiveSnapshots with unstable selections nulled out.

    This is the live-forward analogue of the XLSM `baseline_q_sp_stable` gate:
    moderate SP, predicted settlement ratio not too adverse, and small recent
    move from 10h to 1h. It is descriptive and does not alter C0/C1/C2.
    """
    import math

    from src.phase5a.data_loader import LiveSnapshot
    from src.sp_drift import panel as P

    fp = forward_panel(panel, forward_start)
    dec = P.decision_view(fp, mtk_target=decision_mtk)
    base = P.decision_view(fp, mtk_target=base_mtk)
    base_sp = {
        (str(r["match_id"]), str(r["selection"])): float(r["sp"])
        for _, r in base.iterrows()
        if r["sp"] and float(r["sp"]) > 1.0
    }

    out = []
    for mid, grp in dec.groupby("match_id"):
        any_row = grp.iloc[0]
        kept: dict[str, float] = {}
        for _, row in grp.iterrows():
            sel = str(row["selection"])
            sp = float(row["sp"])
            if sp <= 1.0 or sp > max_odds:
                continue
            multiplier, _sd, _n = model.lookup(sp, float(row["mtk"]))
            if multiplier < min_multiplier:
                continue
            b = base_sp.get((str(mid), sel))
            move_log = None
            if b is not None and b > 1.0:
                move_log = math.log(sp / b)
                if abs(move_log) > max_abs_log_move:
                    continue
            stability_score = multiplier * _odds_stability_component(sp) * _move_stability_component(move_log)
            if stability_score < min_stability_score:
                continue
            kept[sel] = sp

        if not kept:
            continue
        out.append(
            LiveSnapshot(
                match_id=str(mid),
                issue=str(any_row["issue"]),
                match_idx=int(any_row["match_idx"]),
                league=any_row["league"],
                kickoff_ts=str(any_row["kickoff_ts"]),
                home=None,
                away=None,
                handicap_line=(None if pd.isna(any_row["handicap_line"]) else float(any_row["handicap_line"])),
                sp_3=kept.get("3"),
                sp_1=kept.get("1"),
                sp_0=kept.get("0"),
                snapshot_ts=None,
            )
        )
    return out


def stable_sp_arm_row(panel, live_db_path, niche_config, run_date: str, *,
                      forward_start: str = FORWARD_START, n_legs: int = 7,
                      decision_mtk: float = STABLE_MTK,
                      base_mtk: float = STABLE_BASE_MTK,
                      start_bankroll: float = 100000.0,
                      kelly_fraction: float = 0.0625,
                      combo_ev_threshold: float = 0.05,
                      weekly_stake_cap_frac: float = 0.25,
                      max_odds: float = STABLE_STRICT["max_odds"],
                      min_multiplier: float = STABLE_STRICT["min_multiplier"],
                      max_abs_log_move: float = STABLE_STRICT["max_abs_log_move"],
                      min_stability_score: float = STABLE_STRICT["min_stability_score"]) -> dict:
    """Descriptive stable-SP N=7 paper arm.

    Trains the drift model on pre-forward data only, filters the 1h live panel
    with the strict stable-SP gate, then uses the existing planner and settles
    against true `winning_sp`. Not part of the C0/C1/C2 GATE-FT verdict.
    """
    from src.backtest_combo.settler import settle_plans
    from src.phase5a.planner import build_weekly_plan
    from src.sp_drift.drift_model import fit_drift_model
    from src.sp_drift.replay import actuals_from_db, aggregate_equity

    model = fit_drift_model(training_panel(panel, forward_start))
    snaps = stable_sp_decision_snapshots(
        panel,
        model,
        forward_start=forward_start,
        decision_mtk=decision_mtk,
        base_mtk=base_mtk,
        max_odds=max_odds,
        min_multiplier=min_multiplier,
        max_abs_log_move=max_abs_log_move,
        min_stability_score=min_stability_score,
    )
    actuals = actuals_from_db(live_db_path)

    by_issue: dict = {}
    for snap in snaps:
        by_issue.setdefault(snap.issue, []).append(snap)

    bankroll = start_bankroll
    weeks = []
    n_tickets = 0
    n_hits = 0
    for issue in sorted(by_issue):
        pr = build_weekly_plan(
            by_issue[issue],
            bankroll=bankroll,
            niche_config=niche_config,
            n_legs=n_legs,
            kelly_fraction=kelly_fraction,
            combo_ev_threshold=combo_ev_threshold,
            weekly_stake_cap_frac=weekly_stake_cap_frac,
        )
        setts = settle_plans(pr.tickets, actuals)
        stake = float(sum(t.total_stake for t in pr.tickets))
        pnl = float(sum(s.total_profit for s in setts))
        n_tickets += len(pr.tickets)
        n_hits += sum(1 for s in setts if s.all_hit)
        weeks.append((issue, stake, pnl))
        bankroll += pnl

    res = aggregate_equity(weeks, start_bankroll=start_bankroll)
    return {
        "run_date": run_date, "arm": f"S{n_legs}", "forward_start": forward_start,
        "n_combos": n_tickets, "n_hits": n_hits,
        "total_stake": res["total_stake"], "total_pnl": res["total_pnl"],
        "roi": res["roi"], "max_dd": res["max_dd"],
        "final_bankroll": res["final_bankroll"],
        "weekly_sigma": _weekly_sigma(res.get("equity", [])),
    }


LEDGER_COLS = ["run_date", "arm", "forward_start", "n_combos", "n_hits",
               "total_stake", "total_pnl", "roi", "max_dd", "final_bankroll",
               "weekly_sigma"]


def favorite_arm_row(panel, live_db_path, run_date: str, *,
                     forward_start: str = FORWARD_START, n_legs: int = 5,
                     mtk_target: float, max_combos: int = 200, seed: int = 0,
                     start_bankroll: float = 100000.0) -> dict:
    """A descriptive 'bet the market favorite' arm: per match pick the lowest-SP
    selection (favorite), form N-leg parlays per issue (flat 1-unit stake),
    settle on real winning_sp. Tests the high-N favorite hypothesis (rake is
    per-ticket, favorites have realized p×SP>1) against true leg correlation.

    NOT a Policy arm (favorite selection ≠ niche qualify) and NOT part of
    GATE-FT. Flat-staked, so `roi`/命中率/`weekly_sigma` are the meaningful
    metrics; `max_dd` is not comparable to the Kelly-sized C/N arms."""
    import math
    import random as _random
    from collections import defaultdict
    from itertools import combinations

    from src.combo_optimizer import RETURN_RATE
    from src.sp_drift import panel as P
    from src.sp_drift.replay import actuals_from_db, aggregate_equity

    dec = P.decision_view(forward_panel(panel, forward_start), mtk_target)
    actuals = actuals_from_db(live_db_path)

    by_issue: dict = defaultdict(list)   # issue -> list of (hit: bool, win_sp)
    for mid, grp in dec.groupby("match_id"):
        sps = {str(r["selection"]): float(r["sp"]) for _, r in grp.iterrows()
               if r["sp"] and float(r["sp"]) > 0}
        if not sps:
            continue
        fav = min(sps, key=sps.get)
        a = actuals.get(str(mid))
        if not a:
            continue
        hit = (a["result_code"] == fav)
        win_sp = a["winning_sp"] if hit else None
        if hit and (win_sp is None or win_sp <= 0):
            continue  # winning favorite without a settlement SP — drop
        by_issue[str(grp.iloc[0]["issue"])].append((hit, win_sp))

    rng = _random.Random(seed)
    weeks, n_comb, n_hits, total_stake, total_pnl = [], 0, 0, 0.0, 0.0
    for issue in sorted(by_issue):
        legs = by_issue[issue]
        m = len(legs)
        if m < n_legs:
            continue
        if math.comb(m, n_legs) <= max_combos:
            combos = list(combinations(range(m), n_legs))
        else:
            seen = set()
            while len(seen) < max_combos:
                seen.add(tuple(sorted(rng.sample(range(m), n_legs))))
            combos = list(seen)
        stake = pnl = 0.0
        for comb in combos:
            stake += 1.0
            n_comb += 1
            if all(legs[i][0] for i in comb):
                prod = 1.0
                for i in comb:
                    prod *= legs[i][1]
                pnl += RETURN_RATE * prod - 1.0
                n_hits += 1
            else:
                pnl += -1.0
        weeks.append((issue, stake, pnl))
        total_stake += stake
        total_pnl += pnl

    res = aggregate_equity(weeks, start_bankroll=start_bankroll)
    return {
        "run_date": run_date, "arm": f"FAV{n_legs}", "forward_start": forward_start,
        "n_combos": n_comb, "n_hits": n_hits,
        "total_stake": total_stake, "total_pnl": total_pnl,
        "roi": res["roi"], "max_dd": res["max_dd"],
        "final_bankroll": res["final_bankroll"],
        "weekly_sigma": _weekly_sigma(res["equity"]),
    }


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
        roi = r["roi"]
        roi_s = "—" if (roi != roi) else f"**{roi * 100:+.1f}%**"   # nan (0-stake) → —
        lines.append(
            f"| {a} | {nc} | {r['n_hits']} | {hit_rate:.1f}% | "
            f"{r['total_stake']:,.0f} | {roi_s} | "
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
