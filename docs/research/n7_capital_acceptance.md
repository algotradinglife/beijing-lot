# Issue #425: research evidence and PI assessment

## Scope and decision

The local research result is **NO_STABLE_FRONTIER**, with a bounded
**SATURATION_SIGNAL** for the 4,096-CNY any-hit objective. This is a diagnostic
of 100 already-exposed 2010 issues, the 24 inherited candidate sets, the registered
depth grid and three simulation seeds. It is not prospective admission, a new
probability model, or a claim of global optimization.

The report supplies a budget-by-preference answer rather than recommending a
universal sleeve count. More frequent payout does not ensure a positive net
return. At 4,096 CNY, buying 2,048 of a single sleeve's 2,187 states can nearly
guarantee some payout while losing money overall. Among the 300 issue/seed
any-hit trials at that budget, 218 use one sleeve. At 1,024 CNY, the any-hit
strategy's median historical ROI is 3.48%, versus −22.41% at 4,096 CNY; median
hit issues rise from 65 to 98. These are separate seed medians, not one combined
portfolio or an unseen validation result.

Some lower-budget alternatives have positive historical ROI, but seed variation,
maximum-profit removal and higher-budget deterioration prevent a stable common
recommendation. Model-price ROI and realized settlement-SP ROI are separate.
Infeasible ROI-constrained policies retain cash and do not count as profitable
allocation solutions. All detailed answers and risk qualifications are in
`quarto/140_n7_capital_frontier.qmd`.

## Completion evidence

| Contract requirement | Inspected evidence | Local result |
|---|---|---|
| Inherited state/fixture identity and probabilities | Shared R matrices; independent NumPy reconstruction; source and implementation closure checks | PASS |
| Full depth curves, exact minimal threshold depth, budget and duplicate-ticket contracts | Depth/portfolio tests, full-curve replay and frozen physical plans | PASS |
| Four budgets, three seeds, all registered controls/preferences | 100 issues × 68 arms × 3 seeds = 20,400 plans; plus 900 separately labeled archived controls | PASS |
| Freeze before this run opens settlement | Complete freeze seal precedes verified restoration of the original settlement members; evaluator checks bindings | PASS |
| Shared outcomes across overlapping sleeves | Persisted optimization/evaluation worlds and independent full-study replay | PASS |
| Authoritative variable-budget settlement and one ticket-level 0.65 factor | Existing settlement API plus separate sleeve-state settlement reconstruction for all 20,400 plans | PASS |
| Explicit preference constraints, infeasibility, solver limits and bounds | Frozen parameters, solver diagnostics, tested small exhaustive allocations, report tables | PASS |
| Group counts, depth/coverage distributions, equal and monetary weighting, conditional support | 195,362 allocation rows, model answer/distribution tables and all period ledgers | PASS |
| ROI, drawdown, cash-stop paths, tails, recovery, matched spend, seed uncertainty | Tested R summaries and executed QMD tables/figures; year removal explicitly inapplicable to one year | PASS |
| Independent replay and portable report | Both replay receipts PASS for 20,400 plans; bound portable fixture | PASS |
| Clean executed QMD and visual inspection | Final render exits 0; 87 tables, 8,106 table rows, five embedded figures; all five inspected, clipped frontier label corrected | PASS |
| Final Codex review | Read-only review exits 0, no actionable defects; reviewer independently recomputed R summaries and checked hashes/receipts | PASS |
| Current native Issue Graph | Authenticated live read: OPEN, In Progress; no blockedBy/blocking, parent or subIssues; research base verified at 8c1713f1 | PASS |
| PI research acceptance | Contract, replay, tests, final render and Codex review reconciled; accepts NO_STABLE_FRONTIER within the stated diagnostic scope | PASS |
| PR submission | Delivery record below | PENDING |

PR submission remains the last delivery step. No merge, issue closure,
or other Issue lifecycle change is performed. This document is evidence and a
local research assessment, not a substitute for live GitHub graph state.

## Reproduction and test mapping

With declared dependencies installed, render from the repository root:

```sh
quarto render quarto/140_n7_capital_frontier.qmd --execute-dir . --execute --no-cache
```

The portable fixture is `tests/fixtures/n7_capital_study.json.gz`. Its body hash is
`2e4e4b77c3fdec20726a5318e2cf9da6c4b50dab108b7c7f46bba5235540d245`.
The complete freeze seal is
`325ef1df5521f3566963234f51ffff45c08314b649d43dc726d3cbd32fea45e1`.
The final HTML hash is
`77aabf9b1121d9cef45b3f0ffb554fae4fb3151291943dbfe48f0f5bdf7bc2da`.

The clean full R command `Rscript --vanilla tests/testthat.R` passed 65 test
files with the project R library and fresh provenance-bound fixtures. The final
frontier regression then passed 30 assertions. R functions map to
`tests/testthat/test-n7-capital-{depth,portfolio,issue,report,compare}.R`.

Using the project Python interpreter, the checker/archive test command
`python -m pytest tests/test_n7_capital_archive.py tests/test_n7_capital_check.py tests/test_n7_joint_check.py`
passed 19 tests. The orchestration command
`python -m pytest tests/test_n7_joint_study.py tests/test_n7_capital_study.py`
passed six tests, including completed-Future release. The original and
variable-budget settlement tests also passed. Shared cutoff governance passed;
the persistent storage layout check passed again after final report generation.
Remote CI stayed disabled as requested.

Full physical plans/worlds remain under the registered persistent root's
`audits/issue425-capital-v2`; the failed v1 run is preserved separately.
The final HTML, extracted figures, portable input and render receipt are under
`reports/issue425-capital-v2`. The portable report does not replace the full
freeze package. Local execution/review logs reside in the session's
`issue425-capital` review-artifact directory and must not be confused with
GitHub lifecycle evidence.

## PI delivery assessment

On 2026-09-13, authenticated live GitHub access was restored and the Issue contract
and native graph were re-read. PI accepts the #425 research deliverable: its
negative conclusion meets the contract, without requiring positive ROI or unseen
data. This acceptance concerns the research evidence, not permission to merge.

The target base is `codex/424-research-base` at
`8c1713f1a60617e9022d7224d067b396dd932607`. The branch also contains pre-existing
persistent-storage commits `544e36c0`, `3e9fafe4`, and `50811d54`, previously pushed
alongside the research. They are explicitly outside the final #425 Codex review's
scope. Their inclusion is disclosed for integration review; research acceptance
must not be interpreted as a blanket merge approval for those changes. Shared
working-tree changes from other sessions are not staged or submitted.

The current main experiment uses 24 inherited candidates and probability prefixes.
Coverage thresholds are minimum first-crossing targets, not a 25% upper cap.
The allocator records overlap/exposure but applies no U/P hard caps. These are
limits of this experiment, not implementations of earlier cap-and-expand ideas.

PR submission is pending; Issue #425 remains open and main integration is separate.
