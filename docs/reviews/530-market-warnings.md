# 530: native-ID market alignment with advisory discrepancies

Owner correction: one reliable ID alignment is sufficient; name/time differences should warn instead of rejecting quotes. Titan/Nowscore native ID remains the identity anchor. Native ID disagreement is an error, while home/away spelling and kickoff differences are recorded as identity diagnostics and readable coverage detail. Coverage remains ok when both markets contain usable quotes. Nowscore remains the schedule/time authority. Raw Titan metadata remains in saved source bytes.

The R input adapter preserves fixture/native-ID binding and warns instead of rejecting changed name/kickoff metadata; its returned schedule values are current supplied values. No temporal availability rules or saved plan contents changed.

Validation:
- `PYTHONPATH=packages/beidan/inst/python .venv/bin/python -m pytest tests/market_capture -q`:20 passed, no skips. Tests cover wrong native ID, advisory names/time, coverage visibility, preserved quotes and real slot63 bytes with provenance.
- Explicit project Python and `devtools::test("packages/beidan",filter="^match-markets$",reporter="summary")`:24 assertions passed. Tests verify ID errors, warnings on names/time and unchanged quote counts/current supplied kickoff.
- Offline replay of actual captured responses using their original observed_at:20/20 coverage ok,9 previously name-rejected fixtures recovered. Slot63:1306 euro rows,150 totals rows,2 translated-name warnings. Original capture preserved as inputs/26098_walkthrough/markets-before-530.rds. No fabricated collection time.
- Original26098 QMD rendered cleanly using real data, no execution errors; 12:18 frozen plan remains unchanged. Local refresh_schedule=TRUE is owner preference; committed default remains FALSE.
- Updated installation with pak::local_install. Restart R to unload the previous Python module.

Logs: `.run-control/530-{python-tests,r-tests,replay,render,install}.log`. Review: `codex review` scoped to #530 implementation/tests/contracts/QMD in isolated delivery worktree, `.run-control/530-review.log`. No CI work.

Final independent codex review: no actionable defects. Reviewer reran20 Python tests and24 R assertions and inspected actual replay/render evidence. Reviewed hashes before attestation:530-reviewed-hashes.json.
