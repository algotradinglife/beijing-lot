"""Contract examples for pruning settlement backups. No network."""
import json
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
                                              file_identity, prune_backups,
                                              replay_anchors)


def snapshot(path: Path, *, at: int, observations: bool = True) -> Path:
    """A file that looks like a pre-write snapshot, ordered by mtime.

    Each one carries its own name as a row so distinct snapshots hash distinctly: real
    snapshots are 3.3 GB databases with different contents, and a fixture of byte-identical
    files would let a content-identity match succeed for the wrong reason.
    """
    connection = sqlite3.connect(path)
    if observations:
        connection.execute("CREATE TABLE observation (observation_id TEXT)")
        connection.execute("INSERT INTO observation VALUES (?)", (path.name,))
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


def test_reads_anchors_from_the_release_the_registry_and_the_receipts(tmp_path: Path) -> None:
    """Every place a batch's anchor is recorded is read, with its identity when stored."""
    release = snapshot(tmp_path / "release.sqlite", at=1, observations=False)
    connection = sqlite3.connect(release)
    connection.execute("CREATE TABLE issue_recovery_batch (backup_path TEXT)")
    connection.execute("INSERT INTO issue_recovery_batch VALUES (?)",
                       ("/somewhere/backups/from-table.sqlite",))
    connection.execute("CREATE TABLE issue_addition_anchor (batch_id TEXT, backup_path TEXT, "
                       "backup_sha256 TEXT, backup_bytes INTEGER, recorded_at TEXT)")
    connection.execute("INSERT INTO issue_addition_anchor VALUES (?,?,?,?,?)",
                       ("b", "/somewhere/backups/from-anchor.sqlite", "abc", 12, "t"))
    connection.commit()
    connection.close()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"corrections": [{"backup": "/somewhere/from-registry.sqlite"}],
                                    "retired_anchors": ["gone.sqlite"]}), encoding="utf-8")
    bundles = tmp_path / "updates" / "bundle-1"
    bundles.mkdir(parents=True)
    (bundles / "applied.json").write_text(
        json.dumps({"status": "added", "backup": "/somewhere/from-receipt.sqlite",
                    "backup_sha256": "def"}), encoding="utf-8")
    claims, retired = replay_anchors(release, registry, tmp_path / "updates")
    assert {Path(claim["path"]).name for claim in claims} == {
        "from-table.sqlite", "from-anchor.sqlite", "from-registry.sqlite", "from-receipt.sqlite"}
    assert {claim["sha256"] for claim in claims if claim["sha256"]} == {"abc", "def"}
    assert retired == {"gone.sqlite"}


def test_refuses_when_an_anchor_receipt_cannot_be_read(tmp_path: Path) -> None:
    """Evidence that cannot be read means a dependency it cannot rule out."""
    release = snapshot(tmp_path / "release.sqlite", at=1, observations=False)
    bundles = tmp_path / "updates" / "bundle-1"
    bundles.mkdir(parents=True)
    (bundles / "applied.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be read"):
        replay_anchors(release, None, tmp_path / "updates")


def test_refuses_when_an_applied_receipt_names_no_anchor(tmp_path: Path) -> None:
    """An applied addition with no anchor is exactly the state retention must not act on."""
    release = snapshot(tmp_path / "release.sqlite", at=1, observations=False)
    bundles = tmp_path / "updates" / "bundle-1"
    bundles.mkdir(parents=True)
    (bundles / "applied.json").write_text('{"status": "added"}', encoding="utf-8")
    with pytest.raises(ValueError, match="names no anchor"):
        replay_anchors(release, None, tmp_path / "updates")


def test_matches_anchors_by_content_not_by_name(tmp_path: Path) -> None:
    """Renaming an anchored snapshot must not make it disposable."""
    root = directory(tmp_path, "renamed.sqlite", "b.sqlite", "c.sqlite")
    sha256, _ = file_identity(root / "renamed.sqlite")
    result = prune_backups(root, keep=1, apply=True,
                           protect=[{"path": "/elsewhere/original.sqlite", "sha256": sha256}])
    assert result["anchored"] == ["renamed.sqlite"]
    assert sorted(path.name for path in root.iterdir()) == ["c.sqlite", "renamed.sqlite"]


def test_refuses_when_a_recorded_anchor_is_missing(tmp_path: Path) -> None:
    """A snapshot that a batch names but that is absent stops the pass."""
    root = directory(tmp_path, "a.sqlite", "b.sqlite")
    with pytest.raises(ValueError, match="missing from this directory"):
        prune_backups(root, keep=1, apply=True, protect=["vanished.sqlite"])


def test_allows_a_registry_retired_anchor(tmp_path: Path) -> None:
    """An anchor recorded as retired is a documented absence, not an unresolvable one."""
    root = directory(tmp_path, "a.sqlite", "b.sqlite")
    result = prune_backups(root, keep=1, apply=True, protect=["vanished.sqlite"],
                           retired={"vanished.sqlite"})
    assert result["remove"] == ["a.sqlite"]


def test_excludes_the_release_by_filesystem_identity(tmp_path: Path) -> None:
    """A release reached through another name is still the release."""
    root = directory(tmp_path, "snapshot.sqlite", "b.sqlite")
    alias = tmp_path / "current.sqlite"
    alias.symlink_to(root / "snapshot.sqlite")
    with pytest.raises(ValueError, match="release database sits"):
        prune_backups(root, keep=1, apply=True, release=alias)


def test_refuses_a_symlinked_entry(tmp_path: Path) -> None:
    """An entry that is a link could point anywhere, including at the release."""
    root = directory(tmp_path, "a.sqlite")
    (root / "link.sqlite").symlink_to(tmp_path / "elsewhere.sqlite")
    with pytest.raises(ValueError, match="symlinked entry"):
        prune_backups(root, keep=1, apply=True)


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
