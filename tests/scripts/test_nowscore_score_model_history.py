from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import nowscore_score_model_history as history  # noqa: E402
from src.multimarket_p0 import HKT  # noqa: E402
from scripts import manage_nowscore_score_model_history as manager  # noqa: E402


EURO_JS = b'''var game=Array("115|RID|William Hill|2.5|3.1|2.8");
var gameDetail=Array("RID^2.50|3.10|2.80|07-12 18:10|0.9|0.9|0.9|2026;2.40|3.20|2.90|07-12 17:40|0.9|0.9|0.9|2026;");'''


def test_excel_source_company_namespaces_are_distinct() -> None:
    assert history.WILLIAM_HILL == {
        "bookmaker_key": "william_hill",
        "euro_company_id": 115,
        "over_under_company_id": 9,
    }
    assert "companyid=9" in history.over_under_history_url(
        "M1", 9, datetime(2026, 7, 12, 18, 30, tzinfo=HKT)
    )


def test_parse_titan_euro_history_and_select_freeze() -> None:
    kickoff = datetime(2026, 7, 12, 18, 30, tzinfo=HKT)
    company, rows, counters = history.parse_euro_history_js(
        EURO_JS, kickoff_hkt=kickoff, company_id=115
    )
    assert company == "William Hill"
    assert counters == {"candidate_rows": 2, "timestamp_rejected_rows": 0, "incomplete_rows": 0}
    csv_rows = [
        {
            "snapshot_ts_hkt": row.snapshot_ts_hkt,
            "phase": row.phase,
            "complete": str(int(row.complete)),
            "fetched_at_utc": "2026-07-16T00:00:00+00:00",
            "snapshot_id": str(index),
        }
        for index, row in enumerate(rows)
    ]
    selected, reason = history.select_latest_complete(
        csv_rows, datetime(2026, 7, 12, 17, 55, tzinfo=HKT)
    )
    assert reason == "selected"
    assert selected is not None
    assert selected["snapshot_ts_hkt"] == "2026-07-12T17:40+08:00"


def test_parse_titan_over_under_excludes_live_and_incomplete() -> None:
    payload = json.dumps(
        [
            {
                "HappenTime": "", "Score": "早", "HomeOdds": "0.95", "PanKou": "2/2.5",
                "AwayOdds": "0.91", "IsClosed": "", "ModifyTime": "20260712174000",
            },
            {
                "HappenTime": "02", "Score": "0-0", "HomeOdds": "1.10", "PanKou": "2.5",
                "AwayOdds": "0.62", "IsClosed": "", "ModifyTime": "20260712183121",
            },
            {
                "HappenTime": "", "Score": "即", "HomeOdds": "0", "PanKou": "2.5",
                "AwayOdds": "0.70", "IsClosed": "", "ModifyTime": "20260712180000",
            },
        ]
    ).encode()
    rows, counters = history.parse_over_under_history_json(
        payload, kickoff_hkt=datetime(2026, 7, 12, 18, 30, tzinfo=HKT)
    )
    assert len(rows) == 3
    assert sum(row.complete for row in rows) == 1
    assert rows[0].line_value == 2.25
    assert counters["incomplete_rows"] == 2


def test_select_reports_missing_reason_and_rejects_future() -> None:
    rows = [
        {
            "snapshot_ts_hkt": "2026-07-12T18:10:00+08:00",
            "phase": "pregame",
            "complete": "1",
            "fetched_at_utc": "2026-07-16T00:00:00+00:00",
            "snapshot_id": "future",
        }
    ]
    selected, reason = history.select_latest_complete(
        rows, datetime(2026, 7, 12, 17, 55, tzinfo=HKT)
    )
    assert selected is None
    assert reason == "all_snapshots_after_freeze"


def test_waf_payload_is_not_accepted_as_history() -> None:
    with pytest.raises(history.ScoreModelHistoryError, match="WAF"):
        history.parse_over_under_history_json(
            "非法访问，您的行为已被WAF系统记录。".encode(),
            kickoff_hkt=datetime(2026, 7, 12, 18, 30, tzinfo=HKT),
        )


def test_only_explicit_provider_absence_is_a_market_exclusion() -> None:
    assert manager.is_market_unavailable_error(
        history.ScoreModelHistoryError("Titan Euro company missing: 115")
    )
    assert manager.is_market_unavailable_error(
        history.ScoreModelHistoryError("Titan O/U history is empty")
    )
    assert not manager.is_market_unavailable_error(
        history.ScoreModelHistoryError("Titan O/U WAF response")
    )


def test_capture_verify_rejects_semantically_wrong_raw_digest(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    final = tmp_path / "published"
    (stage / "raw").mkdir(parents=True)
    (stage / "raw/source.js").write_bytes(b"payload")
    page = {field: "" for field in manager.PAGE_FIELDS}
    page.update(
        {
            "status": "ok",
            "raw_file": "raw/source.js",
            "raw_payload_sha256": "0" * 64,
        }
    )
    manager.write_csv(stage / "page_inventory.csv", [page], manager.PAGE_FIELDS)
    manager.write_csv(stage / "snapshots.csv", [], manager.SNAPSHOT_FIELDS)
    (stage / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": history.CAPTURE_SCHEMA,
                "policy": manager.POLICY,
            }
        ),
        encoding="utf-8",
    )
    manager.publish_bundle(stage, final)
    with pytest.raises(history.ScoreModelHistoryError, match="raw payload link mismatch"):
        manager.verify_score_model_bundle(final, expected_schema=history.CAPTURE_SCHEMA)
