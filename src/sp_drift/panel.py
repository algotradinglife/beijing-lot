"""Phase 0 analysis substrate: build a tidy, MTK-indexed SP panel.

snapshot_ts is UTC (trailing 'Z'); kickoff_ts is Beijing time (UTC+8) with
no tz suffix. The collector keeps polling matches after kickoff (frozen SP),
so the panel keeps only pre-kickoff snapshots (MTK > 0).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
