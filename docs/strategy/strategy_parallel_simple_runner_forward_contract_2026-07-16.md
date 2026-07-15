# Simple Runner Forward Comparator Contract

Date: 2026-07-16

Monitor: `S13_A9_SIMPLE_RUNNER_FORWARD_V1`

Status: `research_paper_nonselectable`. A9 is a prospective comparison of three
fixed protection legs. It cannot select an active strategy, emit a ticket,
modify the decision chain, or alter API, frontend, collector, release, shared
SQLite, or execution state.

## Fixed Candidates

For each row, primary is the strict handicap G0 argmax. The three protection
legs are fixed before any result is known:

- `G0_RUNNER`: highest remaining G0 strict-handicap probability;
- `G1_NONPRIMARY`: highest remaining G1 probability;
- `R3_NONPRIMARY`: highest remaining frozen R3 probability.

Candidates may coincide. No model fitting, threshold selection, A7/A8 score,
league branch, price branch, or issue-specific parameter is allowed during the
forward window.

## Freeze Gate

For every frozen row require complete pre-sale strict handicap 3SP, regular
1X2, and selected-line O/U from a checksum-protected production-owned overlap
artifact. Require provider modification, archive fetch, R3 model freeze, and
snapshot creation all before the row sale cutoff.

The snapshot must retain raw strict SP for all three outcomes, frozen G0/G1/R3
probabilities, fixed candidate codes, timing clocks, input fingerprints, and
checksums. Missing rows remain excluded; no late backfill or post-event market
history is allowed.

## Settlement And Metrics

Settlement is a separate fail-closed operation after every frozen row has an
official handicap result and score. It cannot alter the snapshot.

For each candidate report on identical frozen rows:

- conditional protection-leg hit rate given G0 primary miss;
- top-two coverage and runner rescues;
- equal-budget double profit and its delta versus primary single;
- native two-unit double ROI;
- delta versus `G0_RUNNER`.

All returns are descriptive. No candidate is selected from a single issue.

## Forward Review

Two settled issues are observation only. At four distinct fully settled issues,
review all candidate metrics on the union of frozen rows and by issue. A simple
candidate can be considered for a separate research contract only if it:

1. has nonworse conditional leg hit rate than `G0_RUNNER` in at least three of
   four issues and on the aggregate;
2. has nonworse equal-budget double profit than `G0_RUNNER` in at least three
   of four issues and on the aggregate;
3. has no missing/late/partial settlement exception.

Passing a review cannot enable a protection rule. It can only justify a new,
separately frozen paper-action experiment. Failing keeps all candidates as
diagnostics only.

## Current Readiness

26075 remains excluded from A9 because its earlier R3 snapshot did not freeze
raw strict SP or A9 candidate codes. Its existing R3 observation remains valid
for R3 only. A9 starts with the next production-owned overlap artifact that
satisfies this contract.
