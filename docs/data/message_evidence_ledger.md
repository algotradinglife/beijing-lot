# Timestamped team-news and match-context evidence ledger

`message_evidence_ledger_v1` is the provider-neutral data contract for
BJ-DATA-MESSAGE-EVIDENCE-001. It records what was available, where it came
from, and when it first became usable. It does not score evidence or make a
betting decision.

## Consumer contract

Consumers must request an explicit timezone-aware cutoff and use only the
result of `MessageEvidenceLedger.export_as_of`. They must not query the SQLite
tables directly or substitute `published_at` for the ledger's
`effective_cutoff_utc`. The export is validated by
`schemas/message_evidence_asof_v1.schema.json`.

The stable v1 guarantees are:

- every normalized fact links to one immutable raw capture and its SHA-256;
- every time is normalized to UTC while ingestion rejects naive timestamps;
- every append receives a system-clock `recorded_at_utc` receipt, and its
  effective cutoff can never precede that receipt;
- receipt time is monotonic across process restarts: the ledger persists a
  high-water mark, rejects a regressed system clock, and assigns a strictly
  increasing `receipt_sequence`;
- no export contains a fact, correction, contradiction, missingness record,
  entity alias, or match registration first usable after its cutoff;
- corrections, retractions, contradictions, and missing observations are
  append-only records, never destructive updates;
- repeated ingestion of the exact same record is idempotent; reuse of an
  immutable identifier with different content fails closed;
- raw bytes are hashed again during every as-of export.
- every exported row exposes its content hash and a receipt integrity digest that
  binds the content hash, receipt time, effective cutoff, sequence, and any
  derived timing fields; exports fail closed on inconsistent stored fields;
- every append assigns its receipt in the same write transaction as its row,
  and every export takes a serialized snapshot, so an in-flight append cannot
  make a previously served historical cutoff grow later. A filesystem-read-only
  backup uses a conventional read transaction only when the caller explicitly
  declares `readonly_replica=True` (CLI: `--readonly-replica`). A live ledger
  that cannot reserve the writer slot fails closed; it never silently assumes
  that a differently credentialed writer does not exist.

The v1 SQLite file is a single-writer operational ledger. Back it up by copying
the database and WAL files from a quiesced writer or by using SQLite's backup
API. Filesystem permissions and backup retention remain deployment concerns.

## Provenance registry

Every capture refers to a registered source. Tiers describe provenance, not
truth, and are exposed to consumers without being converted into a strategy
weight.

| Tier | Intended source |
| --- | --- |
| `TIER_0_OFFICIAL` | Club, league, competition, or other accountable official publisher |
| `TIER_1_PRIMARY` | Identified primary reporter or direct accountable report |
| `TIER_2_RELIABLE` | Reviewed news or data provider with an established collection process |
| `TIER_3_UNVERIFIED` | Unverified lead retained for audit; consumers decide whether it is eligible |

Supported normalized fact kinds are `injury`, `suspension`,
`expected_lineup`, `confirmed_lineup`, `coach_change`, `schedule`, `travel`,
and `motivation`.

Tier-0 sources must register a base URL, and captures must use that exact
scheme and network origin. Raw captures are limited to 20 MiB; the CLI accepts
regular files only. Provenance URLs must not embed user-info credentials or
sensitive authentication/signature query parameters; collectors must store a
credential-free canonical URL.

Entities use stable internal IDs and source-specific aliases. Alias rows carry
their own `observed_at_utc`, so an alias learned later cannot leak into an
earlier as-of export. Alias activity is resolved globally per
`(source_id, normalized alias)`, including a later remap to an entity outside
the requested match scope; both the superseded and active rows remain visible.
Matches are linked by the pair `(issue, match_idx)` and a provider-neutral
`match_id`; home and away must be distinct team entities and any competition
reference must have the competition entity type.

## Timestamp semantics

Each raw capture carries:

- `published_at`: publisher timestamp, if the publisher supplies one;
- `observed_at`: first time this collector observed the payload;
- `fetched_at`: time the immutable bytes were fetched and became available;
- `recorded_at`: system-clock time the ledger accepted the row; callers cannot
  supply it through the CLI;
- `receipt_sequence`: persistent total ordering for rows accepted at the same
  effective time;
- `effective_cutoff_utc`: maximum of those supplied timestamps, which is the
  earliest cutoff at which the capture may be consumed. Registry, normalized
  fact, relation, missingness, and collection-observation receipts also
  participate in the relevant maximum.

Ingestion requires `published_at <= fetched_at` and
`observed_at <= fetched_at`. A capture more than 3,600 seconds late relative to
its publisher timestamp is marked `late_arriving=true`; it is still excluded
from all earlier exports. Missing publisher timestamps remain explicit `null`
values rather than inferred history.

Fact-level `effective_from` and `effective_until` describe the real-world
period asserted by the source. Both bounds are inclusive. They never move the
knowledge cutoff backward.

An active, affirmed `schedule` fact may provide a timezone-aware
`kickoff_at_utc`. The latest such revision becomes the coverage gate's
canonical kickoff, so an advance or postponement is applied without mutating
the original match row. A denied schedule assertion never changes the gate,
and unresolved conflicts between gate-affecting schedule facts block
eligibility even when `schedule` is not one of the caller's required kinds.

