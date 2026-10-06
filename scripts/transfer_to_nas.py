#!/usr/bin/env python3
"""Verified, resumable transfer of a Sandisk tree into the NAS persistent root.

Copies bytes verbatim (raw archives, fixtures and evidence that are not tabular
data) into ``<root>/archive/<name>`` and records each file's sha256. Only a
sha256 match counts as transferred — a size match alone is not trusted, because
the NAS is a `soft` CIFS mount where a failed write can leave a truncated file.

Long transfers are resumable and the manifest is flushed as work proceeds, so an
interrupted run (timeout, disconnect) loses at most the files not yet recorded;
re-running re-verifies those and continues. Dry-run by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path("/mnt/nas/Data/beijing-lot")
CHUNK = 1 << 20
FLUSH_EVERY = 200


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_files(source: Path, exclude: list[str]) -> list[Path]:
    """All files under ``source``, pruning excluded subtrees during traversal.

    Pruning happens *before* descending, which matters when an excluded
    directory is pathological (e.g. a single directory holding 200k entries on
    exFAT, where ``stat`` on each entry is extremely slow).
    """
    excluded = [Path(prefix).parts for prefix in exclude]
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(source):
        relative_dir = Path(dirpath).relative_to(source)
        kept: list[str] = []
        for name in dirnames:
            candidate = (relative_dir / name).parts
            if any(candidate[: len(prefix)] == prefix for prefix in excluded):
                continue  # drop from dirnames so os.walk never descends
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            out.append(relative_dir / name)
    return sorted(out)


def copy_verified(src: Path, dst: Path) -> str:
    """Stream one file (temp + rename), hashing as it writes.

    Reading the bytes back to hash them would double the I/O; the bytes written
    are the bytes read, so the digest is computed inline.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    temporary = dst.with_name(dst.name + ".partial")
    digest = hashlib.sha256()
    with open(src, "rb") as reader, open(temporary, "wb") as writer:
        for chunk in iter(lambda: reader.read(CHUNK), b""):
            digest.update(chunk)
            writer.write(chunk)
        writer.flush()
    # No per-file fsync: on this CIFS mount (cache=strict) it forces a server
    # round-trip per file and dominates the cost for many-small-file trees.
    os.replace(temporary, dst)
    return digest.hexdigest()


def write_manifest(manifest_path: Path, *, name: str, source: Path, destination: Path,
                   recorded: dict[str, dict]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "beijing_lot_archive_transfer_v1",
        "name": name,
        "source": str(source),
        "destination": str(destination),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_count": len(recorded),
        "bytes": sum(entry["bytes"] for entry in recorded.values()),
        "files": [recorded[key] for key in sorted(recorded)],
    }
    temporary = manifest_path.with_name(manifest_path.name + ".partial")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, manifest_path)


