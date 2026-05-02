"""DB integration tests."""
from pathlib import Path

import pytest
from conftest import fixture

from live_collector.db import Database
from live_collector.parser import (
    MatchSnapshot,
    Settlement,
    parse_bet_page_500,
    parse_kaijiang,
)


@pytest.fixture()
def tmp_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    yield db
    db.close()


def test_schema_creates_tables(tmp_db: Database):
    cur = tmp_db._conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    assert {"matches", "snapshots", "settlements"} <= tables


def test_insert_snapshot_idempotent(tmp_db: Database):
    snap = MatchSnapshot(issue="26051", match_idx=1, league="挪超",
                         home="博德闪耀", away="斯达", handicap_line=-2.0,
                         sp_3=1.76, sp_1=3.4, sp_0=5.5)
    ts = "2026-05-01T00:00:00Z"
    assert tmp_db.insert_snapshot(snap, source="test", snapshot_ts=ts) is True
    # second call same ts+source -> no new row
    assert tmp_db.insert_snapshot(snap, source="test", snapshot_ts=ts) is False
    assert tmp_db.count_snapshots() == 1
    assert tmp_db.count_matches() == 1


def test_insert_snapshot_different_ts_produces_two_rows(tmp_db: Database):
    snap = MatchSnapshot(issue="26051", match_idx=1, sp_3=1.76)
    tmp_db.insert_snapshot(snap, source="test", snapshot_ts="2026-05-01T00:00:00Z")
    tmp_db.insert_snapshot(snap, source="test", snapshot_ts="2026-05-01T00:05:00Z")
    assert tmp_db.count_snapshots() == 2
    assert tmp_db.count_matches() == 1  # same match


def test_real_bet_page_round_trip(tmp_db: Database):
    html = fixture("bjdc500_26051.html")
    rows = parse_bet_page_500(html, issue="26051")
    inserted = 0
    for r in rows:
        if tmp_db.insert_snapshot(r, source="500", snapshot_ts="2026-05-01T00:00:00Z"):
            inserted += 1
    assert inserted == len(rows)
    assert tmp_db.count_snapshots(issue="26051") == len(rows)


def test_settlement_round_trip(tmp_db: Database):
    html = fixture("kaijiang_500_26051.html")
    settles = parse_kaijiang(html, issue="26051")
    # need matches first
    for s in settles:
        snap = MatchSnapshot(issue=s.issue, match_idx=s.match_idx)
        tmp_db.upsert_match(snap)
    written = sum(tmp_db.insert_settlement(s) for s in settles
                  if s.result_code is not None)
    assert written >= 1
    # writing again is idempotent (REPLACE)
    again = sum(tmp_db.insert_settlement(s) for s in settles
                if s.result_code is not None)
    assert again >= 1


def test_issues_needing_settlement(tmp_db: Database):
    snap = MatchSnapshot(issue="26051", match_idx=1)
    tmp_db.upsert_match(snap)
    assert tmp_db.issues_needing_settlement() == ["26051"]
    tmp_db.insert_settlement(Settlement(match_id="26051_001", issue="26051",
                                        match_idx=1, result_code="3",
                                        winning_sp=1.76))
    assert tmp_db.issues_needing_settlement() == []
