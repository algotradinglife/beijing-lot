# #203 causal issue tensor data card

This immutable package materializes one ragged `X_i[J_i, 3, 24]`
float32 tensor plus an equal-shape Boolean mask for each of 344
canonical issues. Outcome order is `3, 1, 0`; match order is `match_idx,
match_id`; issue order is cutoff then numeric issue.

## Causal boundary

`inference/` is outcome-unexposed and is the only namespace read by the default
loader. `labels/` is imported explicitly and contains development-only result,
final-SP and settlement fields. Issues 25041, 25042 are frozen
whole as 2025-04+ held-out identities; their labels are absent, not encrypted or
hidden in the same payload.

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
SP in development). Downstream #204 must honor these masks. Reinterpreting the
state as a rolling per-match or per-ticket cutoff requires a separate PI
contract decision and a newly versioned package; it cannot be an implicit
backfill in this interface.

## Limitations

This package does not assert that all features are present. Coverage tables make
missing predicted SP, native line, and timestamped Beijing SP explicit. It does
not train a model, build tickets, calculate ROI, or authorize betting.
