# HANDOFF — Issue #237 R2 (BJ-UNIFIED-POWER-FEATURE-SUPPORT-001)

- **SESSION**: 20260816_145000 (engineer profile, R2 rework after EV R1 REJECT)
- **Branch**: `engineer/bj237-r2` (based on `engineer/bj234-issue` @ d2cc56d —
  consumes the #234 canonical identity interface; C-04 requirement)
- **R1 PR**: #240 (REJECTED, AUDITED_SHA=e3db39c) — superseded by this R2 PR
- **Worktree**: `~/beijing-lot-237-r2`
- **Status at handoff**: EV Review (PR ready)

## What was done (R2)

1. **C-01 FAIL-CLOSED line semantics**: the R1 `_finite(NaN)=0.0` default
   silently turned 765 rows / 255 matches / 63 issues into 0-line
   publishable cells. R2 has a single fail-closed predicate
   `lib.line_is_publishable` (non-null + finite + native grid member);
   missing/NaN/off-grid lines are `line_ok=False`, `triplet_ok=False`,
   `power_probability=None`. Corrected headline: **304,839 cells / 344
   issues** (R1 claimed 305,517). Verifier now asserts line_ok⇒non-null
   grid AND ~line_ok⇒null (no `dropna()` blind spot).
2. **C-02 primitive-only PW06 gates**: `reconstruct_229_power_intersection`
   no longer reads `P_POWER_BJLINE_available`; every gate is rebuilt from
   primitives (vector presence → observed_at ≤ decision epoch → freeze
   triplet complete → exact non-null line equality). Independent result:
   **234 cells / 9 issues** (matches EV's independent recomputation).
   Gate-level rows/issues published.
3. **C-03 aggregation keys**: `support_summary` keyed by
   (issue, year, league, line) — 33,142 groups, rows sum 304,839 =
   publishable cells; `calibration_through_2023` keyed by
   (issue, year, league, line, outcome) — 78,012 groups. Match counts are
   per-issue (no cross-issue folding: matches sum 101,613 = distinct
   (issue, match_idx) pairs). REPORT annual table corrected (2025=15
   issues, 2020=35,781 cells).
4. **C-04 #234 canonical identity consumed**: `fixture_id =
   fix_{issue}_{match_idx}_{sha256}` per #234 contract; `identity_status`
   ∈ {CANONICAL, ALIAS, AMBIGUOUS, UNIDENTIFIED}; temporal alias validity
   (`alias_active`, future-alias rejection); duplicate (issue, match_idx)
   → AMBIGUOUS; unknown keys → UNIDENTIFIED (never fuzzy). Tests cover
   temporal validity, unknown alias, duplicate fixture, future alias
   mutation.
5. **E-01 13/13 remanifested semantic tampers detected**: outcome
   permutation, legal line rewrite, team swap, league rewrite, epoch
   shift, history-depth forgery, outcome-domain forgery, whole-issue
   digest forgery (manifest `issue_digests` anchor), support zeroing,
   calibration forgery, manifest source-hash forgery, schema clear, file
   deletion. Detection via cross-table anchors (power_p3/p1/p0 duplicated
   in diagnostics), aggregate recomputation, per-issue digest map, file-
   existence closure.
6. **E-02 atomic publication + schema + receipt closure**: builder now
   uses #234's `publication.atomic_publish_directory` (fail-on-existing,
   same-parent staging, fsync tree, atomic rename, rollback);
   `feature_schema.json` covers 4 tables with physical/logical types,
   nullability, domains, FKs; manifest binds `producer_commit_sha` and
   receipts only participating sources (`databases={xlsm}` + 3 package
   hashes); SHA256SUMS written once in staging; verifier recomputes source
   hashes, output counts, schema coverage.
7. **PROTOCOL-LOG.md** created with entries 001–006 (incl. E-01/E-02 debt
   closure). **SWEEP_EVIDENCE.md** documents the same-class full sweep
   (EV R1 requirement: declare all checked call points per class).

## Key numbers (all independently recomputed by verifier)

- publishable cells 304,839 / issues 344 (2019–2025)
- support groups 33,142; calibration groups 78,012
- #180 baseline: 234 cells / 9 issues (primitives)
- year table: 55/44/58/58/55/59/15 issues for 2019..2025
- tests: 56 passed; verifier: PACKAGE VERIFIED OK + TAMPER SELF-DEFENSE OK
  (13/13)

## Reproduce

```bash
git worktree add ~/beijing-lot-237-r2 origin/engineer/bj234-issue -b engineer/bj237-r2
cd ~/beijing-lot-237-r2
.venv/bin/python scripts/bj237_build_features.py --root . \
  --report docs/research/issue-237/REPORT.md
.venv/bin/python scripts/bj237_verify_package.py \
  --pkg results/bj237_power_feature_support_v2 --root .
.venv/bin/python -m pytest tests/scripts/test_bj237_power_features.py -q
```

## Known limits / risks

- Completion proxied by 180-minute embargo (no completion timestamp in
  source — #180 source binding).
- 2025 xlsm coverage partial (4,855 raw rows); 2026+ lives in beidan_live.db
  (not part of this historical rebuild).
- Only TEAM_PRIMARY configuration frozen; conservative/responsive arms
  available in core for later sensitivity work.
- Football-Data census recorded as external candidates, not yet
  identity-mapped (separately countable, not silently merged).
- #237 R2 is based on the #234 delivery branch (d2cc56d). If #234's
  accepted interface changes during EV, rebase #237 onto the accepted HEAD.

## Next steps (for EV / PI)

- EV: fresh checkout, re-run builder + verifier + pytest, review tamper
  gaps (expect 0), confirm 234/9 primitive reconstruction and 304,839
  headline, audit PROTOCOL-LOG/SWEEP_EVIDENCE claims.
- PI: merge #234 first (PR #242), then rebase/merge this PR.
