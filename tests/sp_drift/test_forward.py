import pandas as pd

from src.sp_drift.forward import (
    FORWARD_START,
    HAIRCUT_MAP,
    LEDGER_COLS,
    build_arms,
    forward_panel,
    render_arm_table,
)


def test_ledger_cols_include_weekly_sigma():
    assert "weekly_sigma" in LEDGER_COLS


def test_favorite_arm_row_picks_favorites_and_settles():
    import sqlite3
    import tempfile
    from pathlib import Path as _Path
    from src.sp_drift import panel as P
    from src.sp_drift.forward import favorite_arm_row

    d = _Path(tempfile.mkdtemp())
    db = d / "fav.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE matches (match_id TEXT, issue TEXT, match_idx INT, league TEXT,"
        " kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);"
        "CREATE TABLE snapshots (match_id TEXT, snapshot_ts TEXT, sp_3 REAL, sp_1 REAL,"
        " sp_0 REAL, vol_pct_3 REAL, vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL);"
        "CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL);")
    # 6 forward-dated matches, favorite is always home (sp_3=2.0 lowest).
    # 4 favorite-hits (result 3), 2 favorite-misses (result 0).
    for i in range(1, 7):
        con.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                    (f"M{i}", "26099", i, "挪超", "2026-06-20T19:35:00", "H", "A", 1.0))
        con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,"
                    "vol_pct_3,vol_pct_1,vol_pct_0,pool_total) VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"M{i}", "2026-06-20T10:35:00Z", 2.0, 4.0, 5.0, 0, 0, 0, 1000))
        rc, wsp = ("3", 2.0) if i <= 4 else ("0", 5.0)
        con.execute("INSERT INTO settlements VALUES (?,?,?)", (f"M{i}", rc, wsp))
    con.commit(); con.close()

    pan = P.build(db, cache_path=d / "p.parquet", rebuild=True)
    row = favorite_arm_row(pan, db, run_date="2026-06-21", forward_start="2026-06-13",
                           n_legs=2, mtk_target=30.0, max_combos=999)
    assert row["arm"] == "FAV2"
    assert row["n_combos"] == 15          # C(6,2)
    assert row["n_hits"] == 6             # C(4,2): both legs must be hitting favorites
    assert "weekly_sigma" in row and "roi" in row


def test_render_arm_table_shows_hit_rate_and_weekly_sigma():
    latest = {
        "C0": {"n_combos": 10, "n_hits": 2, "total_stake": 100.0,
               "roi": 0.5, "max_dd": 0.1, "weekly_sigma": 12.34},
        "N3": {"n_combos": 0, "n_hits": 0, "total_stake": 0.0,
               "roi": 0.0, "max_dd": 0.0, "weekly_sigma": 0.0},
    }
    lines = render_arm_table(latest, ["C0", "N3"])
    header = lines[0]
    assert "命中率" in header and "周σ" in header
    body = "\n".join(lines)
    assert "20.0%" in body          # C0 hit rate = 2/10
    assert "12.3" in body           # C0 weekly sigma rendered
    # zero-combo arm must not divide-by-zero; deterministic 0
    n3_row = [ln for ln in lines if ln.startswith("| N3 ")][0]
    assert "0.0%" in n3_row


def test_forward_panel_keeps_only_kickoffs_after_start():
    panel = pd.DataFrame({
        "match_id": ["A", "B"],
        "kickoff_ts": ["2026-06-10T19:00:00", "2026-06-20T19:00:00"],
        "sp": [4.0, 4.0],
    })
    out = forward_panel(panel, "2026-06-13")
    assert list(out["match_id"]) == ["B"]


def test_build_arms_drift_arms_with_expected_policies():
    arms = build_arms(baseline_mtk=1080.0, haircut_map=HAIRCUT_MAP)
    by = dict(arms)
    # SP-drift arms (unchanged): control + window + window/haircut
    assert by["C0"].mtk_target == 1080.0 and by["C0"].haircut is None
    assert by["C1"].mtk_target == 180.0 and by["C1"].haircut is None
    assert by["C2"].mtk_target == 180.0 and by["C2"].haircut == HAIRCUT_MAP


def test_build_arms_includes_n_sweep_arms():
    # N3/N5 isolate leg count: same decision timing as C0 (baseline, no
    # haircut), only n_legs differs. C0 is the N=4 reference (Policy default).
    arms = build_arms(baseline_mtk=1080.0, haircut_map=HAIRCUT_MAP)
    by = dict(arms)
    assert "N3" in by and "N5" in by
    assert by["C0"].n_legs == 4
    assert by["N3"].n_legs == 3 and by["N3"].mtk_target == 1080.0 and by["N3"].haircut is None
    assert by["N5"].n_legs == 5 and by["N5"].mtk_target == 1080.0 and by["N5"].haircut is None


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
    # one row per arm, whatever the arm set is
    assert len(rows) == len(arms)
    assert {r["arm"] for r in rows} == {n for n, _ in arms}
    assert {"C0", "C1", "C2", "N3", "N5"} <= {r["arm"] for r in rows}
    r0 = rows[0]
    assert set(LEDGER_COLS) <= set(r0)               # every ledger column present
    assert r0["forward_start"] == "2026-06-13" and r0["run_date"] == "2026-06-21"


