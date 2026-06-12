import pandas as pd

from src.sp_drift.replay import decision_snapshots


def _panel():
    # match A, two selections present at the decision snapshot (MTK 60)
    return pd.DataFrame({
        "match_id": ["A", "A", "A"],
        "selection": ["3", "1", "0"],
        "sp": [2.5, 3.4, 4.0],
        "mtk": [60.0, 60.0, 60.0],
        "issue": ["26099", "26099", "26099"],
        "match_idx": [1, 1, 1],
        "league": ["英超", "英超", "英超"],
        "kickoff_ts": ["2026-06-09T19:35:00"] * 3,
        "handicap_line": [-1.0, -1.0, -1.0],
    })


def test_decision_snapshots_pivots_to_livesnapshot(tmp_path):
    snaps = decision_snapshots(_panel(), mtk_target=30)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.match_id == "A"
    assert s.sp_3 == 2.5 and s.sp_1 == 3.4 and s.sp_0 == 4.0
    assert s.league == "英超" and s.handicap_line == -1.0
    assert s.issue == "26099"


from src.sp_drift.replay import apply_band_haircut


def test_band_haircut_lowers_sp_by_band_bias():
    snaps = decision_snapshots(_panel(), mtk_target=30)
    # band map keyed by sp_band label; -0.10 means "expect final SP 10% lower"
    hc = {"<3.5": 0.0, "3.5-4.5": -0.25, "5-8": -0.50}
    out = apply_band_haircut(snaps, hc)
    s = out[0]
    # sp_3=2.5 (<3.5) unchanged; sp_1=3.4 (3.5-4.5? no, <3.5) ; sp_0=4.0 (3.5-4.5) ×0.75
    assert s.sp_3 == 2.5
    assert abs(s.sp_0 - 4.0 * 0.75) < 1e-9


import sqlite3 as _sql

from src.sp_drift.replay import actuals_from_db


def test_actuals_from_db(tmp_path):
    db = tmp_path / "live.db"
    con = _sql.connect(db)
    con.execute("CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL)")
    con.execute("INSERT INTO settlements VALUES ('A','0',3.0)")
    con.execute("INSERT INTO settlements VALUES ('B','3',4.5)")
    con.execute("INSERT INTO settlements VALUES ('C',NULL,0)")  # unsettled → skipped
    con.commit(); con.close()
    a = actuals_from_db(db)
    assert a["A"] == {"result_code": "0", "winning_sp": 3.0}
    assert a["B"]["winning_sp"] == 4.5
    assert "C" not in a


from src.sp_drift.replay import aggregate_equity


def test_aggregate_equity_rolls_bankroll_and_computes_maxdd():
    # weekly (issue, stake, pnl) in chronological order
    weeks = [("26051", 100.0, 50.0), ("26052", 100.0, -80.0), ("26053", 100.0, 60.0)]
    res = aggregate_equity(weeks, start_bankroll=1000.0)
    # equity: 1000 → 1050 → 970 → 1030
    assert res["final_bankroll"] == 1030.0
    assert abs(res["total_pnl"] - 30.0) < 1e-9
    assert abs(res["total_stake"] - 300.0) < 1e-9
    assert abs(res["roi"] - 30.0 / 300.0) < 1e-9
    # peak 1050, trough after 970 → MaxDD = (1050-970)/1050
    assert abs(res["max_dd"] - (1050.0 - 970.0) / 1050.0) < 1e-9


import sqlite3

from src.sp_drift import panel as P
from src.sp_drift.replay import Policy, replay_policy
from src.phase5a.filter import NicheConfig


def test_replay_policy_runs_pipeline_and_returns_metrics(tmp_path):
    # Build a tiny live db with 6 matches in one issue so build_weekly_plan can
    # form at least one N=2 combo; we only assert the result shape + that it
    # settled against winning_sp, not exact pnl.
    db = tmp_path / "live.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,"
        " league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);"
        "CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,"
        " snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL, vol_pct_3 REAL,"
        " vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL);"
        "CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL);")
    for i in range(1, 7):
        con.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                    (f"M{i}", "26099", i, "挪超", "2026-06-09T19:35:00", "H", "A", 1.0))
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,"
                    "vol_pct_3,vol_pct_1,vol_pct_0,pool_total) VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"M{i}", "2026-06-09T10:35:00Z", 6.0, 3.4, 1.6, 0, 0, 0, 1000))
        con.execute("INSERT INTO settlements VALUES (?,?,?)", (f"M{i}", "3", 6.0))
    con.commit(); con.close()

    pan = P.build(db, cache_path=tmp_path / "p.parquet", rebuild=True)
    pol = Policy(mtk_target=30, haircut=None, n_legs=2, kelly_fraction=0.0625,
                 combo_ev_threshold=0.0, start_bankroll=100000.0)
    res = replay_policy(pan, db, NicheConfig.load(), pol)
    assert {"roi", "max_dd", "final_bankroll", "n_weeks", "n_tickets"} <= set(res)
    assert res["n_weeks"] == 1
