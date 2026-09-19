"""Immutable Titan release sealing and offline verification."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .store import TitanRosterStore


class TitanReleaseError(ValueError):
    """Raised when a release cannot be sealed or verified."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def seal_titan_release(store: TitanRosterStore, *, release_id: str) -> Path:
    """Create a self-contained control snapshot plus raw-evidence manifest."""
    if not release_id or "/" in release_id or release_id in {".", ".."}:
        raise TitanReleaseError("release id must be a plain path segment")
    releases = store.root / "releases" / "titan"
    final = releases / release_id
    if final.exists():
        raise TitanReleaseError(f"release already exists: {release_id}")
    releases.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{release_id}.staging-", dir=releases))
    try:
        snapshot = staging / "control.sqlite"
        with sqlite3.connect(snapshot) as destination:
            store.connection.backup(destination)
        raw_manifest = json.loads(store.manifest())
        release = {
            "schema_version": "titan_clean_release_v1",
            "release_id": release_id,
            "control_sqlite_sha256": _sha256(snapshot),
            "titan_store_manifest": raw_manifest,
        }
        _atomic_json(staging / "MANIFEST.json", release)
        directory_fd = os.open(staging, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.replace(staging, final)
        return final
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_titan_release(root: Path, *, release_id: str) -> list[str]:
    """Verify release snapshot and all content-addressed Titan raw references."""
    release_dir = Path(root).expanduser().resolve() / "releases" / "titan" / release_id
    manifest_path = release_dir / "MANIFEST.json"
    control_path = release_dir / "control.sqlite"
    problems: list[str] = []
    if not manifest_path.exists() or not control_path.exists():
        return ["release manifest or control snapshot is missing"]
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except json.JSONDecodeError:
        return ["release manifest is invalid JSON"]
    if manifest.get("schema_version") != "titan_clean_release_v1" or manifest.get("release_id") != release_id:
        problems.append("release identity mismatch")
    if manifest.get("control_sqlite_sha256") != _sha256(control_path):
        problems.append("release control snapshot hash mismatch")
    raw_manifest = manifest.get("titan_store_manifest")
    if not isinstance(raw_manifest, dict):
        return [*problems, "Titan store manifest is missing"]
    if "500" in json.dumps(raw_manifest, sort_keys=True):
        problems.append("Titan release manifest contains settlement source data")
    roster_batch_ids = {item.get("batch_id") for item in raw_manifest.get("batches", [])}
    authorizations = {item.get("batch_id"): item for item in raw_manifest.get("capture_authorizations", [])}
    if set(authorizations) != roster_batch_ids:
        problems.append("release roster captures lack an authorization binding")
    for authorization in authorizations.values():
        mode, receipt = authorization.get("mode"), authorization.get("receipt_sha256")
        if mode == "PROBE" and receipt is not None:
            problems.append("probe capture carries an authorization receipt")
        if mode in {"AUTHORIZED", "USER_RISK_ACKNOWLEDGED"} and (not isinstance(receipt, str) or len(receipt) != 64):
            problems.append("operational capture lacks a valid receipt hash")
        if mode not in {"PROBE", "AUTHORIZED", "USER_RISK_ACKNOWLEDGED"}:
            problems.append("capture has an unknown authorization mode")
    batches = [*raw_manifest.get("batches", []), *raw_manifest.get("fixture_captures", [])]
    root = Path(root).expanduser().resolve()
    for batch in batches:
        raw_path = batch.get("raw_path")
        raw_sha = batch.get("raw_sha256")
        if not isinstance(raw_path, str) or not isinstance(raw_sha, str):
            problems.append("raw receipt is incomplete")
            continue
        path = root / raw_path
        if not path.exists() or _sha256(path) != raw_sha:
            problems.append(f"raw evidence mismatch: {batch.get('batch_id')}")
    try:
        with sqlite3.connect(control_path) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            problems.append("release control snapshot integrity check failed")
    except sqlite3.DatabaseError:
        problems.append("release control snapshot is unreadable")
    return problems
