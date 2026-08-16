# HANDOFF — Issue #208 v10 minor rework (E1 rollback rename-fault closure)

- SESSION: 20260816_145531_b32d04
- Issue: algotradinglife/beijing-lot #208 (BJ-UNIFIED-DYNAMIC-N-001)
- PR: #230 (branch head advanced to `analyst/bj208-rework-r11` → pushed to
  PR branch `analyst/bj208-rework-r1`)
- Worktree: /home/drwho1985/workspace/soccer/beijing-lot-bj208-r11

## Current HEAD (worktree)

- Base: `eeabd3036375f6a2e7d224c77bae292249ff2207` (audited v9 HEAD)
- Local commit: v10 fix + replay artifacts (see git log)

## What was done

EV finalize REJECT (2026-08-16T06:48Z, `REWORK_TYPE=minor`) identified one
blocking evidence defect at audited HEAD `eeabd30`:

- **E1 (publication atomicity / rollback state machine):** when the
  post-publication verify fails and the rollback's `new→failed` rename
  faults, the semantic-invalid new package stayed on the canonical path
  (`visible_value=new-unverified`, `last_good_visible=false`), the old
  last-good was orphaned in `.backup-*`, and a production retry left that
  stale backup behind.  The v9 test encoded the wrong contract (asserted
  unverified new visible) and manually called the private helper instead of
  a real production retry; another test had `assert ... or True`.

Fix — three lines of defence:

1. `_rollback_publish` never leaves the unverified new on canonical:
   - `new→failed` rename fault → remove the invalid tree, restore old
     last-good from backup (POSIX rename cannot replace a non-empty
     directory target, so the tree is deleted first; an absent output is
     fail-closed for any reader).
   - removal also fails → mark the visible tree `.PUBLICATION_INVALID`
     (fail-closed; readers/verifiers reject it) and keep the backup intact.
   - first-publish branch likewise fail-closed via the marker.
2. `run()` starts with `_recover_stale_transaction()`: restores any
   leftover backup (or drops it when the visible tree verifies as a
   complete last-good), removes stale `.failed-*`/`.staging-*` — a real
   production retry converges with zero orphan artifacts.
3. Tests: wrong-contract test rewritten (asserts restored last-good +
   real production retry), tautology removed, new production-entry tests
   for backup→output rename fault, cannot-clear-canonical fail-closed
   marker path, and commit-cleanup stale-backup recovery-verify path.

## Key decisions & rationale

- Visibility restoration is the commit point: after last-good is visible at
  canonical, fsync/cleanup faults are warnings, never a second rollback.
- The `new→failed` fault sacrifices the `.failed-*` diagnostic copy when
  the invalid tree must be removed to restore visibility (contract priority:
  old last-good visible, no invalid final exposed, retry safe).
- Recovery is verify-based: if the visible tree is a complete verified
  package (commit succeeded, cleanup failed), it is kept and the stale
  backup dropped — never roll a committed package back to obsolete bytes.
- All fault probes are run()-level production-entry (monkeypatched
  `_run_stages`/`verify_package`/`os.replace`/`shutil.rmtree`), so EV can
  re-probe through the same entry point.
- No scientific/model/grid/seed/selection change: E1 is purely the runner's
  transactional publication step; deterministic replay must produce
  byte-identical science frames to v9.

## Replay results (completed 2026-08-16)

- `run --output results/issue-208`: EXIT=0, elapsed 1060.6s, COMPLETED.
- Production verifier: `verify ok; tamper detected=26` (26/26 attacks).
- Selection: `eligible=false`, median matched lift 0.0, positive folds 0,
  candidate=frozen `N7/K8/MARKET_WOR/NATIVE_2_YUAN` (unchanged vs v9).
- Handoff: candidate=fallback=FROZEN_N7_INCUMBENT; `2024_opened=false`.
- Science frames byte-identical to v9: only COMPLETED.json, SHA256SUMS.json,
  decision.json, provenance.json changed (elapsed / execution metadata —
  the expected delta set; producer_code_commit now `0e7e27b` which contains
  the v10 runner code). All 55 CSV/Parquet frames, 9 joblib models and the
  remaining JSON artifacts are unchanged.
- Fold endings reproduce EV exactly: CV_2022 99072.00/99072.00,
  CV_2023 99245.37814957523/99245.37814957523.
- Notebook rebuilt + executed: 20/20 code cells, 0 errors.
- `method_preflight.py --worktree <r11>`: PASS.

## Known issues

- `.PUBLICATION_INVALID` marker is only written when the invalid tree cannot
  be removed at all (deeply broken filesystem); normal faults restore
  last-good directly.
- Recovery verify call is skipped for a marker-flagged tree (marker wins).
- ood_fallback_census cosmetic note from v3–v9 remains (pre-existing
  diagnostic-only, not part of this E1 closure).

## Next step

EV independent finalize audit at the new exact PR #230 HEAD: fresh
checkout, re-run production-entry fault probes (third verify fails + first
rollback `new→failed` rename fault → old visible, retry converges), focused
suite, preflight, package verify/tamper, notebook clean-run, replay
comparison, REQ-208-01..09 evidence at the exact SHA.

## 返工

按 REWORK_TYPE 分支 (method → fresh / minor → resume)
