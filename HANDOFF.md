# Issue #232 R2 fresh rework handoff

[SESSION] 20260816_142900_bj232_r2_fresh

- Role: Engineer (worker), issue #232, mode: candidate.
- Fresh rework after EV REJECT (PR #239, REWORK_TYPE=method, 2026-08-16).
- This is a FRESH rebuild — no resumed R1 session. R1 code was read only as
  reference material (R1 HEAD a3cb398 on engineer/bj232-issue).
- Worktree: engineer/bj232-r2-fresh based on origin/main @ 784a23b.
- NOTE: a duplicate parallel engineer session (PID 2446802) was terminated
  mid-run after it began writing conflicting files into this worktree; all
  files under src/divergence_support/ were re-verified as this session's
  implementation (no GateVerdict/sources.py remnants).

## What was delivered (R2)

1. `src/divergence_support/` — fresh implementation:
   - `causal.py`: THE single causal gate `observed_at <= decision_epoch
     <= kickoff` (EV C1) used by every module.
   - `disposition.py`: pure READY truth table (EV C2) with mutation tests —
     READY requires Q_BJ×SP positive AND (Q_BJ×EU×SP OR Q_BJ×POWER×SP)
     positive AND every chronological role (fit/tune/calibration) supported.
   - `waterfall.py`: full stage ledger with LINE_RECONCILIATION for EVERY
     source (EV E4), issue/date/native-line dimensions, official 3SP
     fail-closed LABEL_ONLY (EV C3).
   - `recovery.py`: decision-epoch SP triplets from #214 committed
     observations only, full frozen gate.
   - `reconcile.py`: EU/POWER independent-source alignment reusing the
     unified gate; POWER completeness uses team_primary_p* (EV C2).
   - `modelability.py`: issue-level interface summary consuming the
     reconcile views; disposition from the truth table.
   - `debt.py`: E1 binding requires the exact externally reviewed HEAD and
     rejects the zero placeholder (EV E1); E2-E4 preserved.
   - `verifier.py`: independent semantic verifier recomputing causality,
     de-vig, disposition, requirement set, source binding, schema, files,
     binding, waterfall reconstruction, manifest consistency and label-year
     cross-check (EV E2) — 9/9 tamper mutations blocked.
   - `manifest.py` / `publication.py`: #232-native manifest/replay/atomic
     writers (EV E3), no #229 resolver reuse.
2. `results/bj232_divergence_support_v2/` — immutable package, 28 files,
   MANIFEST + SHA256SUMS + REPLAY + disposition + evidence + DEBT_CLOSURE;
   CLI build/verify both PASS.
3. `notebooks/research/issue-232/bj232_support_waterfall.ipynb` — executed
   8/8 cells, 0 errors.
4. `tests/test_bj232_divergence_support.py` — 37 focused tests incl. C1
   post-kickoff rejection, C2 mutation tests, 11 tamper tests; 129 pass
   with #229 suites.
5. `docs/research/roadmap.md` updated.

## Key numbers (independent verification anchors)

- Frozen causal SP recovery: **376 matches / 16 issues / 1,128 cells**,
  all label-year 2026 — EXACTLY the EV independent recomputation of the
  frozen pre-event gate (R1 wrongly published 741 / 2,223 incl. 365
  post-kickoff matches).
- Q_BJ causal anchor: 228 cells / 76 matches (issues 26011..26049).
- SP source: #214 observations 16,496 raw -> 11,164 identity-matched ->
  1,766 causal matches -> 376 complete triplets (all 2026, issues 26051+).
- Q_BJ × SP = 0, Q_BJ × EU × SP = 0, Q_BJ × POWER × SP = 0.
- EU reconciliation: 2,976 causal de-vig cells (historical), 0 anchor
  overlap; POWER: 234 causal cells, 0 anchor overlap.
- Terminal disposition: **UNRECOVERABLE_WITH_CURRENT_SOURCES**.
- REQ-S01..S10: 10/10 pass on computed evidence (no hard-coded TRUE).
- Debt closure: E1-E4 all_closed=true with the externally supplied
  AUDITED_SHA (a3cb398c20be...). The zero placeholder is rejected at build.

## Key decisions and reasons

1. Fresh rebuild over R1 patching: EV REWORK_TYPE=method demands root-cause
   closure, not line fixes. The unified gate + pure truth table make the
   class of defect (half-gates) impossible to re-introduce.
2. Official 3SP is censused but NEVER recovered (#203 DATA_CARD label-only
   adjudication); even when the asset exists it drops at RAW with
   LABEL_ONLY_SOURCE.
3. READY requires all necessary conditions — a single positive cell cannot
   unlock #209 (contract modelability gate).
4. Verifier does not trust producer pass flags: it recomputes every decisive
   payload from the published tables plus the external trust anchor.
5. E1 binding: AUDITED_SHA.json must equal the externally reviewed HEAD;
   `"0"*40` fails validation even without an expected SHA.

## Known limitations / risks

- Disposition is UNRECOVERABLE: no causal SP support exists for any
  historical cohort (fit <=2021, tune 2022, cal 2023). Raw recoverable
  assets (data/ gitignored) are ABSENT in this checkout; the conclusion is
  independent of them (lenient-gate probe = 102 rows all 2026).
- 2024+ labels untouched; no settlement/final/payout column in any payload
  (verifier-enforced).
- candidate mode: EV should re-run pytest + notebook clean-run + CLI
  build/verify with the exact reviewed HEAD, plus additional tamper attacks.

## Next step

EV Review on PR; verdict PASS -> PI Review; REJECT -> Ready with defect list.
