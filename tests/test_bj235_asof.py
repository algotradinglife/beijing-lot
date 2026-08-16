"""Golden as-of replay tests (REQ-BJ03), line-state retention (REQ-BJ04),
0.65 absence (REQ-BJ05), idempotency (REQ-BJ07).

Builds a tiny canonical DB in a tmp dir with synthetic observations designed
to trip every selection gate.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.bj_sp_timeseries.asof import (
    build_decision_epochs,
    build_probability_estimates,
    run_asof_replay,
)
from src.bj_sp_timeseries.ingest import connect_canonical, register_sources

TMP = Path(__file__).resolve().parent / "_tmp_bj235"


def _mk_canonical(tmp_path: Path) -> sqlite3.Connection:
    con = connect_canonical(tmp_path / "canon.sqlite")
    register_sources(con)
    return con


def _add_fixture(con, fid="26075_001", kickoff="2026-07-14T19:30:00Z",
                 line=-1.0, issue="26075"):
    con.execute(
        """INSERT OR IGNORE INTO fixture
           (fixture_id, issue_code, match_idx, source_match_key, competition,
            home, away, kickoff_at_utc, native_handicap_line, identity_status)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (fid, issue, 1, None, "L", "H", "A", kickoff, line, "canonical"),
    )


def _add_obs(con, obs_id, fid, recv, observed=None, line=-1.0,
             sp=None, source="beidan_live_500", batch_id=None):
    """sp: dict code->odds or None for missing."""
    con.execute(
        """INSERT OR IGNORE INTO market_observation
           (observation_id, fixture_id, source_id, market_type, handicap_line,
            observed_at_utc, received_at_utc, snapshot_kind, batch_id, sale_status)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (obs_id, fid, source, "handicap_3way", line,
         observed or recv, recv, "live_poll", batch_id, None),
    )
    for code in ("3", "1", "0"):
        val = (sp or {}).get(code)
        qs = "present" if val is not None and val > 0 else "missing"
        con.execute(
            """INSERT OR IGNORE INTO market_quote
               (quote_id, observation_id, outcome_code, decimal_odds, quote_status)
               VALUES (?,?,?,?,?)""",
            (f"{obs_id}_{code}", obs_id, code, val, qs),
        )
    con.commit()


# ---------------------------------------------------------------------------
# REQ-BJ03: as-of replay selects no post-decision/post-kickoff row
# ---------------------------------------------------------------------------
def test_replay_rejects_post_decision_and_post_kickoff(tmp_path):
    con = _mk_canonical(tmp_path)
    _add_fixture(con, kickoff="2026-07-14T19:30:00Z")
    # observation AFTER decision epoch (epoch = kickoff - 1h => 18:30)
    _add_obs(con, "o_late", "26075_001", recv="2026-07-14T18:45:00Z",
             sp={"3": 2.0, "1": 3.0, "0": 4.0})
    # observation AFTER kickoff
    _add_obs(con, "o_after_ko", "26075_001", recv="2026-07-14T20:00:00Z",
             sp={"3": 2.0, "1": 3.0, "0": 4.0})
    # valid pre-decision observation
    _add_obs(con, "o_valid", "26075_001", recv="2026-07-14T17:00:00Z",
             sp={"3": 2.2, "1": 3.1, "0": 3.9})

    build_decision_epochs(con, epochs_hours_before_kickoff=(1.0,))
    stats = run_asof_replay(con)
    assert stats["selected_complete"] == 1
    assert stats["post_kickoff_rejected"] >= 1

    sel = con.execute(
        """SELECT aso.observation_id, aso.complete FROM as_of_selection aso
           JOIN decision_epoch de ON de.decision_epoch_id = aso.decision_epoch_id"""
    ).fetchall()
    assert len(sel) == 1
    assert sel[0]["observation_id"] == "o_valid"


# ---------------------------------------------------------------------------
# REQ-BJ02: incomplete triplet stays explicit (complete=0 or exclusion ledger)
# ---------------------------------------------------------------------------
def test_replay_marks_incomplete_triplet_explicit(tmp_path):
    con = _mk_canonical(tmp_path)
    _add_fixture(con, kickoff="2026-07-14T19:30:00Z")
    # incomplete: only 2 of 3 outcomes (observed LATER than the complete one)
    _add_obs(con, "o_incomplete", "26075_001", recv="2026-07-14T17:00:00Z",
             sp={"3": 2.2, "1": 3.1})
    # valid complete (earlier)
    _add_obs(con, "o_complete", "26075_001", recv="2026-07-14T16:30:00Z",
             sp={"3": 2.2, "1": 3.1, "0": 3.9})

    build_decision_epochs(con, epochs_hours_before_kickoff=(1.0,))
    stats = run_asof_replay(con)
    # latest COMPLETE triplet wins: o_complete (16:30) selected complete
    assert stats["selected_complete"] == 1
    assert stats["selected_incomplete"] == 0
    # the later incomplete observation lost but is explicit in the exclusion ledger
    assert stats["incomplete_lost_explicit"] >= 1
    excl = con.execute(
        "SELECT reason_code, detail FROM exclusion_ledger WHERE reason_code='INCOMPLETE_TRIPLET'"
    ).fetchall()
    assert len(excl) >= 1
    assert "o_incomplete" in excl[0]["detail"]
    sel = con.execute("SELECT observation_id, complete FROM as_of_selection").fetchall()
    assert sel[0]["observation_id"] == "o_complete"
    assert sel[0]["complete"] == 1


# ---------------------------------------------------------------------------
# REQ-BJ04: line changes retained, never joined across different native-line states
# ---------------------------------------------------------------------------
def test_line_state_never_joined_across(tmp_path):
    con = _mk_canonical(tmp_path)
    # kickoff 19:30, epochs at 17:00 (kickoff-2.5h)
    _add_fixture(con, kickoff="2026-07-14T19:30:00Z")
    # line -1 observed at 16:00
    _add_obs(con, "o_line_m1", "26075_001", recv="2026-07-14T16:00:00Z",
             line=-1.0, sp={"3": 2.2, "1": 3.1, "0": 3.9})
    # line -2 observed at 18:00 (line change)
    _add_obs(con, "o_line_m2", "26075_001", recv="2026-07-14T18:00:00Z",
             line=-2.0, sp={"3": 2.5, "1": 3.0, "0": 3.5})
    build_decision_epochs(con, epochs_hours_before_kickoff=(2.5,))
    run_asof_replay(con)

    sel = con.execute(
        """SELECT aso.observation_id, aso.complete, mo.handicap_line
           FROM as_of_selection aso
           JOIN market_observation mo ON mo.observation_id = aso.observation_id"""
    ).fetchall()
    # Latest complete wins: line -2 obs (18:00), which is <= decision (17:00)? NO
    # decision 17:00 -> 18:00 is post-decision; so line -1 obs (16:00) is selected.
    assert len(sel) == 1
    assert sel[0]["handicap_line"] == -1.0

    # now test selection at a later epoch where the line-2 obs qualifies
    build_decision_epochs(con, epochs_hours_before_kickoff=(1.0,))  # decision 18:30
    run_asof_replay(con)
    sel2 = con.execute(
        """SELECT aso.observation_id, aso.complete, mo.handicap_line
           FROM as_of_selection aso
           JOIN market_observation mo ON mo.observation_id = aso.observation_id
           JOIN decision_epoch de ON de.decision_epoch_id = aso.decision_epoch_id
           WHERE de.decision_at_utc='2026-07-14T18:30:00Z'"""
    ).fetchall()
    assert len(sel2) == 1
    assert sel2[0]["handicap_line"] == -2.0  # never joined across line states


# ---------------------------------------------------------------------------
# REQ-BJ05: 0.65 and settlement SP absent from inference tables
# ---------------------------------------------------------------------------
def test_no_065_and_no_settlement_sp_in_inference(tmp_path):
    con = _mk_canonical(tmp_path)
    _add_fixture(con, kickoff="2026-07-14T19:30:00Z")
    _add_obs(con, "o_ok", "26075_001", recv="2026-07-14T17:00:00Z",
             sp={"3": 2.2, "1": 3.1, "0": 3.9})
    build_decision_epochs(con, epochs_hours_before_kickoff=(1.0,))
    run_asof_replay(con)
    build_probability_estimates(con)

    probs = con.execute("SELECT outcome_code, probability FROM probability_estimate").fetchall()
    assert len(probs) == 3
    for code, p in probs:
        assert 0.0 < p < 1.0
    # no 0.65 coefficient anywhere in quote/probability tables
    bad = con.execute(
        "SELECT COUNT(*) FROM market_quote WHERE decimal_odds=0.65"
    ).fetchone()[0]
    assert bad == 0
    # settlement table is physically separate
    assert con.execute("SELECT COUNT(*) FROM settlement").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# REQ-BJ07: duplicate ingestion is idempotent under canonical batch keys
# ---------------------------------------------------------------------------
def test_ingestion_idempotent(tmp_path):
    from src.bj_sp_timeseries.ingest import ingest_beidan_live
    import os

    # fabricate a tiny beidan_live.db
    live = tmp_path / "beidan_live.db"
    lc = sqlite3.connect(str(live))
    lc.executescript(
        """CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INT,
            league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, handicap_line REAL,
            status TEXT, created_ts TEXT, fid TEXT);
           CREATE TABLE snapshots (id INTEGER PRIMARY KEY, match_id TEXT, snapshot_ts TEXT,
            sp_3 REAL, sp_1 REAL, sp_0 REAL, vol_pct_3 REAL, vol_pct_1 REAL, vol_pct_0 REAL,
            pool_total REAL, eu_h REAL, eu_d REAL, eu_a REAL, source TEXT);
           INSERT INTO matches VALUES ('26075_001','26075',1,'L','2026-07-14T19:30:00','H','A',-1.0,'open','2026-07-01','f1');
           INSERT INTO snapshots VALUES (1,'26075_001','2026-07-14T17:00:00Z',2.2,3.1,3.9,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'500');
           INSERT INTO snapshots VALUES (2,'26075_001','2026-07-14T18:00:00Z',2.3,3.0,3.8,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'500');"""
    )
    lc.commit()
    lc.close()

    con = _mk_canonical(tmp_path)
    c1 = ingest_beidan_live(con, live, batch_id="dup_test")
    c2 = ingest_beidan_live(con, live, batch_id="dup_test")
    assert c1["observations"] == c2["observations"] == 2
    assert con.execute("SELECT COUNT(*) FROM market_observation").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM market_quote").fetchone()[0] == 6


# ---------------------------------------------------------------------------
# fixture: determinism of the whole as-of selection (golden numbers)
# ---------------------------------------------------------------------------
def test_golden_asof_selection(tmp_path):
    con = _mk_canonical(tmp_path)
    _add_fixture(con, kickoff="2026-07-14T19:30:00Z", line=-1.0)
    # obs timeline (received):
    #   17:00 complete
    #   18:45 complete (within decision 18:30? no -> 18:45 > 18:30, rejected)
    #   19:00 complete (post-decision for 18:30, pre for 19:00? decision 19:00 < kickoff ok)
    _add_obs(con, "o1", "26075_001", recv="2026-07-14T17:00:00Z",
             sp={"3": 2.2, "1": 3.1, "0": 3.9})
    _add_obs(con, "o2", "26075_001", recv="2026-07-14T18:45:00Z",
             sp={"3": 2.4, "1": 3.0, "0": 3.7})
    _add_obs(con, "o3", "26075_001", recv="2026-07-14T19:00:00Z",
             sp={"3": 2.5, "1": 2.9, "0": 3.6})

    build_decision_epochs(con, epochs_hours_before_kickoff=(0.5, 1.0))
    stats = run_asof_replay(con)
    assert stats["selected_complete"] == 2
    sel = con.execute(
        """SELECT de.decision_at_utc, aso.observation_id, aso.complete
           FROM as_of_selection aso JOIN decision_epoch de
             ON de.decision_epoch_id = aso.decision_epoch_id
           ORDER BY de.decision_at_utc"""
    ).fetchall()
    # epoch 18:30 -> o1 (17:00) since o2(18:45) post-decision
    assert sel[0]["decision_at_utc"] == "2026-07-14T18:30:00Z"
    assert sel[0]["observation_id"] == "o1"
    # epoch 19:00 -> o3 (19:00) is in window (19:00 <= 19:00 < 19:30) and
    # latest complete wins
    assert sel[1]["decision_at_utc"] == "2026-07-14T19:00:00Z"
    assert sel[1]["observation_id"] == "o3"


# ---------------------------------------------------------------------------
# REQ-BJ08 cohort classification: strict_historical vs prospective
# ---------------------------------------------------------------------------
def test_cohort_classification():
    from src.bj_sp_timeseries.recover import cohort_name, issue_year
    assert issue_year("26075") == 2026
    assert issue_year("140101") == 2014
    assert issue_year("25042") == 2025
    assert cohort_name(2026) == "prospective"
    assert cohort_name(2025) == "strict_historical"
    assert cohort_name(2014) == "strict_historical"
