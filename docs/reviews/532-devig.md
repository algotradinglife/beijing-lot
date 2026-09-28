# #532 per-company de-vig then average

Owner-requested implementation: select each company's latest pre-cutoff quote, normalize its three reciprocal odds, then equal-average those three probabilities across available members. The existing minimum-two/drop_member policy is unchanged. `euro_mean` now exposes prob_home/prob_draw/prob_away/n_members; it does not expose averaged odds. Projection consumes the probabilities directly and checks their sum, without inversing them or applying a second de-vig. Raw source odds and the historical frozen plan are unchanged.

Regression: odds(2,4,4) and(3,3,1.5), whose margins differ, must produce(3/8,1/4,3/8). The old odds-average calculation does not. Scaling one company's entire price triple by1.2 leaves both the aggregate and end-to-end projected probabilities unchanged. Minimum coverage/empty cases remain tested.

Checks: fresh Rscript --vanilla with devtools::load_all and testthat::test_file on package test-n7-pipeline-epoch.R and repository test-26098-walkthrough.R:162 assertions passed. Log .run-control/532-devig-tests.log. Roxygen help regenerated; unrelated generated change restored.

Clean, uncached Quarto render of verification copy .run-control/532-devig-validation.qmd, differing from original only by refresh_schedule/refresh_markets=FALSE, using saved real snapshots:19 admitted fixtures,57 probabilities,80 preview tickets. HTML tables inspected. Original plan80 pending,0 settled, remains separate. Command quarto render .run-control/532-devig-validation.qmd --no-cache --execute, with explicit writable TMPDIR/XDG_CACHE_HOME/DENO_DIR and project R_LIBS/RETICULATE_PYTHON. Log .run-control/532-devig-render.log. Original user refresh flags preserved.

Independent codex review scoped to implementation/tests/help/QMD reports no new defects; it independently passed epoch tests but did not render QMD. PI rendered it as above. Full command prompt and findings .run-control/532-devig-review.log. File hashes532-devig-hashes.json precede QMD attestation. pak::local_install to r_lib succeeded (.run-control/532-devig-install.log). No CI participation, merge or issue closure claimed.

## Calculation discrimination verified

A disposable R process replaced match_euro_mean with the old mean-odds-then-de-vig calculation while leaving the committed test expectations unchanged. Running the actual epoch testthat file produced5 failed assertions:3 in the hand-calculated expected-probability test,2 in the company-margin/projection invariance test; neither test errored. Therefore the suite detects the incorrect formula, not merely successful execution. Production files were never modified. Script .run-control/532-devig-mutation.R; output .run-control/532-devig-mutation.log. The unmutated implementation previously passed162 assertions.
