# #203 causal issue tensor data card

This immutable package materializes one ragged `X_i[J_i, 3, 24]`
float32 tensor plus an equal-shape Boolean mask for each of 394
canonical issues. Outcome order is `3, 1, 0`; match order is `match_idx,
match_id`; issue order is cutoff then numeric issue.

## Causal boundary

`inference/` is outcome-unexposed and is the only namespace read by the default
loader. `labels/` is imported explicitly and contains development-only result,
final-SP and settlement fields. The exact 52-issue held-out sequence is recorded
in `audit/heldout_registry.csv`: 25041-25042 plus every locally inventoried 2026
issue from 26011 through 26069. Their labels are absent, not encrypted or hidden
in the same payload. The prior `results/bj203_causal_tensor_v1` package is
preserved unchanged as superseded two-issue evidence; v2 is the operative handoff.
Its complete byte census remains independently checkable with the
`verify-superseded` command and is locked to original HEAD `38dc5ae1223a96cf361db851215143bd73afb05d`.

The 8,661 added 2026 matches are deliberately identity only. Rows 26011-26049
come from the retrospective modelling inventory and carry no asserted observation
timestamp. Rows 26051-26069 come from the timestamped live match inventory and
bind `created_ts`, but expose no market, SP, line, league or team decision feature.
Only the canonical outcome axis, issue/match order, calendar year and nonnegative
kickoff delay can be unmasked. The loader fails closed if an identity-only row
exposes any other feature.

Historical official Beijing 3SP has no trustworthy observation timestamp and is
therefore label-only. The pre-event `bj_sp_snapshot` slots remain present but
fully masked. Match-safe 1h EURO and 10h predicted-SP inputs are also masked
whenever their snapshot cutoff follows the issue-level cutoff; the leakage audit
reports those negative coverage counts explicitly. All 275
rows excluded from #190's estimator
universe are retained with explicit missing-team, missing-1h-EURO and/or
missing-line reasons; no future or terminal value repairs them.

## Learner handoff

Use `unified_tensor.load_issue_tensors(package, split="development")`. It
returns values and masks with shapes `[J_i, 3, F]`; masked values are zeroed only
at load time. The probability/SP learner must treat calibrated market
probability as the incumbent, preserve zero-residual fallback, and must not
import `unified_tensor.settlement_labels` until an authorized validation path.

The executed analysis notebook is
`notebooks/research/issue-203/bj203_causal_tensor_contract.ipynb`. It verifies
the package, renders `analysis/coverage_summary.csv` and embeds the frozen
coverage figure without opening held-out labels.

The issue-level cutoff makes most match-relative market snapshots causally
unavailable (roughly 1% coverage for 1h market cells and 8% for 10h predicted
SP in development; Beijing SP is 0%). The explicit capability decision is that
**#204 remains blocked**. See `analysis/downstream_readiness.json` and
`analysis/DECISION_REPORT.md`. The required PI-owned Data capability is proposed
as `BJ-UNIFIED-MARKET-COVERAGE-001`: causally timestamped development 1h
EURO/market probability and pre-event Beijing SP, exact provenance, matched
coverage, and a PI-approved representative-support gate. PI must create that
native Issue and make #204 blockedBy it; this Engineer-owned package does not
mutate Issue Graph contracts. Reinterpreting the cutoff or backfilling terminal
prices is prohibited.

## Limitations

This package does not assert that all features are present. Coverage tables make
missing predicted SP, native line, and timestamped Beijing SP explicit. It does
not train a model, build tickets, calculate ROI, or authorize betting.
