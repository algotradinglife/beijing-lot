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
