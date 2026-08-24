# Issue #382 — cutoff-driven historical learning protocol

## Decision summary

The reusable temporal-learning gate is ready. `src/temporal_learning` now owns
cutoff identity, actual-availability filtering, prior-only partitions, recency
weights, effective-sample-size enforcement, cache identity, receipts, and the
per-issue walk-forward runner. Domain modules own only fitting, prediction, or
selection. New hidden year globals, duplicated temporal utilities, detached
mapping acceptance, or direct model fitting outside the shared context fail the
repository governance check.

The first real client is the European-probability plus Beijing-handicap mapping.
At the explicit 2022 evaluation boundary (`2021-12-31 11:00 UTC`), the latest
admitted label was issue 21125 at `2021-12-31 09:00 UTC`. The shared context
derived 2014–2018 fit, 2019 tune, 2020 calibration, and an expanding refit
through 2021 without hidden temporal constants.

## Real-data evidence

| Check | Result |
| --- | ---: |
| Eligible rows | 136,738 |
| Equal-weight ESS | 136,738 |
| Tune log-loss delta, experimental − control | −0.014065 |
| Calibration log-loss delta | −0.014820 |
| Tune Brier delta | −0.011180 |
| Calibration Brier delta | −0.011008 |
| Prior-only mapping gate | Accepted |
| 2022–2024 cells exact to accepted #354 client output | 48,658 / 48,658 |
| Evaluation-year vs equivalent last-issue science | Exact |
| Cache identities for the two cutoff representations | Distinct |

This is an interface and causal-provenance result, not a new betting Edge. Exact
parity means #382 does not reinterpret the exposed #354 evidence; it provides a
safe reusable way for future target periods to reconstruct it.

## Walk-forward extension

The primary adaptive interface is a target issue's fixture-relative decision
epoch. Already completed current-year issues enter only after their actual label
availability; the target and future issues remain excluded. Three explicit
policies are supported: expanding equal weight, expanding exponential decay,
and a bounded recent-state blend that retains positive long-history weight.
Every receipt binds the complete weight-ledger hash, sum, extrema, effective
sample size, policy parameters, cutoff, sources, and transitive implementation
hashes.

The genericity test uses a separate threshold-selection client through the same
context and receipt protocol. Synthetic walk-forward tests prove that later
label mutation cannot rewrite an earlier artifact, recent weights are monotone
and reconciled, cache direction is isolated, and a regime shift affects only a
subsequent issue while retaining the long-history prior. Full real-data policy
comparison is intentionally separated into #383; it is historical hypothesis
generation and cannot consume #210/#218 evidence.

## Commands

```bash
PYTHONPATH=. python scripts/check_cutoff_governance.py
PYTHONPATH=. python scripts/run_cutoff_mapping.py --data-root /path/to/canonical/data
PYTHONPATH=. python scripts/verify_cutoff_mapping.py --data-root /path/to/canonical/data
PYTHONPATH=. pytest -q tests/scripts/test_cutoff_mapping.py tests/scripts/test_cutoff_governance.py
```

When the canonical data directory is outside the worktree, call
`build_package(..., explicit_data_root=...)` / `verify_package(...)` explicitly;
the receipt binds the consumed sources.

## Boundaries and migration

- Existing exposed packages remain historical evidence; there is no silent
  rewrite or clean reinterpretation.
- #381 must call the shared cutoff interface and publish parity before its
  corrected N6 all-R package is accepted.
- #378 remains transitively blocked on #381.
- #383 owns empirical equal/decay/recent-state walk-forward comparison before
  any prospective adaptive reuse.
- #210 and #218 are unchanged and no prospective evidence was consumed.
