from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from scripts import refresh_adhoc_inputs as refresh_script
from scripts import scrape_500_bjdc
from src.adhoc_input_freshness import (
    AdhocInputFreshnessError,
    CAPTURE_CLASSIFICATION,
    build_same_cycle_batch,
    canonical_json,
    parse_utc,
    sha256_bytes,
    verify_same_cycle_evidence,
)


def _sources(*, parlay_modes: tuple[str, ...] = ("自由过关",)):
    issue_rows = [
        {
            "issue": "26078",
            "match_idx": 1,
            "end_time": "2026-07-27T13:30:00+08:00",
            "disabled": "no",
            "sp_home": 3.0,
            "sp_draw": 3.0,
            "sp_away": 3.0,
        }
    ]
    nowscore_rows = [
        {
            "issue": "26078",
            "match_idx": 1,
            "can_sale": 1,
        }
    ]
    market_rows = [
        {
            "issue": "26078",
            "playid": 34,
            "market_key": "handicap_3way",
            "row_idx": 1,
            "outcome_code": code,
            "outcome_label": label,
            "sp": 3.0,
            "source_attribute": attribute,
            "source_updatetime": "2026-07-27 12:00:00",
            "home": "主队",
            "away": "客队",
            "league": "测试联赛",
            "raw_node": "<w1/>",
            "source_url": "https://example.test/live.xml",
        }
        for code, label, attribute in (
            ("3", "胜", "c1"),
            ("1", "平", "c3"),
            ("0", "负", "c5"),
        )
    ]
    return build_same_cycle_batch(
        issue="26078",
        issue_rows=issue_rows,
        nowscore_rows=nowscore_rows,
        market_rows=market_rows,
        source_clocks_utc={
            "issue_html": "2026-07-27T04:00:00+00:00",
            "nowscore_html": "2026-07-27T04:00:01+00:00",
            "live_sp_xml": "2026-07-27T04:00:02+00:00",
        },
        source_sha256={
            "issue_html": "a" * 64,
            "nowscore_html": "b" * 64,
            "live_sp_xml": "c" * 64,
        },
        parlay_modes=parlay_modes,
    )


def test_same_cycle_batch_binds_sp_sale_and_parlay_evidence() -> None:
    batch = _sources()

    assert batch["receipt"]["status"] == "PASS"
    assert batch["receipt"]["eligible_match_count"] == 1
    assert len(batch["rows"]) == 3
    assert {row["sale_status"] for row in batch["rows"]} == {"open"}
    assert {row["parlay_allowed"] for row in batch["rows"]} == {"allowed"}
    assert {row["capture_classification"] for row in batch["rows"]} == {
        CAPTURE_CLASSIFICATION
    }
    evidence = verify_same_cycle_evidence(
        batch_id=batch["batch_id"],
        capture_classification=batch["rows"][0]["capture_classification"],
        evidence_json=batch["rows"][0]["eligibility_evidence_json"],
        expected_issue="26078",
    )
    assert evidence["source_sha256"]["live_sp_xml"] == "c" * 64


def test_missing_official_parlay_evidence_fails_with_specific_reason() -> None:
    batch = _sources(parlay_modes=())

    assert batch["receipt"]["status"] == "FAILED_CLOSED"
    assert batch["receipt"]["eligible_match_count"] == 0
    assert batch["receipt"]["rejection_counts"] == {"PARLAY_EVIDENCE_MISSING": 1}
    assert {row["eligibility_reasons_json"] for row in batch["rows"]} == {
        '["PARLAY_EVIDENCE_MISSING"]'
    }


def test_collection_clocks_must_be_explicit_utc() -> None:
    with pytest.raises(
        AdhocInputFreshnessError,
        match="must include a timezone offset",
    ):
        parse_utc("2026-07-27 04:00:00")

    collected = datetime.fromisoformat(scrape_500_bjdc.now_utc())
    assert collected.tzinfo is not None
    assert collected.utcoffset() == timezone.utc.utcoffset(collected)


