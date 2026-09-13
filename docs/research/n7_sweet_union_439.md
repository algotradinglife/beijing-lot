# #439 joint-coverage follow-up

Historical-only 200-issue probe, native Cutoff-bound frozen probability inputs; no fitting or cleaning. Issue #439 is the contract. Candidate targets 25%/30%, entry cost <=256 CNY. BREADTH opens new groups only; DEPTH opens affordable new groups first, then deepens held prefixes. No copies, no U/P hard caps. Allocation scenarios 256; independent evaluation 5000; seeds 42501/42502/42503. Initial capital 100000, issue ceiling 1024, unit2, payout .65 once.

## Stage 1

1200 frozen plans, independent settlement/budget replay PASS; 22 R assertions PASS; clean QMD render PASS. At target25% three seeds: net35645–40322, ROI20.23–22.86%, hit80–82issues, maxDD16261–16574. Target30% ROI17.07–18.44%, no convincing improvement over old summed-probability allocation. Greedy union and the previous sum optimizer differ in solver as well as objective; this does not isolate a pure causal union effect.

Artifacts: explicit persistent audit `audits/issue439-union-v1/stage1`; report `reports/issue439-union-v1/stage1`. Stage1 freeze bbbef67ddc5ca2c398da436fd2871a0f311e7b8673bc7130ab24b3cf6ac505b3. Results5c6502ec3f99b84acf5376d49b1ca832d860b7cf079c88a2f2d63bc984f86e3b. Re-run entry: Rscript scripts/run_n7_sweet_union.R CONFIG_JSON (explicit source catalog, new output). Report entry quarto/149_n7_sweet_joint_coverage.qmd with stages, prior_study, rank_dir, output_dir params. Tests: Rscript -e "testthat::test_dir('tests/testthat',filter='n7-sweet-union',stop_on_failure=TRUE)". Independent replay: project-python scripts/check_n7_sweet_union.py STUDY NEW_RECEIPT.

Stages 2/3 and final Codex review remain pending; not final acceptance.

## Stage 2

1200 additional plans, independent settlement replay PASS, clean combined QMD render PASS. Target25% DEPTH: stake190496–190614, net40871–50857, ROI21.45–26.68%, hit88–92issues, DD14532–16671. Seed42501 gains only549 CNY versus BREADTH for14120 additional spend; seeds42502/42503 gain12812/8848. Target30% DEPTH ROI13.39–15.63%; extra hit issues do not translate to better net return. Thus no uniform depth advantage. Stage2 freeze and exact plan hashes are in audits/issue439-union-v1/stage2/evaluation-receipt.json.

The label-free replay entry also checks exact selected IDs/depths and allocation-world union coverage. Budget-control prototype reuses original #433 partition/allocator and passes36-plan settlement and label-free replay. Stages1/2 full final allocation replay and Codexreview are pending.

## Review corrections and v3 execution

Codex review found three defects before final acceptance: the reduced control policy list lost legal depths contributed by C12 policies; Python implementation/rank provenance were not bound to the freeze; and a completely unfunded batch produced untyped empty CSVs. All are fixed. Controls now retain the full original policy depth union before selecting evaluated policies. `src/n7_union_inputs.py` binds the source catalog, rank receipt, exact source bundles/cutoffs and shared transitive Python implementation closure; runners and replay verify it. Both runners retain typed empty tables and stop if implementation files change during a run.

Regression validation: 17 Python tests, including three full cash-only runner/checker/replay cases and saved original shared-depth control equivalence; 213 affected/shared R assertions. Codex third code review found no remaining actionable code defects. Earlier v1 results above are preliminary; v2 interrupted runs are debugging evidence only. Final v3 generation, full allocation replay and final QMD acceptance remain pending. Authoritative final outputs will be `audits/issue439-union-v3`, with no overwriting of earlier evidence.

Exact Python command: `RSCRIPT=/usr/local/bin/Rscript R_LIBS_USER=PROJECT_R_LIBRARY OPENBLAS_NUM_THREADS=1 PROJECT_PYTHON -m pytest tests/test_n7_union_inputs.py tests/test_n7_sweet_union_replay.py tests/test_n7_union_empty_runner.py -q`. R integration tests additionally require `FUNDAMENTALS_PYTHON=PROJECT_PYTHON` and `PYTHONPATH=REPOSITORY_ROOT`; the first two broad attempts lacked these environment settings and were rerun successfully after correction.
