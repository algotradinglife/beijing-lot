"""Atomic, minimal input snapshots for SP-CONSISTENCY-001A G0.

The G0 audit never reads a mutable operational SQLite file.  This module first
exports only the outcome-blind columns required by the audit from one read
transaction, then the audit reads those exported SQLite files.  A verified p42
segment package is copied and deterministically archived before use.
"""

from __future__ import annotations

import hashlib
import gzip
import json
import shutil
import sqlite3
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.multimarket_p0 import MultimarketP0Error, verify_segment_freeze


MODEL_TERMS = ("william", "willhill", "1x2", "over_under", "overunder", "ou_")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("BEGIN")
    return connection


def _write_snapshot(destination: Path, schema: str, rows: Iterable[tuple[Any, ...]], insert_sql: str) -> None:
    connection = sqlite3.connect(destination)
    try:
        connection.executescript(schema)
        connection.executemany(insert_sql, rows)
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()


def _snapshot_p34(source: Path, destination: Path) -> dict[str, Any]:
    connection = _read_only(source)
    try:
        matches = [tuple(row) for row in connection.execute(
            "SELECT match_id, issue, match_idx, kickoff_ts FROM matches ORDER BY issue, match_idx, match_id"
        )]
        snapshots = [tuple(row) for row in connection.execute(
            "SELECT match_id, snapshot_ts, sp_3, sp_1, sp_0 FROM snapshots ORDER BY match_id, snapshot_ts"
        )]
    finally:
        connection.close()
    _write_snapshot(
        destination,
        """
        CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT NOT NULL, match_idx INTEGER, kickoff_ts TEXT);
        CREATE TABLE snapshots (match_id TEXT NOT NULL, snapshot_ts TEXT NOT NULL, sp_3 REAL, sp_1 REAL, sp_0 REAL);
        CREATE INDEX idx_snapshot_match ON snapshots(match_id, snapshot_ts);
        """,
        matches,
        "INSERT INTO matches VALUES (?, ?, ?, ?)",
    )
    connection = sqlite3.connect(destination)
    try:
        connection.executemany("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)", snapshots)
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()
    return {"logical_name": "p34_g0_snapshot.sqlite", "rows": {"matches": len(matches), "snapshots": len(snapshots)}}


def _snapshot_p0_handicaps(source: Path, destination: Path) -> dict[str, Any]:
    connection = _read_only(source)
    try:
        rows = [tuple(row) for row in connection.execute(
            "SELECT issue, match_idx, handicap_line FROM matches ORDER BY issue, match_idx"
        )]
        schema_rows = [
            {"name": str(row["name"]), "type": str(row["type"]), "sql": str(row["sql"] or "")}
            for row in connection.execute("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name")
        ]
    finally:
        connection.close()
    _write_snapshot(
        destination,
        "CREATE TABLE matches (issue TEXT NOT NULL, match_idx INTEGER NOT NULL, handicap_line REAL);",
        rows,
        "INSERT INTO matches VALUES (?, ?, ?)",
    )
    return {"logical_name": "p0_handicap_snapshot.sqlite", "rows": {"matches": len(rows)}, "schema_inventory": schema_rows}