## Append-only correction and conflict model

`evidence_relations` links a later fact (`source_fact_id`) to an earlier fact
(`target_fact_id`):

- `corrects` supersedes the target at the later fact's cutoff;
- `retracts` deactivates the target at the later fact's cutoff;
- `contradicts` keeps both facts visible and marks the conflict on both.

Relations are allowed only for the same issue, match, entity, and fact kind.
Their source must be strictly later by `(effective_cutoff_utc,
receipt_sequence)`, which makes cycles impossible while permitting a correction
recorded later from the same capture time. Active state is folded
newest-to-oldest: only an active later fact can correct or retract an older
fact. Retracting a corrector therefore restores the older target while
preserving the full relation history. An unresolved contradiction between
active facts makes the affected coverage row ineligible.

`missingness_records` record attempted collection that yielded no normalized
fact. If a later usable fact arrives, coverage recovers at that later cutoff;
the earlier missingness row stays in the export for audit. If a later
missingness observation follows the latest fact, the kind is explicitly
missing at that cutoff.

Facts use non-empty JSON objects. An optional `coverage_entity_ids` array says
which registered entities a match-level fact covers; an entity-scoped fact
also covers its `entity_id`.

`collection_observations` separately record whether collection was `complete`
or `partial` for one match/fact kind. A complete observation must include both
registered match teams in `expected_entity_ids`, may add players or other
entities, and identifies every checked source. The capture's source must be in
that source set. Coverage independently verifies that active facts cover the
full expected entity set, so a producer cannot certify only one team.

## Storage schema

The SQLite schema is created by `MessageEvidenceLedger.initialize`:

- `source_registry`: provenance identity and tier;
- `entity_registry`, `entity_aliases`: canonical entity resolution and
  timestamped source spellings;
- `match_registry`: issue/match linkage and kickoff;
- `raw_captures`: immutable source bytes, URL, timestamps, and SHA-256;
- `evidence_facts`: normalized assertions linked to raw captures;
- `evidence_relations`: correction, retraction, and contradiction edges;
- `missingness_records`: explicit failed or absent observations.
- `collection_observations`: audited collection completeness, expected entity
  population, and checked source population.

SQLite triggers reject every update or delete on these tables. A change is a
new row with a new content-derived identifier. The receipt digest detects
accidental or partial out-of-band changes, but it is not a signature or a
security boundary against a writer who can alter the database and recompute
hashes.

## CLI workflow

All mutation commands take small JSON object records whose keys match the
corresponding Python method. Raw source content is passed as a separate file.

```bash
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite init

python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  register-source --record source.json
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  register-entity --record team.json
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  register-alias --record alias.json
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  register-match --record match.json
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  capture --record capture.json --raw raw/club-report.html
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  fact --record fact.json
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  observation --record observation.json
```

Corrections and missing observations are appended in the same way with
`relation --record relation.json` and `missing --record missing.json`.

The capture command opens raw input without following symlinks, validates the
opened descriptor as a regular file, and applies the 20 MiB limit before
reading it. Consumer-facing commands use directory-relative, no-follow
temporary files and atomic replacement to write canonical JSON; output paths
cannot alias the ledger database or its `-wal`, `-shm`, and `-journal`
sidecars:

```bash
python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  export --cutoff 2026-08-04T12:00:00+08:00 --issue 26081 \
  --output results/message_evidence/26081-asof.json

python3 scripts/manage_message_evidence.py --db data/message_evidence.sqlite \
  coverage --cutoff 2026-08-04T12:00:00+08:00 --issue 26081 \
  --required-kind injury --required-kind suspension \
  --required-kind confirmed_lineup --max-age-seconds 21600 \
  --output results/message_evidence/26081-coverage.json
```

## Coverage and freshness

Coverage is policy-parameterized: a caller supplies the required fact kinds
and maximum age, plus optional allowed provenance tiers. A match is
decision-chain eligible only at a cutoff strictly before kickoff, when every
required kind has a current, non-`unknown` active fact, a latest `complete`
collection observation covering both teams and its declared entity set,
permitted provenance, no later explicit missingness, no stale required fact,
no stale completeness observation, and no unresolved active contradiction.
Freshness is evaluated for every expected entity using the worst age, not only
the newest fact for the kind. Its clock is the raw capture's publisher time
when present, otherwise its fetched time; the later ledger receipt controls
causal visibility but cannot make old source evidence fresh. Reports expose the exact failure reasons,
per-kind observation ages, stale/uncovered entity IDs, plus per-issue match
count, eligible count, and eligible rate. The report schema is
`schemas/message_evidence_coverage_v1.schema.json`.

Coverage measures whether a later prospective decision-chain study has usable
inputs. It does not claim that the facts are correct or predictive.

## Explicit non-goals

The ledger does not synthesize historical timestamps, backfill unavailable
news, calculate model features, rank matches, authorize ROI claims, create
tickets, or provide a UI. A source first collected after kickoff remains a late
observation even if its page alleges an earlier publication time.

The replay tests rebuild a fresh ledger from the same append sequence and
compare content IDs plus canonical exports before and after a correction. They
also prove that caller-supplied backdated timestamps cannot make an append
visible before its system receipt.
