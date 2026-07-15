# A9 Production/Research Automation Coordination Contract

Date: 2026-07-16

Status: `proposed_for_production_integration`. This contract defines the
cross-session handshake needed to run A9 prospectively. It does not authorize
production strategy activation, ticket generation, or production-data writes
by the research session.

## Principle

Messages notify people; immutable artifacts trigger automation. The executor
must never infer readiness from a chat message, database row, directory name,
or polling timestamp alone.

## Ownership

| Component | Owner | Write authority |
| --- | --- | --- |
| three-market overlap artifact | production session | production-owned input artifact only |
| `A9_INPUT_READY` event bundle | production session | shared coordination root only |
| A9 freeze/settlement artifacts | strategy research session | `results/strategy_parallel/` research output only |
| scheduler and user notification | production-owned coordinator | orchestration state only |

The research session opens shared SQLite only in immutable read-only mode. It
does not create or modify an input-ready event. The production session never
writes an A9 snapshot or settlement result.

## Input-Ready Event

The production coordinator publishes one immutable directory per issue:

```text
<shared-coordination-root>/a9/<issue>/A9_INPUT_READY_v1/
  manifest.json
  SHA256SUMS
```

It must construct the directory in a private temporary location, write and
verify `SHA256SUMS`, then atomically rename it into the shared coordination
root. A published directory is never edited, deleted, or reused.

`manifest.json` schema:

```json
{
  "schema_version": "strategy_parallel_forward_event_v1",
  "event_type": "A9_INPUT_READY",
  "event_id": "A9:ISSUE:OVERLAP_SHA256SUMS_SHA256",
  "issue": "ISSUE",
  "status": "READY",
  "emitted_at_hkt": "ISO-8601 timestamp with +08:00",
  "overlap_dir": "/absolute/path/to/production-owned/overlap",
  "overlap_sha256s_sha256": "sha256 of overlap/SHA256SUMS",
  "earliest_sale_cutoff_hkt": "ISO-8601 timestamp with +08:00",
  "issue_rows": 0,
  "eligible_rows": 0,
  "excluded_match_indices": [],
  "producer": "beijing-lot-production-session"
}
```

The event is valid only when the event checksum, overlap checksum, issue,
coverage, and earliest cutoff all agree with the overlap artifact. The event ID
is the idempotency key.

## State Machine

```text
INPUT_READY
  -> CLAIMED
  -> FROZEN | FREEZE_REJECTED | FREEZE_EXPIRED
  -> SETTLEMENT_READY
  -> SETTLED | SETTLEMENT_REJECTED
```

`CLAIMED`, `FROZEN`, and later receipts are separate immutable research output
artifacts keyed by `event_id`; their paths and hashes are sent in notifications.
No state is mutated in place. A duplicate event ID must return the existing
receipt rather than create a second snapshot.

## Coordinator Rules

The production-owned coordinator may poll the shared coordination root or
receive a filesystem/event notification. On `A9_INPUT_READY` it must:

1. verify event and overlap hashes;
2. require at least a 10-minute margin before the declared earliest sale
   cutoff;
3. invoke the research A9 freeze command once with the event's issue and
   overlap directory;
4. publish/notify the resulting immutable receipt path and hash;
5. emit `FREEZE_EXPIRED` rather than retry when the time margin is missed.

For settlement, it may request the research settlement command only after the
research `status` reports a complete frozen cohort. A partial result is not a
retryable settlement and must remain `SETTLEMENT_REJECTED` until official data
is complete.

The coordinator must never pass output codes, action depth, ticket budgets, or
thresholds to A9. Its role is timing and artifact routing only.

## Notifications

The coordinator may use agent-deck, a Codex thread message, or an operational
chat channel for notification. Each notification must contain only:

- event ID;
- event or receipt absolute path;
- SHA-256 fingerprint;
- state and time-to-cutoff or settlement count.

The notification is informational. Consumers re-verify the referenced artifact
before acting.

## Acceptance

Before enabling the scheduler, production and research must jointly complete:

1. a synthetic ready-event checksum rejection test;
2. duplicate event-id test proving exactly one snapshot is produced;
3. expired-cutoff test proving no snapshot is produced;
4. incomplete-settlement test proving no settlement artifact is produced;
5. successful dry-run against a non-live fixture root.

The first live event remains research-only. It cannot modify any production
strategy, API, frontend, collector, release manifest, shared SQLite, ticket,
or execution state.

## Production Integration Request

The production session should decide the canonical shared coordination root and
implement publication of the checksum-protected `A9_INPUT_READY` bundle after
it locks a standard three-market overlap artifact. It should then provision the
coordinator under its own scheduler/notification authority. The strategy
session will consume only valid event bundles and return freeze/settlement
receipts.
