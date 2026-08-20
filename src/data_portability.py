"""Versioned, migration-safe snapshots for local Beijing-lot data assets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_ROOT_ENV = "BEIJING_LOT_DATA_ROOT"
SNAPSHOT_SCHEMA = "bj249-data-snapshot-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _logical_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"asset path must be repository-relative: {value!r}")
    return path


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _read_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("snapshot config requires a non-empty assets list")
    seen: set[str] = set()
    for asset in assets:
        logical = str(_logical_path(str(asset.get("path") or "")))
        if logical in seen:
            raise ValueError(f"duplicate asset path: {logical}")
        seen.add(logical)
        if asset.get("kind") not in {"sqlite", "file", "tree"}:
            raise ValueError(f"unsupported asset kind for {logical}")
    return payload


def sqlite_inventory(path: Path, time_columns: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Return an exact semantic receipt from one consistent SQLite file."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        integrity_rows = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        if integrity_rows != ["ok"]:
            raise ValueError(f"SQLite integrity check failed for {path}: {integrity_rows[:5]}")
        schema_rows = connection.execute(
            "SELECT type,name,tbl_name,coalesce(sql,'') FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        row_counts = {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0]
            )
            for table in tables
        }
        available_columns = {
            table: {row[1] for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")}
            for table in tables
        }
        ranges: list[dict[str, Any]] = []
        for spec in time_columns or []:
            table, column = str(spec["table"]), str(spec["column"])
            if table not in available_columns or column not in available_columns[table]:
                raise ValueError(f"configured time column is absent: {table}.{column}")
            minimum, maximum, usable = connection.execute(
                f"SELECT MIN({_quote_identifier(column)}),MAX({_quote_identifier(column)}),"
                f"COUNT({_quote_identifier(column)}) FROM {_quote_identifier(table)}"
            ).fetchone()
            ranges.append(
                {
                    "table": table,
                    "column": column,
                    "minimum": minimum,
                    "maximum": maximum,
                    "non_null_rows": int(usable),
                }
            )
        return {
            "integrity_check": "ok",
            "schema_sha256": hashlib.sha256(_canonical_json(schema_rows)).hexdigest(),
            "table_count": len(tables),
            "row_counts": row_counts,
            "time_ranges": ranges,
        }
    finally:
        connection.close()


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source.resolve().as_posix()}?mode=ro"
    source_connection = sqlite3.connect(source_uri, uri=True)
    target_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(target_connection)
        target_connection.execute("PRAGMA journal_mode=DELETE")
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()
    with destination.open("rb") as handle:
        os.fsync(handle.fileno())


def _copy_file(source: Path, destination: Path) -> str:
    if source.is_symlink():
        raise ValueError(f"symlink assets are not accepted: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as input_handle, destination.open("wb") as output_handle:
        for chunk in iter(lambda: input_handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            output_handle.write(chunk)
        output_handle.flush()
        os.fsync(output_handle.fileno())
    return digest.hexdigest()


def _file_receipt(
    logical_path: Path, snapshot_path: Path, destination: Path, kind: str, sha256: str
) -> dict[str, Any]:
    return {
        "kind": kind,
        "logical_path": logical_path.as_posix(),
        "snapshot_path": snapshot_path.as_posix(),
        "bytes": destination.stat().st_size,
        "sha256": sha256,
    }


def create_snapshot(
    *, config_path: Path, source_root: Path, external_root: Path, snapshot_id: str
) -> Path:
    """Create and atomically publish one full, configured external snapshot."""
    if not snapshot_id or "/" in snapshot_id or snapshot_id.startswith("."):
        raise ValueError("snapshot_id must be a non-hidden single path component")
    config = _read_config(config_path)
    container = external_root.resolve() / "snapshots"
    container.mkdir(parents=True, exist_ok=True)
    final = container / snapshot_id
    if final.exists():
        raise FileExistsError(f"snapshot already exists: {snapshot_id}")
    staging = container / f".{snapshot_id}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    receipts: list[dict[str, Any]] = []
    local_stage = Path(
        tempfile.mkdtemp(prefix=".bj249-local-stage-", dir=source_root.resolve().parent)
    )
    try:
        for asset in config["assets"]:
            logical = _logical_path(str(asset["path"]))
            source = source_root.resolve() / logical
            if not source.exists():
                raise FileNotFoundError(f"configured source asset is missing: {logical}")
            if asset["kind"] == "sqlite":
                if not source.is_file():
                    raise ValueError(f"SQLite asset is not a file: {logical}")
                local_database = local_stage / logical
                _backup_sqlite(source, local_database)
                inventory = sqlite_inventory(local_database, asset.get("time_columns"))
                local_sha = _sha256(local_database)
                destination = staging / logical
                copied_sha = _copy_file(local_database, destination)
                if copied_sha != local_sha or _sha256(destination) != local_sha:
                    raise ValueError(f"external SQLite copy mismatch: {logical}")
                receipt = _file_receipt(logical, logical, destination, "sqlite", local_sha)
                receipt["sqlite"] = inventory
                receipts.append(receipt)
                local_database.unlink()
            elif asset["kind"] == "file":
                if not source.is_file():
                    raise ValueError(f"file asset is not a file: {logical}")
                destination = staging / logical
                copied_sha = _copy_file(source, destination)
                if _sha256(destination) != copied_sha:
                    raise ValueError(f"external file copy mismatch: {logical}")
                receipts.append(_file_receipt(logical, logical, destination, "file", copied_sha))
            else:
                if not source.is_dir():
                    raise ValueError(f"tree asset is not a directory: {logical}")
                for child in sorted(item for item in source.rglob("*") if item.is_file()):
                    if child.is_symlink():
                        raise ValueError(f"symlink assets are not accepted: {child}")
                    relative_child = child.relative_to(source_root.resolve())
                    destination = staging / relative_child
                    copied_sha = _copy_file(child, destination)
                    if _sha256(destination) != copied_sha:
                        raise ValueError(f"external file copy mismatch: {relative_child}")
                    receipts.append(
                        _file_receipt(relative_child, relative_child, destination, "file", copied_sha)
                    )
    finally:
        shutil.rmtree(local_stage)
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot_id,
        "created_at_utc": _utc_now(),
        "source_identity": "repository-relative-assets",
        "asset_count": len(receipts),
        "assets": receipts,
    }
    manifest_path = staging / "MANIFEST.json"
    _write_atomic(manifest_path, _canonical_json(manifest))
    manifest_sha = _sha256(manifest_path)
    _write_atomic(staging / "COMPLETE", (manifest_sha + "\n").encode("ascii"))
    _snapshot_envelope(staging)
    os.replace(staging, final)
    _fsync_directory(container)
    return final


def _snapshot_envelope(snapshot_path: Path) -> tuple[dict[str, Any], str]:
    """Validate the completion marker, manifest, exact file set and sizes."""
    marker = snapshot_path / "COMPLETE"
    manifest_path = snapshot_path / "MANIFEST.json"
    if not marker.is_file() or not manifest_path.is_file():
        raise ValueError("snapshot is not complete")
    expected_manifest_sha = marker.read_text(encoding="ascii").strip()
    actual_manifest_sha = _sha256(manifest_path)
    if expected_manifest_sha != actual_manifest_sha:
        raise ValueError("snapshot manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SNAPSHOT_SCHEMA:
        raise ValueError("unsupported snapshot schema")
    expected_files = {
        _logical_path(asset["snapshot_path"]).as_posix()
        for asset in manifest["assets"]
    } | {"MANIFEST.json", "COMPLETE"}
    actual_files = {
        path.relative_to(snapshot_path).as_posix()
        for path in snapshot_path.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError("snapshot contains missing or unmanifested files")
    for asset in manifest["assets"]:
        path = snapshot_path / _logical_path(asset["snapshot_path"])
        if not path.is_file() or path.stat().st_size != int(asset["bytes"]):
            raise ValueError(f"snapshot asset size mismatch: {asset['snapshot_path']}")
    return manifest, actual_manifest_sha


def snapshot_summary(snapshot_path: Path) -> dict[str, Any]:
    """Return the receipt already proven during atomic snapshot publication."""
    manifest, manifest_sha = _snapshot_envelope(snapshot_path)
    return {
        "snapshot_id": manifest["snapshot_id"],
        "manifest_sha256": manifest_sha,
        "asset_count": len(manifest["assets"]),
        "total_bytes": sum(int(asset["bytes"]) for asset in manifest["assets"]),
        "verified_at_utc": _utc_now(),
        "status": "PASS",
    }


def verify_snapshot(snapshot_path: Path) -> dict[str, Any]:
    """Read back and hash every external asset against its semantic manifest."""
    manifest, actual_manifest_sha = _snapshot_envelope(snapshot_path)
    for asset in manifest["assets"]:
        path = snapshot_path / _logical_path(asset["snapshot_path"])
        if _sha256(path) != asset["sha256"]:
            raise ValueError(f"snapshot asset hash mismatch: {asset['snapshot_path']}")
    return {
        "snapshot_id": manifest["snapshot_id"],
        "manifest_sha256": actual_manifest_sha,
        "asset_count": len(manifest["assets"]),
        "total_bytes": sum(int(asset["bytes"]) for asset in manifest["assets"]),
        "verified_at_utc": _utc_now(),
        "status": "PASS",
    }


def restore_snapshot(*, snapshot_path: Path, target: Path) -> dict[str, Any]:
    """Stream-verify into an isolated stage, then atomically expose it."""
    manifest, manifest_sha = _snapshot_envelope(snapshot_path)
    if target.exists():
        raise FileExistsError(f"restore target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    restored: list[dict[str, Any]] = []
    for asset in manifest["assets"]:
        relative = _logical_path(asset["snapshot_path"])
        source = snapshot_path / relative
        destination = staging / relative
        copied_sha = _copy_file(source, destination)
        if copied_sha != asset["sha256"] or _sha256(destination) != asset["sha256"]:
            raise ValueError(f"restored asset hash mismatch: {relative}")
        restored.append(
            {
                "logical_path": relative.as_posix(),
                "sha256": asset["sha256"],
                "comparison": "BYTE_IDENTICAL_TO_VERIFIED_SNAPSHOT",
            }
        )
    receipt = {
        "snapshot_id": manifest["snapshot_id"],
        "manifest_sha256": manifest_sha,
        "asset_count": len(manifest["assets"]),
        "total_bytes": sum(int(asset["bytes"]) for asset in manifest["assets"]),
        "verified_at_utc": _utc_now(),
        "status": "PASS",
        "restored_at_utc": _utc_now(),
        "restored_asset_count": len(restored),
        "assets": restored,
    }
    _write_atomic(staging / "RESTORE_RECEIPT.json", _canonical_json(receipt))
    os.replace(staging, target)
    _fsync_directory(target.parent)
    return receipt