# ---- P3: QHC (model conservative-quantile haircut) forward arm ----
def test_apply_sp_adjust_maps_each_sp():
    from src.phase5a.data_loader import LiveSnapshot
    from src.sp_drift.replay import apply_sp_adjust
    s = LiveSnapshot(match_id="m", issue="1", match_idx=1, league="x",
                     kickoff_ts="t", home=None, away=None, handicap_line=None,
                     sp_3=4.0, sp_1=None, sp_0=2.0, snapshot_ts=None)
    out = apply_sp_adjust([s], lambda sp: sp * 0.5)[0]
    assert out.sp_3 == 2.0 and out.sp_0 == 1.0 and out.sp_1 is None


def test_build_qhc_arm_uses_model_quantile():
    from src.sp_drift.drift_model import DriftModel
    from src.sp_drift.forward import build_qhc_arm
    # empty cells → everything falls back to global prior (mean 0.8). q=0.5 → mean.
    model = DriftModel(cells={}, band_prior={}, global_prior=(0.8, 0.2))
    name, pol = build_qhc_arm(model, decision_mtk=600.0, q=0.5)
    assert name == "QHC"
    assert pol.mtk_target == 600.0
    assert pol.sp_adjust is not None and pol.haircut is None
    assert abs(pol.sp_adjust(4.0) - 3.2) < 1e-6      # 4.0 × 0.8


def test_run_forward_includes_qhc_arm(tmp_path):
    from src.sp_drift import panel as P
    from src.sp_drift.drift_model import fit_drift_model
    from src.sp_drift.forward import build_qhc_arm
    db = _forward_db(tmp_path)
    pan = P.build(db, cache_path=tmp_path / "p.parquet", rebuild=True)
    model = fit_drift_model(pan)
    arms = build_arms(baseline_mtk=600.0, haircut_map=HAIRCUT_MAP)
    arms.append(build_qhc_arm(model, decision_mtk=30.0, q=0.25))
    rows = run_forward(pan, db, NicheConfig.load(), arms,
                       run_date="2026-06-21", forward_start="2026-06-13")
    by = {r["arm"] for r in rows}
    assert "QHC" in by
    qhc = [r for r in rows if r["arm"] == "QHC"][0]
    assert set(LEDGER_COLS) <= set(qhc)


def test_stable_sp_decision_snapshots_filters_unstable_legs():
    from src.sp_drift.forward import stable_sp_decision_snapshots

    class NeutralModel:
        def lookup(self, sp, mtk):
            return (1.0, 0.0, 10)

    panel = pd.DataFrame([
        # M1 passes: odds <= 4.5 and small 10h->1h move.
        {"match_id": "M1", "selection": "3", "sp": 4.0, "mtk": 600.0, "kickoff_ts": "2026-06-20T19:00:00",
         "issue": "26099", "match_idx": 1, "league": "英超", "handicap_line": 2.0},
        {"match_id": "M1", "selection": "3", "sp": 4.05, "mtk": 60.0, "kickoff_ts": "2026-06-20T19:00:00",
         "issue": "26099", "match_idx": 1, "league": "英超", "handicap_line": 2.0},
        # M2 fails max_odds.
        {"match_id": "M2", "selection": "3", "sp": 5.2, "mtk": 600.0, "kickoff_ts": "2026-06-20T19:00:00",
         "issue": "26099", "match_idx": 2, "league": "英超", "handicap_line": 2.0},
        {"match_id": "M2", "selection": "3", "sp": 5.2, "mtk": 60.0, "kickoff_ts": "2026-06-20T19:00:00",
         "issue": "26099", "match_idx": 2, "league": "英超", "handicap_line": 2.0},
        # M3 fails recent move.
        {"match_id": "M3", "selection": "3", "sp": 3.0, "mtk": 600.0, "kickoff_ts": "2026-06-20T19:00:00",
         "issue": "26099", "match_idx": 3, "league": "英超", "handicap_line": 2.0},
        {"match_id": "M3", "selection": "3", "sp": 4.4, "mtk": 60.0, "kickoff_ts": "2026-06-20T19:00:00",
         "issue": "26099", "match_idx": 3, "league": "英超", "handicap_line": 2.0},
    ])
    snaps = stable_sp_decision_snapshots(panel, NeutralModel(), forward_start="2026-06-13")
    assert [s.match_id for s in snaps] == ["M1"]
    assert snaps[0].sp_3 == 4.05 and snaps[0].sp_1 is None and snaps[0].sp_0 is None


