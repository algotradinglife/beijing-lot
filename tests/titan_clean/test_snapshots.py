from __future__ import annotations

from datetime import datetime

import pytest

from src.titan_clean.snapshots import (
    SNAPSHOT_KINDS,
    TitanSnapshotError,
    _parse_kickoff,
    derive_fixture_snapshot,
    parse_market_time,
)


def test_parse_kickoff_legacy_and_modern() -> None:
    assert _parse_kickoff("2010,01-1,02,12,30,00") == datetime(2010, 1, 2, 12, 30, 0)
    assert _parse_kickoff("2019,12-1,31,08,00,00") == datetime(2019, 12, 31, 8, 0, 0)
    assert _parse_kickoff("2020,01-0,2,08,00,00") == datetime(2020, 1, 2, 8, 0, 0)
    assert _parse_kickoff(None) is None
    assert _parse_kickoff("garbage") is None


def test_parse_kickoff_plain_no_dash() -> None:
    # UTF-16 早期格式：YYYY,M,D,HH,MM,SS（无破折号、无前导零）
    assert _parse_kickoff("2010,4,3,12,30,0") == datetime(2010, 4, 3, 12, 30, 0)














def test_parse_market_time_legacy_full_year() -> None:
    kickoff = datetime(2010, 1, 2, 12, 30, 0)
    assert parse_market_time("2009,12-1,28,09,24,00", kickoff=kickoff) == datetime(2009, 12, 28, 9, 24, 0)


def test_parse_market_time_modern_same_year() -> None:
    kickoff = datetime(2019, 12, 31, 8, 0, 0)
    assert parse_market_time("12-20 12:29", kickoff=kickoff) == datetime(2019, 12, 20, 12, 29, 0)


def test_parse_market_time_modern_cross_year() -> None:
    # kickoff 01-02, a 12-31 stamp belongs to the previous year
    kickoff = datetime(2020, 1, 2, 8, 0, 0)
    assert parse_market_time("12-31 15:59", kickoff=kickoff) == datetime(2019, 12, 31, 15, 59, 0)


def test_parse_market_time_modern_requires_kickoff() -> None:
    assert parse_market_time("12-20 12:29", kickoff=None) is None
    assert parse_market_time(None, kickoff=datetime(2020, 1, 1)) is None


def _mock_con():
    """In-memory sqlite with the minimal tables derive_fixture_snapshot reads."""
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE historical_fixture_observation (
          batch_id TEXT PRIMARY KEY, kickoff_source_raw TEXT
        );
        CREATE TABLE historical_euro_1x2_quote (
          batch_id TEXT, company_source_id TEXT, bookmaker_source_name TEXT,
          record_source_id TEXT, ordinal INTEGER, home_odds REAL, draw_odds REAL,
          away_odds REAL, market_time_source_raw TEXT,
          home_kelly REAL, draw_kelly REAL, away_kelly REAL
        );
    """)
    return con


def test_derive_snapshot_legacy_single_snapshot() -> None:
    con = _mock_con()
    try:
        con.execute("INSERT INTO historical_fixture_observation VALUES('b', '2010,01-1,02,12,30,00')")
        con.executemany(
            "INSERT INTO historical_euro_1x2_quote VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                # 公司 A：开盘 2.37 / 即时 2.87，同一时间戳
                ("b", "16", "10BET", "r1", 0, 2.37, 3.2, 2.75, "2010,01-1,02,10,24,00", None, None, None),
                ("b", "16", "10BET", "r1", 1, 2.87, 3.3, 2.63, "2010,01-1,02,10,24,00", None, None, None),
            ],
        )
        snap = derive_fixture_snapshot(con, "b", "356275")
        assert snap.kickoff == datetime(2010, 1, 2, 12, 30, 0)
        assert snap.captured_quote_count == 2
        kinds = {s.kind for s in snap.rows}
        assert kinds == {"initial", "final", "1h"}  # 10h 前无记录（10:24 距 02:30 开赛 < 10h）
        by_kind = {s.kind: s for s in snap.rows}
        assert by_kind["initial"].home_odds == 2.37
        assert by_kind["final"].home_odds == 2.87
    finally:
        con.close()


def test_derive_snapshot_modern_final_excludes_after_kickoff() -> None:
    con = _mock_con()
    try:
        con.execute("INSERT INTO historical_fixture_observation VALUES('b', '2019,12-1,31,08,00,00')")
        con.executemany(
            "INSERT INTO historical_euro_1x2_quote VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                # 三条记录：开赛前 1 天、开赛前 5 分钟、开赛后 10 分钟（应排除）
                ("b", "177", "Pinnacle", "r1", 0, 4.0, 3.75, 1.87, "12-30 08:00", None, None, None),
                ("b", "177", "Pinnacle", "r1", 1, 4.4, 3.75, 1.8, "12-31 07:55", None, None, None),
                ("b", "177", "Pinnacle", "r1", 2, 9.0, 5.0, 1.2, "12-31 08:10", None, None, None),
            ],
        )
        snap = derive_fixture_snapshot(con, "b", "1784028")
        by_kind = {s.kind: s for s in snap.rows}
        assert by_kind["final"].market_time == datetime(2019, 12, 31, 7, 55, 0)
        assert by_kind["final"].home_odds == 4.4
        # 1h 切片 target = 07:00；07:55 晚于 target，回退到 12-30 08:00 的记录
        assert by_kind["1h"].home_odds == 4.0
        assert snap.rows  # no crash
    finally:
        con.close()


def test_snapshot_kinds_contract() -> None:
    assert SNAPSHOT_KINDS == ("initial", "final", "10h", "1h")
    with pytest.raises(TitanSnapshotError):
        raise TitanSnapshotError("fixture has no euro quotes")


def test_diagnostic_receipt_never_claims_observed_availability():
    from src.titan_clean.snapshots import SnapshotSet
    receipt = SnapshotSet('00123', None, (), 'a' * 64, 0, 0).receipt()
    assert receipt['availability_policy'] == 'HISTORICAL_PROXY'
    assert receipt['prospective_use'] is False
    assert receipt['source_timezone'] == 'Asia/Shanghai'


def test_snapshot_fails_closed_without_prior_timestamped_quotes():
    con = _mock_con()
    try:
        with pytest.raises(TitanSnapshotError, match='missing kickoff'):
            derive_fixture_snapshot(con, 'b', '00123')
        con.execute("INSERT INTO historical_fixture_observation VALUES('b','2010,1,2,12,30,00')")
        con.execute("INSERT INTO historical_euro_1x2_quote VALUES('b','1','Book','r',0,2,3,4,'2010,1,2,12,31,00',NULL,NULL,NULL)")
        with pytest.raises(TitanSnapshotError, match='no timestamped pre-kickoff'):
            derive_fixture_snapshot(con,'b','00123')
    finally:
        con.close()
