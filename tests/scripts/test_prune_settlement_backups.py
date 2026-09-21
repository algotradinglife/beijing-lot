"""Contract examples for pruning settlement backups. No network."""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (str(ROOT), str(ROOT / "tests")):
    if path not in sys.path:
        sys.path.insert(0, path)

from scripts.prune_settlement_backups import (authorize_directory,  # noqa: E402
                                              prune_backups,
                                              replay_protected_backups)


def snapshot(path: Path, *, at: int, observations: bool = True) -> Path:
    """A file that looks like a pre-write snapshot, ordered by mtime."""
    connection = sqlite3.connect(path)
    if observations:
        connection.execute("CREATE TABLE observation (observation_id TEXT)")
    connection.commit()
    connection.close()
    os.utime(path, (at, at))
    return path


def directory(tmp_path: Path, *names: str) -> Path:
    """The real layout is a per-release directory inside a `backups` parent."""
    root = tmp_path / "backups" / "release"
    root.mkdir(parents=True)
    for index, name in enumerate(names):
        snapshot(root / name, at=1_700_000_000 + index * 60)
    return root


def test_keeps_the_most_recent_and_removes_the_rest(tmp_path: Path) -> None:
    """The unprotected remainder thins to the retention count."""
    root = directory(tmp_path, "a.sqlite", "b.sqlite", "c.sqlite")
    result = prune_backups(root, keep=1, apply=True)
    assert result["keep"] == ["c.sqlite"]
    assert result["remove"] == ["a.sqlite", "b.sqlite"]
    assert [path.name for path in root.iterdir()] == ["c.sqlite"]


def test_never_removes_a_snapshot_a_batch_names(tmp_path: Path) -> None:
    """A replay needs its own batch's snapshot, so rank alone is not permission to delete."""
    root = directory(tmp_path, "anchor.sqlite", "b.sqlite", "c.sqlite", "d.sqlite")
    result = prune_backups(root, keep=1, apply=True, protect={"anchor.sqlite"})
    assert result["anchored"] == ["anchor.sqlite"]
    assert [path.name for path in root.iterdir()] == ["anchor.sqlite", "d.sqlite"]


def test_reads_anchors_from_the_release_and_the_bundle_receipts(tmp_path: Path) -> None:
    """The anchor is recorded in the release's batch tables and in each applied bundle."""
    release = snapshot(tmp_path / "release.sqlite", at=1, observations=False)
    connection = sqlite3.connect(release)
    connection.execute("CREATE TABLE issue_recovery_batch (backup_path TEXT)")
    connection.execute("INSERT INTO issue_recovery_batch VALUES (?)",
                       ("/somewhere/backups/from-table.sqlite",))
    connection.commit()
    connection.close()
    bundles = tmp_path / "updates" / "bundle-1"
    bundles.mkdir(parents=True)
    (bundles / "applied.json").write_text(
        '{"backup": "/somewhere/backups/from-receipt.sqlite"}', encoding="utf-8")
    protected = replay_protected_backups(release, bundles_root=tmp_path / "updates")
    assert protected == {"from-table.sqlite", "from-receipt.sqlite"}


def test_refuses_a_symlinked_directory(tmp_path: Path) -> None:
    """A symlink could point the prune at anything."""
    root = directory(tmp_path, "a.sqlite")
    link = tmp_path / "link"
    link.symlink_to(root)
    with pytest.raises(ValueError, match="symlink"):
        authorize_directory(link, None)


def test_refuses_a_directory_that_is_not_under_backups(tmp_path: Path) -> None:
    """A release directory is not a backup directory."""
    other = tmp_path / "somewhere"
    other.mkdir()
    with pytest.raises(ValueError, match="backups parent"):
        authorize_directory(other, None)


def test_refuses_when_the_release_sits_in_the_directory(tmp_path: Path) -> None:
    """The release must never be treated as a disposable snapshot."""
    root = directory(tmp_path, "release.sqlite")
    with pytest.raises(ValueError, match="release database sits"):
        prune_backups(root, keep=1, apply=True, release=root / "release.sqlite")


def test_refuses_an_unrecognised_sqlite_file(tmp_path: Path) -> None:
    """A file that is not a snapshot stops the run instead of being deleted."""
    root = directory(tmp_path, "a.sqlite")
    (root / "not-ours.sqlite").write_bytes(b"not a database")
    with pytest.raises(ValueError, match="not settlement snapshots"):
        prune_backups(root, keep=1, apply=True)
    assert (root / "not-ours.sqlite").exists()


def test_dry_run_reports_without_deleting(tmp_path: Path) -> None:
    """The default is a report; deletion is asked for."""
    root = directory(tmp_path, "a.sqlite", "b.sqlite")
    result = prune_backups(root, keep=1, apply=False)
    assert result["removed"] is False
    assert result["remove"] == ["a.sqlite"]
    assert len(list(root.iterdir())) == 2


def test_rejects_a_non_positive_keep(tmp_path: Path) -> None:
    """A zero retention count would delete every snapshot."""
    root = directory(tmp_path, "a.sqlite")
    with pytest.raises(ValueError, match="positive integer"):
        prune_backups(root, keep=0, apply=True)


def test_rejects_a_directory_without_snapshots(tmp_path: Path) -> None:
    """An empty backup directory is a mistake, not a no-op."""
    root = tmp_path / "backups" / "release"
    root.mkdir(parents=True)
    with pytest.raises(ValueError, match=r"no \*\.sqlite snapshots"):
        prune_backups(root, keep=1, apply=True)
