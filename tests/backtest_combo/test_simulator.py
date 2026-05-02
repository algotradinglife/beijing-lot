"""Simulator integration tests on a tiny in-memory toy DB."""
from __future__ import annotations

import sqlite3

import pandas as pd

from src.backfill import db as backfill_db
from src.backtest_combo.simulator import (
    actuals_for_issue,
    build_candidates_for_issue,
    fit_sp_model_from_db,
    run_combo_backtest,
    simulate_issue,
)


def _toy_db(tmp_path):
    """20 matches in one issue: a mix of strong-favourite and dog patterns
    so that a few qualify as candidates with edge ≥ 0.05 under the empirical
    OLS proxy. We don't care about realism here, just exercise the pipeline.
    """
    path = tmp_path / "toy.db"
    conn = backfill_db.connect(path)
    rows = []
    # Spread heavy favourites + their actual outcomes — empirical OLS will
    # strongly bias the small fitted SP slope against avg-EU, generating
    # candidates.
    for i in range(20):
        rows.append(dict(
            issue="26001",
            match_idx=i + 1,
            league="X",
            kickoff_ts=f"2026-01-0{1 + i % 9} 12:00:00",
            home=f"H{i}",
            away=f"A{i}",
            handicap_line=0,
            fthg=2,
            ftag=0,
            result_code="3",
            winning_sp=1.4 + 0.05 * (i % 5),
            avg_eu_home=1.6,
            avg_eu_draw=3.8,
            avg_eu_away=5.5,
        ))
    cur = conn.cursor()
    for r in rows:
        cur.execute(
            """INSERT INTO historical_matches
               (issue, match_idx, league, kickoff_ts, home, away,
                handicap_line, fthg, ftag, result_code, winning_sp,
                avg_eu_home, avg_eu_draw, avg_eu_away)
               VALUES (:issue,:match_idx,:league,:kickoff_ts,:home,:away,
                       :handicap_line,:fthg,:ftag,:result_code,:winning_sp,
                       :avg_eu_home,:avg_eu_draw,:avg_eu_away)""",
            r,
        )
    conn.commit()
    return conn


def test_actuals_for_issue(tmp_path):
    conn = _toy_db(tmp_path)
    df = pd.read_sql_query("SELECT * FROM historical_matches", conn)
    a = actuals_for_issue(df)
    assert len(a) == 20
    sample_key = list(a.keys())[0]
    assert "result_code" in a[sample_key]
    assert "winning_sp" in a[sample_key]


def test_build_candidates_returns_some(tmp_path):
    conn = _toy_db(tmp_path)
    df = pd.read_sql_query("SELECT * FROM historical_matches", conn)
    df["kickoff_ts"] = pd.to_datetime(df["kickoff_ts"])
    sp_model = fit_sp_model_from_db(df)
    cands = build_candidates_for_issue(df, sp_model, edge_floor=-1.0)
    # With edge_floor=-1 we should emit 3 candidates per match
    assert len(cands) == 60
    # Every candidate should have valid sp and p
    for c in cands:
        assert c.sp > 0
        assert 0 < c.p_hat < 1


def test_simulate_issue_runs_end_to_end(tmp_path):
    conn = _toy_db(tmp_path)
    df = pd.read_sql_query("SELECT * FROM historical_matches", conn)
    df["kickoff_ts"] = pd.to_datetime(df["kickoff_ts"])
    sp_model = fit_sp_model_from_db(df)
    summary, settlements = simulate_issue(
        "26001", df, sp_model,
        bankroll=100_000.0,
        edge_floor=-1.0,  # accept everything
        combo_ev_threshold=-1.0,
        n_legs=7,
        top_k=14,
        max_combos=5,
    )
    assert summary["issue"] == "26001"
    assert summary["n_candidates"] >= 7
    # Plan may be empty if EV threshold drops everything; with -1 it shouldn't
    assert summary["n_combos"] >= 0
    if summary["n_combos"] > 0:
        # Total stake should not exceed 25% bankroll cap
        assert summary["total_stake"] <= 25_000


def test_run_combo_backtest_full(tmp_path):
    conn = _toy_db(tmp_path)
    issues, plans, sp_model = run_combo_backtest(
        conn,
        bankroll=100_000.0,
        edge_floor=-1.0,
        combo_ev_threshold=-1.0,
        n_legs=7,
        top_k=14,
        max_combos=5,
    )
    assert len(issues) == 1
    # plans dataframe schema
    if not plans.empty:
        for col in ["issue", "joint_p", "joint_sp", "ev",
                    "stake_per_ticket", "n_tickets", "total_stake",
                    "all_hit", "total_profit"]:
            assert col in plans.columns
