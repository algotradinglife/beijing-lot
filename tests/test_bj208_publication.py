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


# ==== EV E1 production-entry regressions (finalize REJECT 7302d644) ====
# EV fault: post-publication verify fails, then the FIRST rollback parent
# fsync fails; the outer BaseException handler must NOT re-enter rollback
# with the stale (already-consumed) backup handle and delete the restored
# last-good package.


def _run_probe_harness(tmp_path, monkeypatch, *, post_verify_failures):
    """Drive run() to publication with a minimal payload, returning the
    harness state so fault injections can target the rollback boundary.
    Does NOT replace _fsync_directory — each test wraps it with its own
    counting + fault injection to avoid ordering conflicts.

    The final-output verify fails on the FIRST call only; subsequent calls
    (e.g. an immediate retry) verify cleanly so retry success is observable.
    """
    output = tmp_path / "issue-208"
    _payload(output, "old")

    state = {
        "post_verify_failed": False,
        "output_verify_calls": 0,
        "rollback_fsync_calls": 0,
        "cleanup_fsync_calls": 0,
    }

    def build(staging, *, published_output):
        _payload(staging, "new")

    def fake_verify(pkg, *args, **kwargs):
        pkg_path = Path(pkg)
        if pkg_path == output:
            state["output_verify_calls"] += 1
            if state["output_verify_calls"] == 1:
                state["post_verify_failed"] = True
                return post_verify_failures
        return []

    monkeypatch.setattr(runner, "_run_stages", build)
    monkeypatch.setattr(runner, "_write_metadata", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_write_manifest", lambda *a, **k: None)
    monkeypatch.setattr(runner, "verify_package", fake_verify)
    monkeypatch.setattr(runner, "run_tamper_suite", lambda *a, **k: [])
    return output, state


def _rollback_fsync_window(tmp_path, state):
    """Return True when the fsync call is inside the rollback boundary:
    post-verify failed, the backup has been consumed back to output, and
    the failed (new) copy exists or was just cleaned.  Updates counters."""
    backup_exists = bool(list(tmp_path.glob(".issue-208.backup-*")))
    failed_exists = bool(list(tmp_path.glob(".issue-208.failed-*")))
    if not state["post_verify_failed"] or backup_exists:
        return False
    if failed_exists:
        state["rollback_fsync_calls"] += 1
        return True
    if state["rollback_fsync_calls"] >= 1:
        state["cleanup_fsync_calls"] += 1
        return True
    return False


def test_run_post_verify_failure_rollback_parent_fsync_fault_preserves_last_good(
    tmp_path, monkeypatch
):
    """EV E1 exact production probe: third (final-output) verify fails, then
    the FIRST rollback parent-fsync fails.  The restored old last-good must
    stay visible; the outer handler must not delete it a second time."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_fsync = runner._fsync_directory
    injected = {"n": 0}

    def fail_first_rollback_fsync(path):
        if injected["n"] == 0 and _rollback_fsync_window(tmp_path, state):
            injected["n"] += 1
            raise OSError("injected rollback parent fsync failure")
        return real_fsync(path)

    monkeypatch.setattr(runner, "_fsync_directory", fail_first_rollback_fsync)
    with pytest.raises(runner.VerifyError, match="post-publication verification"):
        runner.run(output)

    # The restored old package is the visible canonical output.  A second
    # rollback (the old EV failure mode) would have moved it to .failed-*
    # and deleted it; it must still be present.
    assert injected["n"] == 1
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    # The failed new copy was cleaned up; the restored last-good remains.
    assert not list(tmp_path.glob(".issue-208.failed-*"))

    # Immediate retry is safe: the visible old package is the input to the
    # next publish, and the retry publishes the new package cleanly.
    monkeypatch.setattr(runner, "_fsync_directory", real_fsync)
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))


def test_run_post_verify_failure_rollback_new_to_failed_rename_fault_restores_last_good(
    tmp_path, monkeypatch
):
    """EV E1 exact production probe (v10): the rollback's new→failed rename
    fails.  The semantic-invalid new must NOT keep the canonical path: the
    old last-good is restored by atomic overwrite, the backup handle is
    consumed, and a real production retry converges with no orphan."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_replace = runner.os.replace
    injected = {"n": 0}

    def fail_new_to_failed(source, target):
        nonlocal injected
        source_path = Path(source)
        if (
            state["post_verify_failed"]
            and injected["n"] == 0
            and ".issue-208.failed-" in str(target)
            and source_path == output
        ):
            injected["n"] += 1
            raise OSError("injected rollback new→failed rename failure")
        return real_replace(source, target)

    monkeypatch.setattr(runner.os, "replace", fail_new_to_failed)
    with pytest.raises(runner.VerifyError, match="post-publication verification"):
        runner.run(output)

    # Contract: the unverified new package must never occupy canonical
    # output after the rollback fault.  The old last-good is restored by
    # atomic overwrite and the backup is consumed — no stale backup, no
    # failed copy, no unverified canonical.
    assert injected["n"] == 1
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))

    # Real production retry (no private-helper calls): converges with the
    # new package visible and zero transaction artifacts.
    monkeypatch.setattr(runner.os, "replace", real_replace)
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))
    assert not list(tmp_path.glob(".issue-208.staging-*"))


