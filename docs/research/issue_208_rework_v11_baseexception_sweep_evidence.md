# Issue #208 REWORK v11 — E1 BaseException boundary sweep evidence

- SESSION: 20260816_173919_ce1447 (minor rework, RESUME lineage from v10)
- Audited base: `819ef799e67534cc1feebbe0fa417745cee638ef` (PR #230 v10)
- Controlling verdict: EV independent finalize REJECT (2026-08-16T09:34Z),
  `AUDITED_SHA=819ef799e675`, `REWORK_TYPE=minor`.  Single blocking defect
  **E1** under live `finalize` mode; scientific numbers were reproduced and
  the only open item was transactional-publication evidence closure.
- This document is the mandatory same-category complete-sweep declaration
  (EV §4): root cause, EVERY `os.replace` / `rmtree` boundary of the
  category, per-fault state proof, production-entry regressions, supersede
  of the v10 sweep claims, and the preserved-passing list.
- Supersedes the v10 sweep evidence for the KI/SE coverage claim: the v10
  document (`issue_208_rework_v10_rollback_sweep_evidence.md`) §3.7 and the
  PROTOCOL-LOG row #208-39 claimed KeyboardInterrupt/SystemExit rollback
  coverage, but only at the restore parent-fsync boundary.  It did NOT cover
  the `output→failed` rename boundary that decides canonical ownership.

---

## 1. Root cause (EV E1 — BaseException boundary at the canonical-ownership rename)

v10 `_rollback_publish` handled the `new→failed` rename fault with
`except OSError:` only.  The EV production probe:

1. `run()` publishes the new package (staging/tamper verification passes);
2. the FINAL canonical verification at the published path explicitly returns
   a semantic rejection;
3. the rollback's `output→failed` rename raises `KeyboardInterrupt` (probe 1)
   or `SystemExit` (probe 2) — a single control interruption, injected
   through the production `run()` entry point.

Because v10 only caught `OSError`, the control interrupt escaped the
rollback without entering the remove-invalid-tree/restore-backup path AND
without writing `.PUBLICATION_INVALID`.  Meanwhile `run():480-482` had
already transferred the outer `backup` ownership to a local before invoking
rollback, so the outer `BaseException` handler at `run():494-497` had no
handle left to restore.  EV observed both probes identically:

```json
{
  "canonical_value": "new-semantic-invalid",
  "invalid_marker": false,
  "backup_values": ["old-last-good"],
  "failed_values": [],
  "last_good_visible": false,
  "semantic_invalid_new_exposed_unmarked": true
}
```

This is a single control interruption, not a crash-window speculation: the
canonical path kept existing, without the fail-closed marker, so any
consumer that did not call the verifier first could read a package the final
verifier had just judged invalid.  The true last-good was hidden in a random
`.backup-*`.

Category: publication atomicity / BaseException boundary / rollback
ownership / validation blind spot.

---

## 2. Fix — BaseException-bounded rollback with convergence-before-propagation

### 2.1 `_rollback_publish` — `output→failed` rename (restore branch)

The `output→failed` rename is now `except BaseException as fault:`.  Inside
the handler:

- the invalid tree is removed with `shutil.rmtree(output)` inside a nested
  `except BaseException` (if removal also faults, `.PUBLICATION_INVALID` is
  written and the fault propagates — backup stays intact);
- the old last-good is restored with `os.replace(backup, output)` inside a
  nested `except BaseException` (if restore faults, the marker is written —
  canonical is absent, fail-closed — and the fault propagates);
- the parent directory is fsynced (durability warning only);
- if the original fault is an ordinary `OSError`, recovery succeeded and the
  caller continues with its own `VerifyError` (v10 contract preserved);
- if the original fault is `KeyboardInterrupt`/`SystemExit` (or another
  `BaseException`), the safe state has been converged FIRST, then the control
  interrupt intent propagates to the caller.

### 2.2 `_rollback_publish` — first-publish branch (`backup is None`)

The first-publish `output→failed` rename is now `except BaseException:`.
If the unverified new cannot be set aside (OSError or a control interrupt),
`.PUBLICATION_INVALID` is written (fail-closed; there is no last-good to
restore) and the fault propagates.

### 2.3 `_mark_publication_invalid` — marker writer

The marker writer now swallows any `BaseException` (not just `OSError`), so
a control interrupt during the marker write never masks the caller's own
boundary fault.  The marker is best-effort; the caller re-raises its fault
and the backup (if any) keeps the true last-good for the run()-start
recovery pass.

### 2.4 Safety state invariant (EV §4.2)

Every ordinary-exception / KeyboardInterrupt / SystemExit return path from
the publication transaction now satisfies exactly one of:

1. last-good visible at canonical; OR
2. canonical absent; OR
3. canonical has a verifiable `.PUBLICATION_INVALID` marker AND the backup is
   intact (fail-closed for readers/verifiers).

The forbidden state — unmarked semantic-invalid canonical with the last-good
hidden in `.backup-*` — is unreachable after this fix.

---

## 3. Same-category complete sweep — EVERY os.replace / rmtree boundary

EV §4.1 requires coverage of `_atomic_publish`, `_rollback_publish`,
`_recover_stale_transaction`, `_commit_publish` and the outer handler, with
focus on `output→failed`, fallback invalid-tree removal, `backup→output` and
recovery cleanup.  This table enumerates every boundary in the category and
its BaseException disposition.

### 3.1 `_rollback_publish`

| Boundary | Line | Exception bound | Fault → state | Test |
|---|---|---|---|---|
| `os.replace(output, failed)` (first-publish) | ~267 | `BaseException` | cannot set aside → marker + propagate (no last-good) | `test_run_first_publish_post_verify_failure_new_to_failed_rename_keyboard_interrupt_marks_invalid` |
| `os.replace(output, failed)` (restore) | ~293 | `BaseException` | remove invalid tree + restore backup → then re-raise control interrupt / return for OSError | `test_run_post_verify_failure_rollback_new_to_failed_rename_keyboard_interrupt_converges`, `..._system_exit_converges` |
| `shutil.rmtree(output)` (invalid-tree removal, nested) | ~303 | `BaseException` | removal faults → marker + backup intact + propagate | `test_run_post_verify_failure_rollback_new_to_failed_rename_ki_then_rmtree_fault_marks_invalid` |
| `os.replace(backup, output)` (restore, nested) | ~312 | `BaseException` | restore faults → canonical absent (fail-closed) + backup intact + propagate | `test_run_post_verify_failure_rollback_backup_to_output_rename_fault_converges` |
| `os.replace(backup, output)` (restore, main path) | ~321 | `BaseException` | output stays absent + backup intact + re-raise | `test_run_post_verify_failure_rollback_backup_to_output_rename_fault_converges` |
| `shutil.rmtree(failed)` (diagnostic cleanup ×2) | ~278, ~335 | `OSError` pass | cleanup fault keeps `.failed-*` diagnostic; visibility already safe | `test_run_post_verify_failure_rollback_failed_tree_cleanup_keeps_last_good` |
| `_fsync_directory` (durability ×3) | restore/cleanup | `OSError` pass | durability warning; last-good already visible | `test_run_post_verify_failure_rollback_cleanup_fsync_fault_keeps_last_good` |

### 3.2 `_atomic_publish`

| Boundary | Exception bound | Fault → state | Test |
|---|---|---|---|
| `os.replace(output, backup)` + first parent fsync | `BaseException` | restore backup → output (canonical absent meanwhile = fail-closed) | `test_first_parent_fsync_failure_restores_visible_last_good` |
| `os.replace(staging, output)` + second parent fsync | `BaseException` | new visible uncommitted → move back to staging / restore backup | `test_second_rename_failure_restores_last_good`, `test_second_parent_fsync_failure_restores_last_good_and_retry` |
| `os.replace(output, staging)` (inner recovery) | `BaseException` (re-raise from handler) | output absent or new back at staging; backup intact | covered by the two tests above |
| `os.replace(backup, output)` (inner recovery) | `BaseException` (re-raise from handler) | output absent; backup intact (fail-closed) | covered above |

`_atomic_publish` never exposes the new package on the canonical path before
the caller's final verification; its own fault paths restore last-good or
leave canonical absent.

### 3.3 `_recover_stale_transaction`

| Boundary | Exception bound | Fault → state | Test |
|---|---|---|---|
| `verify_package(output)` (recovery decision) | `BaseException` → treated as failures | cannot verify → restore backup | `test_run_commit_cleanup_failure_retry_keeps_verified_new_and_drops_stale_backup` |
| `_rollback_publish(output, backup)` (recovery) | BaseException-bounded (§3.1) | converges to a safe state | v11 probes + v10 recovery tests |
| `shutil.rmtree(backup)` (stale drop) | `ignore_errors=True` (OSError) | stale backup gone; verified visible tree kept | `test_run_commit_cleanup_failure_retry_keeps_verified_new_and_drops_stale_backup` |
| `shutil.rmtree(.failed-*)`, `shutil.rmtree(.staging-*)` | `ignore_errors=True` (OSError) | stale artifacts removed; never last-good | v10 convergence tests |

Recovery only ever touches artifacts that are NOT the verified canonical
last-good (verified tree is kept; a marker-flagged tree restores from
backup).

### 3.4 `_commit_publish`

| Boundary | Exception bound | Fault → state | Test |
|---|---|---|---|
| `shutil.rmtree(backup)` (obsolete cleanup ×2) | `OSError` retry once, then propagate | verified new visible; stale backup remains for next recovery | `test_backup_cleanup_transient_fault_retries_without_rollback`, `test_run_commit_cleanup_failure_retry_keeps_verified_new_and_drops_stale_backup` |
| `_fsync_directory` (cleanup durability) | propagates (OSError) | verified new visible; caller handle already cleared → no rollback | `test_cleanup_parent_fsync_failure_preserves_verified_new_and_retry` |

### 3.5 `run()` outer handler

| Boundary | Exception bound | Fault → state | Test |
|---|---|---|---|
| `_rollback_publish(output, backup)` | BaseException-bounded | converges to safe state | v11 probes |
| `shutil.rmtree(staging, ignore_errors=True)` | `ignore_errors=True` (OSError) | staging temp dir removed; canonical already safe | `test_keyboard_interrupt_during_build_preserves_output` |

### 3.6 KeyboardInterrupt / SystemExit coverage (supersedes v10 §3.7)

| Interrupt point | v10 status | v11 status | Test |
|---|---|---|---|
| `output→failed` rename (restore) | **NOT covered** (E1) | converge-then-propagate | `..._rename_keyboard_interrupt_converges`, `..._rename_system_exit_converges` |
| `output→failed` rename (first publish) | **NOT covered** | marker + propagate | `..._first_publish_..._keyboard_interrupt_marks_invalid` |
| `output→failed` rename + invalid-tree removal fault | **NOT covered** | marker + backup intact | `..._ki_then_rmtree_fault_marks_invalid` |
| invalid-tree removal (second fault) | NOT covered (only OSError) | `BaseException` → marker + backup intact | same test |
| `backup→output` restore (second fault) | NOT covered (only OSError) | `BaseException` → canonical absent + backup intact | `..._backup_to_output_rename_fault_converges` |
| restore parent-fsync | covered in v10 | unchanged | `test_run_post_verify_failure_keyboard_interrupt_not_double_consumed`, `..._system_exit_not_double_consumed` |
| during build | covered in v10 | unchanged | `test_keyboard_interrupt_during_build_preserves_output` |

---

## 4. Production-entry regression evidence (EV §4.3 exact probes)

The two exact EV probes are reproduced at the production `run()` entry
point: third (final-output) verify fails, then the rollback's
`output→failed` rename raises `KeyboardInterrupt` / `SystemExit`.  Observed
state after the fix (equivalent of the EV probe JSON):

```json
{
  "canonical_value": "old-last-good",
  "invalid_marker": false,
  "backup_values": [],
  "failed_values": [],
  "last_good_visible": true,
  "semantic_invalid_new_exposed_unmarked": false
}
```

Immediate healed production retry (plain `runner.run(output)`, no private
helper calls):
`visible_value=new`, `backup_values=[]`, `failed_values=[]`,
`staging_values=[]` — transaction fully converged with zero orphans.

Double-fault probe (`KeyboardInterrupt` at rename + `OSError` at invalid-tree
removal):

```json
{
  "canonical_value": "new-semantic-invalid",
  "invalid_marker": true,
  "backup_values": ["old-last-good"],
  "failed_values": [],
  "last_good_visible": false,
  "semantic_invalid_new_exposed_unmarked": false
}
```

Healed retry restores last-good and converges.

---

## 5. Files changed

- `scripts/run_bj208_policy.py` — `_rollback_publish` `output→failed`
  rename + first-publish branch now `BaseException`-bounded; nested recovery
  steps `BaseException`-bounded; `_mark_publication_invalid` swallows
  `BaseException`.
- `tests/test_bj208_publication.py` — 7 new production-entry tests (EV exact
  KI/SE probes + double-fault marker + first-publish marker + three
  `_atomic_publish` inner-recovery KI boundaries), all with real healed
  `run()`/recovery retry convergence assertions.
- `docs/research/issue_208_protocol_log.md` — row #208-40 supersedes #208-39;
  v11 executable-evidence section appended.
- This sweep evidence document.

No scientific output changed: the publication transaction lives entirely in
the runner's final publish step; candidate pools, label surface, model fits,
decisions, capital paths, selection, handoff and all data frames are
byte-identical to v10 (verified by the deterministic replay comparison in
the delivery; only `COMPLETED.json`, `SHA256SUMS.json`, `decision.json`,
`provenance.json` carry execution metadata).

## 6. Preserved passing regressions (all re-run green)

- Focused suite: `106 passed` (99 retained + 7 new v11 publication tests).
- 0.65-once payout economics, canonical paired identity (C1), label/chronology,
  actual-refit full inventory, selection/handoff binding, manifest coverage,
  capital accounting, holding metrics, alternate-output replay, 55-frame
  reproducibility, 26 tamper attacks (production verifier suite), notebook
  clean-run, preflight.

## 7. Protocol log

`docs/research/issue_208_protocol_log.md` row #208-40 supersedes the #208-39
rollback-path claim; method.yaml protocol version stays unchanged (no
model/grid/seed/selection change).
