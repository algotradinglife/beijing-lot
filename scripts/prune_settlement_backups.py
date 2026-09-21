#!/usr/bin/env python3
"""Prune settlement backups, never removing a snapshot a recorded batch still needs.

Each update writes a ~3.3 GB pre-write snapshot, so an unattended schedule grows the backup
directory without bound. Retention cannot be "keep the most recent N": a replay derives which
issues a batch owed from the *exact* pre-write database of that batch, so a newer snapshot
cannot stand in for an older one. Any snapshot named as the anchor of a recorded batch — in the
release's own batch tables or in the registry's corrections — is therefore kept regardless of
rank, and only the unprotected remainder is thinned to the retention count.

Nothing is deleted until the destination and every candidate have been identified: the
directory must be a real `backups` directory rather than a symlink or a release directory, and
each candidate must be a readable SQLite database carrying the release's observation table.
A file that is not a recognised snapshot stops the run instead of being treated as disposable.
"""
import argparse
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
                "issue_recovery_batch")


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


def replay_protected_backups(release: Path, registry: Path | None = None,
                             bundles_root: Path | None = None) -> set[str]:
    """Names of the backups that recorded batches name as their replay anchor.

    Read from the release's batch tables, from the registry's corrections and from the receipt
    each applied bundle carries, so a batch whose anchor is recorded in any of those places
    keeps that snapshot alive.
    """
    protected: set[str] = set()
    release = Path(release)
    if release.is_file():
        connection = sqlite3.connect(f"file:{release}?mode=ro", uri=True)
        try:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for table in BATCH_TABLES:
                if table not in tables:
                    continue
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if "backup_path" not in columns:
                    continue
                for (path,) in connection.execute(f"SELECT backup_path FROM {table}"):
                    if path:
                        protected.add(Path(path).name)
        finally:
            connection.close()
    if bundles_root is not None and Path(bundles_root).is_dir():
        for receipt in sorted(Path(bundles_root).glob("*/applied.json")):
            try:
                document = json.loads(receipt.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for key in ("backup", "backup_path", "snapshot"):
                if document.get(key):
                    protected.add(Path(document[key]).name)
    if registry is not None and Path(registry).is_file():
        document = json.loads(Path(registry).read_text(encoding="utf-8"))
        for correction in document.get("corrections") or []:
            for key in ("backup", "backup_path", "snapshot"):
                if correction.get(key):
                    protected.add(Path(correction[key]).name)
    return protected


def authorize_directory(directory: Path, release: Path | None) -> None:
    """Refuse a destination where a deletion could reach something other than a snapshot."""
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError(f"refusing a symlinked backup directory: {directory}")
    if not directory.is_dir():
        raise ValueError(f"not a backup directory: {directory}")
    if directory.parent.name != "backups":
        raise ValueError(f"not a directory under a backups parent: {directory}")
    if release is not None and Path(release).name in {path.name for path in directory.iterdir()}:
        raise ValueError("the release database sits in the backup directory")


def prune_backups(directory: Path, *, keep: int, apply: bool, release: Path | None = None,
                  protect=()) -> dict:
    """Return the snapshots to keep and to remove, deleting them only when asked.

    Ordering among the unprotected snapshots is by modification time with the path as a
    tiebreaker, so two snapshots written in the same second still prune deterministically.
    """
    directory = Path(directory)
    if type(keep) is not int or keep < 1:
        raise ValueError("keep must be a positive integer")
    authorize_directory(directory, release)
    protect = {Path(name).name for name in protect}
    release_name = Path(release).name if release is not None else None
    candidates = sorted((path for path in directory.iterdir()
                         if path.is_file() and path.name.endswith(SUFFIX)),
                        key=lambda path: (path.stat().st_mtime, path.name))
    if not candidates:
        raise ValueError(f"no *{SUFFIX} snapshots in {directory}")
    unrecognised = [path.name for path in candidates if not looks_like_snapshot(path)]
    if unrecognised:
        raise ValueError(f"not settlement snapshots, refusing to touch them: {unrecognised}")
    anchored = sorted(path for path in candidates
                      if path.name in protect or path.name == release_name)
    thinnable = [path for path in candidates if path not in anchored]
    keep_set = thinnable[-keep:] if keep < len(thinnable) else thinnable
    remove = [path for path in thinnable if path not in keep_set]
    if apply:
        for path in remove:
            path.unlink()
    return {"directory": str(directory),
            "keep": [path.name for path in sorted(keep_set + anchored)],
            "anchored": [path.name for path in anchored],
            "remove": [path.name for path in remove],
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
    protect = (replay_protected_backups(args.release, args.registry, args.bundles_root)
               if args.release else set())
    result = prune_backups(args.directory, keep=args.keep, apply=args.apply,
                           release=args.release, protect=protect)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
