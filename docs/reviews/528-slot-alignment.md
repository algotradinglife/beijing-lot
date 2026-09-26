# 528 current-issue slot alignment

Owner correction: current-period 500/Nowscore schedules align by validated issue plus slot; team-name/JEV judgments are unnecessary. Each parser still verifies its source page issue, duplicate slots still fail, direct mismatched slots fail, and single-source rows remain explicit. Names are retained verbatim; Nowscore remains primary for match fields. Handicap discrepancies remain data diagnostics rather than identity conflicts. Titan native-ID mapping is unchanged.

Deleted unused Python name-agreement helpers; removed current walkthrough's JEV blocks and credential requirement. The missing credential was independently checked without exposing secrets: no TYPESAFE_API_KEY in agent process and no project/user .Renviron files. No credentials created or modified.

Validation:
- `PYTHONPATH=packages/beidan/inst/python .venv/bin/python -m pytest packages/beidan/tests/python/test_issue_schedule.py -q`:123 passed,1 skipped (old optional control snapshot absent). Existing tests cover wrong source issue, duplicate slots and primary-source boundaries; new regression covers differing names/handicap with same slot and refusal of different slots.
- R cross-language `devtools::test("packages/beidan",filter="^issue-schedule$",reporter="summary")`, project Python explicitly selected:75 assertions,0 failures/warnings. Added slot method check on returned tibble.
- `quarto render quarto/26098_walkthrough.qmd --no-cache --execute`, writable TMPDIR/cache and explicit Python:exit0. Real146 rows now all identity_method=slot; diagnostics empty. User's refresh_schedule=TRUE preserved. Frozen12:18 plan unchanged; refreshed observations are not backdated to that cutoff.
- Package installation via pak::local_install updated project r_lib. Python-loaded sessions need restart for implementation reload.

Review command: `codex review` scoped to #528 files; local log `.run-control/528-review.log`. Validation logs: `.run-control/528-{python-tests,r-tests,render,install}.log`.

Review resolution: exclude the owner’s preexisting refresh_schedule=TRUE WIP from delivery; committed default remains FALSE. Final codex review (528-final-review.log) found no actionable defects. Offline delivery render also passed. Reviewed hashes before attestation are in528-reviewed-hashes.json.
