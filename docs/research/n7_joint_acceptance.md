# #424 retrospective research acceptance — R joint sleeve study

Study `n7-joint-r-v2`, selection commit `e5ba7f53c3626c10b2c7a73ea8d7b9998c492b8f`.
PR #428 follows merged PR #426 into `codex/424-research-base`; integration into main is separate.
This is the owner's already-exposed historical research, not an unseen validation.

## Research decision

The provisional PI classification is **COVERAGE_STRUCTURE_SIGNAL**, with no demonstrated capital superiority. It remains provisional until final Codex review is resolved.
Across 100 issues, QUALITY_PROB hits40 with ROI27.79%; JOINT_FULL hits53–60 with ROI0.26–26.03% (median2.00%). Its ex-best-issue ROI median is−4.98%, versus QUALITY15.21%. Matched97-issue full-minus-quality ROI difference is−22.31pp, issue-cluster bootstrap95% interval[−67.01,16.39]. This is descriptive uncertainty, not a correction for repeated search.

UNION_PROB has median58 hit issues,44 profitable issues, ROI10.40%; JOINT_UP without the risk gate has median ROI13.93%. These are trade-offs, not a dominant replacement. Different column medians can come from different seeds. The risk gate constrains an artificial five-round distribution, not actual chronological drawdown. The strongest raw-return old reference, MONOLITHIC_PROB512, has ROI52.98%, ex-best5.82%, and max drawdownCNY20,641; its broader candidate access prevents a clean attribution to decomposition.

Retain the simple quality ranking as the economic comparison and the union-only solution as the coverage comparison. Do not promote the full constraint stack based on this result. No additional seed/threshold search was made after opening this run's settlements.

## Contract coverage and limitations

- R enumerates canonical2187 states and probability/value arrays, constructs PROB64/VALUE64/frontier64 options and jointly chooses8 options. CRAN HiGHS solves the sparse MILP; deterministic policy and numerical tolerances are frozen.
- New arms share the same24 candidate match sets,500 shared selection worlds,10000 independent numerical-check worlds and3 seeds. Full constraint=return+U4/P3+mean five-round max drawdown; each arm/seed freezes before the evaluation opens the audit.
- Per-option coverage floor and expected-return frontier are independently checked. PROB/VALUE/frontier controls and coverage-floor cost evidence are retained in the predecessor sleeve reports; new union/return/U/P/risk add/remove comparisons isolate portfolio constraints. Candidate budgets24/240/960 and variable depths remain reports135–137, not hidden changes in this run.
- All2400 plans independently replay: identity,512unique tickets or explicitcash,exact64states/sleeve,p/q accounting,one ticket-level0.65,shared-scenario union,return,U/P and synthetic path risk. Original source/hash-bound files remain immutable.
-100issues×8arms×3seeds plus600 prior monolithic rows=3000 report rows. Constraints force3 cash issues for U/P arms; both cash-inclusive curves and97-issue matched-budget comparisons are reported. Cash retention is not alpha.
- Sleeve/state identities and deterministic full-state reconstruction remain in frozen plans/source bundles. Earlier sleeve-level distribution/diversity/depth tables and interfaces remain the PR426 evidence; this PR adds joint portfolio construction and risk/ablation results.
- QMD reports per-issue stake,gross,net,ROI,hits; curves and absolute/relative drawdowns; streaks,underwater duration,worst5/10/20windows,largest payout contribution,ex-best,exposure/payoutHHI,seed ranges and paired issue-cluster bootstrap. It provides typed structure/head plus expandable complete display-seed rows. Full3-seed rows are in the archived input.
- Only2010 exists here. Year-exclusion removes the entire sample; cross-year/ex-largest-year comparison is therefore unavailable, not passed. Within-year halves are descriptive.
- p is the frozen calibrated market model; q is raw market. Historical source/label availability is unproven; historical_admission=false. No new fitting or retrospective target labels enter selection. Freeze does not erase prior exposure.
- The accounting path assumes previous issue proceeds have settled before the next stake. Real overlapping decision/settlement clocks are not established; no operational bankroll claim.
- The finite24G candidate set and fixed node/gap policy do not prove a global optimum over all possible seven-match sets. PROB and VALUE are exact rankings; frontier and portfolio MILPs are bounded by declared tolerances.
- No #425/#427 routing, future collection, other issue lifecycle changes, or main integration is part of acceptance.

