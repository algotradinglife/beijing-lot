# Expert models 2.0.0 (historical candidate)

Study: `data/derived/fundamentals_417/expert-refresh-96-v2/clock-verified-final`.
Report: `quarto/76_expert_refresh.qmd`.
The model identity is 2.0.0; the calibrated inference API remains 1.1.0.
Old catalogs and model directories are unchanged. This is retrospective fixed
holdout evidence, not virgin test data or a prospective prediction release.

## Reproduction

Use the configured project Python and R library; no render-time installation.
Use a **new output directory** when reproducing training. The ordered steps are:

1. `scripts/prepare_expert_refresh.py`: explicit prior study, predictor-clock study,
   latest complete clean projection and output paths. Verifies source snapshots;
   freezes 72 train/CV issues and 24 test issues, label-free.
2. `scripts/query_expert_refresh_labels.R`: contract, `train`, SQLite path, output.
   Queries only the nominated train issues through `query_nowscore_settlement`.
3. `scripts/attach_expert_refresh_training.py --study ...`: exact-ID admission,
   shared diagnostic clocks and exclusions. Copy the reviewed `fit-policy.json`
   to the new study before fitting; this policy must precede target evaluation.
4. `scripts/fit_expert_refresh.py --study ... --expert draw` and `--expert high`.
   Each refuses an existing output. CV, fitting and rate calibration use shared
   temporal_learning contexts. No target labels are opened here.
5. Run `scripts/freeze_expert_refresh.py --study ...` to freeze both model
   directories before querying test labels. Keep this immutable receipt.
6. Query the `test` partition using the same R entry point; then run
   `scripts/evaluate_expert_refresh.py --study ... --python ... --legacy-root ...`.
   Exact-version catalogs are isolated to this study, not registered as latest.
7. `scripts/replay_expert_refresh_inputs.py --study ...` independently rebuilds
   this study's nominated source inputs; source/feature/label changes fail.
   Evaluation also freezes `report-inputs.json`, binding settlement, training
   exclusions and all four prediction files. For an existing audited evaluation,
   explicitly call `freeze_refresh_report_inputs(study)` once to establish this
   retrospective snapshot; this does not certify earlier file history. Subsequent
   changes fail verification and require a new evaluation directory.
8. Render QMD with execution enabled, clean session, cache/freeze disabled.

## Prediction

Load the current release using `load_portable_experts` from
`src.fundamentals_portable_experts`, supplying the pinned
`config/expert_versions/portable-2.0.0.json`, `expected_version='2.0.0'`,
and explicit `model_root`, `source_root`, `provenance_root`, `repository_root`.
Use `predict_portable_expert(artifacts, 'draw' or 'high', frame, cutoff=...)`
for independent prediction. Roots locate the model bundle, audited source
snapshot, exact training code archive and current runtime code respectively.
Moving all four roots preserves model identity and predictions; missing or
changed files fail before deserialization. Only trusted audited bundles may be
loaded. Training replay warns rather than refusing.

For draw, omit `draw_weight` to use frozen CV policy; any explicit value in [0,1]
is recorded as a caller override. `draw_target_probability` is already blended.
Project it once into the score grid using `signal_rate_score_choices`. High
probability is the giving team's handicap-cover probability, not ordinary win.

No score protection, ticket allocation, or P&L optimization is included here.

## Paired active selection

At the user's instruction both experts are selected as 2.0.0 in
`config/expert_versions/active.json`. Use
`src.fundamentals_active_experts.predict_active_experts(frame, cutoffs=...,
selection_path=..., repository_root=..., python=..., draw_weight=None)`.
The explicit selection pins the portable manifest by hash; both experts and
all transitive source/code hashes are validated before either prediction runs.
Optional `model_root`, `source_root` and `provenance_root` arguments explicitly
locate separately mounted archives. `python` must identify the current project
interpreter. This changes the caller's selected models, not
the retrospective evidence or the old version catalogs. `draw_weight` applies
only to draw; high keeps its own frozen output. Prior version catalogs remain
available through the existing explicit-version router.

## Code delivery and required data

This change ships code, version selections, dependency pins and offline tests.
Raw pages, SQLite databases, trained pickle files and historical study outputs
remain separate data inputs; they are not copied into Git. To replay the actual
2.0.0 release, supply the audited `expert-refresh-96-v2` study and the upstream
snapshots/runtime archives named by its receipts. Missing files or mismatched
hashes fail closed; cloning the repository alone does not provide those inputs.

`config/expert_versions/runtime.json` declares the verified runtimes and direct
packages for this interface. CI generates synthetic data using
`prepare_expert_refresh_report_fixture.py`, runs the affected function tests and
renders QMD without scraping or access to the historical database. The synthetic
render validates reporting contracts, not the historical model's performance.

The scoped clean checkout passed the affected Python tests, the full existing R suite plus
the two new report/query suites, cutoff governance and an executed offline QMD
render. Historical evaluation remains: draw Brier 0.19315 → 0.19235 (1,087 games),
high-margin Brier 0.19329 → 0.18979 (111 eligible games). Those retrospective
results do not establish future profitability.

## Portable publication

`scripts/freeze_portable_experts.py --model-root BUNDLE --source-root SNAPSHOT
--provenance-root TRAINING_CODE --output NEW_MANIFEST` creates an immutable
manifest without refitting or altering original model bytes. Original source
identifiers are retained as provenance keys; sealed relative locators, never
those original paths, resolve files during loading. The exact-version legacy
router remains for archived rollback; it is not the current portable entry.
Relocation tests move models, sources and runtime together, remove their old
location, compare both predictions and reject subsequent source tampering.

## Reviewed clock repair

The original candidate omitted predictor clocks for 364 warmup rows. Existing
context/quote snapshots reconstruct all 364 strictly before fixture decisions.
`prepare_expert_refresh.py --repair-study ORIGINAL --clock-audit AUDIT
--source-root SNAPSHOT --output NEW_STUDY` verifies source hashes, replays shared
clock receipts and preserves all 4,195 rows and numeric features. Refit using the
unchanged policies, freeze, then evaluate and run `replay_expert_refresh_inputs.py`.
Both tree identities, leaf counts/probabilities and calibration estimates remain
identical. The reviewed manifest pins these newly validated receipts; the old
candidate remains archived. No new issues or target outcomes enter selection.
