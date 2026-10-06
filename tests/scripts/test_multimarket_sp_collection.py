from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from beidan_backend.sources.five_hundred_betting import MARKET_OUTCOMES  # noqa: E402
from scripts import live_sp_refresh_loop as refresh  # noqa: E402
from scripts import scrape_500_bjdc as scraper  # noqa: E402


def xml(playid: int) -> bytes:
    _, outcomes = MARKET_OUTCOMES[playid]
    attributes = " ".join(f'{attribute}="{index + 1}.25"' for index, (_, _, attribute) in enumerate(outcomes))
    payload = (
        f'<root updatetime="2026-07-16 20:00:00">'
        f'<w1 {attributes} h="主队" a="客队" gn="测试联赛" r="-1" />'
        f"</root>"
    )
    return payload.encode("gb18030")


def test_multimarket_outcome_maps_are_complete_and_stable() -> None:
    expected = {34: 3, 40: 8, 41: 4, 42: 25, 51: 9}
    for playid, outcome_count in expected.items():
        source_at, rows = scraper.parse_live_market_sp("X", playid, xml(playid), "2026-07-16 12:00:00")
        assert source_at == "2026-07-16 20:00:00"
        assert len(rows) == outcome_count
        assert {row["market_key"] for row in rows} == {MARKET_OUTCOMES[playid][0]}
        assert all(row["sp"] is not None for row in rows)

    _, total_goals = scraper.parse_live_market_sp("X", 40, xml(40), "now")
    assert [row["outcome_code"] for row in total_goals] == ["0", "1", "2", "3", "4", "5", "6", "7+"]
    assert [row["source_attribute"] for row in total_goals] == ["c1", "c3", "c5", "c7", "c9", "c11", "c13", "c15"]

    _, upper_lower = scraper.parse_live_market_sp("X", 41, xml(41), "now")
    assert [row["outcome_label"] for row in upper_lower] == ["上+单", "上+双", "下+单", "下+双"]

    _, scores = scraper.parse_live_market_sp("X", 42, xml(42), "now")
    assert scores[0]["outcome_label"] == "胜其他"
    assert scores[16]["outcome_code"] == "0:1"
    assert scores[-1]["outcome_code"] == "2:4"

    _, half_full = scraper.parse_live_market_sp("X", 51, xml(51), "now")
    assert [row["outcome_code"] for row in half_full] == [
        "3-3", "3-1", "3-0", "1-3", "1-1", "1-0", "0-3", "0-1", "0-0"
    ]


def test_parse_playids_defaults_to_all_markets_and_deduplicates() -> None:
    assert scraper.parse_playids(None) == (34, 40, 41, 42, 51)
    assert scraper.parse_playids(["40,41", "41", 51]) == (40, 41, 51)


def test_scrape_live_sp_writes_normalized_rows_and_distinct_fetch_kind(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "market.sqlite"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    scraper.create_schema(connection)
    monkeypatch.setattr(
        scraper,
        "fetch_url",
        lambda *args, **kwargs: scraper.FetchResult(
            url="https://example.test/40.xml",
            status=200,
            body=xml(40),
            elapsed_sec=0.1,
        ),
    )
    monkeypatch.setattr(
        scraper,
        "now_utc",
        lambda: "2026-07-16T12:00:00+00:00",
    )
    args = argparse.Namespace(
        playid=40,
        timeout=10,
        user_agent="test",
        keep_going=False,
        capture_root=tmp_path / "captures",
    )

    assert scraper.scrape_live_sp(connection, "X", args) == 1
    stored = connection.execute(
        "SELECT outcome_code, outcome_label, source_attribute, sp FROM live_market_sp_snapshots ORDER BY source_attribute"
    ).fetchall()
    assert len(stored) == 8
    assert connection.execute("SELECT COUNT(*) FROM live_sp_snapshots").fetchone()[0] == 0
    log = connection.execute("SELECT kind, rows_parsed FROM fetch_log").fetchone()
    assert dict(log) == {"kind": "live_market_sp_xml_40", "rows_parsed": 1}
    connection.close()


def test_refresh_loop_defaults_to_five_playids(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "refresh.sqlite"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    scraper.create_schema(connection)
    monkeypatch.setattr(
        refresh,
        "fetch_issue_list",
        lambda conn, args: [{"issue": "X", "is_current": 1}],
    )
    monkeypatch.setattr(
        refresh,
        "resolve_sp_refresh_issues",
        lambda *args, **kwargs: ["X", "OLD"],
    )
    monkeypatch.setattr(refresh, "scrape_issue", lambda conn, issue, args: 1)
    captured: list[tuple[str, int]] = []
    monkeypatch.setattr(
        refresh,
        "scrape_live_sp",
        lambda conn, issue, args: captured.append((issue, args.playid)) or 1,
    )
    args = argparse.Namespace(
        issue=["current"],
        recent_count=0,
        open_limit=0,
        open_year_lookback=1,
        playid=None,
        timeout=10,
        user_agent="test",
        force=True,
        live_sp=True,
        sleep=0,
    )

    assert refresh.run_once(connection, args) == 2
    assert captured == [
        ("X", 34),
        ("X", 40),
        ("X", 41),
        ("X", 42),
        ("X", 51),
        ("OLD", 34),
    ]
    connection.close()
