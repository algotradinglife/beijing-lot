# HANDOFF — Issue #208 v11 minor rework (E1 BaseException boundary closure)

- SESSION: 20260816_173919_ce1447
- Issue: algotradinglife/beijing-lot #208 (BJ-UNIFIED-DYNAMIC-N-001)
- PR: #230 (branch head advanced on `analyst/bj208-rework-r11` → pushed to
  PR branch `analyst/bj208-rework-r1`)
- Worktree: /home/drwho1985/workspace/soccer/beijing-lot-bj208-r11

## Current HEAD (worktree)

- Base: `819ef799e67534cc1feebbe0fa417745cee638ef` (audited v10 HEAD)
- Fix commit: `8c43934f60c60c46aa82ff9a8721617b2dcb916d` (v11 fix: scripts,
  tests, protocol log, sweep docs)
- Artifacts commit: PENDING (this delivery — results, notebook, HANDOFF)

## What was done

EV finalize REJECT (2026-08-16T09:34Z, `REWORK_TYPE=minor`) identified one
blocking evidence defect at audited HEAD `819ef79`:

- **E1 (publication atomicity / BaseException boundary):** the rollback's
  `output→failed` rename caught only `OSError`.  When a `KeyboardInterrupt`
  or `SystemExit` was raised AT that rename (a single control interruption,
  injected through the production `run()` entry after final canonical
  verification rejected the new package), v10 skipped the
  remove-invalid-tree/restore-backup path AND skipped the
  `.PUBLICATION_INVALID` marker.  `run()` had already transferred backup
  ownership, so the outer handler had no handle left.  EV observed:
  `canonical_value=new-semantic-invalid`, `invalid_marker=false`,
  `backup_values=[old-last-good]`, `last_good_visible=false`.

Fix — BaseException-bounded rollback with convergence-before-propagation:

1. `_rollback_publish` `output→failed` rename (restore branch) is now
   `except BaseException as fault:`; recovery (invalid-tree removal then
   `backup→output` restore) is itself nested `BaseException`-bounded; if the
   original fault is `OSError` the caller continues with its own VerifyError
   (v10 contract preserved), otherwise the safe state is converged FIRST and
   then the control interrupt re-propagates.
2. First-publish branch (`backup is None`) has the same `BaseException`
   boundary: cannot set aside → `.PUBLICATION_INVALID` marker + propagate.
3. `_mark_publication_invalid` swallows any `BaseException` so a control
   interrupt during marker writing never masks the caller's boundary fault.
4. Safety invariant on every return path: last-good visible at canonical |
   canonical absent | fail-closed marker + intact backup.  The forbidden
   state (unmarked semantic-invalid canonical) is unreachable.

## Key decisions & rationale

- The `output→failed` rename decides canonical ownership, so it must be
  BaseException-bounded; the v10 sweep only covered KI/SE at restore
  parent-fsync (superseded — see v11 sweep doc and PROTOCOL-LOG #208-40).
- Convergence-before-propagation: a control interrupt does NOT abort the
  rollback mid-recovery; the transaction reaches a safe state first, then
  the interrupt intent continues to the caller.
- No scientific/model/grid/seed/selection change: E1 is purely the runner's
  transactional publication step; deterministic replay must produce
  byte-identical science frames to v10.

## Tests & evidence (completed 2026-08-16)

- 7 new production-entry tests: EV exact probes (KI/SE at `output→failed`
  rename, healed real `run()` retry converges zero-orphan), KI+rmtree
  double-fault marker path, first-publish KI marker path, and three
  `_atomic_publish` inner-recovery KI boundaries (output→backup rename,
  backup→output restore, output→staging move-back).
- Focused suite: `106 passed` (99 retained + 7 new).
- Ruff (touched runner/test), compileall, `git diff --check`: PASS.
- Deterministic replay (bound to fix commit `8c43934`): EXIT=0 in ~1130s;
  production verifier PASS 26/26 tamper; science frames byte-identical to
  v10 — only COMPLETED/SHA256SUMS/decision/provenance metadata changed
  (producer_code_commit now `8c43934f60c60c46aa82ff9a8721617b2dcb916d`).
- Notebook rebuilt + executed: 20/20 code cells, 0 errors.
- Selection (unchanged vs v10): `eligible=false`, median matched lift 0.0,
  positive folds 0, frozen `N7/K8/MARKET_WOR/native ¥2` incumbent for #209;
  2024 not opened.
- `method_preflight.py --worktree <r11>`: PASS (receipt hash
  `d2a8c5345d67` exact match; holdout_isolated true).

## Known issues

- Marker is only written when recovery cannot converge (rename fault + a
  second removal/restore fault); normal KI/SE faults restore last-good
  directly, which is the preferred safe state.
- Recovery verify is skipped for a marker-flagged tree (marker wins).

## Next step

EV independent finalize audit at the new exact PR #230 HEAD: fresh
checkout, re-run production-entry fault probes (final verify fails + rollback
`output→failed` rename raises KeyboardInterrupt/SystemExit → last-good
restored, retry converges), focused suite, preflight, package verify/tamper,
notebook clean-run, replay comparison, REQ-208-01..09 evidence at the exact
SHA.

## 返工

按 REWORK_TYPE 分支 (method → fresh / minor → resume)
