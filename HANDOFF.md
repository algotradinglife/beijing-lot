# HANDOFF — Issue #208 v9 minor rework (E1 rollback idempotence)

- SESSION: 20260816_115337_d2cea9
- Issue: algotradinglife/beijing-lot #208 (BJ-UNIFIED-DYNAMIC-N-001)
- PR: #230 (branch head will be updated to `analyst/bj208-rework-r11`)
- Worktree: /home/drwho1985/workspace/soccer/beijing-lot-bj208-r11

## Current HEAD (worktree)

- Base: `7302d6448cd1cf055f4220740be6fcb864685d93` (audited v8 HEAD)
- Local commit: `badd443` "research: fix #208 E1 rollback idempotence (v9
  minor rework)" — NOT yet pushed (waiting for deterministic replay).

## What was done

EV finalize REJECT (2026-08-16T03:52Z, `REWORK_TYPE=minor`) identified one
blocking evidence defect at audited HEAD `7302d644`:

- **E1 (publication atomicity / rollback idempotence):** when the
  post-publication verify fails and the FIRST rollback parent-fsync then
  faults, `run()`'s outer BaseException handler re-entered
  `_rollback_publish` with the same (already-consumed) backup handle,
  moved the restored last-good to `.failed-*` and deleted it —
  `output_exists=false`. Existing tests only covered the rollback happy
  path and the commit-side cleanup fsync, not the rollback-internal fsync.

Fix — two independent lines of defence:

1. `run()` transfers backup ownership to a local
   (`rollback_backup = backup; backup = None`) BEFORE calling
   `_rollback_publish`, so the outer handler can never re-enter with a
   consumed handle (mirrors the v8 commit-side fix).
2. `_rollback_publish` is now idempotent and fault-bound:
   - consumed/missing backup → fail-closed no-op (never touches visible);
   - restore parent-fsync and failed-copy cleanup fsync → durability
     warnings (visibility is the commit point), never a second rollback;
   - failed-copy removal failure → explicit `.failed-*` diagnostic, no
     unaccounted orphan;
   - first-ever publication (backup None) → removes unverified new package
     back to absent state (idempotent).

## Key decisions & rationale

- Ownership transfer at the caller is the primary fix (EV §4.1 explicit
  requirement); idempotence in `_rollback_publish` is the second line.
- Chose run()-level production-entry tests (monkeypatched `_run_stages`,
  `verify_package`, `_fsync_directory`/`os.replace`/`shutil.rmtree`) so EV
  can re-probe through the same entry point, not helper-only tests.
- The nested-fault matrix covers: new→failed rename, backup→output rename,
  restore parent fsync, failed-copy removal, cleanup fsync — each with
  explicit state proof (old visible / new-failed state / no orphan / retry
  safe) in `docs/research/issue_208_rework_v9_e1_sweep_evidence.md`.
- KeyboardInterrupt / SystemExit at the rollback boundary verified to not
  double-consume the transaction owner (EV §4.3).
- No scientific/model/grid/seed/selection change: E1 is purely the runner's
  transactional publication step; deterministic replay must produce
  byte-identical science frames to v8 (replay comparison in delivery).

## Replay results (completed 2026-08-16 ~12:30 local)

- `run --output results/issue-208`: EXIT=0, elapsed 1311.8s, COMPLETED.
- Production verifier: `verify ok; tamper detected=26` (26/26 attacks).
- Selection: `eligible=false`, median matched lift 0.0, positive folds 0,
  candidate=frozen `N7/K8/MARKET_WOR/NATIVE_2_YUAN` (unchanged vs v8).
- Handoff: candidate=fallback=FROZEN_N7_INCUMBENT; `2024_opened=false`.
- Science frames byte-identical to v8: only COMPLETED.json,
  SHA256SUMS.json, decision.json, provenance.json changed (elapsed /
  execution metadata — the expected delta set), 75/79 files untouched
  (git status confirms no diff on scientific artifacts).
- Fold endings reproduce EV exactly: CV_2022 99072.00/99072.00,
  CV_2023 99245.37814957523/99245.37814957523.
- `method_preflight.py --worktree <r11>`: **PASS** (receipt hash
  `d2a8c5345d67…` exact match with EV).

## Known issues

- `_rollback_publish` first-publish branch uses `try/except OSError: pass`
  on its own fsyncs; an fsync fault there still leaves the package removed
  (pre-publication state) — acceptable because the output was unverified.

## Next steps

1. Push branch `analyst/bj208-rework-r11`; update PR #230 body (append v9).
2. `post_handoff.py` then `finalize_delivery.py` → EV Review.
