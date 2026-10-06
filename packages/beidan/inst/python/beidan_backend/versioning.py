"""Versioned publication shared by base datasets and derived artifacts.

Both kinds of data are published the same way: each publication lands in its own
immutable directory under ``versions/<label>/`` and ``current.json`` points at
the newest one. The rules are also the same:

* a label already published with identical content is a no-op (``unchanged``);
* a label already published with different content is refused — a finalized
  label is never rewritten;
* refreshing an older label does not move the pointer backwards.

The caller supplies how to write the content, so a base dataset (many tables
plus a manifest) and a derived artifact (one Parquet file plus a receipt) share
one lifecycle without pretending to share a layout.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable

VERSIONS_DIR = "versions"
CURRENT_FILE = "current.json"
VERSION_SCHEMA = "beijing_lot_derived_version_v1"


class VersionError(RuntimeError):
    """A version cannot be published, or is inconsistent with its record."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Metadata files record how a version was produced (timestamps, parameters) and
# change on every run; they must not decide whether two versions are the same.
VOLATILE_SUFFIXES = (".json",)


def content_digest(path: Path, *, data_only: bool = True) -> str:
    """A deterministic digest of a file or directory's *content*.

    For a directory only data files are hashed (see ``VOLATILE_SUFFIXES``), so a
    re-run that produces identical data but a new ``generated_at`` has the same
    digest and is recognised as an unchanged republication.
    """
    path = Path(path)
    if path.is_file():
        return sha256_file(path)
    if not path.is_dir():
        raise VersionError(f"cannot digest a missing path: {path}")
    files = [p for p in sorted(path.rglob("*")) if p.is_file()]
    if data_only:
        files = [p for p in files if not p.name.endswith(VOLATILE_SUFFIXES)]
    if not files:
        raise VersionError(f"cannot digest: no content files under {path}")
    lines = [f"{p.relative_to(path).as_posix()}:{sha256_file(p)}" for p in files]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def version_directory(base: Path, label: str) -> Path:
    """``<base>/versions/<label>``, rejecting labels that could escape."""
    if not label or "/" in label or label in {".", ".."}:
        raise VersionError(f"invalid label version: {label!r}")
    return Path(base) / VERSIONS_DIR / label


def list_versions(base: Path) -> list[str]:
    """Published labels, oldest first (ISO dates sort chronologically)."""
    directory = Path(base) / VERSIONS_DIR
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_dir())


def read_current(base: Path) -> dict | None:
    """The ``current.json`` pointer, or ``None`` when nothing is published."""
    path = Path(base) / CURRENT_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VersionError(f"current pointer is unreadable: {path}: {error}") from error


def write_json_atomically(value, path: Path) -> None:
    """Write ``value`` as JSON atomically (temp file, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def point_current_at_newest(base: Path) -> dict:
    """Point ``current.json`` at the newest published label and return it."""
    base = Path(base)
    versions = list_versions(base)
    if not versions:
        raise VersionError(f"nothing published under {base}")
    newest = versions[-1]
    pointer = {"schema": VERSION_SCHEMA, "label_version": newest}
    record = base / VERSIONS_DIR / newest / "version.json"
    if record.is_file():
        pointer.update(json.loads(record.read_text(encoding="utf-8")))
        pointer["label_version"] = newest
    write_json_atomically(pointer, base / CURRENT_FILE)
    return pointer


def _rebase_paths(value, *, from_root: Path, to_root: Path):
    """Rewrite any string under ``from_root`` to sit under ``to_root``.

    The publish callback runs against a staging directory, so paths it records
    would otherwise keep the staging prefix after the directory is renamed.
    """
    if isinstance(value, str):
        prefix = str(from_root)
        return str(to_root) + value[len(prefix):] if value.startswith(prefix) else value
    if isinstance(value, dict):
        return {k: _rebase_paths(v, from_root=from_root, to_root=to_root)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_rebase_paths(v, from_root=from_root, to_root=to_root) for v in value]
    return value


def publish_version(
    base: Path,
    label: str,
    publish: Callable[[Path], dict],
    *,
    allow_republish: bool = True,
) -> dict:
    """Publish one label version.

    @param base The artifact's base directory (its ``versions/`` lives here).
    @param label Immutable label, e.g. an ISO date or a dataset release version.
    @param publish Callback that writes the version's content into the directory
        it is given and returns the version record (at least ``rows``).
    @param allow_republish When false, any existing label is refused even if the
        content is identical; used where re-publishing is never meaningful.
    @return ``{"label_version", "status", "record", "versions"}`` where status is
        ``"published"`` or ``"unchanged"``.
    @raises VersionError when the label is published with different content, or
        when the label is invalid.
    """
    base = Path(base)
    destination = version_directory(base, label)
    existing = list_versions(base)
    staging = destination.with_name(f".{label}.staging")
    if staging.exists():
        raise VersionError(f"stale staging directory present: {staging}")

    try:
        staging.mkdir(parents=True, exist_ok=False)
        record = publish(staging)
        incoming = content_digest(staging)

        if label in existing:
            prior = content_digest(destination)
            if allow_republish and prior == incoming:
                # identical bytes: keep the published copy, drop the staging one
                import shutil

                shutil.rmtree(staging)
                pointer = point_current_at_newest(base)
                return {"label_version": label, "status": "unchanged",
                        "record": record, "versions": list_versions(base),
                        "current": pointer}
            raise VersionError(
                f"label {label!r} is already published with different content "
                f"(recorded {prior[:12]}, incoming {incoming[:12]}); publish under a "
                f"new label instead of rewriting a finalized version")

        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)
        # The callback wrote paths pointing at the staging directory. Rewrite
        # them against the final directory before recording, so a pointer never
        # names a location that no longer exists.
        record = _rebase_paths({**record, "label_version": label,
                                "content_digest": incoming,
                                "directory": str(destination)},
                               from_root=staging, to_root=destination)
        write_json_atomically(record, destination / "version.json")
        pointer = point_current_at_newest(base)
        return {"label_version": label, "status": "published", "record": record,
                "versions": list_versions(base), "current": pointer}
    finally:
        if staging.exists():
            import shutil

            shutil.rmtree(staging, ignore_errors=True)
