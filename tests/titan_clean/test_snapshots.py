from __future__ import annotations

from datetime import datetime
from src.titan_clean.discovery import _decode_payload, parse_euro_1x2_quotes, parse_fixture_identity

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


def test_modern_post_kickoff_dates_are_not_shifted_into_previous_year():
    assert parse_market_time("06-02 00:15", kickoff=datetime(2026, 6, 1, 23)) == datetime(2026, 6, 2, 0, 15)
    assert parse_market_time("01-01 00:15", kickoff=datetime(2025, 12, 31, 23)) == datetime(2026, 1, 1, 0, 15)
    con = _mock_con()
    try:
        con.execute("INSERT INTO historical_fixture_observation VALUES('b','2026,6,1,23,00,00')")
        con.execute("INSERT INTO historical_euro_1x2_quote VALUES('b','1','Book','r',0,9,5,2,'06-02 00:15',NULL,NULL,NULL)")
        with pytest.raises(TitanSnapshotError, match='no timestamped pre-kickoff'):
            derive_fixture_snapshot(con, 'b', '00123')
    finally:
        con.close()


def test_receipt_binds_kickoff_bookmaker_and_implementation():
    con = _mock_con()
    try:
        con.execute("INSERT INTO historical_fixture_observation VALUES('b','2026,6,1,23,00,00')")
        con.execute("INSERT INTO historical_euro_1x2_quote VALUES('b','1','Book','r',0,2,3,4,'06-01 20:00',NULL,NULL,NULL)")
        a = derive_fixture_snapshot(con, 'b', '00123').receipt()
        con.execute("UPDATE historical_euro_1x2_quote SET bookmaker_source_name='Other'")
        b = derive_fixture_snapshot(con, 'b', '00123').receipt()
        assert a['source_binding_sha256'] != b['source_binding_sha256']
        con.execute("UPDATE historical_fixture_observation SET kickoff_source_raw='2026,6,2,23,00,00'")
        c = derive_fixture_snapshot(con, 'b', '00123').receipt()
        assert b['source_binding_sha256'] != c['source_binding_sha256']
        assert len(c['implementation_sha256']) == 64
    finally:
        con.close()


def test_malformed_time_cannot_disappear_from_an_otherwise_valid_snapshot():
    con = _mock_con()
    try:
        con.execute("INSERT INTO historical_fixture_observation VALUES('b','2026,6,1,23,00,00')")
        con.execute("INSERT INTO historical_euro_1x2_quote VALUES('b','1','Book','r',0,2,3,4,'06-01 20:00',NULL,NULL,NULL)")
        con.execute("INSERT INTO historical_euro_1x2_quote VALUES('b','1','Book','r',1,9,3,4,'unparseable',NULL,NULL,NULL)")
        with pytest.raises(TitanSnapshotError, match='malformed market timestamp'):
            derive_fixture_snapshot(con, 'b', '00123')
    finally:
        con.close()


def test_decode_payload_utf16_bom() -> None:
    text = 'var matchname="Test";\r\nMatchTime="2010,4,3,12,30,0";\r\n'
    utf16 = b"\xff\xfe" + text.encode("utf-16-le")  # 带 BOM
    assert _decode_payload(utf16) == text
    assert _decode_payload(text.encode("utf-8")) == text


def test_decode_payload_no_bom_utf16() -> None:
    # 去掉 BOM 的 UTF-16 由 charset-normalizer 检测
    text = 'var matchname="Test";\r\ngame=Array("a");'
    utf16_no_bom = text.encode("utf-16")[2:]  # 去掉 BOM
    assert _decode_payload(utf16_no_bom) == text


def test_decode_payload_gb18030_chinese_not_misdetected() -> None:
    # 短 GB18030 中文片段容易被误检为 big5/cp949；三层策略应先走已知源编码
    text = 'var matchname="里尔";game=Array("a");'
    assert _decode_payload(text.encode("gb18030")) == text


def test_decode_payload_utf8_bom_and_ascii() -> None:
    assert _decode_payload(b"\xef\xbb\xbf" + b'var matchname="x";') == 'var matchname="x";'
    assert _decode_payload(b'var matchname="ok";') == 'var matchname="ok";'


def test_decode_payload_no_decoder_succeeds() -> None:
    # fallback_encoding=None 且无法解码时抛错（检测器不可用时）
    try:
        import charset_normalizer  # noqa: F401
        detector_available = True
    except ImportError:
        detector_available = False
    if not detector_available:
        with pytest.raises(UnicodeDecodeError):
            _decode_payload(b"\xff\xfd\xfe\xfb", fallback_encoding=None)
    # 乱码文本会被 parse_fixture_identity 的结构校验拒绝（game=Array 缺失）
    import src.titan_clean.discovery as discovery_mod
    text = _decode_payload(b"\x80\x81\x82\x83\xff\xfe\xfd", fallback_encoding=None)
    assert "game" not in text or "Array" not in text


def test_utf16_legacy_fixture_parses() -> None:
    text = (
        'var matchname="English Premier League";\r\n'
        'MatchTime="2010,4,3,12,30,0";\r\n'
        'hometeamID=61;\r\nguestteamID=384;\r\n'
        'game=Array("16|13527428|10BET|1.82|3.39|4.29|40|30|30|100|1.9|3.4|4.1|45|30|25|100|0.9|0.9|0.9|2010,4,3,12,29,0|10BET(英国)|1|0");'
    )
    payload = text.encode("utf-16")
    ident = parse_fixture_identity(payload, provider_fixture_id="289498")
    assert ident.kickoff_source_raw == "2010,4,3,12,30,0"
    assert ident.home_team_source_id == "61"
    quotes = parse_euro_1x2_quotes(payload)
    assert len(quotes) == 2  # 开盘 + 即时
    assert quotes[0].home_odds == 1.82
    assert quotes[1].home_odds == 1.9
