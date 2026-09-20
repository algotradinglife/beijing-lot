"""Release-local Titan roster coverage and source-ID reuse diagnostics."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .release import verify_titan_release


@dataclass(frozen=True)
class FixtureIdReuse:
    source_fixture_id: str
    fixture_capture_batch_ids: tuple[str, ...]


def fixture_id_reuse_in_release(root: Path, *, release_id: str) -> tuple[FixtureIdReuse, ...]:
    """Report source IDs with multiple sealed fixture captures; never merge them."""
    root = Path(root).expanduser().resolve()
    if problems := verify_titan_release(root, release_id=release_id):
        raise ValueError("release verification failed: " + "; ".join(problems))
    snapshot = root / "releases" / "titan" / release_id / "control.sqlite"
    with sqlite3.connect(snapshot) as connection:
        rows = connection.execute(
            """SELECT source_fixture_id, GROUP_CONCAT(batch_id, '|') FROM fixture_capture
               GROUP BY source_fixture_id HAVING COUNT(*) > 1 ORDER BY source_fixture_id"""
        ).fetchall()
    return tuple(FixtureIdReuse(source_id, tuple(batch_ids.split("|"))) for source_id, batch_ids in rows)
