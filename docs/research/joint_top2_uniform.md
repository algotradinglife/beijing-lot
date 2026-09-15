# JOINT / Top2: uniform-calendar replay

The earlier chart combined the 94-issue Top2 experiment with the 390-issue outside-window experiment. Their HANDICAP freeze calendars differ. That chart is superseded and must not support a controlled strategy comparison.

`quarto/182_joint_top2_uniform.qmd` regenerates ORIGINAL and HARD tickets for every one of the 484 post-warmup issues, using the single 49-block model collection in `top2-outside-v4`. The 94-issue replay inputs come from `factorial-drawdown-v1`, which binds the same model collection; no outputs from `handicap-top2-v1` are admitted. All tickets are frozen before the settlement stage. No model is refitted and no thresholds are selected in this rerun.

Three ledgers are compared: verified old JOINT, HANDICAP ORIGINAL, and HANDICAP HARD. ORIGINAL must match the already independently verified factorial ledger on every issue's spending and payout. HARD retains ORIGINAL groups and ticket count; only the purchased outcome combinations change. Therefore ORIGINAL versus HARD isolates the purchase rule; old JOINT versus HARD compares two complete methods with different probability foundations.

The common scope is 100708–121114: 305 issues before the drawdown, 94 in it, and 85 after it. The first ten issues of the 494-issue source snapshot are model warmup, not filled with another model. The fixed parameters are CNY 1,024 budget per issue, CNY 100,000 starting capital, CNY 2 tickets, and one ticket-level 0.65 payout factor. Unspent funds remain cash. Historical availability proxies and the legacy frozen-model limitation remain; this is research, not proof of prospective profitability.

## Reproduction

Render from the repository root with `--execute-dir` set to that root, `--no-cache`, and an explicit JSON/YAML parameter file. Declare `study`, `drawdown`, `baseline`, `output`, `labels`, `python`, and the SHA256 identities `receipt_sha256`, `drawdown_receipt_sha256`, `baseline_receipt_sha256`. The output directory must not exist. R packages and the Python environment must already be installed.

The business implementations are reused unchanged: `third_outcome_ticket_plan`, `third_outcome_ticket_settle`, `strategy_equity_curves`, and `n7_baseline_comparison`. Their ticket and comparison tests are `tests/testthat/test-third-outcome-tickets.R` and `tests/testthat/test-n7-baseline-comparison.R`. Full ledger replay and independent outcome-enumeration checks complement those tests.

## Final evidence

The full 484-issue rerun reports old JOINT net CNY 53,342.31, ROI 12.3975%, max drawdown CNY 23,852.02; uniform HARD net −CNY 7,385.56, ROI −1.8568%, max drawdown CNY 53,179.60. In the 94-issue drawdown window HARD net is −CNY 6,042.58, not the approximately +CNY 63,881 from the earlier independent-calendar experiment. Lower end-window loss is not lower within-window maximum drawdown: HARD is CNY 25,807.75 versus JOINT CNY 23,852.02.

The 182 execution completes all computation and receipt generation, but this environment's Quarto project HTML postprocessor fails resolving the entry filename. Preserve that failed wrapper log; do not claim a successful single-step render. The report-only entry `quarto/183_joint_top2_uniform_report.qmd` reads the hash-verified generated results and renders successfully from a clean standalone staging directory with explicit `study` and `receipt_sha256`. It has no fitting or selection logic. Source and staging copies must be byte-identical. Thus execution and report rendering are separately evidenced, rather than rerunning or substituting different results for display.

The independent replay verifies all 484 issues, 4,820 group/rule options, complete ORIGINAL/HARD funded group identities and depths, original-state enumeration/ranking, exact model blocks, official payouts, complete issue accounting and no-bet cash. Tests: 30 ticket assertions, 16 comparison assertions, and 6 regression assertions evaluating the actual report input expression, all passing. Cutoff governance passes. Final artifacts reside under the explicit `joint-top2-uniform-v2` evidence snapshot; failed first-run outputs are not final evidence.
