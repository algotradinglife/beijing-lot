# #532 source-order correction

The owner confirmed on2026-09-26 that equal displayed timestamps should use the newer source position. The saved Titan slot57 history is newest-first:17:14 rows are(1.57,4.1,5.25),(1.5,4.2,5.75),(1.53,4.1,5.25). Its current quote agrees with the first row. The parser previously sorted ties by SHA256, losing source order. It now uses stable chronological sorting, and the source adapter retains the first row per company/minute before validity filtering. Raw bytes retain every row; diagnostics count superseded records. The generic R selector remains strict for input without known source-order semantics. Removed the obsolete slot56 conflict exclusion from the original walkthrough.

Checks:
- `PYTHONPATH=packages/beidan/inst/python .venv/bin/python -m pytest tests/market_capture/test_service.py -q`:21 passed, including actual slot57 and source-order mutation. Saved slot39 now has1190 usable distinct-minute quotes rather than1208 rows;18 superseded rows are represented in diagnostics and original bytes.
- Fresh R `devtools::load_all`, then `testthat::test_file` for package test-match-markets.R and repository test-26098-walkthrough.R:26+10 assertions passed. Includes older conflicts and post-cutoff quotes not affecting latest selection.
-20 actual saved captures reparsed without networking, preserving original observed_at. R latest-quote selector for slot57 at17:30 now returns exactly(1.57,4.1,5.25) at17:14. Logs `.run-control/532-replay.log` and `532-order-real.log`. Old processed snapshot retained as markets-before-532.rds.
- `codex review` scoped to quote-order implementation/tests/QMD: no actionable defects; review independently reran21 Python tests. Full prompt/output `.run-control/532-order-review.log`; reviewed hashes `532-source-order-hashes.json` (QMD before this evidence annotation).
- `pak::local_install("packages/beidan",lib="r_lib",upgrade=FALSE,ask=FALSE)` succeeded. Restart R for already-imported Python modules.

This resolves the same-minute quote blocker in the earlier532 report. It is not full walkthrough acceptance: the independently reported slot74 missing fixed company177 remains separate. No issue closure, merge or CI work claimed.
