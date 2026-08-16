"""Focused transaction and retry tests for the #208 package publisher."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.run_bj208_policy as runner


def _payload(path: Path, value: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "payload.txt").write_text(value, encoding="utf-8")


def test_second_rename_failure_restores_last_good(tmp_path, monkeypatch):
    output = tmp_path / "issue-208"
    staging = tmp_path / "staging"
    _payload(output, "old")
    _payload(staging, "new")
    real_replace = runner.os.replace
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second rename failure")
        return real_replace(source, target)

    monkeypatch.setattr(runner.os, "replace", fail_second)
    with pytest.raises(OSError, match="second rename"):
        runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"

    # The same complete staging tree can be retried immediately.  The old
    # package remains available until the retry has installed and committed
    # the new package.
    backup = runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    runner._commit_publish(output, backup)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"


def test_first_parent_fsync_failure_restores_visible_last_good(
    tmp_path, monkeypatch
):
    output = tmp_path / "issue-208"
    staging = tmp_path / "staging"
    _payload(output, "old")
    _payload(staging, "new")
    real_fsync = runner._fsync_directory
    calls = 0

    def fail_first_parent_fsync(path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected first parent fsync failure")
        return real_fsync(path)

    monkeypatch.setattr(runner, "_fsync_directory", fail_first_parent_fsync)
    with pytest.raises(OSError, match="first parent fsync"):
        runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert (staging / "payload.txt").read_text(encoding="utf-8") == "new"

    backup = runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    runner._commit_publish(output, backup)


def test_second_parent_fsync_failure_restores_last_good_and_retry(
    tmp_path, monkeypatch
):
    output = tmp_path / "issue-208"
    staging = tmp_path / "staging"
    _payload(output, "old")
    _payload(staging, "new")
    real_fsync = runner._fsync_directory
    calls = 0

    def fail_second_parent_fsync(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second parent fsync failure")
        return real_fsync(path)

    monkeypatch.setattr(runner, "_fsync_directory", fail_second_parent_fsync)
    with pytest.raises(OSError, match="second parent fsync"):
        runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert (staging / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))

    backup = runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    runner._commit_publish(output, backup)


def test_backup_cleanup_transient_fault_retries_without_rollback(
    tmp_path, monkeypatch
):
    output = tmp_path / "issue-208"
    staging = tmp_path / "staging"
    _payload(output, "old")
    _payload(staging, "new")
    backup = runner._atomic_publish(staging, output)
    real_rmtree = runner.shutil.rmtree
    calls = 0

    def fail_once(path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected backup cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(runner.shutil, "rmtree", fail_once)
    runner._commit_publish(output, backup)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))


def test_cleanup_parent_fsync_failure_preserves_verified_new_and_retry(
    tmp_path, monkeypatch
):
    """A cleanup durability error must not delete both old and new packages."""
    output = tmp_path / "issue-208"
    _payload(output, "old")

    def build(staging, *, published_output):
        _payload(staging, "new")

    monkeypatch.setattr(runner, "_run_stages", build)
    monkeypatch.setattr(runner, "_write_metadata", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "_write_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "verify_package", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, "run_tamper_suite", lambda *args, **kwargs: [])
    real_fsync = runner._fsync_directory
    injected = False

    def fail_after_backup_cleanup(path):
        nonlocal injected
        backup_exists = bool(list(tmp_path.glob(".issue-208.backup-*")))
        new_visible = (
            output.exists()
            and (output / "payload.txt").read_text(encoding="utf-8") == "new"
        )
        if not injected and new_visible and not backup_exists:
            injected = True
            raise OSError("injected cleanup parent fsync failure")
        return real_fsync(path)

    monkeypatch.setattr(runner, "_fsync_directory", fail_after_backup_cleanup)
    with pytest.raises(OSError, match="cleanup parent fsync"):
        runner.run(output)

    assert injected
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))

    # The verified package remains the last-good input to an immediate retry.
    monkeypatch.setattr(runner, "_fsync_directory", real_fsync)
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))


def test_fsync_tree_flushes_nested_directories_bottom_up(tmp_path, monkeypatch):
    root = tmp_path / "package"
    nested = root / "models" / "folds"
    _payload(nested, "model")
    seen: list[Path] = []

    monkeypatch.setattr(runner, "_fsync_file", lambda path: None)
    monkeypatch.setattr(runner, "_fsync_directory", lambda path: seen.append(path))
    runner._fsync_tree(root)

    assert seen[-1] == root
    assert set(seen) == {root, root / "models", nested}
    assert seen.index(nested) < seen.index(root / "models") < seen.index(root)


def test_post_publish_failure_rolls_back(tmp_path):
    output = tmp_path / "issue-208"
    staging = tmp_path / "staging"
    _payload(output, "old")
    _payload(staging, "new")
    backup = runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    runner._rollback_publish(output, backup)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"


def test_commit_removes_backup_and_keeps_new(tmp_path):
    output = tmp_path / "issue-208"
    staging = tmp_path / "staging"
    _payload(output, "old")
    _payload(staging, "new")
    backup = runner._atomic_publish(staging, output)
    assert backup is not None and backup.exists()
    runner._commit_publish(output, backup)
    assert not backup.exists()
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"


def test_keyboard_interrupt_during_build_preserves_output(tmp_path, monkeypatch):
    output = tmp_path / "issue-208"
    _payload(output, "old")

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_run_stages", interrupt)
    with pytest.raises(KeyboardInterrupt):
        runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.staging-*"))


def test_alternate_output_uses_canonical_handoff_before_scientific_stages(
    tmp_path, monkeypatch
):
    seen = {}

    def inspect_boundary(staging, *, published_output):
        seen["published_output"] = published_output
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_run_stages", inspect_boundary)
    with pytest.raises(KeyboardInterrupt):
        runner.run(tmp_path / "independent-audit-package")
    assert seen["published_output"] == runner.CANONICAL_PUBLISHED_OUTPUT
    assert not list(tmp_path.glob(".independent-audit-package.staging-*"))
