"""Cutoff-bound Titan raw-slice materialization from a pinned release."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.temporal_learning.core import Cutoff, stable_json_hash

from .release import verify_titan_release


class TitanAsOfError(ValueError):
    """Raised when a Titan release cannot prove strict as-of admissibility."""


@dataclass(frozen=True)
class TitanAsOfSlice:
    cutoff: Cutoff
    release_id: str
    release_manifest_sha256: str
    fixture_rows: tuple[dict[str, str | None], ...]
    source_slice_sha256: str
    maximum_trusted_received_at_utc: str | None

    def receipt(self) -> dict[str, object]:
        return {
            "cutoff_identity": self.cutoff.identity,
            "cutoff_kind": self.cutoff.kind,
            "cutoff_ts": self.cutoff.cutoff_ts.isoformat(),
            "target_issue": self.cutoff.target_issue,
            "release_id": self.release_id,
            "release_manifest_sha256": self.release_manifest_sha256,
            "source_slice_sha256": self.source_slice_sha256,
            "fixture_count": len(self.fixture_rows),
            "maximum_trusted_received_at_utc": self.maximum_trusted_received_at_utc,
            "availability_policy": "OBSERVED_AVAILABILITY",
            "availability_predicate": "trusted_received_at_utc < cutoff_ts",
        }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def materialize_titan_asof(root: Path, *, release_id: str, cutoff: Cutoff) -> TitanAsOfSlice:
    """Materialize only receipt-observed Titan fixtures strictly before ``cutoff``.

    The function intentionally reads the sealed release snapshot, never the live
    control database, so later captures cannot alter an earlier cutoff slice.
    """
    root = Path(root).expanduser().resolve()
    problems = verify_titan_release(root, release_id=release_id)
    if problems:
        raise TitanAsOfError("release verification failed: " + "; ".join(problems))
    release_dir = root / "releases" / "titan" / release_id
    manifest_path = release_dir / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes())
    release_hash = _hash_file(manifest_path)
    cutoff_ts = cutoff.cutoff_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    query = """
        SELECT c.batch_id,c.roster_batch_id,c.source_fixture_id,c.raw_sha256,
               c.trusted_received_at_utc,o.kickoff_source_raw,o.home_team_source_id,
               o.away_team_source_id,o.competition_source_id
        FROM fixture_capture c
        JOIN fixture_observation o ON o.batch_id=c.batch_id
        WHERE c.source_id='titan' AND c.source_role='PRIMARY_FEATURE'
          AND c.trusted_received_at_utc < ?
        ORDER BY c.trusted_received_at_utc,c.batch_id
    """
    with sqlite3.connect(release_dir / "control.sqlite") as connection:
        columns = [item[0] for item in connection.execute(query, (cutoff_ts,)).description]
        rows = tuple(dict(zip(columns, row)) for row in connection.execute(query, (cutoff_ts,)))
    raw_hashes = {item["raw_sha256"] for item in rows}
    declared = {
        item["raw_sha256"]
        for item in manifest["titan_store_manifest"].get("fixture_captures", [])
    }
    if not raw_hashes.issubset(declared):
        raise TitanAsOfError("as-of fixture row is absent from the release raw manifest")
    maximum = max((str(item["trusted_received_at_utc"]) for item in rows), default=None)
    return TitanAsOfSlice(
        cutoff=cutoff,
        release_id=release_id,
        release_manifest_sha256=release_hash,
        fixture_rows=rows,
        source_slice_sha256=stable_json_hash(list(rows)),
        maximum_trusted_received_at_utc=maximum,
    )
