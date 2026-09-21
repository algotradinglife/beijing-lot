#!/usr/bin/env python3
"""Compress a settlement snapshot that a passing replay no longer needs as a live database.

A snapshot is the evidence a replay derives its owed issues from, so it cannot simply be
deleted once used — but it does not have to stay a 3.3 GB database either. Compression is
lossless and the archive keeps the snapshot's identity: the sidecar manifest records the
snapshot's content hash, which is what the anchor evidence was recorded against, so a later
prune still resolves the anchor and a later replay can still be run from the archive.

The precondition is deliberate: the replay report for that batch must exist and must record a
passing verification, and it must be given explicitly. Nothing is removed until the archive has
been read back, decompressed and confirmed to hash to the snapshot's own identity.

Default is a dry run; `--apply` performs the compression and removes the original.
"""
import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ARCHIVE_SUFFIX = ".zst"
MANIFEST_SUFFIX = ".manifest.json"
COMPRESS_LEVEL = "-3"


def file_identity(path: Path) -> tuple[str, int]:
    """Content hash and byte length of `path`."""
    digest = hashlib.sha256()
    length = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
            length += len(chunk)
    return digest.hexdigest(), length


@contextlib.contextmanager
def materialize_snapshot(path: Path):
    """Yield a usable database path for `path`, decompressing an archive to a temporary file.

    An archived snapshot is still the evidence a replay runs against; the decompression is
    transient so the point of archiving — not keeping 3.3 GB on disk — is preserved.
    """
    path = Path(path)
    if path.suffix != ARCHIVE_SUFFIX:
        yield path
        return
    handle, temporary = tempfile.mkstemp(suffix=".sqlite", prefix="snapshot-")
    try:
        # Streamed into the file mkstemp already created: zstd -o refuses to overwrite, and
        # capturing the decompressed bytes would need the snapshot to fit in memory.
        reader = subprocess.Popen(["zstd", "-d", "-q", "-c", str(path)], stdout=subprocess.PIPE)
        with os.fdopen(handle, "wb") as sink:
            for chunk in iter(lambda: reader.stdout.read(1 << 22), b""):
                sink.write(chunk)
        reader.stdout.close()
        if reader.wait() != 0:
            raise ValueError(f"the archive could not be decompressed: {path}")
        yield Path(temporary)
    finally:
        Path(temporary).unlink(missing_ok=True)


def archive_path(snapshot: Path) -> Path:
    """Where the archive for `snapshot` lives, beside it so the pair moves together."""
    return Path(str(snapshot) + ARCHIVE_SUFFIX)


def manifest_path(snapshot: Path) -> Path:
    """Where the archive's sidecar manifest lives."""
    return Path(str(snapshot) + MANIFEST_SUFFIX)


def verified_precondition(report: Path, snapshot: Path) -> dict:
    """Read the replay report and require that it passes *for this snapshot*.

    A report about a different snapshot is not a reason to compress this one: the archive is
    only safe to make when the replay that justifies it actually ran against these bytes.
    """
    report = Path(report)
    if not report.is_file():
        raise ValueError(f"the replay report does not exist: {report}")
    document = json.loads(report.read_text(encoding="utf-8"))
    if (document.get("conclusion") or {}).get("verified") is not True:
        raise ValueError(f"the replay report does not record a passing verification: {report}")
    recorded = (document.get("backup") or {}).get("path")
    if not recorded:
        raise ValueError(f"the replay report names no backup: {report}")
    if Path(recorded).resolve() != Path(snapshot).resolve():
        raise ValueError(f"the replay report verified a different backup ({recorded}), so it "
                         f"does not justify compressing {Path(snapshot).name}")
    return document


def compress(snapshot: Path, *, report: Path, apply: bool) -> dict:
    """Compress `snapshot`, prove the archive round-trips, then remove the original.

    The archive is written beside the snapshot and only replaces it once it has been
    decompressed and hashed back to the same identity, so an interrupted run leaves the
    snapshot in place.
    """
    snapshot = Path(snapshot)
    if not snapshot.is_file():
        raise ValueError(f"not a snapshot: {snapshot}")
    document = verified_precondition(report, snapshot)
    archive, manifest = archive_path(snapshot), manifest_path(snapshot)
    if archive.exists() or manifest.exists():
        raise ValueError(f"an archive already exists for {snapshot.name}")
    snapshot_sha256, snapshot_bytes = file_identity(snapshot)
    result = {"snapshot": str(snapshot), "snapshot_sha256": snapshot_sha256,
              "snapshot_bytes": snapshot_bytes, "archive": str(archive),
              "report": str(report), "report_kind": document.get("kind"),
              "applied": bool(apply)}
    if not apply:
        result["status"] = "dry_run"
        return result
    subprocess.run(["zstd", COMPRESS_LEVEL, "-q", "-T0", "-o", str(archive), str(snapshot)],
                   check=True)
    archive_sha256, archive_bytes = file_identity(archive)
    # Prove the archive is the snapshot before the original goes: a compression that cannot be
    # read back is not evidence, and the one thing that must not happen is a silent loss.
    # Streamed, not captured: the snapshot is 3.3 GB and the check must not depend on it
    # fitting in memory.
    reader = subprocess.Popen(["zstd", "-d", "-q", "-c", str(archive)],
                              stdout=subprocess.PIPE)
    digest = hashlib.sha256()
    try:
        for chunk in iter(lambda: reader.stdout.read(1 << 22), b""):
            digest.update(chunk)
    finally:
        reader.stdout.close()
    if reader.wait() != 0 or digest.hexdigest() != snapshot_sha256:
        archive.unlink()
        raise ValueError("the archive does not decompress to the snapshot; nothing removed")
    manifest.write_text(json.dumps(
        {"snapshot": snapshot.name, "snapshot_sha256": snapshot_sha256,
         "snapshot_bytes": snapshot_bytes, "archive": archive.name,
         "archive_sha256": archive_sha256, "archive_bytes": archive_bytes,
         "replay_report": str(report), "replay_report_sha256": file_identity(report)[0],
         "archived_at": datetime.now(timezone.utc).isoformat(),
         "note": "The snapshot was compressed after its replay passed. The anchor evidence "
                 "records the snapshot's content hash; this manifest ties that hash to the "
                 "archive that now holds those bytes."},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    snapshot.unlink()
    result.update({"status": "archived", "archive_sha256": archive_sha256,
                   "archive_bytes": archive_bytes, "manifest": str(manifest),
                   "ratio": round(snapshot_bytes / archive_bytes, 2) if archive_bytes else None})
    return result


def main(argv=None):
    """Report what would be archived; compress and remove only with --apply."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path,
                        help="the passing replay report that justifies compressing it")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(compress(args.snapshot, report=args.report, apply=args.apply),
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
