# HANDOFF — Issue #229 divergence-aware M×3 data profile (REWORK R1)

- Session: `20260815_102938_e3dab9` (fresh rework, no resume)
- Issue: algotradinglife/beijing-lot#229
- PR: #231 (rejected at ef852d56; this rework replaces it)
- Branch: engineer/bj229-rework-r1 → pushed as engineer/bj229-divergence-profile
- Base: 2dbcd88

## Completed

- Fresh `src/divergence_profile/` package (9 modules) with the five EV
  defect classes fixed; 54 focused tests all pass.
- Full package build: `results/bj229_divergence_profile_v1/` (61 files),
  disposition `READY_WITH_EXPLICIT_LIMITATIONS`, 357,705 cells / 119,235
  matches / 419 issues.  Verify command passes (60 files match SHA256SUMS +
  semantic checks).
- Report: `docs/research/issue_229_data_readiness.md`.
- Notebook executor: `scripts/execute_bj229_notebook.py` (nbclient in the
  linked main venv), with manifest-binding finalize step.

## Key decisions

1. **Match-level causal join (B1)**: #203 identity joined on (issue,
   match_idx); 377 issues have multiple kickoffs (audited: 0);
   post-decision = 15 cells / 5 matches on the #204 axis.
2. **EU alias policy (B3)**: #204 avg-EU cells are SAME_SOURCE_NON_INDEPENDENT
   (Q_EU == Q_BJ from the same market_probability); independent EU = #203
   devig only (2,976 cells).  This is why coverage dropped 50,904 → 2,976.
3. **POWER causally unavailable at decision epoch**: #180 cutoff (first
   kickoff) > #203 decision epoch for 4,440/4,674 cells → profiled only,
   not offered to #209.
4. **Half-goal lines (B2)**: float handicap, no rounding; EV goldens
   reproduce exactly.
5. **REQ-D01 fail closed**: pass=False while 15 post-decision cells exist;
   exclusions countable with stable reason codes; no hardcoded PASS
   anywhere in evidence.
6. **REQ-D09 evidence**: computed from filesystem (notebook + code present),
   not `root is not None`.

## Known issues

- Q_BJ_SP_DEVIG coverage = 0 (#214 observations did not match the axis);
  document, don't fake.
- 34,146 test-side cells (2026 live axis) lack #203 identity timestamps
  (DQ02 = 68,298 = 34,146 × 2 columns), excluded with NO_CAUSAL_EPOCH.
- DQ04 flags 3,648 missing native lines (test-side handicap gaps).
- Executed notebook must be produced by execute_bj229_notebook.py BEFORE
  the final manifest binding is committed (finalize step rebinds
  notebook_hash to the executed notebook).

## Next steps (if rework continues)

- Independent rebuild by EV at the exact new HEAD; verify command must
  resolve from repo root.
- #209 consumes only causally-available Q_BJ_CALIBRATED (+ optional
  independent EU on development issues); POWER/SP unavailable.