def test_stable_sp_arm_row_returns_s7_ledger_row(tmp_path):
    from src.sp_drift.forward import stable_sp_arm_row

    db = tmp_path / "stable.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,"
        " league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL);"
        "CREATE TABLE snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,"
        " snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL, vol_pct_3 REAL,"
        " vol_pct_1 REAL, vol_pct_0 REAL, pool_total REAL);"
        "CREATE TABLE settlements (match_id TEXT, result_code TEXT, winning_sp REAL);")
    for phase, issue, kickoff in [
        ("train", "26040", "2026-06-10T19:35:00"),
        ("forward", "26099", "2026-06-20T19:35:00"),
    ]:
        day = "2026-06-10" if phase == "train" else "2026-06-20"
        for i in range(1, 9):
            mid = f"{phase}_{i}"
            con.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                        (mid, issue, i, "英超", kickoff, "H", "A", 1.0))
            # 10h and 1h snapshots. Stable away SP fits the phase5a
            # away_sp_3.0-3.5_h1 rule and remains below the N=7 tax-cap cliff.
            con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,"
                        "vol_pct_3,vol_pct_1,vol_pct_0,pool_total) VALUES (?,?,?,?,?,?,?,?,?)",
                        (mid, f"{day}T01:35:00Z", 2.5, 2.4, 3.4, 0, 0, 0, 1000))
            con.execute("INSERT INTO snapshots (match_id,snapshot_ts,sp_3,sp_1,sp_0,"
                        "vol_pct_3,vol_pct_1,vol_pct_0,pool_total) VALUES (?,?,?,?,?,?,?,?,?)",
                        (mid, f"{day}T10:35:00Z", 2.5, 2.4, 3.4, 0, 0, 0, 1000))
            con.execute("INSERT INTO settlements VALUES (?,?,?)", (mid, "0", 3.4))
    con.commit(); con.close()

    pan = P.build(db, cache_path=tmp_path / "stable.parquet", rebuild=True)
    row = stable_sp_arm_row(pan, db, NicheConfig.load(), run_date="2026-06-21",
                            forward_start="2026-06-13", n_legs=7,
                            start_bankroll=1_000_000.0, kelly_fraction=0.25)
    assert row["arm"] == "S7"
    assert set(LEDGER_COLS) <= set(row)
    assert row["n_combos"] > 0


# ---- P3 fix: QHC model must train only on pre-forward data (no leakage) ----
def test_training_panel_is_preforward_complement():
    from src.sp_drift.forward import training_panel
    panel = pd.DataFrame({"match_id": ["A", "B"],
                          "kickoff_ts": ["2026-06-10T19:00:00", "2026-06-20T19:00:00"],
                          "sp": [4.0, 4.0]})
    tr = training_panel(panel, "2026-06-13")
    fw = forward_panel(panel, "2026-06-13")
    assert list(tr["match_id"]) == ["A"]            # only kickoff <= cutoff
    assert list(fw["match_id"]) == ["B"]
    assert set(tr["match_id"]) & set(fw["match_id"]) == set()


def test_qhc_model_trained_only_on_pre_forward_data():
    from src.sp_drift.forward import build_qhc_arm_from_panel
    fs = "2026-06-13"
    rows = []
    # pre-forward (kickoff <= cutoff): ratio 0.9 (decision 4.0@800min, close 3.6@10)
    for i in range(40):
        rows.append((f"P{i}", "3", 4.0, 800.0, "2026-06-10T19:00:00"))
        rows.append((f"P{i}", "3", 3.6, 10.0, "2026-06-10T19:00:00"))
    # post-forward (kickoff > cutoff): ratio 0.3 — MUST NOT leak into the model
    for i in range(40):
        rows.append((f"Q{i}", "3", 4.0, 800.0, "2026-06-20T19:00:00"))
        rows.append((f"Q{i}", "3", 1.2, 10.0, "2026-06-20T19:00:00"))
    panel = pd.DataFrame(rows, columns=["match_id", "selection", "sp", "mtk", "kickoff_ts"])
    name, pol = build_qhc_arm_from_panel(panel, fs, decision_mtk=800.0, q=0.5)
    assert name == "QHC"
    adj = pol.sp_adjust(4.0)          # q=0.5 → sp × mean ratio at (3.5-4.5, 720-1440)
    assert abs(adj - 3.6) < 0.15      # pre-forward mean 0.9 → 3.6
    assert adj > 3.0                  # NOT the leaked blend (~2.4) or post (~1.2)
