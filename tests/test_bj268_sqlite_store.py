"""SQLite-first persistence tests for #268."""
from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path

import pandas as pd

from src.eu_proxy_backfill.sqlite_store import build_recovery_sqlite


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _issue_part(root: Path, issue: str) -> None:
    part = root / "issue_parts" / issue
    part.mkdir(parents=True)
    receipts = pd.DataFrame([{
        "source_kind": "titan_1x2", "source_key": f"{issue}:001:99",
        "source_url": "https://example.test/99", "requested_at_utc": "2026-01-01T00:00:00Z",
        "received_at_utc": "2026-01-01T00:00:01Z", "parser_version": "test",
        "acquisition_result": "SUCCESS", "status_code": 200, "payload_bytes": 10,
        "payload_sha256": "a" * 64, "error_class": None, "error_detail": None,
        "attempt_count": 1,
    }])
    receipts.to_csv(part / "receipts.csv", index=False)
    pd.DataFrame([{
        "issue_code": issue, "match_idx": 1, "provider_match_id": "99",
        "snapshot_kind": "initial", "disposition": "RECOVERED_RAW_QUOTE", "detail": "rows=2",
    }]).to_parquet(part / "fixture_horizon_dispositions.parquet", index=False)
    pd.DataFrame([
        {
            "issue_code": issue, "match_idx": 1, "source_match_id": f"{issue}:001:99",
            "provider_match_id": "99", "snapshot_kind": "initial", "bookmaker_id": "A",
            "v1": 2.0, "v2": 3.0, "v3": 4.0, "native_handicap_line_raw": 0,
            "native_handicap_line": 0.0, "handicap_norm_source": "test",
            "payload_sha256": digest,
        }
        for digest in ("b" * 64, "a" * 64)
    ]).to_parquet(part / "raw_quotes.parquet", index=False)
    (part / "issue_disposition.json").write_text(
        json.dumps({"issue_code": issue, "issue_disposition": "RECOVERED"}), encoding="utf-8"
    )
    names = ["receipts.csv", "raw_quotes.parquet", "fixture_horizon_dispositions.parquet", "issue_disposition.json"]
    (part / "DONE.json").write_text(
        json.dumps({"issue_code": issue, "files": names, "sha256": {name: _sha256(part / name) for name in names}}),
        encoding="utf-8",
    )


def test_recovery_store_commits_issues_and_resolves_exact_duplicates(tmp_path: Path) -> None:
    _issue_part(tmp_path, "25043")
    (tmp_path / "GATE_START.json").write_text(
        json.dumps({"selected_issue_codes": ["25043"]}), encoding="utf-8"
    )
    target = tmp_path / "candidate.sqlite"
    summary = build_recovery_sqlite(tmp_path, target)

    assert summary["raw_quote_rows"] == 2
    assert summary["resolved_quote_rows"] == 1
    with sqlite3.connect(target) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT payload_sha256 FROM resolved_quotes").fetchone()[0] == "a" * 64
        assert connection.execute("SELECT reason FROM duplicate_resolution_ledger").fetchone()[0] == "EXACT_DUPLICATE_SOURCE_QUOTE"
