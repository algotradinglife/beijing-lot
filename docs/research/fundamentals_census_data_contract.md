# #407 diagnostic census data contract

## Scope and identities

The release is a bounded capability census, not a league census, source error-rate
estimate, admitted feature store or settlement database. It includes 100 stratified
fixtures (70 historical, 30 upcoming at the declared diagnostic sampling epoch)
and a separate three-case historical regression panel. Membership revision v2
corrects lottery-day/calendar-day interpretation while preserving v1 and all
captures. Sampling revision time is distinct from its diagnostic as-of time.

`issue`, `provider_id`, team IDs and history IDs are strings. `slot` is a positive
integer. `(issue, slot)` identifies a source-native issue entry; provider ID is
unique within a panel. Equal Nowscore/Titan IDs are a candidate relationship,
not proof of independent upstream identity. Team orientation, source clock and
original/restarted/rescheduled occurrence require separate checks.

Roster `name` is retained as `roster_group_date`. `roster_clock` is the published
clock; `roster_deadline_utc` comes from the explicit sale-deadline label. The next
published clock at or after that deadline is a **diagnostic reconstruction** of
kickoff; `kickoff_basis` names that rule. Analysis identity is checked separately.
Neither source clock nor sale deadline proves the actual whistle time. Source
local timestamps are Asia/Shanghai; normalized timestamps are aware UTC.

## Tidy outputs

| File | Row meaning / key | Values and missingness |
| --- | --- | --- |
| `panel.csv` | One selected issue/slot; provider ID unique | Explicit period, competition, sampling epoch, roster provenance and selection reason. |
| `denominator.csv` | One candidate issue/slot | All candidates retained with exclusion/selection reason; selected-key join is one-to-one. |
| `responses.csv` | One selected issue/slot/source, exactly two per fixture | Request status, final URL, raw hash, bytes, capture/parse states, error and required auxiliary receipt fields. Effective `received_at_utc` is no earlier than any required payload; original document time remains in its raw receipt. |
| `identity.csv` | One successfully parsed issue/slot/source | Team strings/IDs, source kickoff, native season links and roster-clock equality. Missing parse rows are not synthetic identities. |
| `fields.csv` | One successfully parsed issue/slot/source/field | Record count and original JSON value; payload hash points to the external script for history arrays and HTML for HTML fields. |
| `history.csv` | One issue/slot/source/block/ordinal | Referenced event ID, source event date, home/away IDs, integer goals, original team text. Duplicate occurrences are retained. |
| `findings.csv` | One comparison finding for fixture/field | Both observations and disposition. Coverage differences retain absent-side arrays; identity ambiguity remains quarantined. |
| `receipt.json` | One immutable replay | Input JSON/roster/revision hashes, transitive implementation hashes, dependencies, generation time, CSV hashes and diagnostic-only admission. |

Booleans are emitted as `True`/`False`; R reads only fields used in computations
as their declared numeric/datetime types. Empty cells represent missing scalar
values; integer zero remains zero. Nested cells are JSON, preserving `null`, `[]`
and populated arrays distinctly. No parser failure becomes an empty table.

History blocks: `h_data` home-team recent history, `a_data` away-team recent
history, `v_data` head-to-head. Array history IDs occupy Nowscore column 20 and
Titan column 15 (zero-based). A two-digit source year is explicitly interpreted
as 2000–2099 for these inspected profiles; four-digit years are preserved.
The raw original is retained. This is not a clean interface for arbitrary older
centuries or decision-facing chronology.

`season_tables` contains ordered source totals with nine integer statistics:
played, wins, draws, losses, goals for, goals against, goal difference, points,
rank. Goals are counts, points/rank are source-defined competition values.
`injuries` contains raw player/reason rows; no injury severity or availability
probability is inferred. `previous_lineup` contains published previous-match
player entries, not confirmed target starters; source bench coverage can differ.
`schedules` retains raw future-schedule rows, including source date text and
relative-day labels; it does not silently invent a year for month/day-only cells.
Venue/weather/temperature remain source text; temperature is not normalized.

Field states describe this extractor's recognized payload: `POPULATED`,
`PUBLISHED_NO_DATA`, `ABSENT`. `ABSENT` is not proof that no information exists
elsewhere on the site or in another profile. The archived 2016 weather layout is
not a normalized weather interface. Main-panel coverage and regression-profile
limitations must be reported separately. HTML/JS schema changes fail visibly;
unsupported old interfaces are not fallback production paths.

## Comparison and independent review

Comparable checks cover target names/team IDs/kickoff, standings totals, and
same-ID historical event date/orientation/goals. Field coverage is inventoried
for the other fields; arbitrary text/lineup/weather differences are **not**
claimed to be semantically adjudicated. History depth/membership differences
are `COVERAGE_DIFFERENCE`, not false score votes. Missingness is never agreement.

Versioned `independent-cases.v1.json` retains official original evidence hashes,
URLs, actual capture time, reviewer, rationale, disposition and quarantine
policy. `agreement-spotchecks.v1.json` independently checks two shared facts.
These reviews validate original club/organizer/venue statements, not every
embedded statistic. An unknown/shared statistical feed has no independent vote.
The R reader validates review completeness and raw hashes; it does not automate
the truth of a human/agent narrative assessment.

## Availability and reproducibility

`OBSERVED` means all required captured payloads preceded the diagnostic source
kickoff. It is collection evidence, not admission to a historical model or
lottery decision. Historical captures remain `HISTORICAL_PROXY`. Unresolved
time/occurrence ambiguity blocks dependent features and fixture admission.
All outputs declare historical learning `NONE`; fitting and temporal feature
clients belong to the shared `src/temporal_learning` contract in later work.

Replay writes into a temporary directory, refuses an existing destination,
checks implementation did not change during execution, and publishes by rename.
The release bundle separately preserves code, original receipts, review records,
old/new sampling versions and a complete hash manifest. A second fresh-process
replay must reproduce CSV hashes from the same declared inputs and code.
