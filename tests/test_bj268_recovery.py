"""End-to-end synthetic Gate-1 recovery tests for Issue #268."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.eu_proxy_backfill.runner import recover_issue


ISSUE = b"""
<input id="issueNum" value="25043" />
<script>
var M = new Array();
M[1] = new Array(); M[1][0] = 12345;
M[1][3] = new Date(2025,3,16,09,00,00); M[1][4] = 0;
M[1][16] = 1; M[1][17] = "Home"; M[1][20] = "Away";
</script>
"""
TITAN = b"""
MatchTime="2025,4,16,1,0,0";
var game=Array("115|r1|William Hill");
var gameDetail=Array("r1^2.0|3.0|4.0|04-16 00:30|0.9|0.9|0.9|2025;2.1|3.1|4.1|04-15 14:00|0.9|0.9|0.9|2025;2.2|3.2|4.2|04-14 12:00|0.9|0.9|0.9|2025");
"""


@dataclass
class _Client:
    payloads: dict[str, bytes]

    def get(self, url: str, timeout: float) -> bytes:
        return self.payloads[url]


def test_recovery_produces_every_horizon_disposition_and_hash_bound_raw_rows(tmp_path: Path) -> None:
    issue_url = "https://issue.test/25043"
    titan_url = "https://titan.test/12345"
    expected = pd.DataFrame([{"issue_code": "25043", "match_idx": 1}])
    result = recover_issue(
        _Client({issue_url: ISSUE, titan_url: TITAN}),
        issue_code="25043",
        expected=expected,
        staging_root=tmp_path,
        issue_url=issue_url,
        titan_url_template="https://titan.test/{provider_match_id}",
        timeout=1.0,
        attempts=1,
    )

    assert result.issue_disposition == "RECOVERED"
    assert len(result.receipts) == 2
    assert {row["snapshot_kind"] for row in result.quote_rows} == {"initial", "10h", "1h"}
    assert "威廉" in {row["bookmaker_id"] for row in result.quote_rows}
    assert any(
        row["bookmaker_id"] == "威廉" and row["v1"] == 2.0
        for row in result.quote_rows
    )
    assert all(row["payload_sha256"] == result.receipts[1]["payload_sha256"] for row in result.quote_rows)
    assert result.fixture_horizon_dispositions[["snapshot_kind", "disposition"]].to_dict("records") == [
        {"snapshot_kind": "initial", "disposition": "RECOVERED_RAW_QUOTE"},
        {"snapshot_kind": "10h", "disposition": "RECOVERED_RAW_QUOTE"},
        {"snapshot_kind": "1h", "disposition": "RECOVERED_RAW_QUOTE"},
    ]


def test_issue_page_failure_is_an_explicit_denominator_disposition(tmp_path: Path) -> None:
    expected = pd.DataFrame([{"issue_code": "25043", "match_idx": 1}])
    result = recover_issue(
        _Client({}),
        issue_code="25043",
        expected=expected,
        staging_root=tmp_path,
        issue_url="https://issue.test/25043",
        titan_url_template="https://titan.test/{provider_match_id}",
        timeout=1.0,
        attempts=1,
    )

    assert result.issue_disposition == "UNAVAILABLE_ISSUE_PAGE_REQUEST_ERROR"
    assert len(result.receipts) == 1
    assert result.fixture_horizon_dispositions[["snapshot_kind", "disposition"]].to_dict("records") == [
        {"snapshot_kind": "initial", "disposition": "UNAVAILABLE_ISSUE_PAGE_REQUEST_ERROR"},
        {"snapshot_kind": "10h", "disposition": "UNAVAILABLE_ISSUE_PAGE_REQUEST_ERROR"},
        {"snapshot_kind": "1h", "disposition": "UNAVAILABLE_ISSUE_PAGE_REQUEST_ERROR"},
    ]
