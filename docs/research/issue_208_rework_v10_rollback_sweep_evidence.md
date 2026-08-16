# Issue #208 REWORK v10 — E1 rollback rename-fault closure sweep evidence

- SESSION: 20260816_145531_b32d04 (minor rework, RESUME lineage from v9)
- Audited base: `eeabd3036375f6a2e7d224c77bae292249ff2207` (PR #230 v9)
- Controlling verdict: EV independent finalize REJECT (2026-08-16T06:48Z),
  `AUDITED_SHA=eeabd3036375`, `REWORK_TYPE=minor`.  Single blocking defect
  **E1** under live `finalize` mode; scientific numbers were reproduced and
  the only open item was transactional-publication evidence closure.
- This document is the mandatory same-category complete-sweep declaration
  (EV §4): root cause, every call site of the category, per-fault state
  proof, production-entry regressions, and the preserved-passing list.

---

## 1. Root cause (EV E1 — publication atomicity / rollback state machine)

v9 `_rollback_publish` moved the unverified new package aside first:

```python
failed = output.parent / f".{output.name}.failed-{uuid}"
try:
    if output.exists():
        os.replace(output, failed)      # new -> .failed-*
    os.replace(backup, output)          # old -> output
except BaseException:
    if backup.exists() and not output.exists():
        os.replace(backup, output)      # restore ONLY when output absent
    raise
```

EV production probe: the `new→failed` rename raises an ordinary `OSError`.
At that point `output` still exists (it holds the semantic-invalid new
package), so the recovery condition `not output.exists()` is false and the
old last-good is never restored.  The caller's ownership had already been
transferred (`backup = None` before rollback), so nothing else recovers.
EV observed:

```json
{ "error": "OSError: independent new-to-failed rename fault",
  "visible_value": "new-unverified",
  "backup_values": ["old-last-good"],
  "failed_values": [],
  "last_good_visible": false,
  "unverified_new_visible": true }
```

A subsequent production `run()` then succeeded and published the new
package, but the first run's `.backup-*` (old last-good) survived as a
stale orphan — the immediate retry did not close the transaction.

Two worker-test defects encoded the same wrong contract:

- `test_run_post_verify_failure_rollback_new_to_failed_rename_fault_keeps_backup`
  asserted `output == "new"` (unverified) after the fault, then manually
  called the private `_rollback_publish(output, backups[0])` to patch the
  state — not a production retry.
- `test_run_post_verify_failure_rollback_backup_to_output_rename_fault_restores`
  ended with the tautology `assert not list(...) or True`, proving nothing
  about the failed-copy/orphan state.

Category: publication atomicity / rollback state machine / verifier-failure
recovery / validation blind spot.

---

## 2. Fix — three lines of defence

### 2.1 `_rollback_publish` — never leave the unverified new on canonical

On `new→failed` rename fault the invalid tree is **removed** and the old
last-good is **restored from the backup**.  (A POSIX rename cannot replace
a non-empty directory target, so the invalid tree must be deleted first;
an absent output is fail-closed for any reader.)  If removal also fails,
the visible tree is explicitly marked `.PUBLICATION_INVALID` so readers
and the production verifier fail closed, and the backup stays intact for
the run()-start recovery pass.

Fault matrix implemented:

| Rollback fault (post-verify) | Canonical output | Backup | `.failed-*` | Retry |
|---|---|---|---|---|
| `new→failed` rename faults | old last-good restored (invalid tree removed) | consumed | none | safe |
| removal of invalid tree faults (after rename fault) | invalid tree marked `.PUBLICATION_INVALID` | intact (true last-good) | none | recovery restores |
| `backup→output` rename faults | absent (fail-closed) | intact | new (diagnostic) | recovery restores |
| restore parent-fsync faults | old last-good visible | consumed | new or none | safe |
| failed-copy cleanup faults | old last-good visible | consumed | kept as diagnostic or none | safe |
| first-publish `new→failed` fault | invalid tree marked `.PUBLICATION_INVALID` | N/A | none | run() retries cleanly |

The `backup is None` (first-ever publication) branch is now also
fault-bound: if the unverified new cannot be set aside, it is marked
`.PUBLICATION_INVALID` instead of remaining silently consumable.

### 2.2 `run()` — `_recover_stale_transaction` before the next build

A real production retry must converge: `run()` now starts by converging
leftover transaction artifacts.

- Every `.backup-*` holds the pre-transaction last-good; the canonical
  output is at most an unverified/invalid candidate.
- If the visible tree is NOT marked `.PUBLICATION_INVALID` and `verify_package`
  accepts it as a complete package, it IS the last-good (e.g. a prior run
  committed the new package and then failed while cleaning the obsolete
  backup): the stale backup is dropped, the verified tree is kept.
- Otherwise `_rollback_publish(output, backup)` restores last-good
  (persistent faults keep the tree marked invalid and the backup intact for
  a later attempt).
- Stale `.failed-*` and `.staging-*` are removed (never last-good).

### 2.3 Tests — contract asserts + real production retry only

- The v9 wrong-contract test is replaced by
  `test_run_post_verify_failure_rollback_new_to_failed_rename_fault_restores_last_good`:
  after the fault the canonical path holds **old**, no `.backup-*`, no
  `.failed-*`; the immediate retry is a real `runner.run(output)` call that
  publishes **new** with zero artifacts.
- The tautology is removed; the backup→output fault test now asserts an
  absent canonical (fail-closed), old intact in backup, new in `.failed-*`,
  then a real production retry converges.
- New `..._cannot_clear_canonical_fail_closed_and_retry` covers the
  `.PUBLICATION_INVALID` marker path (rename fault + rmtree fault) with a
  healed-filesystem production retry.
- New `..._commit_cleanup_failure_retry_keeps_verified_new_and_drops_stale_backup`
  covers the recovery-verify path (stale backup after commit cleanup
  failure; retry keeps the verified new and drops the backup).

---

## 3. Same-category complete sweep — every call site checked

### 3.1 `_rollback_publish` callers (ALL)

| Caller | File:line | v9 behaviour | v10 behaviour | Proof |
|---|---|---|---|---|
| post-verify branch | `run_bj208_policy.py` | ownership transferred, but rename fault left invalid new visible | ownership transferred + rollback restores last-good on every rename fault | `test_run_post_verify_failure_rollback_new_to_failed_rename_fault_restores_last_good` |
| outer BaseException handler | `run_bj208_policy.py` | fires only while `backup is not None` | unchanged (idempotent rollback as second line) | `test_rollback_publish_idempotent_after_backup_consumed`, `test_rollback_publish_idempotent_with_missing_backup` |
| run()-start recovery | `run_bj208_policy.py` (new) | N/A | restores leftover backup or drops stale verified duplicate | `test_run_post_verify_failure_rollback_backup_to_output_rename_fault_converges`, `test_run_commit_cleanup_failure_retry_keeps_verified_new_and_drops_stale_backup` |
| direct (tests) | `test_bj208_publication.py` | — | — | all green |

### 3.2 `_atomic_publish` callers + internal fault points (ALL)

Single production caller `run()`.  Internal transaction faults unchanged
from v9 and re-verified green:

| Fault point | File:line | Handling | Proof |
|---|---|---|---|
| output→backup rename | `_atomic_publish` | restore on fault | `test_second_rename_failure_restores_last_good` |
| FIRST parent fsync | `_atomic_publish` | restore last-good | `test_first_parent_fsync_failure_restores_visible_last_good` |
| staging→output rename | `_atomic_publish` | restore last-good | `test_second_rename_failure_restores_last_good` |
| SECOND parent fsync | `_atomic_publish` | restore last-good + retry | `test_second_parent_fsync_failure_restores_last_good_and_retry` |

### 3.3 `_commit_publish` callers (ALL)

Single production caller `run()`.  Caller clears `backup` BEFORE commit
(`commit_backup = backup; backup = None`), so a cleanup parent-fsync
failure leaves the verified new visible and never triggers a rollback.
A double `rmtree` failure leaves the obsolete backup behind; the run()-start
recovery-verify path drops it on the next real retry
(`test_run_commit_cleanup_failure_retry_keeps_verified_new_and_drops_stale_backup`).

### 3.4 Every rename call site (ALL)

| Call | Owner | Fault exposure | v10 status |
|---|---|---|---|
| `os.replace(output, backup)` | `_atomic_publish` | transaction, inside try | unchanged |
| `os.replace(staging, output)` | `_atomic_publish` | transaction, inside try | unchanged |
| `os.replace(backup, output)` (atomic restore) | `_atomic_publish` except | transaction, inside try | unchanged |
| `os.replace(output, failed)` | `_rollback_publish` first-publish | fail-closed marker + raise | NEW |
| `os.replace(output, failed)` | `_rollback_publish` restore | fault → remove invalid tree + restore | NEW |
| `os.replace(backup, output)` (restore) | `_rollback_publish` | fault → output absent, backup intact; recovery converges | NEW |
| `os.replace(backup, output)` (recovery) | `_recover_stale_transaction` via `_rollback_publish` | persistent fault → marker + intact backup | NEW |

### 3.5 Every `_fsync_directory` call site (ALL)

| Owner | Fault exposure | v10 status |
|---|---|---|
| `_fsync_tree` (nested dirs) | durability, staging only | unchanged; `test_fsync_tree_flushes_nested_directories_bottom_up` |
| `_atomic_publish` after backup rename | transaction, inside try | unchanged |
| `_atomic_publish` restore | transaction, inside try | unchanged |
| `_atomic_publish` after install | transaction, inside try | unchanged |
| `_atomic_publish` restore | transaction, inside try | unchanged |
| `_rollback_publish` first-publish branch (×2) | AFTER removal | wrapped `except OSError: pass` |
| `_rollback_publish` restore fsync | AFTER last-good visible | wrapped `except OSError: pass` |
| `_rollback_publish` failed-copy cleanup fsync | AFTER last-good visible | wrapped `except OSError: pass` |
| `_recover_stale_transaction` final fsync | AFTER convergence | wrapped `except OSError: pass` (NEW) |
| `_commit_publish` cleanup fsync | AFTER verified new visible | unchanged; caller cleared handle |

### 3.6 Every removal (`rmtree`) call site (ALL)

| Call | Owner | Fault exposure | v10 status |
|---|---|---|---|
| `shutil.rmtree(staging)` (invalid tree removal) | `_rollback_publish` fallback | fault → `.PUBLICATION_INVALID` marker + intact backup | NEW |
| `shutil.rmtree(failed)` (diagnostic cleanup) | `_rollback_publish` (×2 branches) | fault → kept as explicit diagnostic | unchanged |
| `shutil.rmtree(backup)` (obsolete cleanup) | `_commit_publish` | one bounded retry; stale backup converges via recovery | unchanged |
| `shutil.rmtree(backup)` (stale drop) | `_recover_stale_transaction` | ignore_errors; stale backup gone on retry | NEW |
| `shutil.rmtree(failed/staging)` (stale sweep) | `_recover_stale_transaction` | ignore_errors; never last-good | NEW |
| `shutil.rmtree(staging, ignore_errors=True)` | `run()` outer handler | cleanup after failure | unchanged |

### 3.7 KeyboardInterrupt / SystemExit (EV §4.3)

| Interrupt point | Transaction owner | old last-good visible | Test |
|---|---|---|---|
| KeyboardInterrupt at rollback restore fsync | backup consumed; outer handler no-op | yes | `test_run_post_verify_failure_keyboard_interrupt_not_double_consumed` |
| SystemExit at rollback restore fsync | backup consumed; outer handler no-op | yes | `test_run_post_verify_failure_system_exit_not_double_consumed` |
| KeyboardInterrupt during build | backup None; staging cleaned | yes | `test_keyboard_interrupt_during_build_preserves_output` |

---

## 4. Production-entry regression evidence (EV §4.3 exact probe)

`test_run_post_verify_failure_rollback_new_to_failed_rename_fault_restores_last_good`
reproduces the EV scenario at the `run()` entry point: third (final-output)
verify fails, then the rollback's `new→failed` rename fails.  Observed
after the fix (equivalent of the EV probe JSON):

```json
{ "error": "VerifyError: post-publication verification failed",
  "visible_value": "old-last-good",
  "backup_values": [],
  "failed_values": [],
  "last_good_visible": true,
  "unverified_new_visible": false }
```

Immediate production retry (plain `runner.run(output)`):
`visible_value=new`, `backup_values=[]`, `failed_values=[]`,
`staging_values=[]` — transaction fully converged.

---

## 5. Files changed

- `scripts/run_bj208_policy.py` — `_rollback_publish` restructured
  (rename-fault closure + fail-closed marker), `_mark_publication_invalid`
  added, `_recover_stale_transaction` added and called at `run()` start.
- `tests/test_bj208_publication.py` — wrong-contract test rewritten,
  tautology removed, 4 production-entry retry tests (net +2 tests).
- `docs/research/issue_208_protocol_log.md` — row #208-39 supersedes the
  #208-38 rollback path.
- This sweep evidence document.

No scientific output changed: the publication transaction lives entirely in
the runner's final publish step; candidate pools, label surface, model
fits, decisions, capital paths, selection, handoff and all data frames are
byte-identical to v9 (verified by the deterministic replay comparison in
the delivery; only `COMPLETED.json`, `SHA256SUMS.json`, `decision.json`,
`provenance.json` carry execution metadata).

## 6. Preserved passing regressions (all re-run green)

- 0.65-once payout economics, canonical paired identity (C1), label/chronology,
  actual-refit full inventory, selection/handoff binding, manifest coverage,
  capital accounting, holding metrics, alternate-output replay, 55-frame
  reproducibility, 26 tamper attacks (production verifier suite), notebook
  clean-run, preflight.
- Focused suite: `99 passed` at this worktree (97 retained + 4 new/replaced
  publication tests, 2 net new).

## 7. Protocol log

`docs/research/issue_208_protocol_log.md` row #208-39 records the supersede
of the #208-38 rollback path; method.yaml protocol version stays unchanged
(no model/grid/seed/selection change).