## Implementation / automated test map

| Implementation | Automated evidence |
|---|---|
| r/n7_joint_sleeves.R: validate,options,worlds,returns,path_drawdowns,solve,plan,issue | tests/testthat/test-n7-joint-sleeves.R (54 assertions): exact toy optima, binding U/P/return/risk, dependence, cutoffs, identity, deterministic generation, real numerical boundary regression |
| src/n7_joint_study.py: run_joint_issue,freeze_joint_study,evaluate_joint_study | tests/test_n7_joint_study.py: source/code/plan binding, no settlement during freeze, later settlement mutation invariance and evaluation integrity |
| src/n7_joint_check.py: check_joint_plan,check_joint_study | tests/test_n7_joint_check.py (5 tests): independent replay and source/packed/world/accounting mutations, exact identity, fractional-code rejection, probability-only1e-14 R serialization tolerance |
| r/n7_joint_report.R: exposure,report,bootstrap | tests/testthat/test-n7-joint-report.R (25 assertions): funded/cash matching, ROI/drawdown, payout share, physical fixture/outcomeHHI including matrix/list ordering, clustered bootstrap and insufficient sample |
| thin R/Python commands and QMD | actual100-issue run, full2400 replay, fresh executed QMD and visual inspection |

Transitive inventory: `n7_joint_transitive_functions.csv` lists all274 Python function definitions in this run's44 hash-verified transitive source files, reconstructed from the clean frozen checkout. Prior `n7_sleeve_transitive_functions.csv`/dependency receipts also inventory the broader imported pre-rule surface. This run's machine receipt binds the complete shared implementation closure, imported helpers and package parent modules. Active new path is R validation via shared Cutoff/ranking contracts → existing R state tables → R options/worlds/MILP/packed plan → shared stable hashing/freezing → authoritative `settle_single_tickets` only after freeze. Reporting imports existing equity/summary functions. No learned artifact is fit, tuned or admitted here; legacy imported definitions are evidence, not new clean learning interfaces. No temporal utilities were copied.

## Reproduction and verification

Environment: project Python3.14.4, R4.6.1, Quarto1.10.18; package versions in config/n7_joint_runtime.json and config/n7_joint_report_runtime.json. Install during setup, never render. Use a checkout matching the frozen implementation, with explicit project Python/R library paths.

```
Rscript --vanilla tests/testthat.R
$PROJECT_PYTHON -m pytest tests/test_n7_joint_study.py tests/test_n7_joint_check.py -q
$PROJECT_PYTHON scripts/check_n7_joint.py --study data/derived/fundamentals_417/n7-joint-r-v2
quarto render quarto/139_n7_joint_sleeves.qmd --execute-dir . --execute --no-cache
```

Full R suite passed at selection version; corresponding updated report tests passed.52 relevant Python tests passed at selection version; updated checker5tests passed. Shared cutoff governance passed. Independent replay PASS2400. Fresh actual QMD render has9tables,2plots,zero error blocks; Chinese labels, units,10arms,3seed curves and100period span visually inspected. Owner disabled remote CI; it was not re-enabled, these are local results.

The default QMD reads the committed compact accounting archive, verifies its body hash, and recalculates descriptive tables/figures. It does not reconstruct selection from that archive. Source mode verifies the frozen raw/plan/result bindings. The outer acceptance receipt records current report/checker/entrypoint hashes, the selection closure, source hashes, output hashes and verification evidence. That distinction prevents a portable summary from claiming to be the full freeze package.

V1 aborted before all-plan freeze/evaluation on an actual HiGHS tolerance violation in100913. V2 used explicit1e-9 and rejected invalid numerical incumbents; the original failure fixture is retained and tested. The all-study checker originally compared serialized probabilities byte-exactly; jsonlite's15-digit serialization differs at~3e-16. Only six p/q numeric fields now allow absolute1e-14, with larger perturbations and identities still rejected. No tickets or settlement results were changed for this replay correction.

Final review and lifecycle evidence will be recorded after the independent Codex verdict; this document alone does not close the issue.
