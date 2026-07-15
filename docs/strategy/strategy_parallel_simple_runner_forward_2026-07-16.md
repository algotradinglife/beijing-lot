# Simple Runner Forward Comparator

Date: 2026-07-16

Monitor: `S13_A9_SIMPLE_RUNNER_FORWARD_V1`

Status: `ready_waiting_for_prospective_input`. A9 is implemented and tested,
but no A9 issue snapshot exists yet. The only available overlap directory is
the already-frozen 26075 asset; it does not contain A9's raw strict-SP and
candidate-code commitments, so it is ineligible for retrospective conversion.

## What A9 Freezes

For each eligible pre-sale row, primary is fixed as strict-handicap G0 argmax.
Three diagnostic protection legs are frozen at the same time:

| Comparator | Frozen leg |
| --- | --- |
| `G0_RUNNER` | highest remaining G0 probability |
| `G1_NONPRIMARY` | highest remaining G1 probability |
| `R3_NONPRIMARY` | highest remaining frozen R3 probability |

The immutable snapshot additionally contains raw strict SP, G0/G1/R3
probabilities, model/market/archive clocks, source input hashes, and all
candidate codes. No parameter, threshold, league branch, A7 score, or A8 value
ranker is used.

## Safety And Settlement

The monitor reuses the R3 forward monitor's strict pre-sale market extraction,
dual-clock validation, immutable historical-state rebuild, checksum rules, and
read-only SQLite access. It adds the raw strict-SP cross-check needed to assess
equal-budget double economics later.

`freeze` rejects late or incomplete inputs and existing output directories.
`status` reports settlement readiness. `settle` rejects partial official
results, writes a separate checksum-protected settlement artifact, and never
edits the frozen prediction file.

Settlement reports, for each comparator, conditional leg accuracy after a G0
primary miss, top-two coverage, runner rescues, normalized/native double
returns, and deltas versus primary single and `G0_RUNNER`. These are
observational metrics, not recommendations.

## Forward Rule

Two settled issues are observation only. At four fully settled, distinct
issues, evaluate each simple candidate on the union of frozen rows and by
issue. A future, separate research experiment is permitted only when a
candidate is nonworse than G0 runner on both conditional coverage and
equal-budget double profit in at least three of four issues and in aggregate.
No result permits production activation.

## Readiness

Implementation:
`scripts/monitor_strategy_parallel_simple_runner_forward.py`.

The production-owned next issue must first provide its standard
checksum-protected three-market overlap directory. Before its earliest sale
cutoff, the research session can then freeze it with:

```bash
.venv/bin/python scripts/monitor_strategy_parallel_simple_runner_forward.py freeze \
  --issue ISSUE --overlap-dir OVERLAP_DIR \
  --output-dir results/strategy_parallel/S13_A9_ISSUE_freeze_v1
```

The monitor will refuse a late invocation rather than create a pseudo-forward
artifact.

Cross-session event publication, idempotency, receipt, and scheduler rules are
defined separately in
`docs/strategy/strategy_parallel_a9_automation_coordination_contract_2026-07-16.md`.
The scheduler remains production-owned and is not deployed by this research
session.

## Verification

Four focused tests cover fixed candidate selection, checksum tamper detection,
partial-settlement refusal, and separate completed settlement. Ruff passes and
all `tests/scripts` tests are `269 passed`.

No production API, frontend, collector, release manifest, shared SQLite,
strategy, ticket, or execution state changed.
