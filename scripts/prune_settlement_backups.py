#!/usr/bin/env python3
"""Prune settlement backups, never removing a snapshot a recorded batch still needs.

Each update writes a ~3.3 GB pre-write snapshot, so an unattended schedule grows the backup
directory without bound. Retention cannot be "keep the most recent N": a replay derives which
issues a batch owed from the *exact* pre-write database of that batch, so a newer snapshot
cannot stand in for an older one. Every snapshot a recorded batch names as its anchor is kept
whatever its rank, and only the unprotected remainder is thinned to the retention count.

Anchors are matched by *identity*, not by name: where the evidence carries a content hash the
candidate has to hash the same, so renaming a snapshot or editing a receipt can neither make an
anchored snapshot disposable nor protect an unrelated file. An anchor whose snapshot cannot be
found stops the run — unreadable or missing evidence means a dependency exists that this pass
cannot see, not that there is nothing to protect — unless the registry records it as retired.

Nothing is authorised until the destination is identified physically: a symlinked path at the
directory or its parent is refused, the release is excluded by filesystem identity rather than
by name, and every candidate has to open as a SQLite database carrying the release's
observation table. A file that is not a recognised snapshot also stops the run.
"""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.settlement_storage import validate_settlement_storage  # noqa: E402

SUFFIX = ".sqlite"
OBSERVATION_TABLE = "observation"
BATCH_TABLES = ("sp_correction_batch", "halftime_correction_batch",
                "half_full_correction_batch", "finding_supersession_batch",
                "issue_recovery_batch", "issue_addition_batch")
ANCHOR_TABLES = ("issue_addition_anchor",)
ARCHIVE_SUFFIX = ".zst"
MANIFEST_SUFFIX = ".manifest.json"


def archived_snapshots(directory: Path) -> dict:
    """Map each archived snapshot's content hash to the archive that now holds those bytes.

    A snapshot compressed after its replay passed is still the batch's evidence, so the anchor
    has to resolve to the archive. The manifest is checked against the archive it names, so an
    edited manifest cannot claim to hold bytes it does not.
    """
    archived = {}
    for manifest in sorted(Path(directory).glob("*" + MANIFEST_SUFFIX)):
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"an archive manifest cannot be read, so its anchor cannot be "
                             f"ruled out: {manifest} ({error})") from error
        archive = Path(directory) / str(document.get("archive") or "")
        if not document.get("snapshot_sha256") or not archive.is_file():
            raise ValueError(f"an archive manifest names no usable archive: {manifest}")
        if file_identity(archive)[0] != document.get("archive_sha256"):
            raise ValueError(f"the archive does not match its manifest: {archive}")
        archived[document["snapshot_sha256"]] = archive.name
    return archived


def file_identity(path: Path) -> tuple[str, int]:
    """Content hash and byte length: how a snapshot is identified, not by its name."""
    digest = hashlib.sha256()
    length = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
            length += len(chunk)
    return digest.hexdigest(), length


def looks_like_snapshot(path: Path) -> bool:
    """True when `path` is a SQLite database carrying the release's observation table."""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (OBSERVATION_TABLE,)).fetchone()[0] == 1
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def _claims(connection: sqlite3.Connection, table: str) -> list[dict]:
    """Anchor claims recorded in `table`, each naming a snapshot and, when stored, its hash."""
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if not columns:
        return []
    for candidate in ("backup_path", "backup"):
        if candidate in columns:
            path_column = candidate
            break
    else:
        return []
    selected = [path_column,
                "backup_sha256" if "backup_sha256" in columns else "NULL AS backup_sha256",
                "backup_bytes" if "backup_bytes" in columns else "NULL AS backup_bytes"]
    return [{"path": row[0], "sha256": row[1], "bytes": row[2]}
            for row in connection.execute(f"SELECT {', '.join(selected)} FROM {table}")
            if row[0]]