def test_run_post_verify_failure_rollback_backup_to_output_rename_fault_converges(
    tmp_path, monkeypatch
):
    """Nested-fault matrix (EV §4.2): the rollback's backup→output rename
    fails after new→failed succeeded.  Canonical output is absent
    (fail-closed: no reader can consume an unverified package), the old
    last-good stays intact in the backup, and a real production retry
    restores last-good and converges with no orphan."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_replace = runner.os.replace
    injected = {"n": 0}

    def fail_backup_to_output(source, target):
        nonlocal injected
        if (
            state["post_verify_failed"]
            and injected["n"] == 0
            and ".issue-208.backup-" in str(source)
            and target == output
        ):
            injected["n"] += 1
            raise OSError("injected rollback backup→output rename failure")
        return real_replace(source, target)

    monkeypatch.setattr(runner.os, "replace", fail_backup_to_output)
    with pytest.raises(OSError, match="backup→output rename"):
        runner.run(output)

    # The unverified new was moved to .failed-*; canonical output is absent.
    # The old last-good is intact in the backup — never deleted.
    assert injected["n"] == 1
    assert not output.exists()
    backups = list(tmp_path.glob(".issue-208.backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "payload.txt").read_text(encoding="utf-8") == "old"
    failed = list(tmp_path.glob(".issue-208.failed-*"))
    assert len(failed) == 1
    assert (failed[0] / "payload.txt").read_text(encoding="utf-8") == "new"

    # Real production retry: the run()-start recovery pass restores the old
    # last-good from the backup, then the retry publishes the new package
    # and commits it — zero orphan artifacts remain.
    monkeypatch.setattr(runner.os, "replace", real_replace)
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))
    assert not list(tmp_path.glob(".issue-208.staging-*"))


def test_run_post_verify_failure_rollback_cannot_clear_canonical_fail_closed_and_retry(
    tmp_path, monkeypatch
):
    """EV E1 same-category sweep (v10): the rollback cannot move the
    unverified new aside (new→failed rename fault) AND cannot delete it
    (rmtree fault).  The visible tree is fail-closed with a
    .PUBLICATION_INVALID marker, the old last-good stays intact in the
    backup, and a real production retry (filesystem healed) restores and
    converges with zero orphan artifacts."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_replace = runner.os.replace
    real_rmtree = runner.shutil.rmtree
    injected = {"renames": 0, "rmtrees": 0}

    def fail_new_to_failed(source, target):
        source_path = Path(source)
        if (
            state["post_verify_failed"]
            and injected["renames"] == 0
            and ".issue-208.failed-" in str(target)
            and source_path == output
        ):
            injected["renames"] += 1
            raise OSError("injected rollback new→failed rename failure")
        return real_replace(source, target)

    def fail_rmtree_output(path, *args, **kwargs):
        if (
            state["post_verify_failed"]
            and injected["rmtrees"] == 0
            and Path(path) == output
        ):
            injected["rmtrees"] += 1
            raise OSError("injected rollback output removal failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(runner.os, "replace", fail_new_to_failed)
    monkeypatch.setattr(runner.shutil, "rmtree", fail_rmtree_output)
    with pytest.raises(OSError, match="output removal"):
        runner.run(output)

    # Fail-closed: the canonical path holds a tree explicitly marked
    # .PUBLICATION_INVALID (readers/verifiers must reject it), and the true
    # last-good remains intact in the backup for recovery.
    assert injected["renames"] == 1
    assert injected["rmtrees"] == 1
    assert output.exists()
    assert (output / runner.PUBLICATION_INVALID_MARKER).exists()
    backups = list(tmp_path.glob(".issue-208.backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "payload.txt").read_text(encoding="utf-8") == "old"

    # Real production retry with the filesystem healed: recovery restores
    # the last-good from the backup, publishes the new package, commits it,
    # and converges with zero transaction artifacts.
    monkeypatch.setattr(runner.os, "replace", real_replace)
    monkeypatch.setattr(runner.shutil, "rmtree", real_rmtree)
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not (output / runner.PUBLICATION_INVALID_MARKER).exists()
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))
    assert not list(tmp_path.glob(".issue-208.staging-*"))


def test_run_post_verify_failure_rollback_failed_tree_cleanup_keeps_last_good(
    tmp_path, monkeypatch
):
    """Nested-fault matrix (EV §4.2): failed-tree removal inside the
    rollback fails.  The restored old package stays visible; the failed new
    copy remains as an explicit diagnostic (never an unaccounted orphan)."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_rmtree = runner.shutil.rmtree
    injected = {"n": 0}

    def fail_failed_tree_removal(path, *args, **kwargs):
        nonlocal injected
        if (
            state["post_verify_failed"]
            and injected["n"] == 0
            and ".issue-208.failed-" in str(path)
        ):
            injected["n"] += 1
            raise OSError("injected rollback failed-tree removal failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(runner.shutil, "rmtree", fail_failed_tree_removal)
    with pytest.raises(runner.VerifyError, match="post-publication verification"):
        runner.run(output)

    assert injected["n"] == 1
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    failed = list(tmp_path.glob(".issue-208.failed-*"))
    # The failed new copy stays as an explicit .failed-* diagnostic; the
    # canonical path holds the restored last-good.  No backup orphan.
    assert len(failed) == 1
    assert (failed[0] / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))


def test_run_post_verify_failure_rollback_cleanup_fsync_fault_keeps_last_good(
    tmp_path, monkeypatch
):
    """Nested-fault matrix (EV §4.2): the rollback's cleanup parent fsync
    (after failed-tree removal) fails.  The restored old package stays
    visible and the next retry is safe."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_fsync = runner._fsync_directory
    injected = {"n": 0}

    def fail_rollback_cleanup_fsync(path):
        nonlocal injected
        # Update the rollback/cleanup window counters first (the cleanup
        # fsync fires only after the rollback fsync has been observed and
        # the failed tree has been removed).
        window = _rollback_fsync_window(tmp_path, state)
        if (
            injected["n"] == 0
            and state["rollback_fsync_calls"] >= 1
            and window
            and state["cleanup_fsync_calls"] >= 1
        ):
            injected["n"] += 1
            raise OSError("injected rollback cleanup parent fsync failure")
        return real_fsync(path)

    monkeypatch.setattr(runner, "_fsync_directory", fail_rollback_cleanup_fsync)
    with pytest.raises(runner.VerifyError, match="post-publication verification"):
        runner.run(output)

    assert injected["n"] == 1
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.failed-*"))

    # Immediate retry is safe.
    monkeypatch.setattr(runner, "_fsync_directory", real_fsync)
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"


def test_run_post_verify_failure_keyboard_interrupt_not_double_consumed(
    tmp_path, monkeypatch
):
    """EV §4.3: KeyboardInterrupt during the rollback boundary must not let
    the outer handler double-consume the transaction owner.  The restored
    last-good stays visible; the interrupt propagates."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_fsync = runner._fsync_directory
    injected = {"n": 0}

    def interrupt_at_rollback_fsync(path):
        nonlocal injected
        if (
            injected["n"] == 0
            and _rollback_fsync_window(tmp_path, state)
        ):
            injected["n"] += 1
            raise KeyboardInterrupt("injected rollback KeyboardInterrupt")
        return real_fsync(path)

    monkeypatch.setattr(runner, "_fsync_directory", interrupt_at_rollback_fsync)
    with pytest.raises(KeyboardInterrupt):
        runner.run(output)

    assert injected["n"] == 1
    # The restore happened before the interrupt; the old package is visible.
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    # No backup orphan; the failed copy is the explicit diagnostic.
    assert not list(tmp_path.glob(".issue-208.backup-*"))


def test_run_post_verify_failure_system_exit_not_double_consumed(
    tmp_path, monkeypatch
):
    """EV §4.3: SystemExit during the rollback boundary behaves the same as
    KeyboardInterrupt: the outer BaseException handler must not re-enter
    rollback with a stale handle."""
    output, state = _run_probe_harness(
        tmp_path, monkeypatch, post_verify_failures=["boom"]
    )
    real_fsync = runner._fsync_directory
    injected = {"n": 0}

    def exit_at_rollback_fsync(path):
        nonlocal injected
        if (
            injected["n"] == 0
            and _rollback_fsync_window(tmp_path, state)
        ):
            injected["n"] += 1
            raise SystemExit("injected rollback SystemExit")
        return real_fsync(path)

    monkeypatch.setattr(runner, "_fsync_directory", exit_at_rollback_fsync)
    with pytest.raises(SystemExit):
        runner.run(output)

    assert injected["n"] == 1
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.backup-*"))


def test_rollback_publish_idempotent_after_backup_consumed(tmp_path, monkeypatch):
    """Second-line defence: _rollback_publish called twice with the same
    handle is idempotent — after the backup is consumed, the second call is
    a fail-closed no-op and never touches the visible package."""
    output = tmp_path / "issue-208"
    staging = tmp_path / "staging"
    _payload(output, "old")
    _payload(staging, "new")
    backup = runner._atomic_publish(staging, output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert backup is not None and backup.exists()

    runner._rollback_publish(output, backup)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not backup.exists()

    # Second call with the same (consumed) handle: no-op, old stays visible.
    runner._rollback_publish(output, backup)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.failed-*"))
    assert not list(tmp_path.glob(".issue-208.backup-*"))


def test_rollback_publish_idempotent_with_missing_backup(tmp_path):
    """A rollback with a missing backup handle is a fail-closed no-op: the
    visible package is never moved to .failed-* (the old EV failure mode
    deleted the restored package because the handle was stale)."""
    output = tmp_path / "issue-208"
    _payload(output, "old")
    missing = tmp_path / ".issue-208.backup-does-not-exist"
    runner._rollback_publish(output, missing)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".issue-208.failed-*"))


def test_run_first_publish_post_verify_failure_removes_unverified_new(
    tmp_path, monkeypatch
):
    """First-ever publication (no previous package, backup is None): a
    final-output verify failure removes the unverified new package, so the
    canonical path returns to the pre-publication (absent) state."""
    output = tmp_path / "issue-208"

    state = {
        "post_verify_failed": False,
        "output_verify_calls": 0,
        "rollback_fsync_calls": 0,
        "cleanup_fsync_calls": 0,
    }

    def build(staging, *, published_output):
        _payload(staging, "new")

    def fake_verify(pkg, *args, **kwargs):
        pkg_path = Path(pkg)
        if pkg_path == output:
            state["output_verify_calls"] += 1
            if state["output_verify_calls"] == 1:
                state["post_verify_failed"] = True
                return ["boom"]
        return []

    monkeypatch.setattr(runner, "_run_stages", build)
    monkeypatch.setattr(runner, "_write_metadata", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_write_manifest", lambda *a, **k: None)
    monkeypatch.setattr(runner, "verify_package", fake_verify)
    monkeypatch.setattr(runner, "run_tamper_suite", lambda *a, **k: [])
    with pytest.raises(runner.VerifyError, match="post-publication verification"):
        runner.run(output)

    # No previous package existed; the unverified new package is removed.
    assert not output.exists()
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))

    # Immediate retry publishes cleanly.
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))


def test_run_commit_cleanup_failure_retry_keeps_verified_new_and_drops_stale_backup(
    tmp_path, monkeypatch
):
    """v10 recovery-verify path: a prior run committed the verified new
    package but failed while deleting the obsolete backup.  A real
    production retry verifies the visible tree as the last-good, drops the
    stale backup, and converges with zero orphans."""
    output = tmp_path / "issue-208"
    _payload(output, "old")

    def build(staging, *, published_output):
        _payload(staging, "new")

    monkeypatch.setattr(runner, "_run_stages", build)
    monkeypatch.setattr(runner, "_write_metadata", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_write_manifest", lambda *a, **k: None)
    monkeypatch.setattr(runner, "verify_package", lambda *a, **k: [])
    monkeypatch.setattr(runner, "run_tamper_suite", lambda *a, **k: [])
    real_rmtree = runner.shutil.rmtree
    calls = {"n": 0}

    def fail_commit_cleanup(path, *args, **kwargs):
        nonlocal calls
        # _commit_publish retries once; both attempts must fail so the
        # obsolete backup survives into the retry.
        if ".issue-208.backup-" in str(path) and calls["n"] < 2:
            calls["n"] += 1
            raise OSError("injected commit backup cleanup failure")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(runner.shutil, "rmtree", fail_commit_cleanup)
    with pytest.raises(OSError, match="commit backup cleanup"):
        runner.run(output)

    # The verified new package stays visible; the obsolete backup survived
    # the failed cleanup.
    assert calls["n"] == 2
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    backups = list(tmp_path.glob(".issue-208.backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "payload.txt").read_text(encoding="utf-8") == "old"

    # Real production retry: recovery verifies the visible tree (a complete
    # package) as last-good, drops the stale backup, then republishes and
    # commits — zero transaction artifacts remain.
    monkeypatch.setattr(runner.shutil, "rmtree", real_rmtree)
    runner.run(output)
    assert (output / "payload.txt").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".issue-208.backup-*"))
    assert not list(tmp_path.glob(".issue-208.failed-*"))
    assert not list(tmp_path.glob(".issue-208.staging-*"))
