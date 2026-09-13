"""Remove retired workspace copies only after hash, inventory and byte verification.

Single-writer maintenance command. Collectors must already use persistent paths.
Archives are never removed. A persistent journal makes completed removals resumable.
"""
import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.market_storage import _publish_json


def verify_remaining_source_bytes(archive_path, source, remaining):
    """Verify surviving members after an interrupted, previously verified removal.

    Caller verifies archive SHA and that remaining names are a subset. Directory
    mtimes may change during removal; file bytes and link targets must not change.
    This function is read-only and raises ValueError on any mismatch.
    """
    with tarfile.open(archive_path, mode="r:*") as archive:
        for name in remaining:
            member = archive.getmember(name)
            path = source.parent / name
            if member.isdir():
                if not path.is_dir() or path.is_symlink():
                    raise ValueError("remaining directory type changed")
            elif member.issym():
                if not path.is_symlink() or os.readlink(path) != member.linkname:
                    raise ValueError("remaining symbolic link changed")
            elif member.isfile() or member.islnk():
                if not path.is_file() or path.is_symlink():
                    raise ValueError("remaining file type changed")
                with archive.extractfile(member) as captured, path.open("rb") as actual:
                    if hashlib.file_digest(captured, "sha256").digest() != hashlib.file_digest(actual, "sha256").digest():
                        raise ValueError("remaining file bytes changed")
            else:
                raise ValueError("unsupported remaining member type")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "data-root", "mountpoint"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--catalog", action="append", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve(strict=True)
    root, mount = Path(args.data_root).resolve(strict=True), Path(args.mountpoint).resolve(strict=True)
    if not mount.is_mount() or not root.is_relative_to(mount):
        raise ValueError("persistent volume must be mounted")
    allowed = {workspace / "data" / kind / domain for kind in ("raw", "derived")
               for domain in ("fundamentals_411", "fundamentals_417")}
    allowed.update({workspace / "data/derived/nowscore_only", workspace / "data/raw/settlement_supplements"})
    journal_path = root / "registry/source-retirement.json"
    lock_path = root / "runtime/state/source-retirement.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        journal = json.loads(journal_path.read_text()) if journal_path.exists() else {"schema": "beijing_lot_source_retirement_v1", "entries": {}}
        for catalog_name in args.catalog:
            catalog_path = (root / catalog_name).resolve(strict=True)
            if not catalog_path.is_relative_to(root):
                raise ValueError("catalog must be inside persistent root")
            catalog = json.loads(catalog_path.read_text())
            for row in catalog["entries"]:
                source = Path(row["source"])
                if not source.is_absolute() or source.parent.resolve() not in allowed:
                    raise ValueError(f"source outside approved workspace data roots: {source}")
                archive = (root / row["archive"]).resolve(strict=True)
                if not archive.is_relative_to(root):
                    raise ValueError("archive outside persistent root")
                with archive.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != row["archive_sha256"]:
                    raise ValueError(f"archive hash mismatch: {archive}")
                previous = journal["entries"].get(str(source), {})
                if not source.exists() and not source.is_symlink():
                    if previous.get("archive_sha256") != digest or previous.get("state") not in ("VERIFIED_READY_FOR_REMOVAL", "REMOVED"):
                        raise ValueError(f"source missing without verified retirement journal: {source}")
                else:
                    actual = {source.name}
                    if source.is_dir() and not source.is_symlink():
                        for directory, directories, files in os.walk(source, followlinks=False):
                            for name in directories + files:
                                actual.add(str((Path(directory) / name).relative_to(source.parent)))
                    with tarfile.open(archive, mode="r|*", stream=True) as captured:
                        members = {member.name.rstrip("/") for member in captured}
                    recovering = previous.get("state") == "VERIFIED_READY_FOR_REMOVAL" and previous.get("archive_sha256") == digest
                    if recovering and actual <= members:
                        verify_remaining_source_bytes(archive, source, actual)
                    elif members != actual:
                        raise ValueError(f"archive/source inventory mismatch: {source}; extra={len(actual-members)}, missing={len(members-actual)}")
                    else:
                        subprocess.run(["tar", "--zstd", "-df", str(archive), "-C", str(source.parent)], check=True)
                    journal["entries"][str(source)] = {"archive": row["archive"], "archive_sha256": digest,
                        "state": "VERIFIED_READY_FOR_REMOVAL", "member_count": len(members)}
                    _publish_json(journal_path, journal)
                    if source.is_dir() and not source.is_symlink():
                        shutil.rmtree(source)
                    else:
                        source.unlink()
                journal["entries"][str(source)].update(state="REMOVED", removed_at_utc=datetime.now(timezone.utc).isoformat())
                _publish_json(journal_path, journal)
                row["source_removed"] = True
                row["state"] = "ARCHIVE_VERIFIED_SOURCE_REMOVED"
                _publish_json(catalog_path, catalog)
                print("RETIRED " + str(source.relative_to(workspace)), flush=True)
        print("Requested catalogs retired; archives retained", flush=True)
