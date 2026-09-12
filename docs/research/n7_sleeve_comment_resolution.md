# PR426 PI comment remediation

Addresses [PI comment](https://github.com/algotradinglife/beijing-lot/pull/426#issuecomment-5645714508).
Review baseline: db4723d6. Scope is numerical metadata, descriptive risk and the
existing export interface; no new strategy, parameter search or model fit.

## P1: corrected mean and funded streaks

`sleeve_portfolios()` now divides summed selected-subset coverage by selected
sleeve count. A nonempty8×64 portfolio averages8 group probabilities, not512
physical tickets. The actual selected option matters: random/frontier/value
subsets do not inherit PROB Top64 coverage. Empty sleeve portfolios return null.
Monolithic `mean_coverage` retains its separate physical-ticket unit.

The independent checker reconstructs each selected option's coverage and rejects
the old factor64 error even if plan/freeze/result hashes are consistently resealed.
Production tests check every sleeve arm, specifically contrast PROB and RANDOM
on identical fixture sets, and cover empty portfolios. Selected tickets, RNG,
probabilities, budgets and settlement arithmetic are unchanged.

`n7_sleeve_summary()` filters to positive funded stake before both loss and
no-payout run calculations. A NO_BET period no longer breaks a funded sequence.
A partial payout that still loses money breaks no-payout but not loss; empty
funded histories return0. Underwater time continues to count all chronological
issues. Regression tests exercise these distinctions.

Archived100-issue recomputation changes only the two streak columns. Fixed-G
frontier has9 consecutive losing funded issues and6 consecutive no-payout funded
issues in every seed; old values were4 and4. Across all33 arm/seed combinations,
stake, net, ROI, hit issues and maximum drawdown remain identical.

## P2: reusable table interface

The existing single R implementation and persisted201 export files remain the
interface; [v1 contract](n7_sleeve_interface.md) specifies keys, types, units,
namespace, cutoff/hash boundaries and explicit CSV reading. Added tests freeze
the output/table column names and exercise leading-zero-preserving CSV round trips.

An independent review caught an initially ambiguous recommendation to reconstruct
all portfolios from coverage_64. It is corrected: use Top64 depth only for PROB
quality; actual selected portfolios require `(sleeve_id, option_kind)` and exact
selected-state probabilities. The non-PROB test explicitly guards this distinction.

Do not ingest old plan `mean_coverage` as group quality or rewrite old immutable
freezes. Use exact subset IDs / long-table membership to derive a separately
receipted correct average. Old native artifacts require their original pinned
implementation; the new checker intentionally rejects the erroneous old metric.
QMD138 reads a hash-checked archive and produces corrected descriptive results,
not a newly admitted causal probability package.

## P3 and lifecycle

No wider threshold/U/P/cap search is performed. Future policy exploration belongs
to independently frozen #425/#427 contracts. Their live graph currently has no
native dependency edges to #424; no edges are inferred from prose or changed here.
#424 remains OPEN / PI Review and PR426 Draft. Causal availability, clean transfer,
R-native numerical core, joint return/path-risk and cross-year gaps remain open.

The owner explicitly disabled all6 remote CI workflows after the earlier billing
failures. They remain disabled; local function tests, cutoff governance, executed
QMD checks and independent Codex review remain the verification route for this
remediation. No remote CI pass or merge authorization is claimed.

## Validation commands and scope

```sh
python -m pytest tests/test_n7_sleeve_states.py tests/test_n7_sleeve_portfolio.py tests/test_n7_sleeve_runner.py tests/test_n7_sleeve_checker.py -q
Rscript tests/testthat.R
python scripts/check_cutoff_governance.py
quarto render quarto/138_n7_sleeve_review_corrections.qmd --execute-dir . --execute --no-cache
quarto render quarto/134_n7_sleeve_portfolio.qmd --execute-dir . --execute --no-cache -P study:data/derived/fundamentals_417/n7-sleeve-comments-134-archive -P archive_fixture:tests/fixtures/n7_sleeve_portfolio.json.gz
```

Use the configured project Python/R/Quarto runtime and the existing full-suite
fixture environment. Both source functions map to their same-named Python/R test
files; checker semantic integration is in `test_n7_sleeve_checker.py`; consumer
interface tests are in `test-n7-sleeve-tables.R`. No new project function or
historical learning utility was introduced. Existing shared cutoff/closure code
remains authoritative; R changes are post-freeze descriptive accounting.

The native full strategy search is intentionally not rerun: this correction does
not select or settle new tickets. Python integration tests generate22 fresh toy
plans and exercise the real production/checker boundary; archived reporting
recomputes the100-issue risk statistics without changing labels or frozen plans.
An initial QMD134 render with a custom output filename failed resource resolution;
retrying the normal output filename succeeded. That failed attempt is retained
in its own log and is not counted as a passing check.

Final evidence:7 scoped Python tests passed; full R suite passed without
warnings/skips; cutoff governance and both QMD renders passed. The final
[independent Codex review](n7_sleeve_comments_codex_review.md) confirms the P2
documentation correction and no actionable defects, with2 final Python tests
rerun. [Receipt](n7_sleeve_comments_receipt.json) binds the exact checked files
and the33-row unchanged-economics /3-row corrected-streak comparison.
