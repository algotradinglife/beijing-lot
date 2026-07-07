from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.decision_artifact_completeness import active_snapshot_completeness, structured_csv_completeness


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["issue", "match_idx"])
        writer.writeheader()
        writer.writerows(rows)


def test_active_snapshot_completeness_reports_missing_match_indices() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            """
            CREATE TABLE matches(issue TEXT, match_idx INTEGER, end_time TEXT);
            CREATE TABLE llm_decision_snapshots(issue TEXT, match_idx INTEGER, status TEXT);
            INSERT INTO matches VALUES('26072', 65, '2026-07-07 01:00:00');
            INSERT INTO matches VALUES('26072', 66, '2026-07-07 02:00:00');
            INSERT INTO matches VALUES('26072', 67, '2026-07-07 03:00:00');
            INSERT INTO llm_decision_snapshots VALUES('26072', 65, 'active');
            INSERT INTO llm_decision_snapshots VALUES('26072', 66, 'draft_replacement');
            """
        )

        status = active_snapshot_completeness(conn, "26072")

        assert status.complete is False
        assert status.expected_count == 3
        assert status.actual_count == 1
        assert status.missing_match_idx == [66, 67]
    finally:
        conn.close()


def test_structured_csv_completeness_compares_csv_rows_to_matches(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            """
            CREATE TABLE matches(issue TEXT, match_idx INTEGER);
            INSERT INTO matches VALUES('26072', 1);
            INSERT INTO matches VALUES('26072', 2);
            """
        )
        csv_path = tmp_path / "structured_shadow_26072.csv"
        _write_csv(csv_path, [{"issue": "26072", "match_idx": "1"}])

        status = structured_csv_completeness(conn, "26072", csv_path)

        assert status.complete is False
        assert status.expected_match_idx == [1, 2]
        assert status.actual_match_idx == [1]
        assert status.missing_match_idx == [2]
    finally:
        conn.close()
