# Cutoff-driven historical-learning contract template

For every function that learns from historical observations, freeze this table
before implementation:

| Field | Required value |
|---|---|
| Function and transitive helpers | Exact import/function names |
| Shared client | `src.temporal_learning` primitives imported; no local temporal duplicate |
| Learned operation | Fit/calibrate/tune/select/rank/gate/optimize |
| Cutoff argument | `CutoffSpec` identity, kind and UTC timestamp |
| Availability rule | Exact source/data/label timestamp column and strict `< cutoff` predicate |
| Internal partitions | Rule deriving fit/tune/calibration inside admitted history |
| Insufficient-history behavior | Explicit fail-closed predicate |
| Returned artifact | Model/parameters/ranking/gate/weights/etc. |
| Receipt | Source/helper hashes, maxima, partitions, parameters, metrics, gates, identity |
| Cache | Key includes cutoff + source + implementation identity |
| Walk-forward mode | Target issue/decision epoch; current-year labels enter only after availability |
| Recency policy | Equal/decay/recent-state blend, prior retention, ESS floor, selection boundary |
| Refit cadence | Per issue or explicit causal cadence; no silent later-model reuse |
| Weight evidence | Complete ledger hash, sum, monotonicity and effective sample size |
| Independent replay | Function and equality tolerance (`rtol=0`) |
| Downstream invariance | Model, selection, support, tickets and routing under post-cutoff mutation |

Business constants must be listed separately and must not be represented as
learned parameters. Historical-only predecessor packages and migration/parity
receipts must be named explicitly.

Domain clients own only fitting/prediction/selection semantics. The shared
library owns cutoff, availability, partitions, weighting, ESS, per-issue runner,
receipt, cache identity and replay protocol. Any exception must fail the static
gate; per-Issue copies are prohibited.

If recency parameters are tuned, name the nested prior-only procedure. Historical
walk-forward diagnostics preregister expanding equal weight, expanding recency
weight, and a bounded rolling/recent-state blend. Compare calibration, gate and
parameter turnover, downstream action/ticket turnover, economics, drawdown,
losing runs, and adaptation lag without using a target or future outcome.
