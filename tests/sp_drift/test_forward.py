import pandas as pd

from src.sp_drift.forward import FORWARD_START, HAIRCUT_MAP, build_arms, forward_panel


def test_forward_panel_keeps_only_kickoffs_after_start():
    panel = pd.DataFrame({
        "match_id": ["A", "B"],
        "kickoff_ts": ["2026-06-10T19:00:00", "2026-06-20T19:00:00"],
        "sp": [4.0, 4.0],
    })
    out = forward_panel(panel, "2026-06-13")
    assert list(out["match_id"]) == ["B"]


def test_build_arms_three_arms_with_expected_policies():
    arms = build_arms(baseline_mtk=1080.0, haircut_map=HAIRCUT_MAP)
    names = [n for n, _ in arms]
    assert names == ["C0", "C1", "C2"]
    by = dict(arms)
    assert by["C0"].mtk_target == 1080.0 and by["C0"].haircut is None
    assert by["C1"].mtk_target == 180.0 and by["C1"].haircut is None
    assert by["C2"].mtk_target == 180.0 and by["C2"].haircut == HAIRCUT_MAP


def test_haircut_map_is_frozen_gate1_values():
    assert HAIRCUT_MAP["5-8"] == -0.36 and HAIRCUT_MAP["<3.5"] == 0.33


from src.sp_drift.forward import LEDGER_COLS, append_ledger


def _row(run_date, arm, roi):
    return {"run_date": run_date, "arm": arm, "forward_start": "2026-06-13",
            "n_combos": 10, "n_hits": 1, "total_stake": 100.0, "total_pnl": roi * 100.0,
            "roi": roi, "max_dd": 0.1, "final_bankroll": 100000.0 + roi * 100.0}


def test_append_ledger_creates_then_appends(tmp_path):
    led = tmp_path / "ledger.csv"
    append_ledger([_row("2026-06-20", "C0", 0.1)], led)
    out = append_ledger([_row("2026-06-27", "C0", 0.2)], led)
    assert list(out.columns) == LEDGER_COLS
    assert set(out["run_date"]) == {"2026-06-20", "2026-06-27"}


def test_append_ledger_is_idempotent_per_run_date(tmp_path):
    led = tmp_path / "ledger.csv"
    append_ledger([_row("2026-06-20", "C0", 0.1)], led)
    # re-run same run_date with a corrected value → replaces, not duplicates
    out = append_ledger([_row("2026-06-20", "C0", 0.5)], led)
    sub = out[(out["run_date"] == "2026-06-20") & (out["arm"] == "C0")]
    assert len(sub) == 1 and abs(float(sub.iloc[0]["roi"]) - 0.5) < 1e-9


from src.sp_drift.forward import check_stopping_rule


def _ledger(c0_roi, c1_roi, c2_roi, c2_n=10, c2_dd=0.1, run_date="2026-06-20"):
    rows = []
    for arm, roi, n, dd in [("C0", c0_roi, 10, 0.1), ("C1", c1_roi, 10, 0.1),
                            ("C2", c2_roi, c2_n, c2_dd)]:
        rows.append({"run_date": run_date, "arm": arm, "forward_start": "2026-06-13",
                     "n_combos": n, "n_hits": 1, "total_stake": 1.0, "total_pnl": 0.0,
                     "roi": roi, "max_dd": dd, "final_bankroll": 1.0})
    return pd.DataFrame(rows)


def test_stopping_maxdd_triggers_no_go():
    res = check_stopping_rule(_ledger(0.0, 0.1, 0.1, c2_dd=0.6), "2026-06-13", "2026-06-20")
    assert res["stop"] and res["reason"] == "maxdd_stop" and res["verdict"] == "no_go"


def test_stopping_n_combos_go_when_margins_met():
    res = check_stopping_rule(_ledger(0.0, 0.10, 0.12, c2_n=220), "2026-06-13", "2026-07-01")
    assert res["stop"] and res["reason"] == "n_combos>=200" and res["verdict"] == "go"


def test_stopping_n_combos_no_go_when_c2_negative():
    res = check_stopping_rule(_ledger(0.0, 0.10, -0.05, c2_n=220), "2026-06-13", "2026-07-01")
    assert res["stop"] and res["verdict"] == "no_go"


def test_stopping_running_pending_before_thresholds():
    res = check_stopping_rule(_ledger(0.0, 0.1, 0.1, c2_n=10), "2026-06-13", "2026-06-20")
    assert not res["stop"] and res["verdict"] == "pending"
    assert abs(res["weeks_elapsed"] - 1.0) < 1e-9


import sqlite3

from src.sp_drift import panel as P
from src.sp_drift.forward import run_forward
from src.phase5a.filter import NicheConfig


def _forward_db(tmp_path):
    db = tmp_path / "live.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,"
        " league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);"
        "CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,"
        " snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL, vol_pct_3 REAL,"
        " vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL);"
        "CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL);")
    # 6 forward-dated matches (kickoff after FORWARD_START), snapshot ~1h before
    for i in range(1, 7):
        con.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                    (f"M{i}", "26099", i, "挪超", "2026-06-20T19:35:00", "H", "A", 1.0))
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,"
                    "vol_pct_3,vol_pct_1,vol_pct_0,pool_total) VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"M{i}", "2026-06-20T10:35:00Z", 6.0, 3.4, 1.6, 0, 0, 0, 1000))
        con.execute("INSERT INTO settlements VALUES (?,?,?)", (f"M{i}", "3", 6.0))
    con.commit(); con.close()
    return db


def test_run_forward_returns_one_row_per_arm(tmp_path):
    db = _forward_db(tmp_path)
    pan = P.build(db, cache_path=tmp_path / "p.parquet", rebuild=True)
    arms = build_arms(baseline_mtk=600.0, haircut_map=HAIRCUT_MAP)
    rows = run_forward(pan, db, NicheConfig.load(), arms,
                       run_date="2026-06-21", forward_start="2026-06-13")
    assert len(rows) == 3
    assert {r["arm"] for r in rows} == {"C0", "C1", "C2"}
    r0 = rows[0]
    assert set(LEDGER_COLS) <= set(r0)               # every ledger column present
    assert r0["forward_start"] == "2026-06-13" and r0["run_date"] == "2026-06-21"
