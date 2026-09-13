# #439 joint-coverage follow-up

Historical-only 200-issue probe, native Cutoff-bound frozen probability inputs; no fitting or cleaning. Issue #439 is the contract. Candidate targets 25%/30%, entry cost <=256 CNY. BREADTH opens new groups only; DEPTH opens affordable new groups first, then deepens held prefixes. No copies, no U/P hard caps. Allocation scenarios 256; independent evaluation 5000; seeds 42501/42502/42503. Initial capital 100000, issue ceiling 1024, unit2, payout .65 once.

## Stage 1

1200 frozen plans, independent settlement/budget replay PASS; 22 R assertions PASS; clean QMD render PASS. At target25% three seeds: net35645–40322, ROI20.23–22.86%, hit80–82issues, maxDD16261–16574. Target30% ROI17.07–18.44%, no convincing improvement over old summed-probability allocation. Greedy union and the previous sum optimizer differ in solver as well as objective; this does not isolate a pure causal union effect.

Artifacts: explicit persistent audit `audits/issue439-union-v1/stage1`; report `reports/issue439-union-v1/stage1`. Stage1 freeze bbbef67ddc5ca2c398da436fd2871a0f311e7b8673bc7130ab24b3cf6ac505b3. Results5c6502ec3f99b84acf5376d49b1ca832d860b7cf079c88a2f2d63bc984f86e3b. Re-run entry: Rscript scripts/run_n7_sweet_union.R CONFIG_JSON (explicit source catalog, new output). Report entry quarto/149_n7_sweet_joint_coverage.qmd with stages, prior_study, rank_dir, output_dir params. Tests: Rscript -e "testthat::test_dir('tests/testthat',filter='n7-sweet-union',stop_on_failure=TRUE)". Independent replay: project-python scripts/check_n7_sweet_union.py STUDY NEW_RECEIPT.

Stages 2/3 and final Codex review remain pending; not final acceptance.
