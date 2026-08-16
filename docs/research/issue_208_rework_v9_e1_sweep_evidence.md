# Issue #208 REWORK v9 — E1 publication-rollback idempotence sweep evidence

- SESSION: 20260816_115337_d2cea9 (minor rework, RESUME lineage)
- Audited base: `7302d6448cd1cf055f4220740be6fcb864685d93` (PR #230 v8)
- Controlling verdict: EV independent finalize REJECT (2026-08-16T03:52Z),
  `AUDITED_SHA=7302d6448cd1`, `REWORK_TYPE=minor`.  Single blocking defect
  **E1** under live `finalize` mode; scientific numbers were reproduced and
  the only open item was transactional-publication evidence closure.
- This document is the mandatory same-category complete-sweep declaration
  (EV §4): root cause, every call site of the category, per-fault state
  proof, production-entry regressions, and the preserved-passing list.

---

## 1. Root cause (EV E1 — publication atomicity / rollback idempotence)

`run()` (scripts/run_bj208_policy.py) post-publication verification failure
path was:

```python
post_failures = verify_package(output)
if post_failures:
    _rollback_publish(output, backup)   # <- if THIS raises after restoring
    backup = None                       #    last-good, this line never runs
    raise VerifyError(...)
```

`_rollback_publish` restored last-good in this order (v8):

```python
failed = output.parent / f".{output.name}.failed-{uuid}"
if output.exists():
    os.replace(output, failed)   # new -> .failed-*
if backup is not None and backup.exists():
    os.replace(backup, output)   # old -> output  (last-good now visible)
_fsync_directory(output.parent)  # <- parent fsync; if THIS raises:
if failed.exists():
    shutil.rmtree(failed)
    _fsync_directory(output.parent)
```

EV production probe: the first rollback parent-fsync (`_fsync_directory`
after backup->output restore) raises `OSError`.  At that point the old
last-good IS already visible at `output`, but the caller's `backup` handle
was NOT yet cleared (`backup = None` never executed).  The exception
propagates to `run()`'s outer `except BaseException` handler, which re-enters
`_rollback_publish(output, backup)` with the SAME (now stale) handle.  The
second call moves the restored old package to a NEW `.failed-*`, finds no
backup to restore, then deletes that failed copy.  Result (EV observed):

```json
{ "error": "OSError: injected rollback parent fsync failure",
  "verify_calls": 3, "fsync_calls": 6,
  "output_exists": false, "visible_value": null,
  "backup_entries": [], "failed_values": {".issue-208.failed-…": "new"} }
```

Category: publication atomicity / rollback idempotence / stale transaction
ownership / fsync fault recovery.

---

## 2. Fix — two independent lines of defence

### 2.1 Caller ownership transfer BEFORE any rollback fault (EV §4.1)

`run()` post-verify branch now:

```python
if post_failures:
    rollback_backup = backup
    backup = None                      # ownership cleared BEFORE rollback
    _rollback_publish(output, rollback_backup)
    raise VerifyError(...)
```

The outer `except BaseException` handler therefore sees `backup is None` and
cannot re-enter rollback with the consumed handle.  This mirrors the
already-fixed commit path (`commit_backup = backup; backup = None` before
`_commit_publish`).

### 2.2 `_rollback_publish` idempotence + fault-bound (EV §4.1 second clause)

- `backup is None` (first-ever publication): remove the unverified new
  package to `.failed-*` (pre-publication state) — idempotent because an
  already-absent output is a no-op.
- `backup is not None and not backup.exists()` (handle consumed by an
  earlier rollback): **fail-closed no-op** — the visible package is never
  moved to `.failed-*` again (this is the exact EV failure mode).
- The new->failed and backup->output renames run in one `try`; on partial
  failure the backup (if still present) is restored to output before
  re-raise, so a retry with the same handle is safe.
- Every `_fsync_directory` in the rollback (restore fsync AND failed-copy
  cleanup fsync) is wrapped in `try/except OSError: pass` — visibility
  restoration is the commit point; a durability fault after it must not
  escalate into a second rollback.
- Failed-copy removal failure is wrapped: the `.failed-*` copy remains as an
  explicit diagnostic (never an unaccounted orphan).

---

## 3. Same-category complete sweep — every call site checked

### 3.1 `_rollback_publish` callers (ALL)

| Caller | File:line | v8 behaviour | v9 behaviour | Proof |
|---|---|---|---|---|
| post-verify branch | `run_bj208_policy.py:382` | backup cleared AFTER rollback (stale on fault) | ownership transferred BEFORE rollback; outer handler no-op | `test_run_post_verify_failure_rollback_parent_fsync_fault_preserves_last_good` |
| outer BaseException handler | `run_bj208_policy.py:396` | could re-enter with consumed handle | only fires while `backup is not None`; rollback itself idempotent | `test_rollback_publish_idempotent_after_backup_consumed`, `test_rollback_publish_idempotent_with_missing_backup` |
| direct (tests) | `test_bj208_publication.py:196,385,588,593,606` | — | — | all green |

### 3.2 `_atomic_publish` callers + internal fault points (ALL)

Single production caller `run():366`.  Internal transaction faults:

| Fault point | File:line | Handling | Proof |
|---|---|---|---|
| output->backup rename | `:176` | inside try; restore on fault | `test_second_rename_failure_restores_last_good` |
| FIRST parent fsync | `:177` | inside try; restore last-good | `test_first_parent_fsync_failure_restores_visible_last_good` |
| staging->output rename | `:192` | inside try; restore | `test_second_rename_failure_restores_last_good` |
| SECOND parent fsync | `:193` | inside try; restore | `test_second_parent_fsync_failure_restores_last_good_and_retry` |

No change needed here; all fault points were already transaction-scoped in
v7/v8 and remain green.

### 3.3 `_commit_publish` callers (ALL)

Single production caller `run():393`.  Caller clears `backup` BEFORE commit
(`commit_backup = backup; backup = None`), so a cleanup parent-fsync failure
(`:307`) leaves the verified new package visible and never triggers a
rollback.  Retained from v8 with its regression
(`test_cleanup_parent_fsync_failure_preserves_verified_new_and_retry`).

### 3.4 Every `_fsync_directory` call site (ALL 10)

| Line | Owner | Fault exposure | v9 status |
|---|---|---|---|
| 151 | `_fsync_tree` (nested dirs) | durability, staging only | unchanged; `test_fsync_tree_flushes_nested_directories_bottom_up` |
| 177 | `_atomic_publish` after backup rename | transaction, inside try | unchanged |
| 185 | `_atomic_publish` restore | transaction, inside try | unchanged |
| 193 | `_atomic_publish` after install | transaction, inside try | unchanged |
| 206 | `_atomic_publish` restore | transaction, inside try | unchanged |
| 242 | `_rollback_publish` first-publish branch | AFTER removal | NEW — wrapped `except OSError: pass` |
| 250 | `_rollback_publish` first-publish branch | AFTER removal | NEW — wrapped `except OSError: pass` |
| 276 | `_rollback_publish` restore fsync | AFTER last-good visible (EV E1) | NEW — wrapped `except OSError: pass` |
| 289 | `_rollback_publish` failed-copy cleanup fsync | AFTER last-good visible | NEW — wrapped `except OSError: pass` |
| 307 | `_commit_publish` cleanup fsync | AFTER verified new visible | unchanged; caller cleared handle (v8) |

### 3.5 Nested-failure matrix (EV §4.2) — each fault proves state

| Fault inside rollback (post-verify failed) | old last-good visible | new/failed state | no orphan | retry safe | Test |
|---|---|---|---|---|---|
| new->failed rename fails | old intact in backup (output holds unverified new) | explicit `.failed-*` absent, new visible | backup named | `_rollback_publish(output, backups[0])` restores | `test_run_post_verify_failure_rollback_new_to_failed_rename_fault_keeps_backup` |
| backup->output rename fails after new->failed | old restored to output (recovery inside try) OR intact in backup | new at `.failed-*` or cleaned | none | next run publishes | `test_run_post_verify_failure_rollback_backup_to_output_rename_fault_restores` |
| restore parent fsync fails (EV exact) | **old restored and visible** | new cleaned | none | next run publishes new | `test_run_post_verify_failure_rollback_parent_fsync_fault_preserves_last_good` |
| failed-copy removal fails | old restored and visible | new kept as explicit `.failed-*` diagnostic | none (named) | next run publishes | `test_run_post_verify_failure_rollback_failed_tree_cleanup_keeps_last_good` |
| cleanup parent fsync fails | old restored and visible | new cleaned | none | next run publishes | `test_run_post_verify_failure_rollback_cleanup_fsync_fault_keeps_last_good` |
| first-ever publish, post-verify fails | N/A (no prior) | new removed, path absent | none | next run publishes | `test_run_first_publish_post_verify_failure_removes_unverified_new` |

### 3.6 KeyboardInterrupt / SystemExit (EV §4.3)

| Interrupt point | Transaction owner | old last-good visible | Test |
|---|---|---|---|
| KeyboardInterrupt at rollback restore fsync | backup consumed; outer handler no-op | yes | `test_run_post_verify_failure_keyboard_interrupt_not_double_consumed` |
| SystemExit at rollback restore fsync | backup consumed; outer handler no-op | yes | `test_run_post_verify_failure_system_exit_not_double_consumed` |
| KeyboardInterrupt during build | backup None; staging cleaned | yes (unchanged) | `test_keyboard_interrupt_during_build_preserves_output` |

---

## 4. Files changed

- `scripts/run_bj208_policy.py` — `_rollback_publish` idempotent + fault-bound
  rewrite; `run()` post-verify ownership transfer.
- `tests/test_bj208_publication.py` — 10 new tests (harness + EV exact probe +
  nested-fault matrix + first-publish + idempotence + KI/SE).

No scientific output changed: the publication transaction lives entirely in
the runner's final publish step; candidate pools, label surface, model fits,
decisions, capital paths, selection, handoff and all data frames are
byte-identical to v8 (verified by the deterministic replay comparison in
the delivery).

## 5. Preserved passing regressions (all re-run green)

- 0.65-once payout economics (42 payout tests), canonical paired identity
  (C1), label/chronology, actual-refit full inventory, selection/handoff
  binding, 78-entry manifest, capital accounting, holding metrics,
  alternate-output replay, 55-frame reproducibility, 26 tamper attacks
  (production verifier suite), notebook clean-run, preflight.
- Focused suite: `87 passed` at the audited v8 HEAD; `97 passed` after the
  10 new E1 rollback tests (`104` in the sweep-evidence draft was a
  miscount; the green focused suite is 97).

## 6. Protocol log

`docs/research/issue_208_protocol_log.md` row #208-38 records the supersede
of #208-36 for the rollback-path idempotence; method.yaml protocol version
stays `bj208-protocol-v7` with the delta row appended (no model/grid/seed/
selection change).
