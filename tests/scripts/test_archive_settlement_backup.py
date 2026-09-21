"""Contract examples for compacting a snapshot whose replay has passed. No network."""
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.archive_settlement_backup import (archive_path, compress,  # noqa: E402
                                               file_identity, materialize_snapshot,
                                               verified_precondition)

pytestmark = pytest.mark.skipif(shutil.which("zstd") is None, reason="zstd is not installed")


def snapshot(tmp_path: Path) -> Path:
    """A small database with a table worth compressing, standing in for a real snapshot."""
    path = tmp_path / "before.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE observation (observation_id INTEGER, score TEXT)")
    connection.executemany("INSERT INTO observation VALUES (?,?)",
                           [(index, "3-1") for index in range(20000)])
    connection.commit()
    connection.close()
    return path


def report(tmp_path: Path, backup: Path, *, verified: bool = True) -> Path:
    """A replay report in the shape the verifiers write."""
    path = tmp_path / "verification.json"
    path.write_text(json.dumps({"conclusion": {"verified": verified},
                                "backup": {"path": str(backup),
                                           "sha256": (file_identity(backup)[0]
                                                      if Path(backup).is_file() else "absent")}}),
                    encoding="utf-8")
    return path


def test_requires_a_report_that_passed(tmp_path: Path) -> None:
    """A failing replay is not a reason to remove the snapshot it ran against."""
    target, document = snapshot(tmp_path), report(tmp_path, tmp_path / "before.sqlite",
                                                  verified=False)
    with pytest.raises(ValueError, match="passing verification"):
        compress(target, report=document, apply=True)
    assert target.exists()


def test_requires_a_report_about_this_snapshot(tmp_path: Path) -> None:
    """A report about another snapshot does not justify compressing this one."""
    target = snapshot(tmp_path)
    with pytest.raises(ValueError, match="different backup"):
        verified_precondition(report(tmp_path, tmp_path / "somewhere-else.sqlite"), target)


def test_missing_report_is_refused(tmp_path: Path) -> None:
    """No report means no evidence that the snapshot has been used."""
    with pytest.raises(ValueError, match="does not exist"):
        compress(snapshot(tmp_path), report=tmp_path / "absent.json", apply=True)


def test_dry_run_reports_without_touching_anything(tmp_path: Path) -> None:
    """The default is a report: the snapshot stays a database."""
    target = snapshot(tmp_path)
    result = compress(target, report=report(tmp_path, target), apply=False)
    assert result["status"] == "dry_run"
    assert result.get("ratio") is None
    assert target.exists()
    assert not archive_path(target).exists()


def test_archives_and_removes_only_after_a_verified_round_trip(tmp_path: Path) -> None:
    """The snapshot goes only once the archive has been read back and confirmed."""
    target = snapshot(tmp_path)
    result = compress(target, report=report(tmp_path, target), apply=True)
    assert result["status"] == "archived"
    assert not target.exists()
    archive = archive_path(target)
    assert archive.exists() and result["archive_bytes"] < result["snapshot_bytes"]
    manifest = json.loads((tmp_path / "before.sqlite.manifest.json").read_text(encoding="utf-8"))
    # The manifest keeps the snapshot's own identity, which is what anchors were recorded
    # against, so a later prune still resolves the anchor.
    assert manifest["snapshot_sha256"] == result["snapshot_sha256"]
    assert manifest["archive_sha256"] == result["archive_sha256"]


def test_refuses_to_archive_twice(tmp_path: Path) -> None:
    """A second archive would silently discard the first one's manifest."""
    target = snapshot(tmp_path)
    compress(target, report=report(tmp_path, target), apply=True)
    target.write_bytes(b"rebuilt")
    with pytest.raises(ValueError, match="already exists"):
        compress(target, report=report(tmp_path, target), apply=True)


def test_a_corrupt_leftover_archive_leaves_the_snapshot_in_place(tmp_path: Path) -> None:
    """An interrupted attempt is adopted only if it really holds the snapshot."""
    target = snapshot(tmp_path)
    archive_path(target).write_bytes(b"not a zstd stream")
    with pytest.raises(ValueError):
        compress(target, report=report(tmp_path, target), apply=True)
    assert target.exists()
    assert not (tmp_path / "before.sqlite.manifest.json").exists()


def test_an_interrupted_archive_is_adopted(tmp_path: Path) -> None:
    """An archive left without its manifest is completed, not refused forever."""
    target = snapshot(tmp_path)
    archive = archive_path(target)
    subprocess.run(["zstd", "-q", "-o", str(archive), str(target)], check=True)
    result = compress(target, report=report(tmp_path, target), apply=True)
    assert result["status"] == "archived"
    assert not target.exists()
    assert (tmp_path / "before.sqlite.manifest.json").exists()


def test_a_report_without_a_content_hash_is_refused(tmp_path: Path) -> None:
    """A report that does not say which bytes passed cannot authorise compression."""
    target = snapshot(tmp_path)
    path = tmp_path / "verification.json"
    path.write_text(json.dumps({"conclusion": {"verified": True},
                                "backup": {"path": str(target)}}), encoding="utf-8")
    with pytest.raises(ValueError, match="no backup content hash"):
        compress(target, report=path, apply=True)


def test_a_snapshot_replaced_after_verification_is_refused(tmp_path: Path) -> None:
    """A passing report for bytes that are no longer there does not carry over."""
    target = snapshot(tmp_path)
    document = report(tmp_path, target)
    connection = sqlite3.connect(target)
    connection.execute("INSERT INTO observation VALUES (99999, 'rewritten')")
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="not the one the replay verified"):
        compress(target, report=document, apply=True)


def test_materialize_decompresses_and_cleans_up(tmp_path: Path) -> None:
    """An archived snapshot stays usable evidence, without staying on disk."""
    target = snapshot(tmp_path)
    compress(target, report=report(tmp_path, target), apply=True)
    with materialize_snapshot(archive_path(target)) as usable:
        assert usable.exists() and usable != archive_path(target)
        connection = sqlite3.connect(f"file:{usable}?mode=ro", uri=True)
        assert connection.execute("SELECT COUNT(*) FROM observation").fetchone()[0] == 20000
        connection.close()
        temporary = usable
    assert not temporary.exists()


def test_materialize_passes_a_plain_snapshot_through(tmp_path: Path) -> None:
    """An uncompressed snapshot is already usable."""
    target = snapshot(tmp_path)
    with materialize_snapshot(target) as usable:
        assert usable == target
    assert target.exists()