def replay_anchors(release: Path, registry: Path | None = None,
                   bundles_root: Path | None = None) -> tuple[list[dict], set[str]]:
    """Anchor claims for every recorded batch, plus the anchor names the registry retires.

    Read from the release's own audit tables, from the registry's corrections and from the
    receipt each applied bundle carries. A claim without a stored hash can only be matched by
    name, which is why an unresolvable one is refused rather than treated as absent.
    """
    claims: list[dict] = []
    release = Path(release)
    if not release.is_file():
        raise ValueError(
            f"the release is unreadable, so its anchors cannot be checked: {release}")
    connection = sqlite3.connect(f"file:{release}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table in BATCH_TABLES + ANCHOR_TABLES:
            if table in tables:
                claims.extend(_claims(connection, table))
    finally:
        connection.close()
    retired: set[str] = set()
    if registry is not None:
        registry = Path(registry)
        if not registry.is_file():
            raise ValueError(
                f"the registry is unreadable, so its anchors cannot be checked: {registry}")
        document = json.loads(registry.read_text(encoding="utf-8"))
        for correction in document.get("corrections") or []:
            if correction.get("backup"):
                claims.append({"path": correction["backup"],
                               "sha256": correction.get("backup_sha256"),
                               "bytes": correction.get("backup_bytes")})
        retired = {Path(name).name for name in document.get("retired_anchors") or []}
    if bundles_root is not None:
        root = Path(bundles_root)
        if not root.is_dir():
            raise ValueError(
                f"the bundle root is unreadable, so its anchors cannot be checked: {root}")
        for receipt in sorted(root.glob("*/applied.json")):
            try:
                document = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError(f"an applied receipt cannot be read, so its anchor cannot be "
                                 f"ruled out: {receipt} ({error})") from error
            if document.get("status") == "added" and not document.get("backup"):
                raise ValueError(f"an applied receipt names no anchor: {receipt}")
            if document.get("backup"):
                claims.append({"path": document["backup"],
                               "sha256": document.get("backup_sha256"),
                               "bytes": document.get("backup_bytes")})
    return claims, retired


def authorize_directory(directory: Path, release: Path | None) -> Path:
    """Refuse a destination where a deletion could reach something other than a snapshot."""
    directory = Path(directory)
    for level in (directory, directory.parent):
        if level.is_symlink():
            raise ValueError(f"refusing a symlinked path: {level}")
    if not directory.is_dir():
        raise ValueError(f"not a backup directory: {directory}")
    directory = directory.resolve()
    if directory.parent.name != "backups":
        raise ValueError(f"not a directory under a backups parent: {directory}")
    release_entry = None
    if release is not None:
        release = Path(release)
        if release.exists():
            release = release.resolve()
            release_entry = (release.stat().st_dev, release.stat().st_ino)
    for path in directory.iterdir():
        if path.is_symlink():
            raise ValueError(f"refusing a symlinked entry in the backup directory: {path}")
        if release_entry is not None and path.is_file():
            if (path.stat().st_dev, path.stat().st_ino) == release_entry:
                raise ValueError("the release database sits in the backup directory")
    return directory


def prune_backups(directory: Path, *, keep: int, apply: bool, release: Path | None = None,
                  protect=(), retired=()) -> dict:
    """Return the snapshots to keep and to remove, deleting them only when asked.

    `protect` holds anchor claims (dictionaries naming a path and, when known, its content
    hash). A claim matching no candidate stops the run unless its name is listed in `retired`,
    because an anchor that cannot be located is evidence of a dependency, not of its absence.
    """
    if type(keep) is not int or keep < 1:
        raise ValueError("keep must be a positive integer")
    directory = authorize_directory(directory, release)
    claims = [dict(claim) if isinstance(claim, dict) else {"path": str(claim)}
              for claim in protect]
    retired = {Path(name).name for name in retired}
    candidates = sorted((path for path in directory.iterdir()
                         if path.is_file() and path.name.endswith(SUFFIX)),
                        key=lambda path: (path.stat().st_mtime, path.name))
    if not candidates:
        raise ValueError(f"no *{SUFFIX} snapshots in {directory}")
    unrecognised = [path.name for path in candidates if not looks_like_snapshot(path)]
    if unrecognised:
        raise ValueError(f"not settlement snapshots, refusing to touch them: {unrecognised}")
    identities = {path.name: file_identity(path)[0] for path in candidates}
    archived = archived_snapshots(directory)
    anchored, unresolved = set(), []
    for claim in claims:
        wanted = Path(claim["path"]).name
        matches = ([path for path in candidates if identities[path.name] == claim["sha256"]]
                   if claim.get("sha256")
                   else [path for path in candidates if path.name == wanted])
        if matches:
            anchored.update(path.name for path in matches)
        elif claim.get("sha256") in archived:
            # Compacted after its replay passed: the archive is the evidence now, and archives
            # are never candidates, so the anchor is resolved without protecting a snapshot.
            pass
        elif wanted in retired and not any(path.name == wanted for path in candidates):
            # Retirement records a snapshot that is gone. A file still sitting under that name
            # is not the retired one — it may be a rewritten anchor — so it is refused rather
            # than exempted, and stays protected by that refusal.
            pass
        else:
            unresolved.append(wanted)
    if unresolved:
        raise ValueError("recorded anchors are missing from this directory, so nothing can be "
                         f"ruled out: {sorted(set(unresolved))}")
    thinnable = [path for path in candidates if path.name not in anchored]
    keep_set = thinnable[-keep:] if keep < len(thinnable) else thinnable
    remove = [path for path in thinnable if path not in keep_set]
    if apply:
        for path in remove:
            path.unlink()
    kept = sorted(keep_set + [path for path in candidates if path.name in anchored])
    return {"directory": str(directory), "keep": [path.name for path in kept],
            "anchored": sorted(anchored), "remove": [path.name for path in remove],
            "removed": bool(apply) and bool(remove),
            "freed_bytes": sum(path.stat().st_size for path in remove) if not apply else 0}


def main(argv=None):
    """Report what would be removed; remove it only with --apply."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=2)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--release", type=Path, help="the release database, excluded explicitly")
    parser.add_argument("--registry", type=Path, help="registry naming further replay anchors")
    parser.add_argument("--bundles-root", type=Path,
                        help="directories whose applied.json receipts name replay anchors")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--mountpoint", type=Path)
    args = parser.parse_args(argv)
    if args.data_root is not None:
        validate_settlement_storage(args.data_root, [args.directory],
                                    mountpoint=args.mountpoint)
    claims, retired = (replay_anchors(args.release, args.registry, args.bundles_root)
                       if args.release else ([], set()))
    result = prune_backups(args.directory, keep=args.keep, apply=args.apply,
                           release=args.release, protect=claims, retired=retired)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
