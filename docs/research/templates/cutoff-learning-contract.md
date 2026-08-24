# Cutoff-driven historical-learning contract template

For every function that learns from historical observations, freeze this table
before implementation:

| Field | Required value |
|---|---|
| Function and transitive helpers | Exact import/function names |
| Shared client | `src.temporal_learning` primitives imported; no local temporal duplicate |
| Learned operation | Fit/calibrate/tune/select/rank/gate/optimize |
| Cutoff argument | `CutoffSpec` identity, kind and UTC timestamp |
| Target exclusion | Exact target issue identity plus strict timestamp exclusion |
| Availability rule | Evidence class (`observed`, conservative safe boundary, or historical proxy), exact timestamp column and strict `< cutoff` predicate |
| Intended use | Historical diagnostic or prospective decision; a proxy cannot authorize prospective use |
| Internal partitions | Rule deriving fit/tune/calibration inside admitted history |
| Insufficient-history behavior | Explicit fail-closed predicate |
| Returned artifact | Model/parameters/ranking/gate/weights/etc. |
| Receipt | Source/helper hashes, maxima, partitions, parameters, metrics, gates, identity |
| Cache | Key includes cutoff + source + implementation identity |
| Walk-forward mode | Target issue/decision epoch; current-year labels enter only after availability |
| Recency policy | Equal/decay/true convex recent-state blend, component masses, prior retention, ESS floor, selection boundary |
| Refit cadence | Per issue or explicit causal cadence; no silent later-model reuse |
| Weight evidence | Complete ledger hash, sum, monotonicity and effective sample size |
| Independent replay | Function and equality tolerance (`rtol=0`) |
| Downstream invariance | Model, selection, support, tickets and routing under post-cutoff mutation |
| Static enforcement | Exact AST occurrence baseline across `src/` and `scripts/`; no whole-file exemption |
| Implementation closure | Transitive local import hashes plus external distribution versions |

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

For a recent-state blend, freeze the two normalized component distributions and
verify `(1-alpha) * long_history + alpha * recent_state` with separate mass
reconciliation. A single globally renormalized vector with boosted recent rows
does not satisfy this contract.
