# PR426 staged delivery and integration contract

This PR delivers N7 sleeve research infrastructure, mechanism prototypes and
exposed historical diagnostics. It does not complete #424's original scientific
contract. This document implements the scope clarified in PI comment
[5646052579](https://github.com/algotradinglife/beijing-lot/pull/426#issuecomment-5646052579).

## Exact integration destination

Use the existing **layered research-branch integration**, not a retarget to main:

- Destination: `codex/424-research-base`, pinned at
  `2798b83a7b8fe31fe3e985c329d28c5ea201af5f`.
- Source: `codex/424-pi-review`; reviewed implementation
  `55fe32e91fadb1853dafc55c59f9bb35e7d4874c`, tree
  `492e20c0a0da02ea023f3ef754298384e7cec858`.
- Observed main: `d9bdcb829fe7dc2a712f4855570a1e4c833bb2d0`.
- Common ancestor: `2f1a38c469320fb4177b2b2b44ed3759bf0b57dc`.

Merging PR426 into this research branch would integrate only its seven existing
commits plus the delivery evidence commit(s); it would **not integrate anything
into main**. All 80 predecessor commits already belong to the destination.
Keep its history intact for pinned historical replay. Do not interpret this as
acceptance of those 80 studies, or as permission to merge their history into main.
Do not squash away the original implementation identities used by old receipts.

Main integration remains a separate, explicitly reviewed step. A future main-based
port can copy the scoped infrastructure and the five missing prerequisite files
with their tests, rather than cherry-picking all 80 historical commits. That port
must reconcile runtime/dependency declarations, cutoff governance and any changed
main implementation, then receive its own validation and PI decision. This PR
neither creates nor claims completion of that port.

## Predecessor audit

`git rev-list` identifies 80 base-only and seven main-only commits. `git cherry`
finds **zero patch-equivalent predecessor commits** in main; this does not mean
all their content is absent. Exact Git blob comparison of the inherited runtime
and literal R report-source closure finds **42 identical files, zero different
files and five absent files**:

| Missing from main | Purpose | Corresponding tests |
|---|---|---|
| `r/fundamentals_equity_curves.R` | Funded equity, retained cash and drawdown | `tests/testthat/test-fundamentals-equity-curves.R` |
| `r/market_conditional_summary.R` | ROI and removal-of-best-issue summaries | `tests/testthat/test-market-conditional-summary.R` |
| `src/n7_single_ticket_sampling.py` | Ticket representation and settlement | `tests/test_n7_single_ticket_sampling.py` |
| `src/n7_probability_gate.py` | Frozen candidate pool and probability/value selection | `tests/test_n7_probability_gate.py` |
| `src/n7_incremental_coverage.py` | Shared-world monolithic controls | `tests/test_n7_incremental_coverage.py` |

All five already exist at the pinned research destination. None requires adding
an unrelated study to the present PR. Their exact source blobs and latest
predecessor commits are recorded in `n7_sleeve_dependency_files.csv`. The other
42 inherited files (including shared `src/temporal_learning` machinery) are
listed individually with matching main blob IDs.

`n7_sleeve_predecessor_commits.csv` inventories all 80 commits: eight touched
inherited code in the audited closure, two additional commits are direct artifact
producers, and 70 are outside that runtime closure. These are touched-file and
direct-artifact observations, **not** a claim that only ten commits can ever be
needed to regenerate all historical source packages. They are not a cherry-pick
approval list. The current staged destination retains all history, while the
PR adds only its bounded diff.

The seven main-only commits are d9bdcb82 (#423), 327f5d04 (#420), 0a12c229 (#418),
4c7229a5 (#416 merge), e07ddf15, 5d70555f and bb359599 (#413/#414). This delivery
does not merge main into the research branch or alter those published modules.
Native GitHub relationships remain authoritative: #424 has parent #202 and no
blockedBy/blocking/subIssues; #419 remains blocked by #421. Code dependencies
in this inventory do not create or override native graph edges. #425/#427 are
prospective interface consumers, not declared graph dependents.

## Delivered surface and evidence boundaries

- Exact 2,187-state enumeration, canonical/official identities, probability,
  estimated payout/contribution, ranks and cumulative depth.
- R matrix and tidy `summary/depth/long` interface.
- Group state selection, shared-event simulation, complete-ticket allocation,
  independent accounting and immutable ledger checks.
- Fixed8×64, expanded pools, probability caps and U/P diagnostics already run.
- Corrected sleeve average, funded streaks and separate estimand fields. New
  sleeve plans have no mixed-unit `mean_coverage`; old evidence is not rewritten.

Fixed business constants are N=7, CNY1,024 per issue, CNY2 tickets and one
complete-ticket 0.65 factor. No free capital-reallocation feature, at-least-two-
sleeve-hit objective, additional parameter search or positive-ROI requirement
is added as a stage acceptance gate.

The import closure uses the existing authoritative
`src.temporal_learning.provenance.implementation_closure()`. The bound JSON
receipt lists Python modules and R literal `source()` edges. Parent-package
`__init__.py` modules are explicitly added as roots until the existing walker
reaches a fixed point; this adds 22 modules/73 functions missed by a submodule-
only traversal. The resulting Python inventory contains 58 files. Initial
independent review identified this P2 inventory gap; no shared provenance utility
or old experiment receipt was modified to repair this delivery inventory. The accompanying
`n7_sleeve_transitive_functions.csv` inventories all 283 Python function
occurrences in the transitive closure, including existing temporal helpers.
This is a structural inventory, not an assertion that each occurrence fits a
model or that every inherited function has newly passed an independent test.
Decision-facing sleeve/candidate/gate/sampling functions accept explicit cutoffs;
settlement and descriptive R projections do not select historical learning data.
Shared chronology/provenance implementations are unchanged. Historical input
availability remains diagnostic; no new causal admission or fitting is introduced.

## Inputs and replay

Runtime used for final implementation checks: Python3.14.4, NumPy2.4.6,
pandas3.0.3, SciPy1.17.1; R4.6.1 and Quarto1.10.18 with project-declared R packages.
Dependencies must be installed before running; no report installs packages.
Execute reports from repository root with `--execute-dir .`, `--execute` and
`--no-cache` so root-relative sources are explicit.

**Portable accounting replay** uses the five committed gzip fixtures:

```sh
quarto render quarto/134_n7_sleeve_portfolio.qmd --execute-dir . --execute --no-cache -P archive_fixture:tests/fixtures/n7_sleeve_portfolio.json.gz
quarto render quarto/135_n7_sleeve_expansion.qmd --execute-dir . --execute --no-cache -P archive_fixture:tests/fixtures/n7_sleeve_expansion.json.gz
quarto render quarto/136_n7_sleeve_probability_cap.qmd --execute-dir . --execute --no-cache -P archive_fixture:tests/fixtures/n7_sleeve_probability_cap.json.gz
quarto render quarto/137_n7_sleeve_reuse.qmd --execute-dir . --execute --no-cache -P archive_fixture:tests/fixtures/n7_sleeve_reuse.json.gz
quarto render quarto/138_n7_sleeve_review_corrections.qmd --execute-dir . --execute --no-cache
```

These regenerate accounting tables/figures in ARCHIVED_ACCOUNTING_ONLY mode.
They are not a fresh selection rerun, full native replay or proof of chronology.
R numerical/identity tests additionally consume `n7_sleeve_numerical.json.gz`.

**Full historical native replay** also needs external, untracked immutable
packages under `data/derived/fundamentals_417/`: `n7-core-profit-v1`,
`n7-probability-gate-v2/pools`, `n7-sleeves-424-v3`,
`n7-sleeve-expansion-v1`, `n7-sleeve-cap25-v1` and `n7-sleeve-reuse-v1`,
including probability pools, cutoff receipts, frozen settlements, bundles, plans
and hash manifests. These are not silently downloaded or provided by Git alone.
The four `config/n7_sleeve*.json` files and prior study docs give exact paths.

Use each original package's bound implementation commit for native replay.
Current code deliberately rejects an old package when its implementation closure
has changed. Never reseal old data, replace a code hash or disable the check just
to run a newer checkout. Existing native acceptance evidence is referenced with
its original identity; new fresh synthetic end-to-end tests exercise current code.

## Final review and lifecycle

Final checks run against a clean `git archive` of the reviewed implementation,
not this shared workspace's unrelated modifications. The final delivery receipt
binds source hashes, implementation tree, verification commands/logs and rendered
artifacts. Documentation-only delivery changes may cite those identical code
bytes; the final Codex review covers the delivery increment and dependency claims.
No statement attributes another executor's checks to PI execution.

The first complete R run rejected an old external test context bound to a
different parser implementation. Clearing only the parse cache did not resolve
it. The authoritative `scripts/prepare_next_issue_fixture.py` was executed from
the clean export into a fresh output directory, regenerating context from the
committed raw fixture responses; the complete R suite then passed. Original
contexts and caches were preserved. This was environment/input setup repair,
not a hash override, research data change, or project implementation change.

Remote CI remains owner-disabled. Local checks and independent review remain
required. No issue-closing keywords are used. At final PI review, decide whether
to mark this scoped stage Ready and approve research-branch merge; until that
explicit decision PR426 stays Draft. Main integration remains pending even after
such a merge. Keep #424 OPEN / PI Review and retain historical_admission=false.

The remaining #424 contract still includes causal probability/price availability,
clean development-to-transfer evidence, cross-year validation, R-native
computational core, and joint return/overlap/path-risk optimization. No
SLEEVE_PORTFOLIO_SIGNAL or live-use claim is granted by staged code delivery.
