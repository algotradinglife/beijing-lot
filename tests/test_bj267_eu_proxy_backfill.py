from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scripts.profile_bj267_eu_proxy_backfill import (
    create_sqlite_snapshot,
    overlaps_protected,
)
from src.eu_proxy_backfill.inventory import (
    InventoryPaths,
    build_inventory,
    inventory_sha256,
    inventory_summary,
)
from src.eu_proxy_backfill.probe import FetchReceipt, StagedProbeClient, probe_issue


def _proxy_db(path: Path, rows: list[tuple[str, int, str]]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE matches(
            issue TEXT,
            match_idx INTEGER,
            provider_match_id TEXT,
            kickoff_ts TEXT,
            league TEXT,
            home TEXT,
            away TEXT,
            handicap_line_norm REAL
        );
        """
    )
    connection.executemany(
        "INSERT INTO matches VALUES (?, ?, ?, '2026-01-01 12:00:00', 'L', 'H', 'A', 0)",
        rows,
    )
    connection.commit()
    connection.close()


def _history_db(path: Path, rows: list[tuple[str, int]]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE historical_matches(
            issue TEXT,
            match_idx INTEGER,
            kickoff_ts TEXT,
            league TEXT,
            home TEXT,
            away TEXT,
            handicap_line REAL
        );
        """
    )
    connection.executemany(
        "INSERT INTO historical_matches VALUES (?, ?, '2026-01-01 12:00:00', 'L', 'H', 'A', 0)",
        rows,
    )
    connection.commit()
    connection.close()


