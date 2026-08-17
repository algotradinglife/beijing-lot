# Issue #252 delivery handoff

[SESSION] 20260818_020021_8538b8

- Base HEAD: `d2cc56d` (`engineer/bj234-issue`); delivery branch: `engineer/bj252-issue`.
- Scope: `BJ-UNIFIED-TEMPORAL-SEMANTICS-001`, candidate mode; no model, ticket, ROI, or profitability work.

## Completed

1. `src/temporal_semantics.py` defines fail-closed strict/proxy vocabulary and validates explicit UTC observations, source-relative historical labels, issue cutoffs, staleness, and deterministic Asia/Shanghai local-date segments.
2. `src/bj252_temporal_package.py` provides atomic package publication plus mechanical and semantic verification. Its REQ-E06 tests show that a recomputed checksum list cannot launder a changed strict-selection ledger or forged contract manifest.
3. `src/bj252_build.py` profiles the raw read-only `beidan_live` strict source and `beidan_xlsm` proxy source. It hashes both before and after reading and refuses publication if either mutable input changes during profiling.
4. `results/bj252_unified_temporal_semantics_v1/` is the sealed evidence package: selected strict receipt, proxy horizon coverage, issue-duration/cutoff/segment/drop tables, vocabulary, report, REQ table, manifest and SHA256 closure.
5. `notebooks/research/issue-252/bj252_temporal_semantics.ipynb` was clean-executed and retains outputs.

## Key decisions and reasons

- `initial`, `10h`, `1h` are distinct `HISTORICAL_PROXY_LABEL_ONLY` observations with null `observed_at_utc`; they cannot enter the strict-forward namespace.
- Strict rows come from `beidan_live.snapshots.snapshot_ts`, require an explicit UTC clock, pre-kickoff availability, and a stable before/after raw-source hash receipt.
- Candidate common-issue cutoffs are 1/6/12/24 hours before earliest kickoff. The package profiles them but does not select one; this remains the PI/user checkpoint.
- Segment fallback groups the explicit Asia/Shanghai schedule by local kickoff date and applies the identical lead rule. This prevents later fixtures being used by earlier decisions.

## Risks / next steps

- Live sources are mutable. A concurrent write makes the build fail closed; retry only produces a package when the source hashes are stable across the entire profiling pass.
- PI/user must select accepted proxy horizons, strict cadence, final lead/cutoff, and permitted claim language. This delivery supplies evidence and does not silently freeze those policy choices.
- EV should independently clean-run the notebook, run the focused tests, invoke the package verifier, then tamper/rehash strict selection and manifest as covered by the test suite.
