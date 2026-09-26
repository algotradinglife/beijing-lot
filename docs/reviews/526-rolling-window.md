# 526: rolling decision window and actual 26098 run

The user clarified that four hours is the lead between decision and eligible kickoff. The authoritative `match_decision_window()` now returns `[decision + 4h, decision + 28h)`, using elapsed durations. At Beijing 20:00 this remains the next whole calendar day. Tests cover daytime decisions, exact inclusion/exclusion boundaries, and DST elapsed durations. No historical fitting or cutoff availability rules changed.

## Actual run

Decision: 2026-09-26 12:18:05 Asia/Shanghai. Window: 2026-09-26 16:18:05 through 2026-09-27 16:18:05 exclusive. Plan: `inputs/26098_walkthrough/plans/26098-20260926-121805.rds`. The prior 10:49 next-day plan and 12:15 empty plan are trial evidence only, not actual purchases.

After first12 candidates yielded only4 matching market identities, capture expanded to slots52,56,57,61,63–78. Identity mismatches remain in coverage; slot56 has conflicting latest same-time euro quotes,70 lacks company82,76 lacks company432. The original QMD explicitly records these exclusions. Eight fixtures admitted; seven selected:52,57,61,66,68,72,75. 3222221 support,80 tickets,CNY160. Selected modeled probability mass0.09896575, not realized win rate. Prematch SP and EV remain unavailable. No bets were placed. All80 tickets are pending actual settlement.

## Local validation

`TMPDIR=<writable> R_LIBS=<primary>/r_lib Rscript --vanilla -e 'devtools::test("packages/beidan", filter="n7-(lubridate|pipeline-epoch|pipeline-candidates|pipeline-value)", reporter="summary")'`:726 assertions,0 failures/warnings/skips. Test mapping: lubridate104,candidates135,epoch145,value342. Log: sibling freeze worktree `.freeze-control/526-window-tests.log`.

`quarto render quarto/26098_walkthrough.qmd --no-cache --execute` with explicit project interpreter and writable TMPDIR/XDG_CACHE_HOME/DENO_DIR: exit0,zero cell-output-error,matching frozen path present. Log: `.run-control/rolling-render.log`.

QMD independent `codex review` scoped to QMD and live execution evidence: no findings. Reviewer independently reproduced frozen epoch and complete saved plan exactly. Log: `.run-control/526-qmd-review.log`. Production review log: `.run-control/526-window-review.log`.

Initial production review found fractional decision timestamps were truncated at the ISO boundary. The shared window and both POSIXct callers now preserve fractions; the existing string-based eligibility output retains its original schema. Final targeted tests: lubridate109,candidates138,epoch145 =392 assertions,0 failures/warnings. Funding/value tests were not repeated because the precision correction affects window selection only; previous342 passed.

Second review found the executable historical `quarto/n7_lubridate.qmd` still asserted23/25-hour DST days. Updated it to direct POSIXct bounds and24 elapsed hours. Both original26098 walkthrough and date-management QMD rendered in fresh processes with no errors after correction. No separate user walkthrough was introduced. Final review log: `.run-control/526-acceptance-review.log`.

Final targeted codex review: no actionable findings. Independent checks passed for DST, fractional boundaries, legacy string outputs and typed empty results. Reviewed implementation/test/QMD hashes before the following attestation: `526-reviewed-hashes.json`.
