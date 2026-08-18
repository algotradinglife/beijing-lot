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
- Collector `issue_code` and `fixture_id` values are URL-expect-derived synthetic buckets, not canonical physical fixture/issue identity. Current bucket counts are descriptive only; #251 must resolve cross-issue aliases before #253 integration.

## Current profile

- Poll-start snapshot: 1,598,178 rows, 5,494 fixtures, 32 issues.
- Common-cutoff AVAILABLE fixtures/model cells: 1h `153/459`; 6h `153/459`; 12h `56/168`; 24h `0/0`.
- Issue duration is multi-day: median 104.25 hours, maximum 201 hours. No universal fixed-offset assumption is accepted.

## R6 method rework (2026-08-18)

- [SESSION] `20260818_183334_cc21fd`
- Rework baseline: `86176c094dcdbbcaca6da26279d9586d8df0831d` (R5); PR #257 remains the delivery PR.
- Closed `KE-252-R5-01`: all lane-defining `time_semantics`, `causal_grade`, `snapshot_horizon`, and `source_id` comparisons use explicit fail-closed equality/membership masks. Null is invalid across object, pandas nullable `string`, and Arrow-backed `string[pyarrow]` inputs.
- Closed `KE-252-R5-02`: the manifest declares both poll and historical-proxy source lanes and their exact main/WAL/SHM receipt-key sets. The verifier rejects deleted, renamed, absent-main/replaced, and unrelated-only re-signed receipt sets. This remains an internal integrity/boundary check, not an external source-authentication claim.
- Frozen poll-start snapshot and profile are unchanged: 1,598,178 rows; SHA256 `cea1459c4783ae7790870ca7c9ed2e643bc1818cf3da2eeaea1c13ca2f25465d`.
- Generated package reports, vocabulary, manifest, REQ evidence and executed notebook were refreshed without rebuilding from mutable live polls.
- Verification: focused #252 suite, #252 + #234 integration, semantic package replay, and notebook clean execution. Lint was attempted with `ruff`/`uvx ruff` but unavailable because the executable was absent and package download failed with a TLS EOF; Python compilation passed.

## Known boundaries / next step

- Preserve the #253 handoff limitations: poll-start is not exact available-at/reschedule-as-of authority, and frozen derived counts are not independently authenticated raw-cell truth.
- Next: independent candidate-mode EV must bind the new PR HEAD and rerun nullable lane-field plus source-receipt mutation attacks.

## R7 PI narrow closure (2026-08-18)

- The observation boundary now rejects null/blank `issue_code` and null `match_idx` before any pandas grouping, including object, nullable `string`, and Arrow-backed string inputs. This closes the R6 silent-row-loss finding without changing the frozen input or profile counts.
- The R6 cross-issue alias finding is assigned to canonical-identity Issue #251, which already blocks #253. This package now machine-declares `COLLECTOR_URL_EXPECT_BUCKET_NOT_CANONICAL_FIXTURE_IDENTITY`; its 5,494/32 figures must not be promoted to canonical fixture/issue truth.
- Focused verification: 68 tests passed; Ruff clean.
