# Issue #232 — causal SP-backed divergence support handoff

[SESSION] 20260816_035949_fe1511f8

## Current HEAD

Worktree branch `engineer/bj232-issue` based on origin/main @ 8c597e3
(accepted #229 PR #231 HEAD c2d43cb).

## What was done

Built a new reusable package `src/divergence_support/` and published the
immutable evidence package `results/bj232_divergence_support_v1/` answering
the #232 controlling question: do existing or recoverable pre-event sources
produce issue-level causal SP support for #209?

Deliverables:
- `src/divergence_support/` — contract, census, waterfall (REQ-S06),
  diagnosis, recovery (decision-epoch SP triplets separate from de-vig,
  REQ-S05), reconciliation, modelability (REQ-S08), debt E1-E4 (REQ-S09),
  builder.
- `scripts/build_bj232_divergence_support.py` (build/verify/manifest),
  `scripts/execute_bj232_notebook.py`.
- `notebooks/research/issue-232/bj232_support_waterfall.ipynb` (executed,
  23 cells, 0 errors).
- `results/bj232_divergence_support_v1/` — census, waterfall, diagnosis,
  triplets, devig, relationship, reconciliation, modelability tables,
  REQ-S evidence, schema, DEBT_CLOSURE, MANIFEST, SHA256SUMS, REPLAY.
- `tests/test_bj232_divergence_support.py` — 16 focused + tamper tests.
- Roadmap update in `docs/research/roadmap.md`.

## Key decisions and reasons

1. Terminal disposition is `UNRECOVERABLE_WITH_CURRENT_SOURCES`. The
   waterfall proves: #214 SP observations (16,496 rows, issues 26051-26083,
   captured from 2026-05-02) begin exactly where the Q_BJ anchor causal axis
   ends (26049). No timestamped pre-event SP exists for any historical
   cohort in any committed or recoverable asset; #203's DATA_CARD
   adjudicates historical official 3SP as label-only.
2. Decision-epoch SP triplets ARE recoverable — 741 matches / 17 issues /
   2,223 cells (all 2026) — but they never intersect the Q_BJ anchor
   (2026-only, issues 26011-26049).  Raw SP prices and normalized de-vig are
   separate columns; the normalize(1/SP) relationship is proven per row.
3. EU de-vig has 2,976 causal cells on historical issues; POWER has 234
   causal cells (78 matches) on historical issues; neither overlaps the
   Q_BJ anchor (2026-only), so all three modelability interfaces are zero.
4. #229 evidence debt E1-E4 is closed in this package: external 40-hex
   `AUDITED_SHA` receipt, physical row identity/domain schema, crash-restart
   journal with kill/restart probe, append-only hash-chained protocol log.

## Verification

- Focused + tamper tests: 108 passed (16 new #232 + #229 suites).
- Ruff and `git diff --check`: PASS.
- Build via CLI: disposition `UNRECOVERABLE_WITH_CURRENT_SOURCES`;
  debt closure all_closed=True; 10/10 REQ-S evidence rows pass.
- Verify via CLI: 27 files match SHA256SUMS.json; semantic checks PASS
  (evidence/schema/debt/waterfall replay/binding).
- Notebook: 23/23 cells, 0 errors; notebook hash bound in MANIFEST.
- Waterfall ledger replays exactly: RAW - DROPs == rows; EXPAND == rows*3
  (or *1 for cell-level EU); EXPAND - cell DROPs == final cells.

## Known limitations / risks

- The E1 `AUDITED_SHA.json` currently carries the placeholder 40-hex; EV
  review must replace it with the exact reviewed PR HEAD before finalize
  (`--audited-sha <40hex>` on the build CLI).
- Raw recoverable assets (official 3SP export, live collector snapshots,
  sp-drift panel, 500.bjdc captures) are gitignored on the producer machine;
  this checkout records them ABSENT. The conclusion does not depend on them:
  even the lenient official-3SP timestamp gate yields only 102 candidate
  rows, all 2026 and identity-only in #203.
- No model fitting, no 0.65 at cell level, no 2024+ outcome opened.

## Next step

EV audit (fresh checkout, re-run tests/notebook/verify, tamper checks),
then PI review of the `UNRECOVERABLE_WITH_CURRENT_SOURCES` receipt and the
#209 data-capability decision.