def _candidate_file_inventory(roots: Iterable[Path]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for root in roots:
        resolved = root.resolve()
        label = root.name
        if not resolved.exists():
            candidates.append({"root": label, "status": "missing"})
            continue
        for path in sorted(resolved.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            name = path.name.lower()
            if any(term in name for term in MODEL_TERMS):
                candidates.append(
                    {"path": str(path.relative_to(resolved)), "root": label, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
                )
    return candidates


def _write_model_inventory(destination: Path, p0_info: dict[str, Any], roots: Iterable[Path]) -> dict[str, Any]:
    schema_matches = [item["name"] for item in p0_info["schema_inventory"] if any(term in item["name"].lower() for term in MODEL_TERMS)]
    file_candidates = _candidate_file_inventory(roots)
    payload = {
        "schema_version": "sp_consistency_model_score_inventory_v1",
        "declared_input": "William Hill 1X2 + O/U strict pre-match snapshots",
        "scanned_p0_schema_candidates": schema_matches,
        "scanned_file_candidates": file_candidates,
        "strict_eligible_assets": [],
        "rejection_counts": {
            "no_named_candidate_table_or_view": 0 if schema_matches else 1,
            "no_named_candidate_file": 0 if any("path" in item for item in file_candidates) else 1,
            "candidate_assets_without_complete_frozen_wh_1x2_ou_panel": sum(1 for item in file_candidates if "path" in item),
            "no_strict_frozen_william_hill_1x2_ou_contract": 1,
        },
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _deterministic_tar(source_root: Path, destination: Path) -> None:
    with destination.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed, tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for source in sorted(source_root.rglob("*")):
            if source.is_dir():
                continue
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"p42 source contains non-regular file: {source}")
            info = archive.gettarinfo(str(source), arcname=source.relative_to(source_root).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with source.open("rb") as handle:
                archive.addfile(info, handle)


def _copy_verified_p42_packages(source_root: Path, destination: Path) -> list[dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for manifest_path in sorted(source_root.rglob("manifest.json")):
        package = manifest_path.parent
        if not (package / "frozen_outcomes.csv").is_file():
            continue
        try:
            verified = verify_segment_freeze(package)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError, MultimarketP0Error):
            continue
        if 42 not in manifest.get("target_playids", []):
            continue
        target = destination / str(manifest["event_id"])
        shutil.copytree(package, target)
        copied.append({"event_id": str(manifest["event_id"]), "sha256s_sha256": str(verified["sha256s_sha256"])})
    return copied


@dataclass(frozen=True)
class G0InputSnapshot:
    p34_snapshot: Path
    p0_snapshot: Path
    p42_archive: Path
    p42_root: Path
    model_inventory: Path
    fingerprints: Path


def create_g0_input_snapshot(
    *, work_dir: Path, p34_db: Path, p0_db: Path, p42_freeze_root: Path, model_search_roots: Iterable[Path]
) -> G0InputSnapshot:
    """Create the entire immutable, outcome-blind input set before running G0."""

    inputs = work_dir / "atomic_inputs"
    inputs.mkdir(parents=True)
    p34_snapshot = inputs / "p34_g0_snapshot.sqlite"
    p0_snapshot = inputs / "p0_handicap_snapshot.sqlite"
    p42_root = inputs / "p42_segment_freezes"
    p42_archive = inputs / "p42_segment_freezes.tar.gz"
    model_inventory = inputs / "model_score_inventory.json"
    fingerprints = inputs / "input_fingerprints.json"
    p34_info = _snapshot_p34(p34_db, p34_snapshot)
    p0_info = _snapshot_p0_handicaps(p0_db, p0_snapshot)
    p42_packages = _copy_verified_p42_packages(p42_freeze_root, p42_root)
    _deterministic_tar(p42_root, p42_archive)
    _write_model_inventory(model_inventory, p0_info, model_search_roots)
    records = {
        "schema_version": "sp_consistency_g0_atomic_inputs_v1",
        "p34": {**p34_info, "bytes": p34_snapshot.stat().st_size, "sha256": sha256_file(p34_snapshot)},
        "p0": {"logical_name": "p0_handicap_snapshot.sqlite", "bytes": p0_snapshot.stat().st_size, "sha256": sha256_file(p0_snapshot), "rows": p0_info["rows"]},
        "p42": {"logical_name": "p42_segment_freezes.tar.gz", "bytes": p42_archive.stat().st_size, "sha256": sha256_file(p42_archive), "verified_packages": p42_packages},
        "model_score_inventory": {"logical_name": "model_score_inventory.json", "bytes": model_inventory.stat().st_size, "sha256": sha256_file(model_inventory)},
    }
    fingerprints.write_text(json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return G0InputSnapshot(p34_snapshot, p0_snapshot, p42_archive, p42_root, model_inventory, fingerprints)
