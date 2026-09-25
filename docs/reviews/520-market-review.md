# #520 market acquisition review evidence

Reviewed runtime revision: `95d18baa404b8b6ebede4ac79c4eeecac49204a8`.

The original `quarto/26098_walkthrough.qmd` remains the sole analysis entry point. No tests execute inside it. Its reviewed source hash is recorded before adding the non-rendered evidence pointer below.

## Review and resolution

- `codex review --commit d6b2f2ce`: three P2 findings; fixed stale identity reuse, per-request spacing after retries, and fixture attribution in diagnostics.
- `codex review --base origin/main` (round 2): two P2 findings; partial markets no longer count as successful two-market coverage; SPECIAL tickets remain unresolved in progress display.
- `codex review --base origin/main` (round 3, including integrated status change): one P2; raw bytes survived interruption but observation metadata did not. Each response's receipt now persists before parser/next request.
- `codex review --commit 95d18baa404b8b6ebede4ac79c4eeecac49204a8` (round 4): **no actionable regressions identified**, 19 service tests rerun. This is targeted verification of the sole remaining finding after the full review, not a claim that the final command re-reviewed every unchanged file.
- Explicit match-state parsing was separately reviewed under `docs/reviews/520-status-evidence.md`; its commit was integrated without changes.

## Local checks

Environment: project Python `/home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python`, R_LIBS primary repository `r_lib`.

- `PYTHONPATH=packages/beidan/inst/python <python> -m pytest tests/market_capture -q`: 19 passed.
- `<python> -m pytest tests/scripts/test_nowscore_score_model_history.py -q`: 7 passed, without PYTHONPATH, confirms repository client still imports the shared package parser.
- `Rscript -e 'devtools::load_all("packages/beidan",quiet=TRUE); testthat::test_dir("packages/beidan/tests/testthat",filter="n7-pipeline|match-markets",stop_on_failure=TRUE)'`: 1,248 assertions, zero failures/warnings/skips (368.1 seconds). Subsequent changes only touch Python receipt/coverage and QMD progress, whose corresponding checks pass.
- `Rscript -e 'testthat::test_file("tests/testthat/test-26098-walkthrough-progress.R",stop_on_failure=TRUE)'`: 5 assertions passed.
- `quarto render quarto/26098_walkthrough.qmd --to html --execute --no-cache` with writable TMPDIR/XDG_CACHE_HOME/DENO_DIR: passed; 0 cell-output-error. Render used explicit actual saved schedule and market captures.

## Actual data result and limits

Bounded capture: ten selected September 27 fixtures, observations 2026-09-26 02:32:29–02:32:49 Asia/Shanghai. Nine passed native identity and both markets; slot 83 identity mismatch retained as an exclusion. Selected fixtures 81,82,84,85,87,90,91,96,98. European members fixed to 281/115/82/177/432 (Bet365/William Hill/Ladbrokes/Pinnacle/HKJC); totals company 8 uses its separate namespace.

Actual schedule plus actual market histories reached 9 admitted fixtures, 27 probability rows, 96 legal 3222221 tickets, 80 selected tickets, CNY160. Leg order 81,96,87,91,90,98,85. Supported probability mass 0.08916745; purchased mass 0.08068476. SP and EV remain missing, not replaced by European prices.

The target 2026-09-26 20:00 decision was still in the future during execution: this is a **predecision diagnostic**, not a frozen/executed decision or an actual purchase. No completed settlement/real return is claimed. Per-issue CNY1024 cap leaves CNY864 unused by this demonstration. Actual later quotes may change the plan.
