"""Gate-1 contract tests for the complete #268 proxy backfill."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest
import requests

from src.eu_proxy_backfill.backfill import (
    AcquisitionResult,
    acquire_terminal,
    parse_declared_issue_payload,
    write_content_addressed_payload,
)


ISSUE_PAGE = """
<html><body>
<input id="issueNum" value="25043" />
<script>
var M = new Array();
M[1] = new Array(); M[1][0] = 12345;
M[1][3] = new Date(2025,3,16,09,00,00); M[1][16] = 1;
M[1][17] = "Home"; M[1][20] = "Away";
</script>
</body></html>
""".encode()


@dataclass
class _SequenceClient:
    values: list[bytes | Exception]

    def get(self, url: str, timeout: float) -> bytes:
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def test_failed_request_has_complete_terminal_receipt_and_no_payload(tmp_path: Path) -> None:
    result = acquire_terminal(
        _SequenceClient([requests.ConnectionError("offline")]),
        source_kind="issue_page",
        source_key="25043",
        source_url="https://example.test/25043",
        timeout=1.0,
        attempts=1,
    )

    assert isinstance(result, AcquisitionResult)
    assert result.payload is None
    assert result.receipt.acquisition_result == "REQUEST_ERROR"
    assert result.receipt.payload_bytes is None
    assert result.receipt.payload_sha256 is None
    assert result.receipt.error_class == "ConnectionError"
    assert result.receipt.source_key == "25043"
    assert result.receipt.source_url == "https://example.test/25043"
    assert result.receipt.attempt_count == 1


def test_payload_identity_rejects_wrong_or_missing_declared_issue_before_assignment() -> None:
    parsed = parse_declared_issue_payload(ISSUE_PAGE, requested_issue="25043")
    assert parsed.declared_issue_code == "25043"
    assert parsed.rows[0]["provider_match_id"] == "12345"

    with pytest.raises(ValueError, match="payload-declared issue"):
        parse_declared_issue_payload(ISSUE_PAGE.replace(b"25043", b"99999"), requested_issue="25043")
    with pytest.raises(ValueError, match="missing payload-declared issue"):
        parse_declared_issue_payload(b"<html><body>no declaration</body></html>", requested_issue="25043")


def test_content_addressed_payload_refuses_conflicting_bytes_for_same_logical_identity(tmp_path: Path) -> None:
    receipt = acquire_terminal(
        _SequenceClient([ISSUE_PAGE]),
        source_kind="issue_page",
        source_key="25043",
        source_url="https://example.test/25043",
        timeout=1.0,
        attempts=1,
    ).receipt
    target = write_content_addressed_payload(tmp_path, receipt, ISSUE_PAGE)
    assert target.is_file()
    assert write_content_addressed_payload(tmp_path, receipt, ISSUE_PAGE) == target
    with pytest.raises(ValueError, match="hash mismatch"):
        write_content_addressed_payload(tmp_path, receipt, b"not the bound payload")


def test_content_addressed_payload_rejects_path_traversal_in_untrusted_receipt_key(tmp_path: Path) -> None:
    receipt = acquire_terminal(
        _SequenceClient([ISSUE_PAGE]),
        source_kind="issue_page",
        source_key="../../escape",
        source_url="https://example.test/25043",
        timeout=1.0,
        attempts=1,
    ).receipt
    with pytest.raises(ValueError, match="unsafe receipt path component"):
        write_content_addressed_payload(tmp_path, receipt, ISSUE_PAGE)


def test_duplicate_bookmaker_rows_are_ledgered_deterministically_not_last_write_wins() -> None:
    from src.eu_proxy_backfill.backfill import resolve_duplicate_quotes

    quotes = pd.DataFrame(
        [
            {"issue_code": "25043", "match_idx": 1, "snapshot_kind": "initial", "bookmaker_id": "William Hill", "v1": 2.0, "v2": 3.0, "v3": 4.0, "payload_sha256": "a" * 64},
            {"issue_code": "25043", "match_idx": 1, "snapshot_kind": "initial", "bookmaker_id": "William Hill", "v1": 2.1, "v2": 3.1, "v3": 4.1, "payload_sha256": "b" * 64},
        ]
    )
    selected, ledger = resolve_duplicate_quotes(quotes)
    assert selected.empty
    assert ledger.to_dict("records") == [
        {
            "issue_code": "25043",
            "match_idx": 1,
            "snapshot_kind": "initial",
            "bookmaker_id": "William Hill",
            "reason": "CONFLICTING_DUPLICATE_SOURCE_QUOTE",
            "payload_sha256": "a" * 64 + "," + "b" * 64,
        }
    ]
