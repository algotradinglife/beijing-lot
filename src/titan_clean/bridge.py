"""One-way, minimal Titan identity export for the isolated settlement lane."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .release import verify_titan_release


class TitanBridgeError(ValueError):
    """Raised when a settlement bridge cannot be proven from a Titan release."""


@dataclass(frozen=True)
class FrozenSlot:
    fixture_capture_batch_id: str
    canonical_fixture_id: str
    canonical_issue_slot_id: str


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def export_settlement_bridge(
    root: Path,
    *,
    release_id: str,
    canonical_issue_id: str,
    slots: tuple[FrozenSlot, ...],
) -> bytes:
    """Export only frozen canonical triples; no Titan or 500 descriptive fields."""
    root = Path(root).expanduser().resolve()
    problems = verify_titan_release(root, release_id=release_id)
    if problems:
        raise TitanBridgeError("release verification failed: " + "; ".join(problems))
    if not canonical_issue_id or not slots:
        raise TitanBridgeError("canonical issue and at least one slot are required")
    if len({slot.canonical_issue_slot_id for slot in slots}) != len(slots):
        raise TitanBridgeError("canonical issue slots must be unique")
    if any(not all((slot.fixture_capture_batch_id, slot.canonical_fixture_id, slot.canonical_issue_slot_id)) for slot in slots):
        raise TitanBridgeError("each slot needs a sealed capture and frozen canonical identity")
    snapshot = root / "releases" / "titan" / release_id / "control.sqlite"
    with sqlite3.connect(snapshot) as connection:
        observed = {row[0] for row in connection.execute("SELECT batch_id FROM fixture_capture")}
    if any(slot.fixture_capture_batch_id not in observed for slot in slots):
        raise TitanBridgeError("bridge slot capture is absent from the sealed Titan release")
    triples = sorted(
        [{"canonical_fixture_id": slot.canonical_fixture_id, "canonical_issue_id": canonical_issue_id,
          "canonical_issue_slot_id": slot.canonical_issue_slot_id} for slot in slots],
        key=lambda item: item["canonical_issue_slot_id"],
    )
    crosswalk_sha256 = hashlib.sha256(_canonical_bytes(triples)).hexdigest()
    return _canonical_bytes({
        "schema_version": "titan_settlement_bridge_v1",
        "titan_release_id": release_id,
        "crosswalk_sha256": crosswalk_sha256,
        "bindings": triples,
    })