def test_one_shot_cli_function_publishes_one_atomic_batch(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issue_rows = [
        {
            "issue": "26078",
            "match_idx": 1,
            "end_time": "2026-07-27T13:30:00+08:00",
            "disabled": "no",
            "sp_home": 3.0,
            "sp_draw": 3.1,
            "sp_away": 3.2,
            "fetched_at": "",
        }
    ]
    nowscore_rows = [
        {
            "issue": "26078",
            "match_idx": 1,
            "provider_match_id": "123",
            "fetched_at": "",
            "schedule_date": "2026-07-26",
            "league": "测试联赛",
            "kickoff_time": "14:00",
            "status_text": "未开赛",
            "status": "scheduled",
            "can_sale": 1,
            "home": "主队",
            "away": "客队",
            "handicap_text": "0",
            "handicap_line": 0.0,
            "score": "",
            "halftime_score": "",
            "result_code": None,
            "panlu_url": "",
            "asian_url": "",
            "europe_url": "",
            "analysis_url": "",
            "recommendation_url": "",
            "sp_url": "",
            "raw_row_hash": "a" * 40,
            "raw_row": "<tr/>",
        }
    ]
    market_rows = [
        {
            "issue": "26078",
            "playid": 34,
            "market_key": "handicap_3way",
            "row_idx": 1,
            "outcome_code": code,
            "outcome_label": label,
            "sp": sp,
            "source_attribute": attribute,
            "source_updatetime": "2026-07-27 12:00:00",
            "home": "主队",
            "away": "客队",
            "league": "测试联赛",
            "raw_node": "<w1/>",
        }
        for code, label, attribute, sp in (
            ("3", "胜", "c1", 3.0),
            ("1", "平", "c3", 3.1),
            ("0", "负", "c5", 3.2),
        )
    ]

    def parse_issue(_issue, _text, *, fetched_at):
        rows = [dict(row) for row in issue_rows]
        rows[0]["fetched_at"] = fetched_at
        return rows

    def parse_nowscore(_issue, _text, fetched_at):
        rows = [dict(row) for row in nowscore_rows]
        rows[0]["fetched_at"] = fetched_at
        return rows

    monkeypatch.setattr(refresh_script.source_500, "parse_issue_rows", parse_issue)
    monkeypatch.setattr(refresh_script.source_nowscore, "parse_rows", parse_nowscore)
    monkeypatch.setattr(
        refresh_script.source_500,
        "parse_live_market_sp",
        lambda *_args: ("2026-07-27 12:00:00", [dict(row) for row in market_rows]),
    )
    fetch_count = 0

    def fetch_500(url, **_kwargs):
        nonlocal fetch_count
        fetch_count += 1
        body = (
            "自由过关".encode("gb18030")
            if "index.php" in url
            else b"<root/>"
        )
        return scrape_500_bjdc.FetchResult(
            url=url,
            status=200,
            body=body,
            elapsed_sec=0.01,
        )

    clocks = iter(
        (
            "2026-07-27T04:00:00+00:00",
            "2026-07-27T04:00:01+00:00",
            "2026-07-27T04:00:02+00:00",
        )
    )
    database = tmp_path / "freshness.sqlite"
    result = refresh_script.refresh_adhoc_inputs(
        issue="26078",
        db_path=database,
        receipt_root=tmp_path / "receipts",
        clock=lambda: next(clocks),
        fetch_500=fetch_500,
        fetch_nowscore=lambda *_args: (200, b"<table/>", 0.01),
    )

    assert fetch_count == 2
    assert result["status"] == "PASS"
    assert result["eligible_match_count"] == 1
    receipt = json.loads(
        (tmp_path / "receipts" / "26078" / f"{result['batch_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    internal_hash = receipt.pop("sha256")
    assert internal_hash == sha256_bytes(canonical_json(receipt))
    assert "database" not in receipt
    with sqlite3.connect(database) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT batch_id, capture_classification,
                            fetched_at_utc, sale_status, parlay_allowed
            FROM live_market_sp_snapshots
            """
        ).fetchall()
    assert rows == [
        (
            result["batch_id"],
            CAPTURE_CLASSIFICATION,
            "2026-07-27T04:00:02+00:00",
            "open",
            "allowed",
        )
    ]