def load_records(journal_path: Path) -> dict[str, dict]:
    """Replay the append-only record journal into a dict keyed by relative path."""
    recorded: dict[str, dict] = {}
    if not journal_path.exists():
        return recorded
    with journal_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn final line from an interrupted run
            recorded[entry["path"]] = entry
    return recorded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--name", required=True, help="name under archive/")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--rehash", action="store_true",
                        help="re-verify every file against the source (slow)")
    parser.add_argument("--exclude", action="append", default=[],
                        help="relative path prefix to skip (repeatable), e.g. a pathological directory")
    parser.add_argument("--shard-over", type=int, default=None, metavar="N",
                        help="shard destinations whose source directory holds more than N files "
                             "into 256 subdirectories (bounds CIFS directory fan-out; the manifest "
                             "records the actual written path)")
    args = parser.parse_args(argv)

    source = args.source
    if not source.is_dir():
        print(f"source is absent: {source}", file=sys.stderr)
        return 2
    if not args.root.is_dir():
        print(f"persistent root unavailable: {args.root}", file=sys.stderr)
        return 2

    destination = args.root / "archive" / args.name
    # The name may be a path (e.g. markets/releases); the ledger file must stay a
    # single flat filename, so "/" becomes "__".
    slug = args.name.replace("/", "__")
    # Enumerate once: walking a flat 200k-entry directory to build a list is
    # expensive, and doing it twice doubled the cost of the worst directory.
    files = relative_files(source, args.exclude)

    # Decide which source directories are flat and huge enough to warrant a
    # sharded destination (256 subdirectories by name hash). Writing many files
    # into one CIFS directory degrades badly, so fan-out is bounded.
    shard_dirs: set[tuple[str, ...]] = set()
    if args.shard_over is not None:
        counts: dict[tuple[str, ...], int] = {}
        for relative in files:
            parent = relative.parent.parts
            counts[parent] = counts.get(parent, 0) + 1
        shard_dirs = {parent for parent, count in counts.items() if count > args.shard_over}
    manifest_path = args.root / "registry" / f"transfer-{slug}.json"
    journal_path = args.root / "registry" / f"transfer-{slug}.jsonl"

    # Replay the append-only journal (cheap, O(n) once) instead of re-reading a
    # giant manifest; the consolidated JSON is written only at the end.
    recorded = load_records(journal_path)
    if not recorded and manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            recorded = {entry["path"]: entry for entry in payload.get("files", [])}
            with journal_path.open("w", encoding="utf-8") as handle:
                for key in sorted(recorded):
                    handle.write(json.dumps(recorded[key], ensure_ascii=False) + "\n")
        except (OSError, json.JSONDecodeError):
            recorded = {}

    journal = journal_path.open("a", encoding="utf-8")
    unflushed = 0

    def record(entry: dict) -> None:
        """Buffer journal lines and flush in batches.

        Flushing per file forces a CIFS round-trip per file and dominates
        many-small-file trees. Batched flushes lose at most ``FLUSH_EVERY``
        records on interruption, and resume re-verifies unrecorded files by
        hashing, so correctness does not depend on the flush cadence.
        """
        nonlocal unflushed
        recorded[entry["path"]] = entry
        journal.write(json.dumps(entry, ensure_ascii=False) + "\n")
        unflushed += 1
        if unflushed >= FLUSH_EVERY:
            journal.flush()
            unflushed = 0

    to_copy = 0
    verified = 0
    failed: list[str] = []
    pending_bytes = 0

    def destination_path(relative: Path) -> Path:
        """Destination for a relative path, sharding flat giant directories."""
        if relative.parent.parts in shard_dirs:
            shard = hashlib.sha256(relative.name.encode("utf-8")).hexdigest()[:2]
            return destination / relative.parent / shard / relative.name
        return destination / relative

    for index, relative in enumerate(files, start=1):
        src = source / relative
        dst = destination_path(relative)
        key = str(relative)

        # A recorded entry only exists after a successful copy whose sha256 was
        # computed, so trusting it avoids a per-file stat pair on the NAS.
        if key in recorded and not args.rehash:
            verified += 1
            continue

        size = src.stat().st_size
        to_copy += 1
        pending_bytes += size
        if not args.execute:
            continue
        try:
            digest = copy_verified(src, dst)
        except OSError as error:
            failed.append(f"{relative}: {error}")
            continue
        entry = {"path": key, "bytes": size, "sha256": digest}
        if str(dst) != str(destination / relative):
            entry["destination"] = str(dst.relative_to(destination))
        record(entry)
        if index % 2000 == 0:
            print(f"  ... {index}/{len(files)} files, {len(recorded)} recorded", flush=True)

    journal.flush()
    journal.close()

    print(f"source      : {source}")
    print(f"destination : {destination}")
    print(f"files       : {len(files)} total, {verified} verified, "
          f"{to_copy} to copy, {len(failed)} failed")
    print(f"pending     : {pending_bytes:,} bytes")

    if not args.execute:
        print("\ndry-run: pass --execute to transfer")
        return 0
    if failed:
        for line in failed[:20]:
            print(f"  FAILED {line}", file=sys.stderr)
        write_manifest(manifest_path, name=args.name, source=source,
                       destination=destination, recorded=recorded)
        return 3

    write_manifest(manifest_path, name=args.name, source=source,
                   destination=destination, recorded=recorded)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(f"\nmanifest: {manifest_path} ({payload['file_count']} files, {payload['bytes']:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