def _live_db(path: Path, rows: list[tuple[str, int]]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE matches(
            issue TEXT,
            match_idx INTEGER,
            kickoff_ts TEXT,
            league TEXT,
            home TEXT,
            away TEXT,
            handicap_line REAL
        );
        """
    )
    connection.executemany(
        "INSERT INTO matches VALUES (?, ?, '2026-01-01 12:00:00', 'L', 'H', 'A', 0)",
        rows,
    )
    connection.commit()
    connection.close()


def test_inventory_freezes_complete_denominator_without_outcomes(tmp_path: Path) -> None:
    base = tmp_path / "base.sqlite"
    extension = tmp_path / "extension.sqlite"
    history = tmp_path / "history.db"
    live = tmp_path / "live.db"
    _proxy_db(base, [("25042", 1, "p1")])
    _proxy_db(extension, [("26051", 1, "p2")])
    _history_db(history, [("25042", 1), ("25043", 1)])
    _live_db(live, [("26051", 1), ("26052", 1)])

    frame = build_inventory(InventoryPaths(base, extension, history, live))
    assert frame[["issue_code", "match_idx", "proxy_status"]].to_dict("records") == [
        {"issue_code": "25042", "match_idx": 1, "proxy_status": "ACCEPTED_236"},
        {
            "issue_code": "25043",
            "match_idx": 1,
            "proxy_status": "UNRESOLVED_SOURCE_RECOVERY",
        },
        {"issue_code": "26051", "match_idx": 1, "proxy_status": "AVAILABLE_EXTENSION"},
        {
            "issue_code": "26052",
            "match_idx": 1,
            "proxy_status": "UNRESOLVED_SOURCE_RECOVERY",
        },
    ]
    summary = inventory_summary(frame)
    assert summary["known_issue_count"] == 4
    assert summary["known_fixture_count"] == 4
    assert summary["accepted_236_issue_count"] == 1
    assert summary["extension_issue_count"] == 1
    assert summary["unresolved_issue_count"] == 2
    assert inventory_sha256(frame) == inventory_sha256(frame.copy())
    assert not {"result_code", "winning_sp", "score"} & set(frame.columns)


def test_inventory_rejects_duplicate_slots_inside_one_source(tmp_path: Path) -> None:
    base = tmp_path / "base.sqlite"
    extension = tmp_path / "extension.sqlite"
    history = tmp_path / "history.db"
    live = tmp_path / "live.db"
    _proxy_db(base, [("25042", 1, "p1"), ("25042", 1, "p2")])
    _proxy_db(extension, [])
    _history_db(history, [])
    _live_db(live, [])
    try:
        build_inventory(InventoryPaths(base, extension, history, live))
    except ValueError as exc:
        assert "duplicate issue slots" in str(exc)
    else:
        raise AssertionError("duplicate source slots must fail closed")


def test_live_sqlite_snapshot_is_consistent_and_independent(tmp_path: Path) -> None:
    source = tmp_path / "live.db"
    snapshot = tmp_path / "staging/live.snapshot.sqlite"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE values_table(value INTEGER)")
    connection.execute("INSERT INTO values_table VALUES (1)")
    connection.commit()
    connection.close()

    create_sqlite_snapshot(source, snapshot)
    connection = sqlite3.connect(source)
    connection.execute("INSERT INTO values_table VALUES (2)")
    connection.commit()
    connection.close()

    with sqlite3.connect(snapshot) as frozen:
        assert frozen.execute("SELECT value FROM values_table").fetchall() == [(1,)]


def test_output_and_staging_overlap_guard_covers_both_directions(tmp_path: Path) -> None:
    protected_file = (tmp_path / "data/source.sqlite").resolve()
    protected = {protected_file}
    assert overlaps_protected(tmp_path / "data", protected)
    assert overlaps_protected(tmp_path / "data/source.sqlite/child", protected)
    assert not overlaps_protected(tmp_path / "staging", protected)


ISSUE_HTML = """
<table><tr id="row1" matchid="1" gamename="Test League" polygoal="0">
<td>1</td><td>Test League</td><td></td><td></td>
<td><span id="HomeTeam_1">Home</span></td><td>0</td><td>-</td>
<td><span id="GuestTeam_1">Away</span></td><td>-</td>
<td><a href="Panlu.aspx?id=12345">odds</a></td></tr></table>
<script>
var M = new Array();
M[1] = new Array(); M[1][0] = 12345;
M[1][3] = new Date(2025,3,16,09,00,00); M[1][4] = 0;
M[1][16] = 1; M[1][17] = "Home"; M[1][20] = "Away";
M[2] = new Array(); M[2][0] = 67890;
M[2][3] = new Date(2025,3,16,10,00,00); M[2][4] = -99;
M[2][16] = 2; M[2][17] = "Hidden Home"; M[2][20] = "Hidden Away";
</script>
"""

TITAN_JS = """
MatchTime="2025,4,16,1,0,0";
var hOrder="1"; var gOrder="2"; hometeamID=10; guestteamID=20; sclassId=30;
var game=Array("115|r1|William Hill");
var gameDetail=Array("r1^2.0|3.0|4.0|04-16 00:30|0.9|0.9|0.9|2025;2.1|3.1|4.1|04-15 14:00|0.9|0.9|0.9|2025;2.2|3.2|4.2|04-14 12:00|0.9|0.9|0.9|2025");
"""


@dataclass
class _FakeClient:
    issue_payload: bytes = ISSUE_HTML.encode()
    titan_payload: bytes = TITAN_JS.encode()

    def fetch(self, source_kind: str, source_key: str, url: str):
        payload = self.issue_payload if source_kind == "issue_page" else self.titan_payload
        return payload, FetchReceipt(
            source_kind=source_kind,
            source_key=source_key,
            source_url=url,
            requested_at_utc="2026-08-19T00:00:00+00:00",
            received_at_utc="2026-08-19T00:00:01+00:00",
            status_code=200,
            payload_bytes=len(payload),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
        )


def test_probe_writes_only_new_staging_and_matches_slots(tmp_path: Path) -> None:
    expected = pd.DataFrame(
        [
            {
                "issue_code": "25043",
                "match_idx": 1,
                "proxy_status": "UNRESOLVED_SOURCE_RECOVERY",
            },
            {
                "issue_code": "25043",
                "match_idx": 3,
                "proxy_status": "UNRESOLVED_SOURCE_RECOVERY",
            }
        ]
    )
    staging = tmp_path / "new-staging"
    result, receipts, source_rows, titan_rows = probe_issue(
        _FakeClient(), "25043", expected, staging, titan_samples=1
    )
    assert result.status == "AUTHORITATIVE_ISSUE_MEMBERSHIP_AVAILABLE"
    assert result.local_only_slot_count == 1
    assert result.source_only_slot_count == 1
    assert result.source_fixture_count == 2
    assert result.sampled_titan_success_count == 1
    assert result.sampled_complete_triplets > 0
    assert len(receipts) == 2
    assert [row["provider_match_id"] for row in source_rows] == ["12345", "67890"]
    assert source_rows[1]["kickoff_ts"] is None
    assert source_rows[1]["issue_deadline_ts"] == "2025-04-16 10:00:00"
    assert source_rows[1]["native_handicap_line"] is None
    assert titan_rows[0]["status"] == "AVAILABLE"
    raw_files = sorted(path for path in staging.rglob("*") if path.is_file())
    assert len(raw_files) == 2
    assert all(path.is_relative_to(staging) for path in raw_files)

    pd.DataFrame(receipts).to_csv(staging / "FETCH_RECEIPTS.csv", index=False)
    replay_result, replay_receipts, replay_source, replay_titan = probe_issue(
        StagedProbeClient(staging), "25043", expected, staging, titan_samples=1
    )
    assert replay_result == result
    assert replay_receipts == receipts
    assert replay_source == source_rows
    assert replay_titan == titan_rows


def test_staged_probe_rejects_tampered_payload(tmp_path: Path) -> None:
    expected = pd.DataFrame(
        [{"issue_code": "25043", "match_idx": 1, "proxy_status": "UNRESOLVED"}]
    )
    staging = tmp_path / "staging"
    _, receipts, _, _ = probe_issue(
        _FakeClient(), "25043", expected, staging, titan_samples=1
    )
    pd.DataFrame(receipts).to_csv(staging / "FETCH_RECEIPTS.csv", index=False)
    issue_payload = next((staging / "raw" / "issue_page").glob("*.html"))
    issue_payload.write_bytes(b"tampered")
    try:
        probe_issue(
            StagedProbeClient(staging),
            "25043",
            expected,
            staging,
            titan_samples=1,
        )
    except ValueError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("tampered staged payload must fail closed")
