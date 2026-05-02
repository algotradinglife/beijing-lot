"""Sanity tests for the backtest simulator on synthetic data."""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src.backfill import db as backfill_db
from src.backtest import simulator


def _toy_db(tmp_path):
    """Build a tiny in-DB dataset of 5 fully consistent matches."""
    path = tmp_path / "toy.db"
    conn = backfill_db.connect(path)
    rows = [
        # Home favourite, h=0, home wins.  EU 1.5/4.0/6.0 (home heavy fav)
        dict(issue="26001", match_idx=1, league="X", kickoff_ts="2026-01-01 12:00:00",
             home="A", away="B", handicap_line=0,
             fthg=2, ftag=0, result_code="3", winning_sp=1.40,
             avg_eu_home=1.50, avg_eu_draw=4.00, avg_eu_away=6.00),
        # Draw at h=0.
        dict(issue="26001", match_idx=2, league="X", kickoff_ts="2026-01-01 12:00:00",
             home="C", away="D", handicap_line=0,
             fthg=1, ftag=1, result_code="1", winning_sp=3.40,
             avg_eu_home=2.50, avg_eu_draw=3.20, avg_eu_away=2.80),
        # Underdog away win, h=-1.
        dict(issue="26001", match_idx=3, league="X", kickoff_ts="2026-01-02 12:00:00",
             home="E", away="F", handicap_line=-1,
             fthg=0, ftag=2, result_code="0", winning_sp=4.50,
             avg_eu_home=2.10, avg_eu_draw=3.50, avg_eu_away=3.30),
        # Strong away fav, h=+2 (rare).
        dict(issue="26002", match_idx=1, league="X", kickoff_ts="2026-01-08 12:00:00",
             home="G", away="H", handicap_line=2,
             fthg=0, ftag=3, result_code="0", winning_sp=2.00,
             avg_eu_home=8.00, avg_eu_draw=5.00, avg_eu_away=1.30),
        # Plain h=0 match where draw model boost might fire.
        dict(issue="26002", match_idx=2, league="X", kickoff_ts="2026-01-08 13:00:00",
             home="I", away="J", handicap_line=0,
             fthg=0, ftag=0, result_code="1", winning_sp=3.20,
             avg_eu_home=2.30, avg_eu_draw=3.30, avg_eu_away=3.10),
    ]
    backfill_db.insert_matches(conn, rows)
    return path, conn


def test_load_matches(tmp_path):
    path, conn = _toy_db(tmp_path)
    df = simulator.load_matches(conn)
    assert len(df) == 5
    assert {"avg_eu_home", "avg_eu_draw", "avg_eu_away"}.issubset(df.columns)


def test_simulate_runs(tmp_path):
    path, conn = _toy_db(tmp_path)
    df = simulator.load_matches(conn)
    picks, _ = simulator.simulate(df, bankroll=10_000.0, ev_threshold=1.05)
    # picks may be empty or non-empty — just make sure it runs and pnl maths
    # are consistent
    if not picks.empty:
        for _, p in picks.iterrows():
            if p["won"]:
                assert p["pnl"] > -1e-9 or abs(p["pnl"]) < 1e-9
            else:
                assert p["pnl"] <= 0


def test_aggregate_weekly_consistency(tmp_path):
    """Total PnL across weeks must equal sum of individual pick PnL."""
    path, conn = _toy_db(tmp_path)
    df = simulator.load_matches(conn)
    picks, _ = simulator.simulate(df, ev_threshold=1.0)  # accept everything
    weekly = simulator.aggregate_weekly(picks)
    if not picks.empty:
        assert abs(weekly["total_pnl"].sum() - picks["pnl"].sum()) < 1e-6
        assert abs(weekly["total_stake"].sum() - picks["stake"].sum()) < 1e-6


def test_cumulative_roi_is_monotonic_in_index(tmp_path):
    path, conn = _toy_db(tmp_path)
    df = simulator.load_matches(conn)
    picks, _ = simulator.simulate(df, ev_threshold=1.0)
    cr = simulator.cumulative_roi(picks)
    if not cr.empty:
        cs = cr["cum_stake"].to_numpy()
        # cumulative stake is non-decreasing
        assert all(cs[i] <= cs[i + 1] + 1e-9 for i in range(len(cs) - 1))
