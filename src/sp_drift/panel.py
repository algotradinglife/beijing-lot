"""Phase 0 analysis substrate: build a tidy, MTK-indexed SP panel.

snapshot_ts is UTC (trailing 'Z'); kickoff_ts is Beijing time (UTC+8) with
no tz suffix. The collector keeps polling matches after kickoff (frozen SP),
so the panel keeps only pre-kickoff snapshots (MTK > 0).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

import pandas as pd

from src.niche_analysis.data_loader import (
    classify_comp_type,
    classify_handicap,
    classify_league,
)

BEIJING = timezone(timedelta(hours=8))


def minutes_to_kickoff(snapshot_ts: str, kickoff_ts: str) -> float:
    """Minutes from a UTC snapshot to a Beijing-local kickoff. Positive = before."""
    snap = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
    if snap.tzinfo is None:
        snap = snap.replace(tzinfo=timezone.utc)
    ko = datetime.fromisoformat(kickoff_ts)
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=BEIJING)
    return (ko - snap).total_seconds() / 60.0


_SELECTIONS = (("3", "sp_3", "vol_pct_3"), ("1", "sp_1", "vol_pct_1"), ("0", "sp_0", "vol_pct_0"))


def build_snapshot_panel(live_db_path: str | Path) -> pd.DataFrame:
    """Long panel: one row per (match, selection, pre-kickoff snapshot)."""
    con = sqlite3.connect(str(live_db_path))
    raw = pd.read_sql_query(
        """
        SELECT s.match_id, s.snapshot_ts, s.sp_3, s.sp_1, s.sp_0,
               s.vol_pct_3, s.vol_pct_1, s.vol_pct_0, s.pool_total,
               m.issue, m.match_idx, m.league, m.kickoff_ts, m.handicap_line
        FROM snapshots s JOIN matches m ON m.match_id = s.match_id
        WHERE m.kickoff_ts IS NOT NULL
        """,
        con,
    )
    con.close()

    base_cols = ["match_id", "snapshot_ts", "issue", "match_idx", "league",
                 "kickoff_ts", "handicap_line", "pool_total"]
    parts = []
    for sel, sp_col, vol_col in _SELECTIONS:
        sub = raw[base_cols + [sp_col, vol_col]].rename(columns={sp_col: "sp", vol_col: "vol_pct"})
        sub["selection"] = sel
        parts.append(sub)
    panel = pd.concat(parts, ignore_index=True)

    snap = pd.to_datetime(panel["snapshot_ts"], utc=True, format="ISO8601")
    ko = pd.to_datetime(panel["kickoff_ts"]).dt.tz_localize(BEIJING)
    panel["mtk"] = (ko - snap).dt.total_seconds() / 60.0

    panel = panel[(panel["mtk"] > 0) & panel["sp"].notna() & (panel["sp"] > 1.0)].copy()
    panel["league_bucket"] = panel["league"].map(classify_league)
    panel["hcp_class"] = panel["handicap_line"].map(classify_handicap)
    panel["comp_type"] = panel["league"].map(classify_comp_type)
    return panel.reset_index(drop=True)


def attach_final_and_settlement(panel: pd.DataFrame, live_db_path: str | Path) -> pd.DataFrame:
    """Collapse to one row per (match, selection) at its closing pre-kickoff
    snapshot, joined with settlement outcome.

    Adds: final_sp (SP at smallest positive MTK), result_code, winning_sp,
    is_winner (result_code == selection).
    """
    closing_idx = panel.groupby(["match_id", "selection"])["mtk"].idxmin()
    closing = panel.loc[closing_idx].rename(columns={"sp": "final_sp"}).copy()

    con = sqlite3.connect(str(live_db_path))
    settle = pd.read_sql_query(
        "SELECT match_id, result_code, winning_sp FROM settlements", con)
    con.close()
    settle["result_code"] = settle["result_code"].astype(str)

    out = closing.merge(settle, on="match_id", how="left")
    out["is_winner"] = out["result_code"] == out["selection"]
    return out.reset_index(drop=True)


def decision_view(panel: pd.DataFrame, mtk_target: float) -> pd.DataFrame:
    """One row per (match, selection): the latest snapshot at least `mtk_target`
    minutes before kickoff (i.e. the SP a decider at MTK=target would observe).
    `sp` is the decision_SP. Matches with no snapshot that early are dropped.
    """
    elig = panel[panel["mtk"] >= mtk_target]
    if elig.empty:
        return elig.copy()
    idx = elig.groupby(["match_id", "selection"])["mtk"].idxmin()
    return panel.loc[idx].reset_index(drop=True)


def baseline_decision_mtk(webui_db_path: str | Path) -> float:
    """Median MTK at which live plans were actually generated, used as the
    no-window baseline decision point. Returns nan if no plan legs found.
    """
    con = sqlite3.connect(str(webui_db_path))
    rows = con.execute("SELECT created_ts, plan_json FROM plans").fetchall()
    con.close()
    mtks = []
    for created_ts, pj in rows:
        try:
            plan = json.loads(pj)
        except (TypeError, ValueError):
            continue
        for ticket in plan.get("tickets", []):
            for leg in ticket.get("legs", []):
                ko = leg.get("kickoff_ts")
                if ko and created_ts:
                    mtks.append(minutes_to_kickoff(created_ts, ko))
    return float(np.median(mtks)) if mtks else float("nan")
