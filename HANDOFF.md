# HANDOFF — Issue #394 (BJ-UNIFIED-N7-MIXED-FULL-HISTORY-001/v1)

Session: analyst-bj394-20260825-01
Branch: analyst/bj394-n7-mixed-full-history (worktree .worktrees/bj394-n7-mixed)
Base: origin/main @ 5e8bed4

## Current HEAD
Feature complete; package built + verified; tests green; PR submission done by
finalize tooling.

## What was delivered
1. src/n7_mixed_full_history/ — contract.py + pipeline.py (frozen evidence
   cutoff, census ledger, extension panel/timing/settlement, frozen
   pre-extension mapping via the shared cutoff client, action transform mirror,
   R3/C1E3/R0 + MIXED_50_50 + FRACTIONAL_50_50 schedules, statistics boards,
   machine decision, build/verify).
2. scripts/run_n7_mixed_full_history.py + verify_n7_mixed_full_history.py.
3. tests/test_n7_mixed_full_history.py — #392 parity on the 2022-2024 overlap,
   budget identities, temporal discipline, tamper resistance (settlement PnL,
   ledger line, manifest forgery, source trace, promotion), decision vocabulary.
4. results/n7_mixed_full_history/ — evidence package (13 files, MANIFEST.json).
5. docs/research/Issue-394-N7-Mixed-Full-History.md, notebook
   notebooks/research/n7-mixed-full-history/Issue-394-N7-Mixed-Full-History.ipynb
   (executed 8/8 cells), figure
   docs/research/figures/issue_394_n7_mixed_full_history.png.

## Decision
verdict = NO_MIXED_N7_EXTENSION_INCREMENT.
Failed gates: R3_2025_positive (2025 R3 control negative -13,722 on the 15
2025-issue native surface), extension ex-largest negative for every arm
(R3 -13,755 / C1E3 -892 / mixed -6,878 on 76 extension issues), no annual
extension-year reversal (2025 mixed R3 negative), moving-block p05 lift
negative on extension and ALL.  Mixed portfolio and both standalone arms are
pooled-positive but the tail-removed and bootstrapped evidence is negative.
No promotion; historical evidence only.

## Key decisions and why
- Core years reuse the accepted #392 EXPANDING_EQUAL mapped surface + accepted
  corrected-N7 settlement; extension pipeline reconstructs bundles and proves
  exact parity on the 2022-2024 overlap (tests).
- Extension mapping: shared fit_issue_mapping called per extension target with
  the SAME frozen EVALUATION_YEAR cutoff (pre-extension boundary =
  2024-12-31T06:00:00Z = min fixture decision of eligible 2025 targets).
  Per-target receipts bind each target's EvaluationEpoch to the frozen
  artifact.  80 eligible targets (15 in 2025, 65 in 2026).
- Evidence cutoff frozen at 2026-08-25T07:50:00Z (execution start).  All
  trusted settlement available strictly before it.
- Extension timing: modeling_plus_2026 for <26051, runtime beidan_live for
  >=26051 (never mixed per key); runtime self-consistency gated (kickoff in
  HKT wall time vs UTC settled receipt); 26-row 26051 overlap discrepancy
  between the stale modeling snapshot and runtime is disclosed in the source
  receipt (not a gate) because runtime is authoritative there.
- Settlement: 2025 only 25011-25042 exists in the canonical xlsm lineage;
  25043-25125 have NO settlement evidence in any source -> excluded census.
  2026: modeling_plus trusted rows 26011-26050 + live observed 26051-26087.
  26087/26088 have no proxy surface -> excluded (ledger reason
  EXTENSION_EXCLUDED_NO_PROXY_SURFACE).
- Mixed 50/50 = CNY512 (128 R3 tickets x 2 units) + CNY512 (216 C1E3 tickets,
  1 unit + 40 extra by the accepted canonical residual order); fractional
  counterfactual keeps the ideal continuous stake.  Integer-vs-fractional
  reconciliation: on ALL, integer adds +11,479 CNY over fractional, entirely
  on the C1E3 arm (R3 mixed == fractional exactly).
- action transform: prepare_actions_years mirrors the frozen
  qeu_threshold_n7.prepare_match_actions byte-for-byte except the year gate;
  parity proven on core rows in tests.  The accepted prepare_match_actions
  binds ALL_YEARS=2020-2024 and would drop extension rows.
- Deterministic replay verifier: verify_package PASS (13/13 hashes + semantic
  replay).  Tamper tests (REQ-E06) all fail-closed.

## Known issues / residual risk
- 2025-05+ issues have no settlement evidence at the frozen cutoff; the
  "extension through 2026" census therefore contains 15 (2025) + 61 (2026)
  native-included issues on the exact-common denominator (227 total with
  2022-2024).  This is a settlement-availability reality, not a mapping gap.
- 26051 timing sources disagree on 26 rows (midnight-default artifacts and one
  stale kickoff); runtime is authoritative, disclosed in source receipt.
- Moving-block bootstrap p05 is negative across all extension contrasts even
  where the pooled lift is positive — expected and consistent with the verdict.

## Reproduction
PYTHONPATH=. python scripts/run_n7_mixed_full_history.py
  --repo-root . --data-root /home/drwho1985/workspace/soccer/beijing-lot/data --force
PYTHONPATH=. python scripts/verify_n7_mixed_full_history.py
  --repo-root . --data-root /home/drwho1985/workspace/soccer/beijing-lot/data
PYTHONPATH=. python -m pytest tests/test_n7_mixed_full_history.py -q
  (full suite takes ~20 min: extension fit is per-target through the shared client)