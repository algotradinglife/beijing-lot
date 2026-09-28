# Nowscore / Titan fundamentals collection

Owner instruction: 2026-09-05. Live contract: [#406](https://github.com/algotradinglife/beijing-lot/issues/406).
This document describes data semantics, not task lifecycle or dispatch. Read
native GitHub relationships and Project Status for execution decisions.

## Source roles

Nowscore supplies the source-native Beijing issue/slot inventory and its own
fundamentals observations. Titan supplies separately captured fundamentals.
Provider IDs belong to their source namespaces: equal numeric IDs are discovery
candidates, never sufficient identity proof. Reviewed crosswalks bind competition,
season, both teams, kickoff, event instance and source receipts. Ambiguous
identity quarantines the fixture; do not fuzzy-match silently.

Both sources remain separate observations. Neither is automatically correct.
Agreement is `AGREED_UNVERIFIED`, not independently verified truth. Different
domains do not establish independent data supply chains. Sample agreements too,
because identical upstream mistakes may survive dual-source comparisons.

The Nowscore-only settlement contract in #405 remains separate. Independent
sporting evidence cannot establish winning SP, refunds or lottery treatment.
Do not import old 500 mappings/corrections or automatically alter settlement.

## Discrepancy resolution

1. Compare the same fact: event instance, home/away orientation, timezone,
   snapshot epoch, score period and regulation/extra-time/penalty semantics.
   Preserve original, abandoned, resumed and replayed matches separately.
2. Seek independent evidence, preferring original competition/federation match
   records and notices; use original club match reports or squad announcements
   for their supported fields. General provider records require documented
   upstream independence. Unknown/shared upstream evidence cannot resolve a
   discrepancy; do not use a majority vote.
3. Store raw bytes and exact supporting passage/locator, request/final URL,
   capture time, SHA256, source/event identity, supported field/period, evidence
   provenance assessment and reviewer rationale. Search snippets and old local
   review notes are discovery leads, not sealed adjudication evidence.
4. Append a resolution version linking every original observation and the
   independent evidence. Distinguish `SEMANTIC_DIFFERENCE`,
   `INDEPENDENTLY_RESOLVED`, `UNRESOLVED` and `IDENTITY_AMBIGUOUS`.
   Unsupported claims remain unresolved, even if another field was verified.
5. Exclude unresolved fields and their dependent features from admitted output.
   Missing is not zero, healthy, a draw or agreement. A later resolution never
   rewrites a previously frozen release or retrospectively supplies availability.

## Field layers

| Layer | Facts | Scope rule |
| --- | --- | --- |
| P0 identity | source fixture/team/competition IDs, season, kickoff, venue, status | Version schedule changes and event instances |
| P0 history | individual match scores by period, opponent and home/away | Include teams' matches outside the Beijing pool |
| P0 context | standings snapshots, adjacent schedules, weather as published | Retain forecast versus observed semantics |
| P1 personnel | injury, suspension, doubtful, expected/confirmed lineup, formation | Per-player identity and timestamp evidence; use #181 contract |
| P2 messages | coach changes and factual competition context | No inferred motivation/strength from prose |

The legacy Nowscore detail parser already summarizes recent records using fixed
windows and blends them with market context. Reuse only suitable pure parsing;
do not treat those summaries as a clean causal learning interface. The Titan
fundamentals parser extracts raw blocks; its pre-match wording does not prove
historical availability. A successful HTTP response or non-raising parser is
not a valid-field/identity acceptance check.

## Time and storage

Use append-only content-addressed raw capture, normalized observations and
versioned adjudications; retain the existing SQLite/Parquet architecture.
Observed availability starts at successful receipt, never an asserted historical
page date. Historical probes/backfills are `HISTORICAL_PROXY`; documented
conservative safe boundaries require their own evidence. Fail closed on absent
chronology. No learned functions are needed for capture or deterministic audit.

Every later historical-learning client must use `src/temporal_learning` with an
explicit Cutoff. Admit strictly prior source AND label availability, exclude the
exact target issue even if its timestamp is corrupt, and derive all partitions,
weights, normalization, imputation and gates inside that prior window. Inventory
transitive helpers. Bind source/label maxima, parameters/metrics/gates, model,
source and implementation hashes and cutoff/cache identity in immutable receipts.
Independent replay must verify cross-cutoff exclusion and post-cutoff mutation
invariance through every implemented feature/selection/support/ticket/router
consumer. Do not duplicate temporal helpers or claim absent consumers verified.

## Sampling and operational acceptance

The initial endpoint probe is deliberately bounded and is not a coverage or
source-error-rate estimate. The subsequent census targets approximately 100
fixtures, stratified by competition/season and current versus historical scope,
using a saved source-native denominator and explicit deterministic sampling
rule. Historical error/regulation-time/replay cases form a separate regression
panel. Deriving model-facing coverage gates from this panel would itself require
shared cutoff-driven learning; this census only reports diagnostics.

After P0 acceptance, start with the most recent completed season per competition
and expand per reviewed stage. Track attempted, captured, parsed, mapped,
agreed, independently verified, unresolved, quarantined and missing records by
source/season/competition/issue/field. Never merge these counts into a single
"success" rate. Capture source-native field absence separately from fetch and
parse failures.

Prospective cadence proposals: roster entry, T-72h, T-24h, T-10h, T-1h and actual
decision freeze. Enforce explicit per-host request budgets, bounded retries and
record missed epochs. Confirmed lineups received after the decision epoch stay
unavailable to that decision. Validate at least two complete available issue
cycles before claiming observed operational coverage.

## Execution contracts

### Executable QMD deliverable

The owner requires an executable `.qmd` entry point under `quarto/` for the
collection and audit deliverable. Declare inputs and parameters there, call
reusable R functions from `r/` and Python functions from `src/`, and present
coverage, discrepancies, independent evidence, quarantine decisions and
versioned facts exports. Keep reusable business functions out of QMD.

When calling Python from R, use `reticulate` to convert outputs to R objects
and select the project interpreter explicitly before initialization. Record
dependencies during environment setup. Test cross-language identifiers and
leading zeros, nulls versus zero, integer precision, empty tables, column types
and timezone-aware timestamps. Run function tests and render in a clean process
with declared inputs, execution enabled, cache/freeze bypassed and errors fatal.
Declare offline replay and live capture modes explicitly; live capture observes
bounded source-specific request budgets. Bind results to immutable input hashes,
code identity, parameters and generation time. The live #408 contract records
this delivery requirement; this document does not define lifecycle state.

### Mandatory Codex review

The owner requires a passing Codex review before #408 acceptance. Review the
final executable QMD, called R/Python modules, data contracts and relevant tests.
Record the reviewed code identity, result, findings and their disposition as
acceptance evidence. Fix blocking findings and obtain a passing follow-up review;
material subsequent changes require review of the changed final implementation.
A requested, skipped, unavailable or failed review does not pass this gate.
Function tests and clean-process QMD rendering remain independently required.
PI final acceptance and issue closure require this gate to pass, as recorded in
the live #408 contract.

- [#407](https://github.com/algotradinglife/beijing-lot/issues/407): source/identity census and independent evidence sources.
- [#408](https://github.com/algotradinglife/beijing-lot/issues/408): P0 capture, conflict adjudication and replay.
- [#409](https://github.com/algotradinglife/beijing-lot/issues/409): prospective snapshots and cutoff exports.
- [#410](https://github.com/algotradinglife/beijing-lot/issues/410): injury/suspension/lineup adapters.
- [#411](https://github.com/algotradinglife/beijing-lot/issues/411): staged historical collection.
- [#412](https://github.com/algotradinglife/beijing-lot/issues/412): independent replay and final acceptance.

The live graph owns dependencies and current state; this list is navigation only.
