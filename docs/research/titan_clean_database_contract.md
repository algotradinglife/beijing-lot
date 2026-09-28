# Titan-only clean database contract

Parent work item: [#405](https://github.com/algotradinglife/beijing-lot/issues/405).

## Fresh-data boundary

This database starts with new capture batches. No legacy SQLite file, Parquet
package, historical export, XLSM workbook, Nowscore cache, or prior capture may
be imported, merged, or used as an input. Prior artifacts are reference evidence
only.

## Source roles

| Source | Role | Permitted data |
| --- | --- | --- |
| Titan | `PRIMARY_FEATURE` | Titan roster, Titan fixture identity, Titan market observations and raw receipts |
| `500_issue_coverage` | `ID_DISCOVERY_ONLY` | isolated historical issue/slot coverage and 500-local IDs; never Titan feature input |
| `nowscore_id_mapping` | `ID_DISCOVERY_ONLY` | isolated `(500 issue, slot) → provider ID` mapping; never Titan feature or label input |
| `trusted_500_settlement` | `SETTLEMENT_ONLY` | final result, nullable native winning SP, correction and receipt provenance |

Titan roster discovery begins at the Titan-owned
`data.titan007.com/soccer_scheduleid.js` script. A listed ID is an observed
source key, not a canonical identifier. Titan fixture detail uses the documented
`1x2d.titan007.com/{provider_match_id}.js` route. Its normalized `euro_1x2_quote`
rows retain market update time only as `market_time_source_raw`; the raw receipt's
`trusted_received_at_utc`, never a provider market timestamp, remains the sole
availability boundary.

## Physical isolation

```text
$BEIJING_LOT_DATA_ROOT/clean_v1/
├── raw/titan/
├── control/titan/control.sqlite
├── raw/settlement_500/
├── control/settlement_500/settlement.sqlite
├── raw/id_discovery_500/
├── raw/id_discovery_nowscore/
└── control/external_id_discovery/discovery.sqlite
```

Titan, settlement, and external-ID discovery raw data and SQLite databases are
physically separate. The future feature reader must run with no 500 or Nowscore
mount, file descriptor, credential, or network access. The discovery ledger may
persist only `500 issue`, `issue slot`, 500-local `fid`, Nowscore provider ID,
and receipt bindings. It rejects slot-set mismatches and never uses names,
kickoff, handicap, odds, score, result, or SP to infer a mapping. The settlement
reader may only return frozen canonical fixture/issue/slot IDs, crosswalk hash,
normalized label, availability, and correction/receipt evidence.

## Time semantics

`trusted_received_at_utc` from a successful content-addressed raw receipt is the
observed availability boundary. Provider event/update times are retained only as
source-state evidence. A record is admissible only when:

```text
availability_boundary_at < decision_at_utc
```

Historical archive records captured later remain `HISTORICAL_PROXY`; they cannot
be promoted to strict forward evidence. `src/titan_clean/asof.py` materializes
only fixture receipts from a pinned Titan release whose trusted receive time is
strictly before the supplied `temporal_learning.Cutoff`; later live captures are
not visible to the pinned release.

### Model-optimization override (operator decision)

During model/strategy optimization the operator explicitly waives the strict
forward-availability gate for the Titan historical captures: their time
coordinate is `market_time_source_raw` (the provider-observed change time at
the fixture's own epoch), not the later capture time. Historical fixtures are
usable as ordinary training/optimization data in this phase. The waiver does
not apply to live production decisioning; re-enable the strict gate before any
prospective use.

## Label one-way bridge

500 may be bound only after Titan identity has been frozen outcome-blind. Its
label must reference all of:

- `canonical_fixture_id`
- `canonical_issue_id`
- `canonical_issue_slot_id`
- crosswalk SHA-256

The label availability timestamp equals the successful FINAL/SETTLED raw
receipt time. Missing winning SP, identity ambiguity, or binding conflict is
explicitly unavailable; it is never backfilled from Titan or another source.

`src/titan_clean/bridge.py` exports a handoff only after release verification;
it anchors each slot to an exact sealed fixture-capture batch (not merely a
reusable Titan source ID) but emits only the canonical triple and crosswalk hash. `SettlementStore.import_frozen_bridge()` accepts only that
minimal schema without opening Titan storage. `append_label()` fails closed
until the exact triple and hash have been imported; 500 team, kickoff,
handicap, odds, fixture description and raw Titan source IDs never cross it.

## Authorization gate

A readable public endpoint is not evidence of authorization for automated
collection. The collector therefore runs only in one of two modes:

- `--probe`: a one-fixture, read-only capability check, permanently marked
  `PROBE` in the roster receipt;
- `--authorization-receipt receipt.json`: operational collection with external
  written authorization;
- `--risk-acknowledgment receipt.json`: the user's explicit risk opt-in, bounded
  to 12 HTTP requests/minute and three fixtures/run.

A receipt itself is not copied into the database and must not contain a
credential. Its SHA-256 is bound to the capture batch and sealed into the Titan
release manifest. The risk path is not provider authorization; it is an
operator-attributable override that reserves all requests before network access
and fails closed at the configured rolling one-minute limit. Schemas are documented
in [`titan_authorization_receipt_schema.md`](titan_authorization_receipt_schema.md)
and [`titan_low_frequency_risk_ack_schema.md`](titan_low_frequency_risk_ack_schema.md).

## Fresh-capture command

```bash
# Read-only capability probe only; at most one fixture
python scripts/collect_titan_clean_roster.py \
  --data-root "$BEIJING_LOT_DATA_ROOT/clean_v1" \
  --capture-key "titan-<UTC-capture-key>" \
  --fixture-id <Titan-ID> --probe

# Operational collection only after an external authorization receipt exists
python scripts/collect_titan_clean_roster.py \
  --data-root "$BEIJING_LOT_DATA_ROOT/clean_v1" \
  --capture-key "titan-<UTC-capture-key>" \
  --authorization-receipt /secure/path/titan-authorization.json
```

The command first captures the current Titan roster, then refuses a requested
fixture that is absent from that exact roster receipt. It captures no settlement
source and accepts no Nowscore or legacy-data argument.

## Historical ID mapping command

The external discovery collector builds the required mapping table without
opening any existing database or admitting external descriptive data:

```bash
python scripts/collect_historical_id_mapping.py \
  --data-root "$BEIJING_LOT_DATA_ROOT/clean_v1" \
  --issue 26089 --capture-key "historical-id-map-<UTC-capture-key>"
```

It records only `(500 issue, issue slot, 500-local fid, Nowscore provider ID)`.
The Nowscore page must declare the requested issue and expose a complete
membership matrix. Its slot set must exactly equal the 500 receipt's slot set;
otherwise the full issue is rejected and no metadata-based matching is allowed.

Issue enumeration spans the full 500 history from 2010 onward: 6-digit
YYMMNN issues >= 100101 (2010-2019) plus 5-digit YYNNN issues (2020+). Older
2007-2009 issues exist on 500 but Nowscore provides no mapping source, so they
are out of scope. The `expect_select` dropdown of the trade page is the
authoritative issue index.

A Nowscore provider ID that appears in more than one slot is a conflict group:
the group's rows are isolated into `conflict_isolated_slot` and the remaining
rows of the issue are still mapped (partial mapping instead of whole-issue
rejection). A conflict can be promoted by an explicit, Titan-verified
`--resolve-conflict PROVIDER=SLOT` argument; the verified slot is mapped and the
other group members stay isolated.

Slot numbering itself can diverge after 500 removes a fixture: 500 may keep a
numbering gap (same-slot alignment) or compress its numbers (team-name-verified
ordered alignment). The collector prefers same-slot alignment and falls back to
a strictly ordered team-name match that fails closed on any unmatched row.

A Titan provider ID referenced by more than one issue is a rescheduled match:
500/Nowscore keep both the original issue slot and the actual one. Each
duplicate provider is probed on Titan and its Beijing kickoff must match the
500 cutoff time of exactly one issue; every other occurrence is a reschedule
ghost and is quarantined into `conflict_isolated_slot` by
`scripts/quarantine_reschedule_ghosts.py`. The candidate bridge deduplicates
provider IDs so the Titan collector fetches each fixture exactly once.

The discovery ledger can export a one-way handoff containing only the Nowscore
provider ID plus an opaque discovery binding hash; it deliberately excludes
500 issue, slot, local fid, and all descriptive external fields.

For full historical construction, `beidanlot-historical-id-map.service` is a
no-agent systemd user service. It advances one unmapped 500 index issue at a
time and exits only when the index is exhausted; no DSH task-board session or
LLM request is involved. Source unit: `ops/systemd/user/beidanlot-historical-id-map.service`.

Seal an immutable, offline-verifiable control snapshot only after the capture
window is complete:

```bash
python scripts/seal_titan_clean_release.py \
  --data-root "$BEIJING_LOT_DATA_ROOT/clean_v1" --release-id r1
python scripts/seal_titan_clean_release.py \
  --data-root "$BEIJING_LOT_DATA_ROOT/clean_v1" --release-id r1 --verify
```

Verification checks the snapshot SQLite hash, SQLite integrity, and every raw
Titan payload hash named by the pinned release manifest. It never opens the
settlement store.
