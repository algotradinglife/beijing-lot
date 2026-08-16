# HANDOFF — Issue #237 (BJ-UNIFIED-POWER-FEATURE-SUPPORT-001)

- **SESSION**: bj237-power-feature-support / 2026-08-16 (engineer profile)
- **Branch**: `engineer/bj237-power-feature-support`
- **Base**: 784a23b (origin/main, 2026-08-16)
- **Worktree**: `~/beijing-lot-237`
- **Status at handoff**: EV Review (PR ready)

## What was done

1. **Root-cause the accepted 9-issue power support** (REQ-PW06):
   - #180 froze only the #134/#179 candidate-role universe: 189 of 702 issues
     (26.9%). The remaining 73% of issues never entered #180's power computation.
   - #229's P_POWER_BJLINE = 234 cells / 9 issues is the intersection of the
     #180 freeze with the #229 inference-cell space and native-line boundary —
     independently reproduced from published artifacts (`ppower_intersection_reconstruction.csv`).
   - Identity loss is small (2,566 rows / 6 issues missing team ids; dup keys 0
     after id filter); the dominant loss is the candidate-pool gap, then
     causal/line/triplet gates.
2. **Rebuilt causal league/team power features on the full #203 decision-epoch
   space**: 305,517 causal publishable cells across 344 issues (2019–2025) —
   ~1,306× cells / ~38× issues vs accepted #180.
3. **Delivered the package** under `results/bj237_power_feature_support_v1/`
   with immutable Parquet (features, diagnostics, support summary, calibration
   through 2023), schema, manifest with source receipts (internal DB hashes +
   external Football-Data census), SHA256SUMS, waterfall + reconstruction CSVs,
   REPORT.md.
4. **Tests**: 23 passing incl. REQ-E06 tamper self-defense (probability /
   ledger-digest / manifest-hash / line forgery all detected). Independent
   verifier `scripts/bj237_verify_package.py` exits 0.

## Key decisions

- Feature engine = accepted #180 `bj180_team_matchup_core.py` (sequential
  EWMA/Elo/poisson state machine), driven on #203 issue-level
  `feature_cutoff_ts_utc` decision epochs; no bespoke optimizer/serialization.
- Completion proxy = 180-minute embargo (source has no completion timestamp,
  verified in #180 source binding).
- Target rows with `kickoff < epoch` dropped (15 corrupt rows incl. one
  1899-12-29 timestamp); publishable only on the native BJ line grid
  `{-3..3 step 0.5}` with normalized 3/1/0 triplets.
- Sealed-label policy: calibration table is asserted `year <= 2023`; 2024+
  outcomes never opened for design.
- TEAM_PRIMARY configuration frozen; conservative/responsive arms available in
  core for later sensitivity work.

## Known limits

- Historical completion is proxied (no completion timestamp); matches inside
  the embargo before an epoch are excluded from history but still publishable
  as targets.
- 2025 xlsm coverage partial; 2026+ lives in beidan_live.db (not part of this
  historical rebuild).
- Football-Data files are census-recorded as external candidates but not yet
  identity-mapped into canonical team/league space (separately countable, not
  silently merged) — per source priority in the contract.

## Next steps (for EV / PI)

- EV: fresh checkout, re-run `scripts/bj237_verify_package.py`, pytest, and
  notebook clean-run; tamper attacks beyond the four built-in ones welcome.
- PI: decide whether the 344-issue power support is sufficient for the unified
  learner's pre-event estimate role, and whether Football-Data identity mapping
  should be a follow-up under #232/#234.
