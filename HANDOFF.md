# Issue #252 delivery handoff

- Base HEAD: `d2cc56d` (`engineer/bj234-issue`); delivery branch: `engineer/bj252-issue`.
- Scope: `BJ-UNIFIED-TEMPORAL-SEMANTICS-001`, candidate mode; no model, ticket, ROI, profitability or crawler-cadence decision.
- Canonical package: `results/bj252_unified_temporal_semantics_v3/`.

## Delivered contract

1. `src/temporal_semantics.py` validates the bounded poll-start namespace, UTC cutoff selection and deterministic Asia/Shanghai local-date segment fallback.
2. `src/bj252_build.py` keeps physical non-null storage presence separate from parseable, finite decimal SP strictly greater than 1.0. Invalid stored values route to `INVALID_VALUE` rather than missing/incomplete.
3. `src/bj252_temporal_package.py` atomically publishes and semantically replays every decision-facing table from the frozen poll-start input snapshot, including exact issue-duration reconciliation.
4. Historical proxy evidence is a 12-row `horizon × market × field-role` aggregate: three horizons (`initial`, `10h`, `1h`) by four market families. Only `euro_1x2` is M×3 outcome-compatible; Kelly, handicap and total rows are separately named diagnostics.
5. `notebooks/research/issue-252/bj252_temporal_semantics.ipynb` is the executed profiling notebook. The v3 package contains cutoff, segment, drop-cause, duration, proxy-role, manifest, checksum and REQ evidence.

## Claim boundaries

- The collector clock is poll-start against the current schedule reference. It is not received-at, commit-at, exact available-at or reschedule-as-of authority.
- Merged poll rows do not retain upstream per-cell lineage. The committed Parquet freezes derived presence/validity counts, not raw SP cell values, so it is not independent raw-value or source-authenticity evidence.
- Internal checksums prove package integrity. The SQLite main/WAL/SHM receipt proves only a stable build interval.
- Historical `initial`/`10h`/`1h` evidence is bound to exact source lane `beidan_xlsm_workbook`, remains a source-relative proxy summary, and is never represented as a row-level strict panel or universal issue-time snapshot.

## Current profile

- Poll-start snapshot: 1,598,178 rows, 5,494 fixtures, 32 issues.
- Common-cutoff AVAILABLE fixtures/model cells: 1h `153/459`; 6h `153/459`; 12h `56/168`; 24h `0/0`.
- Issue duration is multi-day: median 104.25 hours, maximum 201 hours. No universal fixed-offset assumption is accepted.

## Downstream use

#253 may use this package only as a bounded temporal/profile input and must preserve its namespace, clock, lineage and raw-cell limitations. Row-grain physical storage, raw-cell lineage, source authentication and final snapshot cadence remain #253 or later collector work.
