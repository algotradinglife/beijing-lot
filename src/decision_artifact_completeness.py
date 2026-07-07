from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CompletenessStatus:
    issue: str
    scope: str
    expected_count: int
    actual_count: int
    expected_match_idx: list[int]
    actual_match_idx: list[int]
    missing_match_idx: list[int]
    extra_match_idx: list[int]

    @property
    def complete(self) -> bool:
        return not self.missing_match_idx and not self.extra_match_idx and self.expected_count == self.actual_count

    def to_dict(self) -> dict[str, object]:
        return {
            "issue": self.issue,
            "scope": self.scope,
            "complete": self.complete,
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "expected_match_idx": self.expected_match_idx,
            "actual_match_idx": self.actual_match_idx,
            "missing_match_idx": self.missing_match_idx,
            "extra_match_idx": self.extra_match_idx,
        }


def sorted_unique(indices: Iterable[int | str | None]) -> list[int]:
    out: set[int] = set()
    for value in indices:
        if value in {None, ""}:
            continue
        try:
            out.add(int(value))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def issue_match_indices(conn: sqlite3.Connection, issue: str, *, only_date: str | None = None) -> list[int]:
    if not table_exists(conn, "matches"):
        return []
    where = ["issue=?"]
    args: list[object] = [issue]
    if only_date:
        where.append("substr(end_time, 1, 10)=?")
        args.append(only_date)
    rows = conn.execute(
        f"SELECT match_idx FROM matches WHERE {' AND '.join(where)} ORDER BY match_idx",
        args,
    ).fetchall()
    return sorted_unique(row[0] for row in rows)


def active_snapshot_indices(conn: sqlite3.Connection, issue: str) -> list[int]:
    if not table_exists(conn, "llm_decision_snapshots"):
        return []
    rows = conn.execute(
        """
        SELECT match_idx
        FROM llm_decision_snapshots
        WHERE issue=? AND status='active'
        GROUP BY match_idx
        ORDER BY match_idx
        """,
        (issue,),
    ).fetchall()
    return sorted_unique(row[0] for row in rows)


def csv_match_indices(path: Path) -> list[int]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return sorted_unique(row.get("match_idx") for row in csv.DictReader(f))


def completeness_for_indices(
    *,
    issue: str,
    scope: str,
    expected_indices: Iterable[int | str | None],
    actual_indices: Iterable[int | str | None],
    ignore_extra: bool = False,
) -> CompletenessStatus:
    expected = sorted_unique(expected_indices)
    actual = sorted_unique(actual_indices)
    expected_set = set(expected)
    actual_set = set(actual)
    extra = [] if ignore_extra else sorted(actual_set - expected_set)
    return CompletenessStatus(
        issue=issue,
        scope=scope,
        expected_count=len(expected),
        actual_count=len(actual),
        expected_match_idx=expected,
        actual_match_idx=actual,
        missing_match_idx=sorted(expected_set - actual_set),
        extra_match_idx=extra,
    )


def active_snapshot_completeness(
    conn: sqlite3.Connection,
    issue: str,
    *,
    only_date: str | None = None,
) -> CompletenessStatus:
    expected = issue_match_indices(conn, issue, only_date=only_date)
    actual = active_snapshot_indices(conn, issue)
    if only_date:
        expected_set = set(expected)
        actual = [idx for idx in actual if idx in expected_set]
    return completeness_for_indices(
        issue=issue,
        scope="active_decision_snapshots",
        expected_indices=expected,
        actual_indices=actual,
        ignore_extra=bool(only_date),
    )


def structured_csv_completeness(
    conn: sqlite3.Connection,
    issue: str,
    csv_path: Path,
) -> CompletenessStatus:
    return completeness_for_indices(
        issue=issue,
        scope="structured_shadow_csv",
        expected_indices=issue_match_indices(conn, issue),
        actual_indices=csv_match_indices(csv_path),
    )


def format_completeness_error(status: CompletenessStatus) -> str:
    parts = [
        f"{status.scope} incomplete for issue {status.issue}",
        f"expected={status.expected_count}",
        f"actual={status.actual_count}",
    ]
    if status.missing_match_idx:
        parts.append("missing=" + ",".join(str(idx) for idx in status.missing_match_idx))
    if status.extra_match_idx:
        parts.append("extra=" + ",".join(str(idx) for idx in status.extra_match_idx))
    return "; ".join(parts)
