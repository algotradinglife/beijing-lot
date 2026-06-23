"""Phase 4 counterfactual replay.

Invariant: qualify/size on the decision-time SP (optionally drift-haircut
adjusted), but settle on the real final SP (settlement winning_sp). This is
what makes "deciding too early → shrunken payout" show up as realized loss.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, List, Optional

import pandas as pd

from src.phase5a.data_loader import LiveSnapshot
from src.sp_drift import panel as P


def decision_snapshots(panel: pd.DataFrame, mtk_target: float) -> List[LiveSnapshot]:
    """Reconstruct one LiveSnapshot per match using the SP observed at decision
    MTK=mtk_target (the latest snapshot at least that long before kickoff)."""
    dec = P.decision_view(panel, mtk_target=mtk_target)
    out: List[LiveSnapshot] = []
    for mid, grp in dec.groupby("match_id"):
        by_sel = {str(r["selection"]): r for _, r in grp.iterrows()}
        any_row = grp.iloc[0]
        out.append(LiveSnapshot(
            match_id=str(mid),
            issue=str(any_row["issue"]),
            match_idx=int(any_row["match_idx"]),
            league=any_row["league"],
            kickoff_ts=str(any_row["kickoff_ts"]),
            home=None, away=None,
            handicap_line=(None if pd.isna(any_row["handicap_line"])
                           else float(any_row["handicap_line"])),
            sp_3=(float(by_sel["3"]["sp"]) if "3" in by_sel else None),
            sp_1=(float(by_sel["1"]["sp"]) if "1" in by_sel else None),
            sp_0=(float(by_sel["0"]["sp"]) if "0" in by_sel else None),
            snapshot_ts=None,
        ))
    return out


from dataclasses import replace as _dc_replace

from src.sp_drift.drift_stats import sp_band


def apply_band_haircut(snaps: List[LiveSnapshot], band_bias: dict) -> List[LiveSnapshot]:
    """Return new LiveSnapshots whose each-selection SP is adjusted toward its
    expected final value: adjusted = sp × (1 + band_bias[band(sp)]). Missing
    bands default to 0 (no change). band_bias values are signed (negative =
    expected to drift down)."""
    def adj(sp: Optional[float]) -> Optional[float]:
        if sp is None or sp <= 0:
            return sp
        return sp * (1.0 + band_bias.get(sp_band(sp), 0.0))

    return [_dc_replace(s, sp_3=adj(s.sp_3), sp_1=adj(s.sp_1), sp_0=adj(s.sp_0))
            for s in snaps]


def apply_sp_adjust(snaps: List[LiveSnapshot],
                    fn: Callable[[float], float]) -> List[LiveSnapshot]:
    """Return new LiveSnapshots with each selection SP mapped by ``fn`` (e.g. a
    DriftModel conservative-quantile adjustment ``sp -> adjusted_sp``). None or
    non-positive SPs are left unchanged."""
    def adj(sp: Optional[float]) -> Optional[float]:
        if sp is None or sp <= 0:
            return sp
        return fn(sp)

    return [_dc_replace(s, sp_3=adj(s.sp_3), sp_1=adj(s.sp_1), sp_0=adj(s.sp_0))
            for s in snaps]


def actuals_from_db(live_db_path: str | Path) -> dict:
    """Real settlement truth: {match_id: {result_code, winning_sp}}. This is
    the SP you are actually paid at — replay settles against THIS, not the
    decision SP. Rows with null result_code or non-positive winning_sp dropped."""
    con = sqlite3.connect(str(live_db_path))
    rows = con.execute(
        "SELECT match_id, result_code, winning_sp FROM settlements "
        "WHERE result_code IS NOT NULL AND winning_sp > 0").fetchall()
    con.close()
    return {str(m): {"result_code": str(rc), "winning_sp": float(ws)}
            for m, rc, ws in rows}


from dataclasses import dataclass

from src.backtest_combo.settler import settle_plans
from src.phase5a.filter import NicheConfig
from src.phase5a.planner import build_weekly_plan


@dataclass(frozen=True)
class Policy:
    mtk_target: float                 # decision minutes-to-kickoff
    haircut: Optional[dict] = None    # band_bias map, or None
    sp_adjust: Optional[Callable[[float], float]] = None  # per-leg SP map, or None
    n_legs: int = 4
    kelly_fraction: float = 0.0625    # 1/16 per v2.1
    combo_ev_threshold: float = 0.05
    weekly_stake_cap_frac: float = 0.25
    start_bankroll: float = 100000.0


def replay_policy(panel: pd.DataFrame, live_db_path: str | Path,
                  niche_config: NicheConfig, policy: Policy) -> dict:
    """Replay one policy issue-by-issue. Qualify/size on decision-time
    (optionally haircut) SP; settle on real winning_sp; roll bankroll."""
    actuals = actuals_from_db(live_db_path)
    snaps = decision_snapshots(panel, mtk_target=policy.mtk_target)
    if policy.haircut:
        snaps = apply_band_haircut(snaps, policy.haircut)
    if policy.sp_adjust:
        snaps = apply_sp_adjust(snaps, policy.sp_adjust)

    by_issue: dict = {}
    for s in snaps:
        by_issue.setdefault(s.issue, []).append(s)

    bankroll = policy.start_bankroll
    weeks = []
    n_tickets = 0
    n_hits = 0
    for issue in sorted(by_issue):
        pr = build_weekly_plan(
            by_issue[issue], bankroll=bankroll, niche_config=niche_config,
            n_legs=policy.n_legs, kelly_fraction=policy.kelly_fraction,
            combo_ev_threshold=policy.combo_ev_threshold,
            weekly_stake_cap_frac=policy.weekly_stake_cap_frac)
        setts = settle_plans(pr.tickets, actuals)
        stake = float(sum(t.total_stake for t in pr.tickets))
        pnl = float(sum(s.total_profit for s in setts))
        n_tickets += len(pr.tickets)
        n_hits += sum(1 for s in setts if s.all_hit)
        weeks.append((issue, stake, pnl))
        bankroll += pnl

    res = aggregate_equity(weeks, start_bankroll=policy.start_bankroll)
    res["n_tickets"] = n_tickets
    res["n_hits"] = n_hits
    return res


def aggregate_equity(weeks: list, start_bankroll: float) -> dict:
    """weeks: list of (issue, stake, pnl) in chronological order. Rolls a
    bankroll, returns roi/total_pnl/max_dd/final_bankroll/equity."""
    bankroll = start_bankroll
    peak = start_bankroll
    max_dd = 0.0
    equity = [start_bankroll]
    total_stake = total_pnl = 0.0
    for _issue, stake, pnl in weeks:
        bankroll += pnl
        total_stake += stake
        total_pnl += pnl
        equity.append(bankroll)
        peak = max(peak, bankroll)
        if peak > 0:
            max_dd = max(max_dd, (peak - bankroll) / peak)
    return dict(
        final_bankroll=bankroll,
        total_pnl=total_pnl,
        total_stake=total_stake,
        roi=(total_pnl / total_stake if total_stake else float("nan")),
        max_dd=max_dd,
        equity=equity,
        n_weeks=len(weeks),
    )
