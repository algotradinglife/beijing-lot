# Expert models 2.0.0 (historical candidate)

Study: `data/derived/fundamentals_417/expert-refresh-96-v2`.
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
   `scripts/evaluate_expert_refresh.py --study ... --python ...`.
   Exact-version catalogs are isolated to this study, not registered as latest.
7. `scripts/replay_expert_refresh_inputs.py --study ...` independently rebuilds
   this study's nominated source inputs; source/feature/label changes fail.
8. Render QMD with execution enabled, clean session, cache/freeze disabled.

## Prediction

Call the authoritative `src.fundamentals_draw_versions.predict_draw_version`
with `version='2.0.0'`, explicit `cutoffs` (one shared `Cutoff` per fixture),
`catalog_path=study/'draw-catalog.json'` or `study/'high-catalog.json'`, repository
root and project Python. Despite its historical name the RAW_TREE route supports
high-only artifacts. It returns versioned predictions and machine-readable
receipts; imports never scrape or write databases. Missing features remain
explicit. Training replay gives a warning, not a refusal.

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
The explicit selection pins both version catalogs by hash; both are validated
before either prediction runs. This changes the caller's selected models, not
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

The scoped clean checkout passed 52 Python tests, the full existing R suite plus
the two new report/query suites, cutoff governance and an executed offline QMD
render. Historical evaluation remains: draw Brier 0.19315 → 0.19235 (1,087 games),
high-margin Brier 0.19329 → 0.18979 (111 eligible games). Those retrospective
results do not establish future profitability.
